"""Quota status — so the interface can show how many renders are left today."""

from fastapi import APIRouter, Depends

from app.config import settings
from app.core import quota
from app.core.deps import get_current_user
from app.models import User

router = APIRouter(tags=["quota"])


@router.get("/quota")
def get_quota(user: User = Depends(get_current_user)) -> dict:
    """This user's render allowance for today (PRD 4.6)."""
    return {
        "limit": settings.daily_render_quota,
        "used": quota.used_today(str(user.id)),
        "remaining": quota.remaining(str(user.id)),
    }
