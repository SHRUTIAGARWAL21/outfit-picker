"""Application settings.

Anything that changes between your laptop and the real server — secrets,
database addresses — is read from the `.env` file here, in ONE place. The rest
of the code imports `settings` and never touches `.env` directly.

If a required value is missing, the app refuses to start with a clear error.
That is much better than crashing half-way through a real request later.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tells pydantic: load values from a file named `.env`, and ignore any
    # extra lines in it that we haven't listed as fields below.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "dev" on your laptop, "prod" on the real server. Has a default, so it is
    # optional in .env.
    env: str = "dev"

    # No default → this one is REQUIRED. If DATABASE_URL is missing from .env,
    # the app stops immediately and tells you. The name is lowercase here but
    # matches DATABASE_URL in the file (pydantic is case-insensitive).
    database_url: str

    # Redis: our session store (and later the cache, locks, and rate limits).
    # Also required now that login depends on it.
    redis_url: str

    # Whether the session cookie is HTTPS-only. False on your laptop (plain
    # http://localhost); MUST be True on the real, HTTPS server.
    cookie_secure: bool = False


# One shared settings object the whole app imports: `from app.config import settings`.
settings = Settings()  # type: ignore[call-arg]
