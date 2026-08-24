"""Shared building blocks that every table reuses.

Instead of repeating the same `id` and timestamp columns on every model, we
define them once here as small reusable pieces ("mixins") and each model picks
up whichever ones it needs.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Every model inherits from this. Alembic reads `Base.metadata` to learn
    the full set of tables the code expects."""


class UUIDMixin:
    """A random UUID primary key, e.g. `9f3c...`.

    Why not a simple counter (1, 2, 3)? Counting ids leak information — anyone
    could visit /users/1, /users/2 and learn how many users you have, and guess
    other people's ids. A random UUID can't be guessed. Postgres generates it
    itself via gen_random_uuid().
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """`created_at` / `updated_at`, filled in by the database automatically."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
