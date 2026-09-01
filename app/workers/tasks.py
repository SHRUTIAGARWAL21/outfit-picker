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
from app.core.gemini import (
    SCHEMA_VERSION,
    extract_attributes,
    extract_avatar_profile,
    rank_outfits,
)
from app.db import SessionLocal
from app.models import (
    Avatar,
    AvatarStatus,
    Garment,
    GarmentStatus,
    Outfit,
    OutfitRequest,
    RequestStatus,
)
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

# How many outfits a recommendation request returns by default (PRD 4.4).
_DEFAULT_OUTFITS = 5


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


def _fail_avatar(db, avatar_id: str, reason: str) -> None:
    """Re-read the avatar on a clean session and mark it FAILED."""
    db.rollback()
    avatar = db.get(Avatar, uuid.UUID(avatar_id))
    if avatar is not None:
        avatar.status = AvatarStatus.FAILED
        avatar.failure_reason = reason[:500]
        db.commit()


@celery_app.task(bind=True, name="avatars.extract_profile", max_retries=_MAX_RETRIES)
def extract_avatar_profile_task(self, avatar_id: str) -> str:
    """Read the user's base photo and fill in the styling profile (PRD 4.2).

    Same machine as garment extraction: lock, guard, PROCESSING, download, read
    with the vision model, save, READY (or FAILED for a bad photo).
    """
    lock = redis_client.lock(f"lock:avatar:{avatar_id}", timeout=_LOCK_TTL_SECONDS, blocking_timeout=0)
    if not lock.acquire():
        return "locked"

    db = SessionLocal()
    try:
        avatar = db.get(Avatar, uuid.UUID(avatar_id))
        if avatar is None:
            return "missing"
        if avatar.status == AvatarStatus.READY:
            return "already-ready"

        avatar.status = AvatarStatus.PROCESSING
        avatar.attempts = (avatar.attempts or 0) + 1
        db.commit()

        try:
            image_bytes, mime = _download_image(avatar.base_image_url)
            profile = extract_avatar_profile(image_bytes, mime)

            # Not a usable full-body photo: a permanent failure the user can fix
            # by uploading a better picture. Do not retry.
            if not profile.is_full_body:
                avatar.status = AvatarStatus.FAILED
                avatar.failure_reason = (profile.notes or "The photo is not a clear full-body image.")[:500]
                db.commit()
                return "not-full-body"

            avatar.profile_json = profile.model_dump()
            avatar.schema_version = SCHEMA_VERSION
            avatar.status = AvatarStatus.READY
            avatar.failure_reason = None
            db.commit()
            return "ready"

        except PermanentError as exc:
            _fail_avatar(db, avatar_id, str(exc))
            return "failed-permanent"

        except TransientError as exc:
            try:
                raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
            except self.MaxRetriesExceededError:
                _fail_avatar(db, avatar_id, f"Kept failing: {exc}")
                return "failed-exhausted"

    finally:
        db.close()
        try:
            lock.release()
        except LockError:
            pass


def _fail_request(db, request_id: str) -> None:
    """Re-read the request on a clean session and mark it FAILED."""
    db.rollback()
    req = db.get(OutfitRequest, uuid.UUID(request_id))
    if req is not None:
        req.status = RequestStatus.FAILED
        db.commit()


@celery_app.task(bind=True, name="requests.generate", max_retries=_MAX_RETRIES)
def generate_recommendations(self, request_id: str) -> str:
    """Turn one text request into ranked outfits (PRD Step 5, stages 1 and 3).

    Stage 1 (hard filter): take the user's READY garments. Stage 3 (rerank): send
    their descriptions as text to Gemini and get back ranked outfits. We save each
    outfit as a row (garment ids + reason + rank). No images here — that is Step 6.
    """
    lock = redis_client.lock(f"lock:request:{request_id}", timeout=_LOCK_TTL_SECONDS, blocking_timeout=0)
    if not lock.acquire():
        return "locked"

    db = SessionLocal()
    try:
        req = db.get(OutfitRequest, uuid.UUID(request_id))
        if req is None:
            return "missing"
        if req.status == RequestStatus.READY:
            return "already-ready"

        req.status = RequestStatus.PROCESSING
        db.commit()

        try:
            # Stage 1 — the hard filter: only this user's analysed garments.
            garments = (
                db.query(Garment)
                .filter(
                    Garment.user_id == req.user_id,
                    Garment.status == GarmentStatus.READY,
                    Garment.attributes_json.isnot(None),
                )
                .all()
            )
            candidates = {str(g.id): g for g in garments}
            if not candidates:
                req.status = RequestStatus.FAILED
                db.commit()
                return "no-candidates"

            # Stage 3 — ask Gemini to rank outfits from those candidates (text only).
            payload = [{"id": str(g.id), "attributes": g.attributes_json} for g in garments]
            picks = rank_outfits(req.prompt_text, payload, _DEFAULT_OUTFITS)

            # Replace any previous outfits for this request (safe to re-run).
            db.query(Outfit).filter(Outfit.request_id == req.id).delete()

            rank = 0
            for pick in picks:
                # Trust nothing: keep only ids the model was actually given.
                valid = [uuid.UUID(i) for i in pick.garment_ids if i in candidates]
                if not valid:
                    continue
                rank += 1
                db.add(
                    Outfit(
                        request_id=req.id,
                        garment_ids=valid,
                        rank=rank,
                        reason=pick.reason[:500],
                    )
                )

            req.status = RequestStatus.READY
            db.commit()
            return f"ready:{rank}"

        except PermanentError:
            _fail_request(db, request_id)
            return "failed-permanent"

        except TransientError as exc:
            try:
                raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
            except self.MaxRetriesExceededError:
                _fail_request(db, request_id)
                return "failed-exhausted"

    finally:
        db.close()
        try:
            lock.release()
        except LockError:
            pass
