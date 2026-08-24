"""The shapes of auth requests and responses.

Why keep these separate from the `User` model in app/models? Because a model
describes what sits in the DATABASE (including the password hash), while a
schema describes what is allowed to cross the NETWORK. Keeping them apart is
what stops a password hash from ever accidentally leaking into a response.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    """What the client must send to POST /auth/signup.

    FastAPI validates incoming data against this automatically. If the email
    isn't a valid email, or the password is too short, the request is rejected
    with a clear error BEFORE our code runs.
    """

    email: EmailStr  # must look like a real email address
    password: str = Field(min_length=8, max_length=128)  # 8 is a sane floor


class LoginRequest(BaseModel):
    """What the client sends to POST /auth/login.

    Note the password rule is only min_length=1 here, not 8. We never re-check
    the strength of a password someone is trying to log in WITH — we just check
    whether it matches. The 8-char rule belongs on signup.
    """

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MessageResponse(BaseModel):
    """A simple one-line reply, e.g. for logout."""

    detail: str


class UserResponse(BaseModel):
    """What we send BACK about a user. Note what's absent: password_hash.

    `from_attributes=True` lets FastAPI build this straight from a User model
    object, copying across the matching fields.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime
