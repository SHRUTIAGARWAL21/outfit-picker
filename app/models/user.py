"""The user account.

Kept deliberately small for now — just what signing up and logging in needs.
We add more columns in later steps, exactly when a feature requires them.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # The login name. `unique=True` → the database itself refuses two accounts
    # with the same email. `index=True` → looking a user up by email is fast.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)

    # We never store the real password — only an Argon2 hash of it (built in the
    # next step). Kept as text here; the hashing logic comes with signup/login.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
