# Outfit Picker

Virtual try-on and outfit recommendation from clothes you actually own.

See [SPEC](.claude/CLAUDE.md) for the full design. Current status: **Phase 1 — skeleton & auth**.

## Setup

### 1. Create the database (Neon)

1. Sign up at <https://neon.tech> (free tier, no card).
2. Create a project. Name the database `outfit_picker`.
3. Copy the connection string from the dashboard.
4. **Change the prefix** from `postgresql://` to `postgresql+psycopg://` so SQLAlchemy
   uses the psycopg 3 driver. Keep the `?sslmode=require` on the end.

pgvector is pre-installed on Neon; the first migration enables it.

### 2. Create the queue (Upstash) — not needed until Phase 3

1. Sign up at <https://upstash.com>, create a Redis database.
2. Copy the `rediss://` URL (two s's — it's TLS).

### 3. Configure

```bash
cp .env.example .env      # then fill in DATABASE_URL
```

Secrets can be generated with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4. Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 5. Migrate

```bash
alembic upgrade head
```

Creates all ten tables and the pgvector extension.

### 6. Run

```bash
uvicorn app.main:app --reload
```

- Interactive API docs: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

### 7. Run the worker (Step 3 onward)

The web app never calls the AI itself — it hands each garment to a background
worker through the Redis queue. Start the worker in a **second terminal**:

```bash
celery -A app.celery_app worker --loglevel=info --pool=solo --beat
```

`--pool=solo` is required on Windows. On Linux or macOS you can drop it. `--beat`
runs the recovery scheduler (Step 4) inside the same worker: every 2 minutes it
re-queues any garment stuck at `PENDING` (>5 min) or `PROCESSING` (>10 min), and
marks one `DEAD` after too many failed attempts.

You also need `GEMINI_API_KEY` in `.env` (free key from
<https://aistudio.google.com> → "Get API key"). Without the worker running, an
uploaded garment stays at status `PENDING`; start the worker and it moves to
`READY` with an extracted description, or `FAILED` with a reason.

## Google sign-in (optional in Phase 1)

1. [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create an **OAuth client ID**, type *Web application*
3. Authorised redirect URI: `http://localhost:8000/auth/google/callback` — must match
   `OAUTH_REDIRECT_URL` in `.env` exactly, character for character
4. Paste the client ID and secret into `.env`

Without these, `/auth/google/*` returns 503 and the rest of the API works normally.

## Layout

```
app/
  config.py     settings, read from .env in one place
  db.py         engine + per-request session
  models/       SQLAlchemy models — what's in the database
  schemas/      Pydantic models — what crosses the network
  core/         password hashing, JWT, "who is this user?"
  routers/      the endpoints
  main.py       app assembly
alembic/        versioned migrations
```

`models` and `schemas` are deliberately separate: a model contains
`password_hash`, a schema never can.

## Endpoints so far

| Method | Path | |
|---|---|---|
| POST | `/auth/signup` | email + password → access token, sets refresh cookie |
| POST | `/auth/login` | same |
| POST | `/auth/refresh` | refresh cookie → new access token |
| POST | `/auth/logout` | clears the cookie |
| GET | `/auth/google/login` | redirect to Google |
| GET | `/auth/google/callback` | Google returns here |
| GET | `/users/me` | **protected** — the logged-in user |
| POST | `/garments/upload-signature` | signed slip to upload one image to Cloudinary |
| POST | `/garments` | record a finished upload; queues it for the worker |
| GET | `/garments` | list this user's wardrobe, newest first |
| POST | `/garments/{id}/retry` | re-queue a `FAILED` garment |
| GET | `/health` | app + database + Redis status |
