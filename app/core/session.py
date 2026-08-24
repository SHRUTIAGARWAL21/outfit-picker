"""Server-side sessions, stored in Redis.

The coat-check ledger. Each session is one Redis entry:

    key:   sess:<random-id>     value: the user's id     expires: in 7 days

- create_session  -> makes a new entry, returns the random id (the "ticket")
- get_user_id     -> looks a ticket up: who is this? (or None if unknown/expired)
- delete_session  -> tears the ticket up (logout)

The id is long and random, so nobody can guess someone else's ticket.
"""

import secrets

from app.redis_client import redis_client

# The browser cookie that carries the session id.
SESSION_COOKIE_NAME = "session"

# How long a login lasts. Redis deletes the entry automatically after this, so
# sessions time out on their own with no cleanup code.
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

# All our session keys start with this, keeping them tidy among Redis's other
# jobs (cache, locks, quotas) later on.
_KEY_PREFIX = "sess:"


def create_session(user_id: str) -> str:
    """Create a session for this user and return its id (the ticket)."""
    session_id = secrets.token_urlsafe(32)  # ~43 random characters, unguessable
    # SETEX = "set this key to this value, and expire it after N seconds".
    redis_client.setex(_KEY_PREFIX + session_id, SESSION_TTL_SECONDS, user_id)
    return session_id


def get_user_id(session_id: str) -> str | None:
    """Return the user id for a session id, or None if it's unknown/expired."""
    return redis_client.get(_KEY_PREFIX + session_id)


def delete_session(session_id: str) -> None:
    """Delete a session (logout). Safe to call even if it's already gone."""
    redis_client.delete(_KEY_PREFIX + session_id)
