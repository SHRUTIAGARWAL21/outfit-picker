"""Recommendation routes: ask for outfits, then read the result.

This follows the golden rule (PRD 5.2): the AI ranking is slow, so it never runs
inside a web request. Instead:

    POST /requests      -> save the ask, queue the work, return an id instantly
    GET  /requests/{id} -> read the status and the finished outfits

The client creates a request, then polls the GET endpoint until status is READY.
(Live push over Server-Sent Events comes with the render stage, Step 6.)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db import get_db
from app.models import Garment, GarmentStatus, Outfit, OutfitRequest, User
from app.schemas.recommendation import GarmentBrief, OutfitOut, RecommendationCreate, RequestOut
from app.workers.tasks import generate_recommendations

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
