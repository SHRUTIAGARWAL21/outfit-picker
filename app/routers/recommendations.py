"""Recommendation routes: ask for outfits, then read the result.

This follows the golden rule (PRD 5.2): the AI ranking is slow, so it never runs
inside a web request. Instead:

    POST /requests      -> save the ask, queue the work, return an id instantly
    GET  /requests/{id} -> read the status and the finished outfits

The client creates a request, then polls the GET endpoint until status is READY.
(Live push over Server-Sent Events comes with the render stage, Step 6.)
"""

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core import quota
from app.core.deps import get_current_user
from app.db import SessionLocal, get_db
from app.models import (
    Avatar,
    AvatarStatus,
    Garment,
    GarmentStatus,
    Outfit,
    OutfitRequest,
    RenderStatus,
    User,
)
from app.schemas.recommendation import GarmentBrief, OutfitOut, RecommendationCreate, RequestOut
from app.workers.tasks import generate_recommendations, render_outfit_task

router = APIRouter(prefix="/requests", tags=["recommendations"])


def _ready_garments(db: Session, user_id: uuid.UUID) -> list[Garment]:
    """This user's analysed, usable garments — the recommendation candidate set."""
    return (
        db.query(Garment)
        .filter(
            Garment.user_id == user_id,
            Garment.status == GarmentStatus.READY,
            Garment.attributes_json.isnot(None),
        )
        .all()
    )


@router.post("", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RecommendationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutfitRequest:
    """Ask for outfits. Blocks early if the wardrobe is too small (PRD 4.4)."""
    # The system needs at least one upper and one lower garment (a dress covers
    # both). Check it here so the user gets an instant, clear error.
    garments = _ready_garments(db, user.id)
    categories = {(g.attributes_json or {}).get("category") for g in garments}
    has_pair = ("top" in categories and "bottom" in categories) or "dress" in categories
    if not has_pair:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your wardrobe needs at least one top and one bottom (or a dress) that are READY.",
        )

    # Save the request FIRST, then queue the work (same rule as uploads, PRD 10.2).
    req = OutfitRequest(user_id=user.id, prompt_text=payload.prompt_text)
    db.add(req)
    db.commit()
    db.refresh(req)

    try:
        generate_recommendations.delay(str(req.id))
    except Exception:
        pass  # broker blip: the row is saved; a future recovery pass can re-queue

    return req


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    """Read a request's status and its outfits (empty until the worker finishes)."""
    req = db.get(OutfitRequest, request_id)
    if req is None or req.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    outfits = (
        db.query(Outfit).filter(Outfit.request_id == req.id).order_by(Outfit.rank).all()
    )

    # Load every garment referenced by any outfit in one go, then attach the
    # details to each outfit so the caller sees real pieces, not bare ids.
    all_ids = {gid for o in outfits for gid in o.garment_ids}
    by_id = {}
    if all_ids:
        rows = db.query(Garment).filter(Garment.id.in_(all_ids)).all()
        by_id = {g.id: g for g in rows}

    outfit_out = [
        OutfitOut(
            id=o.id,
            rank=o.rank,
            reason=o.reason,
            render_status=o.render_status,
            render_url=o.render_url,
            garment_ids=o.garment_ids,
            garments=[GarmentBrief.model_validate(by_id[gid]) for gid in o.garment_ids if gid in by_id],
        )
        for o in outfits
    ]

    return RequestOut(
        id=req.id,
        prompt_text=req.prompt_text,
        status=req.status,
        created_at=req.created_at,
        outfits=outfit_out,
    )


@router.post("/{request_id}/render", status_code=status.HTTP_202_ACCEPTED)
def render_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Queue one render per outfit for this request (PRD 7.3).

    Needs a READY avatar (the base image to dress). Rendering also starts on its
    own after a recommendation finishes; this endpoint re-runs it on demand.
    """
    req = db.get(OutfitRequest, request_id)
    if req is None or req.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    avatar = (
        db.query(Avatar)
        .filter(Avatar.user_id == user.id, Avatar.status == AvatarStatus.READY)
        .one_or_none()
    )
    if avatar is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You need a READY avatar before outfits can be rendered.",
        )

    outfits = db.query(Outfit).filter(Outfit.request_id == req.id).all()

    # Spend one render token per outfit, up to the daily limit. If the user is
    # already out of tokens, reject the whole request at the API layer (PRD 4.6).
    queued = 0
    for outfit in outfits:
        if not quota.consume(str(user.id)):
            break  # daily quota reached — stop queueing
        try:
            render_outfit_task.delay(str(outfit.id))
            queued += 1
        except Exception:
            pass

    if queued == 0 and outfits:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily render limit reached. Try again tomorrow.",
        )

    return {"queued": queued, "remaining": quota.remaining(str(user.id))}


@router.get("/{request_id}/stream")
def stream_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream each outfit's render as it finishes, over Server-Sent Events.

    The browser opens this once; we poll the database and push an event for every
    outfit that becomes READY or FAILED, then a final 'done' event. SSE is one-way
    and self-recovering, so a dropped connection simply reconnects (PRD 9).
    """
    req = db.get(OutfitRequest, request_id)
    if req is None or req.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    def event_stream():
        seen: set = set()
        for _ in range(150):  # ~150 * 2s = up to 5 minutes
            session = SessionLocal()
            try:
                outfits = (
                    session.query(Outfit)
                    .filter(Outfit.request_id == request_id)
                    .order_by(Outfit.rank)
                    .all()
                )
                total = len(outfits)
                done = 0
                for o in outfits:
                    if o.render_status in (RenderStatus.READY, RenderStatus.FAILED):
                        done += 1
                        if o.id not in seen:
                            seen.add(o.id)
                            payload = {
                                "outfit_id": str(o.id),
                                "rank": o.rank,
                                "render_status": o.render_status,
                                "render_url": o.render_url,
                            }
                            yield f"data: {json.dumps(payload)}\n\n"
            finally:
                session.close()

            if total and done >= total:
                yield "event: done\ndata: {}\n\n"
                return
            time.sleep(2)

        yield "event: timeout\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
