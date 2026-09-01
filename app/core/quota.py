"""Per-user daily render quota — a token bucket in Redis (PRD 4.6, 10.10).

Image generation is the expensive call, so each user gets a fixed number of
renders per day. We count them in Redis under a key that includes today's date:

    quota:<user id>:<YYYY-MM-DD>   ->   how many renders used today

Because the date is in the key, the count resets on its own every day — a new
day means a fresh key starting at zero. No cleanup job needed; the key also
carries a short expiry so old days disappear.

Like everything in Redis, this is rebuildable, not the source of truth: if it is
lost, a user simply gets a fresh daily allowance.
"""

from datetime import datetime, timezone

from app.config import settings
from app.redis_client import redis_client

# Keep each day's counter for ~2 days, then let Redis drop it automatically.
_TTL_SECONDS = 60 * 60 * 48


def _key(user_id: str) -> str:
    day = datetime.now(timezone.utc).date().isoformat()
    return f"quota:{user_id}:{day}"


def used_today(user_id: str) -> int:
    """How many renders this user has already spent today."""
    return int(redis_client.get(_key(user_id)) or 0)


def remaining(user_id: str) -> int:
    """How many renders this user has left today."""
    return max(0, settings.daily_render_quota - used_today(user_id))


def consume(user_id: str, n: int = 1) -> bool:
    """Try to spend `n` renders. Returns True if allowed, False if it would go
    over the daily limit (in which case nothing is spent).

    INCRBY is atomic, so two requests at the same instant can never both slip
    past the limit. If the new total is over budget, we undo it and refuse.
    """
    key = _key(user_id)
    used = redis_client.incrby(key, n)
    redis_client.expire(key, _TTL_SECONDS)
    if used > settings.daily_render_quota:
        redis_client.decrby(key, n)  # roll the tokens back — the spend is refused
        return False
    return True
