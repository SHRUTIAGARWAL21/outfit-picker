"""Routes about the signed-in user."""

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def read_me(user: User = Depends(get_current_user)) -> User:
    """Return the currently logged-in user.

    The whole login check lives in get_current_user. By the time this runs,
    `user` is guaranteed to be a real, logged-in person — otherwise FastAPI
    already returned 401 and we never got here. This is the protected route
    that a real frontend would call to draw the (empty) wardrobe screen.
    """
    return user
