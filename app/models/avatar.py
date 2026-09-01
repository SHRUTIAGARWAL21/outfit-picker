"""The user's avatar — their base image plus a styling profile (PRD 4.2, 8.1).

The avatar is the canvas the render stage (Step 6) dresses. It is the same
ingestion pattern as a garment: a photo is uploaded, a row is saved PENDING, and
a worker reads the photo with the vision model and fills in the profile.

There is at most ONE avatar per user (the unique constraint enforces it).
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class AvatarStatus:
    """The lifecycle of an avatar through profile extraction."""

    PENDING = "PENDING"        # base image uploaded, not analysed yet
    PROCESSING = "PROCESSING"  # a worker is reading the photo
    READY = "READY"            # profile extracted, usable for rendering
    FAILED = "FAILED"          # analysis failed (e.g. not a full-body photo)


class Avatar(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "avatars"

    # One avatar per user: unique, not just indexed.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # The base image in Cloudinary (the strings only, never the bytes).
    base_image_url: Mapped[str] = mapped_column(Text, nullable=False)
    base_image_public_id: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        default=AvatarStatus.PENDING,
        server_default=AvatarStatus.PENDING,
        nullable=False,
        index=True,
    )

    # The extracted styling facts: body shape, build, skin undertone, hair and
    # eye colour. NULL until the worker succeeds. The user may correct these.
    profile_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def profile(self) -> dict | None:
        """A friendlier name for the API to expose than `profile_json`."""
        return self.profile_json
