"""The Celery application — the manager of the background work.

The web app (`app.main:app`) and the worker are two separate programs. They
never call each other directly. They meet only at the queue in Redis:

    web app  --(garment id)-->  Redis queue  --(garment id)-->  worker

This file defines that shared queue. Both sides import `celery_app`: the web app
to *drop* a job in (`.delay(id)`), the worker to *run* it. Start the worker with:

    celery -A app.celery_app worker --loglevel=info --pool=solo

(`--pool=solo` is needed on Windows; the default prefork pool does not work there.)
"""

from celery import Celery

from app.config import settings


def _broker_url() -> str:
    """Upstash gives a `rediss://` (TLS) URL. Celery refuses such a URL unless it
    also says how to check the certificate, so we add that if it is missing.
    Upstash presents a valid certificate, so CERT_REQUIRED is correct."""
    url = settings.redis_url
    if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}ssl_cert_reqs=CERT_REQUIRED"
    return url


# No result backend on purpose: we do NOT store task return values in Redis.
# The garment row in Postgres is the single source of truth for "did it work?".
# That keeps Upstash's small memory free and matches PRD 10.10's warning.
celery_app = Celery(
    "outfit_picker",
    broker=_broker_url(),
    include=["app.workers.tasks"],  # where the worker finds the actual tasks
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,  # a job is only "done" after it finishes, not on pickup
    worker_prefetch_multiplier=1,  # take one job at a time; the AI call is the slow part
    broker_connection_retry_on_startup=True,
)

# The recovery job (Step 4, PRD 6.2). Beat is Celery's alarm clock: every two
# minutes it drops a "run the inspector" message on the queue. The inspector task
# then finds stuck garments and re-queues them. Start Beat alongside the worker:
#
#     celery -A app.celery_app worker --pool=solo --beat --loglevel=info
#
# (`--beat` runs the clock inside the worker — handy for one-machine development.)
celery_app.conf.beat_schedule = {
    "requeue-stuck-garments-every-2-min": {
        "task": "garments.requeue_stuck",
        "schedule": 120.0,  # seconds
    },
}
