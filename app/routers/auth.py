"""Authentication routes: sign up, log in, log out."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password, verify_password
from app.core.session import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    create_session,
    delete_session,
)
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginRequest, MessageResponse, SignupRequest, UserResponse

# An APIRouter is a small bundle of related routes. `prefix="/auth"` means every
# address in here starts with /auth, so the signup route below is /auth/signup.
router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, session_id: str) -> None:
    """Attach the session ticket to the browser as a locked-down cookie."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,              # JavaScript can't read it → a script can't steal it
        secure=settings.cookie_secure,  # only sent over HTTPS in production
        samesite=settings.cookie_samesite,  # "lax" in dev, "none" for a split frontend/backend
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> User:
    """Create a new account.

    `payload` arrives already validated against SignupRequest. `db` is a fresh
    database session, handed to us by the get_db dependency.
    """
    # Store emails in one consistent form so "Me@X.com" and "me@x.com" can't
    # become two separate accounts.
    email = payload.email.strip().lower()

    # Is this email already taken?
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash the password before it ever touches the database.
    user = User(email=email, password_hash=hash_password(payload.password))

    db.add(user)      # stage the new row
    db.commit()       # actually write it to Postgres
    db.refresh(user)  # reload it so we get the DB-generated id and created_at

    # We return the User object; response_model=UserResponse filters it down to
    # only id/email/created_at — the password hash can never slip out.
    return user


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    """Check the password, then start a session.

    `response` is injected by FastAPI so we can attach the session cookie to it.
    """
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).one_or_none()

    # ONE generic message whether the email is unknown OR the password is wrong.
    # Two different messages would let an attacker discover which emails exist.
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Password is correct → create a session in Redis and hand back the ticket.
    session_id = create_session(str(user.id))
    _set_session_cookie(response, session_id)
    return user


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> MessageResponse:
    """End the session: delete it from Redis and clear the cookie.

    `session_id` is read straight from the incoming cookie. If it's already
    missing we still succeed — logging out twice is harmless.
    """
    if session_id:
        delete_session(session_id)
    _clear_session_cookie(response)
    return MessageResponse(detail="Logged out") 
