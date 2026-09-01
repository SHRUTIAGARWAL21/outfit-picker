"""A user's like or dislike of one outfit (PRD 4.5, 8.1).

A like puts the outfit in the interest section. A dislike is kept as a quiet
negative signal — it is not shown to the user again, but it is useful data.

There is at most one feedback row per (user, outfit): liking then disliking the
same outfit updates the single row rather than adding a second.
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class FeedbackSignal:
    LIKE = "like"
    DISLIKE = "dislike"


class Feedback(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("user_id", "outfit_id", name="uq_feedback_user_outfit"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfits.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # "like" or "dislike" (see FeedbackSignal).
    signal: Mapped[str] = mapped_column(String(10), nullable=False)
