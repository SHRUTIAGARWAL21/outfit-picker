"""The recommendation side of the data model (PRD 8.1).

Two tables work together:

- `requests`  — one row each time the user asks "what should I wear?".
- `outfits`   — the ranked answers to one request. Each outfit records WHICH
                garments it pairs (by id), so it can be rebuilt later with no new
                AI call — that is the whole point of storing `garment_ids`.

Both are filled by a worker, never inside a web request, because the ranking is
an AI call (the golden rule, PRD 5.2).
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class RequestStatus:
    """The lifecycle of one recommendation request."""

    PENDING = "PENDING"        # saved, waiting for the worker
    PROCESSING = "PROCESSING"  # the worker is ranking outfits now
    READY = "READY"            # outfits written, ready to read
    FAILED = "FAILED"          # could not produce outfits (e.g. wardrobe too small)


class RenderStatus:
    """The lifecycle of one outfit's image. Nothing renders in Step 5 — every
    outfit stays PENDING here until Step 6 adds the image stage."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class OutfitRequest(UUIDMixin, TimestampMixin, Base):
    """A single "what should I wear?" ask. Named OutfitRequest (not Request) so it
    is never confused with FastAPI's own Request object. Table stays `requests`."""

    __tablename__ = "requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # The plain-text ask, e.g. "something for a warm day at the office".
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional style reference photo (PRD 4.4). We read its style but never add it
    # to the wardrobe. Just the storage key here; not used until later.
    reference_image_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING,
        nullable=False,
        index=True,
    )

    # A fingerprint of (wardrobe version + profile + prompt). Lets us cache and
    # reuse an identical request's result later (PRD 10.10). Unused for now.
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class Outfit(UUIDMixin, TimestampMixin, Base):
    """One ranked outfit: a set of garment ids plus the reason they go together."""

    __tablename__ = "outfits"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # The garments this outfit pairs. Stored as a list of ids so the outfit is
    # reproducible without the rendered image (PRD 8.2).
    garment_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)

    # 1 = best. The order the model ranked them in.
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    # One short line: why these pieces suit the request.
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Where the image stage stands (Step 6). Stays PENDING in Step 5.
    render_status: Mapped[str] = mapped_column(
        String(20),
        default=RenderStatus.PENDING,
        server_default=RenderStatus.PENDING,
        nullable=False,
    )
    # The rendered image's storage key and served URL, once Step 6 fills them.
    render_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    render_url: Mapped[str | None] = mapped_column(Text, nullable=True)
