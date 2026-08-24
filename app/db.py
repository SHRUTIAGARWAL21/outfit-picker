"""The database connection.

Two ideas live here:

1. The `engine` — one long-lived object that manages a POOL of connections to
   Postgres. Opening a fresh connection for every request would be slow, so we
   keep a small set open and reuse them.

2. `get_db()` — hands one database session to a single request, and always
   closes it afterwards, even if the request errors. A "session" is one unit of
   conversation with the database.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # before reusing a pooled connection, check it's still alive
)

# A factory that produces new Session objects bound to our engine.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one database session per request, always closed.

    `yield` hands the session to the route; the `finally` block runs after the
    response is sent, guaranteeing the session is returned to the pool.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
