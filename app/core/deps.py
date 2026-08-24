"""Reusable dependencies. The main one: "who is making this request?"

Any route that should require login just adds `user = Depends(get_current_user)`
to its parameters. FastAPI runs this first; if there's no valid session it
raises 401 and the route body never runs.
"""

import uuid

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.session import SESSION_COOKIE_NAME, get_user_id
from app.db import get_db
from app.models import User

# Reused for every "you're not logged in" case.
_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)


def get_current_user(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    """Turn the session cookie into the logged-in User, or reject with 401."""
    # 1. No cookie at all → not logged in.
    if not session_id:
        raise _UNAUTHORIZED

    # 2. Look the ticket up in Redis. None → expired, logged out, or forged.
    user_id = get_user_id(session_id)
    if user_id is None:
        raise _UNAUTHORIZED

    # 3. The session points at a user id; load that user from Postgres.
    #    (If the account was deleted since login, treat it as not authenticated.)
    user = db.get(User, uuid.UUID(user_id))
    if user is None:
        raise _UNAUTHORIZED

    return user
