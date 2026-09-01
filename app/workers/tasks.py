"""The garment extraction task — PRD Step 3, following the pipeline in PRD 6.1.

For one garment id, the worker:

  7.  takes a Redis lock on that id, so two workers never process it at once
  8.  reads the row, and stops if it is already done (safe to run twice)
  9.  sets the status to PROCESSING
  10. downloads the image and calls the vision model
  11. writes the attributes back to the row
  12. sets the status to READY and releases the lock

If the same photo was already described before, we skip the AI call and copy the
old description (deduplication, PRD 8.2). If the model call fails, we retry the
transient failures and permanently fail the rest (PRD 6.3).
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from celery.utils.log import get_task_logger
from redis.exceptions import LockError
from sqlalchemy import and_, or_

from app.celery_app import celery_app
from app.core.errors import PermanentError, TransientError
from app.core.gemini import SCHEMA_VERSION, extract_attributes
from app.db import SessionLocal
from app.models import Garment, GarmentStatus
from app.redis_client import redis_client

logger = get_task_logger(__name__)

# The lock must outlast the whole job (download + AI call), but expire on its own
# if the worker dies mid-task, so the row is never locked forever.
_LOCK_TTL_SECONDS = 300

# Give up on a stubborn transient failure after this many attempts.
_MAX_RETRIES = 3

# --- Recovery job thresholds (Step 4, PRD 6.2) ------------------------------
# A PENDING row this old was probably never picked up (a lost queue message).
_STUCK_PENDING_MINUTES = 5
# A PROCESSING row this old belongs to a worker that likely died mid-job. It is
# safely longer than the lock TTL above, so the old lock is already gone.
_STUCK_PROCESSING_MINUTES = 10
# After this many touches with no success, stop retrying and mark the row DEAD.
_MAX_ATTEMPTS = 5


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download_image(url: str) -> tuple[bytes, str]:
    """Fetch the image bytes from Cloudinary. A 404 is permanent (the file is
    gone); any other network problem is transient and worth a retry."""
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise TransientError(f"Could not download image: {exc}") from exc

    if response.status_code == 404:
        raise PermanentError("Image no longer exists in storage.")
    if response.status_code >= 400:
        raise TransientError(f"Image download returned {response.status_code}.")

    mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
    return response.content, mime


def _mark_failed(db, garment_id: str, reason: str) -> None:
    """Re-read the row on a clean session state and record a permanent failure."""
    db.rollback()
    garment = db.get(Garment, uuid.UUID(garment_id))
    if garment is not None:
        garment.status = GarmentStatus.FAILED
        garment.failure_reason = reason[:500]
        db.commit()


@celery_app.task(bind=True, name="garments.extract_attributes", max_retries=_MAX_RETRIES)
def extract_garment_attributes(self, garment_id: str) -> str:
    """Describe one garment photo and move it PENDING -> READY (or FAILED)."""
    # Step 7 — the lock. blocking_timeout=0 means "do not wait": if another worker
    # already holds it, we bow out immediately rather than queue up behind it.
    lock = redis_client.lock(f"lock:garment:{garment_id}", timeout=_LOCK_TTL_SECONDS, blocking_timeout=0)
    if not lock.acquire():
        return "locked"

    db = SessionLocal()
    try:
        garment = db.get(Garment, uuid.UUID(garment_id))
        if garment is None:
            return "missing"  # row was deleted before we got to it
        # Step 8 — idempotency. If a previous run already finished this, do nothing.
        if garment.status == GarmentStatus.READY:
            return "already-ready"

        # Step 9 — claim it, and count the attempt (the recovery job reads this).
        garment.status = GarmentStatus.PROCESSING
        garment.attempts = (garment.attempts or 0) + 1
        db.commit()

        try:
            # Step 10 — get the bytes and the fingerprint.
            image_bytes, mime = _download_image(garment.image_url)
            garment.content_hash = _sha256(image_bytes)

            # Deduplication (PRD 8.2): has THIS user already had an identical photo
            # described? If so, copy that description and skip the paid AI call.
            twin = (
                db.query(Garment)
                .filter(
                    Garment.user_id == garment.user_id,
                    Garment.content_hash == garment.content_hash,
                    Garment.status == GarmentStatus.READY,
                    Garment.id != garment.id,
                    Garment.attributes_json.isnot(None),
                )
                .first()
            )
            if twin is not None:
                garment.attributes_json = twin.attributes_json
                garment.schema_version = twin.schema_version or SCHEMA_VERSION
                garment.status = GarmentStatus.READY
                garment.failure_reason = None
                db.commit()
                return "deduped"

            # Step 10 (cont.) — the actual vision call.
            attrs = extract_attributes(image_bytes, mime)

            # The model looked but found no wearable item: a permanent failure the
            # user can act on (retake the photo). Do not retry (PRD 6.3).
            if not attrs.is_garment:
                garment.status = GarmentStatus.FAILED
                garment.failure_reason = (attrs.notes or "No clothing item detected in the photo.")[:500]
                db.commit()
                return "not-a-garment"

            # Step 11 & 12 — save the description and mark it usable.
            garment.attributes_json = attrs.model_dump()
            garment.schema_version = SCHEMA_VERSION
            garment.status = GarmentStatus.READY
            garment.failure_reason = None
            db.commit()
            return "ready"

        except PermanentError as exc:
            _mark_failed(db, garment_id, str(exc))
            return "failed-permanent"

        except TransientError as exc:
            # Retry with a growing delay. When the retries run out, Celery raises
            # MaxRetriesExceededError instead — then we record a permanent failure
            # so the row does not sit at PROCESSING forever.
            try:
                raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
            except self.MaxRetriesExceededError:
                _mark_failed(db, garment_id, f"Kept failing: {exc}")
                return "failed-exhausted"

    finally:
        db.close()
        try:
            lock.release()
        except LockError:
            pass  # the lock already expired on its own — nothing to release


@celery_app.task(name="garments.requeue_stuck")
def requeue_stuck_garments() -> dict:
    """The recovery job (PRD 6.2). Runs on a timer via Celery Beat.

    It looks for two kinds of stuck rows and rescues them:

      - PENDING for over 5 minutes  -> the queue message was probably lost.
      - PROCESSING for over 10 minutes -> the worker probably died mid-job.

    A rescued row is counted (attempts += 1) and put back on the queue. A row
    that has been tried too many times is given up on: it becomes DEAD and we log
    an alert, so it never loops forever.
    """
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    pending_cutoff = now - timedelta(minutes=_STUCK_PENDING_MINUTES)
    processing_cutoff = now - timedelta(minutes=_STUCK_PROCESSING_MINUTES)

    try:
        stuck = (
            db.query(Garment)
            .filter(
                or_(
                    and_(
                        Garment.status == GarmentStatus.PENDING,
                        Garment.updated_at < pending_cutoff,
                    ),
                    and_(
                        Garment.status == GarmentStatus.PROCESSING,
                        Garment.updated_at < processing_cutoff,
                    ),
                )
            )
            .all()
        )

        requeued = 0
        dead = 0
        for garment in stuck:
            if (garment.attempts or 0) >= _MAX_ATTEMPTS:
                # Too many tries. Stop, and raise an alert (here, an error log).
                garment.status = GarmentStatus.DEAD
                garment.failure_reason = "Gave up after too many stuck retries."
                db.commit()
                dead += 1
                logger.error("Garment %s moved to DEAD after %s attempts.", garment.id, garment.attempts)
                continue

            # Count this recovery attempt and reset it to PENDING so a worker can
            # claim it cleanly. Commit BEFORE queueing (same rule as the upload).
            garment.attempts = (garment.attempts or 0) + 1
            garment.status = GarmentStatus.PENDING
            db.commit()
            extract_garment_attributes.delay(str(garment.id))
            requeued += 1
            logger.info("Re-queued stuck garment %s (attempt %s).", garment.id, garment.attempts)

        return {"requeued": requeued, "dead": dead, "scanned": len(stuck)}
    finally:
        db.close()
