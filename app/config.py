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

    # How the session cookie travels. "lax" is right for local dev (one origin).
    # In production, when the frontend and backend are on different addresses,
    # set this to "none" (and cookie_secure=true) so the cookie is sent along.
    cookie_samesite: str = "lax"

    # Which frontend origins may call this API (comma-separated). Empty in dev
    # (the Vite proxy makes everything same-origin). In production set it to your
    # deployed frontend URL, e.g. "https://outfit-web.onrender.com".
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- Cloudinary (image storage) ---
    # All three required. The secret is used server-side to sign uploads, so the
    # browser can upload straight to Cloudinary without us proxying the file.
    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str

    # --- Gemini (vision extraction, Step 3) ---
    # The worker sends each garment photo to this model and gets back a JSON
    # description. Required now that the worker exists. `gemini_model` has a
    # default, so you can swap models in .env without touching code.
    gemini_api_key: str
    gemini_model: str = "gemini-3.6-flash"

    # The image model for the render stage (Step 6). Image generation usually
    # needs billing enabled, and may sit on a different key than the text model,
    # so it has its own optional key. If left blank, the text key is reused.
    gemini_image_model: str = "gemini-3.1-flash-image"
    gemini_image_api_key: str = ""

    # --- Cost control (Step 8) ---
    # How many outfit images one user may generate per day. Image generation is
    # the expensive call, so this caps the daily spend per user (PRD 4.6).
    daily_render_quota: int = 30


# One shared settings object the whole app imports: `from app.config import settings`.
settings = Settings()  # type: ignore[call-arg]
