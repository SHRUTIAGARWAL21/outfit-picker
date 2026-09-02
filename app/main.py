"""FastAPI application entry point.

This is the "front door" of the backend — the waiter from our restaurant
analogy. Every request from a browser arrives here first. For now it only
knows how to answer two simple questions; we add real features step by step.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.redis_client import redis_client
from app.routers import auth, avatar, garments, interest, quota, recommendations, users

# `app` is the whole application object. uvicorn (the web server) looks for
# this exact variable when it starts: it runs `app.main:app`.
app = FastAPI(
    title="Outfit Picker API",
    version="0.1.0",
    description="Virtual try-on and outfit recommendations from your own wardrobe.",
)

# In production the frontend is a separate origin, so allow it to call this API
# and send the session cookie. In dev cors_origins is empty and the Vite proxy
# keeps everything same-origin, so no middleware is added.
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,  # let the browser send the session cookie
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Attach the route groups to the app.
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(avatar.router)
app.include_router(garments.router)
app.include_router(recommendations.router)
app.include_router(interest.router)
app.include_router(quota.router)


@app.get("/")
def home() -> dict[str, str]:
    """The root page. Visiting http://localhost:8000/ runs this function."""
    return {"message": "Outfit Picker is running."}


@app.get("/health")
def health() -> dict[str, object]:
    """Is the app up, AND can it reach the database?

    We send Postgres the simplest possible query — `SELECT 1` — and check it
    answers. If anything goes wrong we report "degraded" plus the reason,
    instead of letting the whole app crash.
    """
    database_ok = True
    redis_ok = True
    detail = None

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        database_ok = False
        detail = f"database: {exc}"

    try:
        redis_client.ping()  # Redis's version of "SELECT 1"
    except Exception as exc:
        redis_ok = False
        detail = f"{detail + ' | ' if detail else ''}redis: {exc}"

    return {
        "status": "ok" if (database_ok and redis_ok) else "degraded",
        "env": settings.env,
        "database": database_ok,
        "redis": redis_ok,
        "detail": detail,
    }
