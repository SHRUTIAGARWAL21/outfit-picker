"""The Redis connection.

Like `engine` for Postgres, this is one shared client the whole app reuses.
`decode_responses=True` means Redis gives us back normal strings instead of raw
bytes, which is friendlier to work with.

Redis is our "sticky-note board": fast, in-memory storage for things that are
temporary or rebuildable — starting with login sessions.
"""

import redis

from app.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)
