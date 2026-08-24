"""A wardrobe item (one photo of one piece of clothing).

Kept minimal for Step 2: just enough to record that a photo was uploaded and
track where it is in the pipeline. The AI-derived columns (attributes,
embedding, category, ...) are added in a later migration, in Step 3, exactly
when the worker that fills them exists.
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class GarmentStatus:
    """The lifecycle of a garment through the ingestion pipeline (PRD 6.1).

    For now everything just sits at PENDING — there is no worker yet to move it
    along. The later statuses are here so the values are agreed from the start.
    """

    PENDING = "PENDING"        # row created, image uploaded, not analysed yet
    PROCESSING = "PROCESSING"  # a worker is analysing it (Step 3)
    READY = "READY"            # analysed, usable in recommendations
    FAILED = "FAILED"          # analysis failed after retries


class Garment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "garments"

    # Who owns it. ondelete="CASCADE" → if the user is deleted, their garments
    # are automatically deleted too. Indexed because we always list a user's
    # garments by this column.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Where the image lives in Cloudinary. We store only these strings — never
    # the image bytes themselves.
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    cloudinary_public_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Where it is in the pipeline. Indexed because the recovery job (Step 4) will
    # search for rows stuck in a given status.
    status: Mapped[str] = mapped_column(
        String(20),
        default=GarmentStatus.PENDING,
        server_default=GarmentStatus.PENDING,
        nullable=False,
        index=True,
    )
