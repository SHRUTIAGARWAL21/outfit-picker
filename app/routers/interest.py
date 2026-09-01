"""Likes, dislikes, and the interest section (PRD 4.5).

No AI here — this is pure database work. A like records a row; the interest
section reads back the liked outfits. It NEVER regenerates an image: it just
returns the render URL already stored in Step 6 (PRD 4.5, 10.8).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db import get_db
from app.models import Feedback, FeedbackSignal, Garment, Outfit, OutfitRequest, User
from app.schemas.recommendation import GarmentBrief, OutfitOut

router = APIRouter(tags=["interest"])


def _owned_outfit(db: Session, outfit_id: uuid.UUID, user: User) -> Outfit:
    """Load an outfit, but only if it belongs to this user (via its request)."""
    outfit = db.get(Outfit, outfit_id)
    if outfit is not None:
        req = db.get(OutfitRequest, outfit.request_id)
        if req is not None and req.user_id == user.id:
            return outfit
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")


def _set_signal(db: Session, user: User, outfit_id: uuid.UUID, signal: str) -> dict:
    """Record (or update) this user's like/dislike of one outfit."""
    outfit = _owned_outfit(db, outfit_id, user)
    fb = (
        db.query(Feedback)
        .filter(Feedback.user_id == user.id, Feedback.outfit_id == outfit.id)
        .one_or_none()
    )
    if fb is None:
        db.add(Feedback(user_id=user.id, outfit_id=outfit.id, signal=signal))
    else:
        fb.signal = signal  # flipping like <-> dislike updates the one row
    db.commit()
    return {"outfit_id": str(outfit.id), "signal": signal}


def _to_outfit_out(db: Session, outfits: list[Outfit]) -> list[OutfitOut]:
    """Attach each outfit's garment details (one batched lookup)."""
    all_ids = {gid for o in outfits for gid in o.garment_ids}
    by_id = {}
    if all_ids:
        by_id = {g.id: g for g in db.query(Garment).filter(Garment.id.in_(all_ids)).all()}
    return [
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


@router.post("/outfits/{outfit_id}/like")
def like_outfit(
    outfit_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Like an outfit — it now appears in the interest section."""
    return _set_signal(db, user, outfit_id, FeedbackSignal.LIKE)


@router.post("/outfits/{outfit_id}/dislike")
def dislike_outfit(
    outfit_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Dislike an outfit — kept as a negative signal, not shown again."""
    return _set_signal(db, user, outfit_id, FeedbackSignal.DISLIKE)


@router.delete("/outfits/{outfit_id}/feedback")
def clear_feedback(
    outfit_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Remove a like or dislike (un-save the outfit)."""
    outfit = _owned_outfit(db, outfit_id, user)
    db.query(Feedback).filter(
        Feedback.user_id == user.id, Feedback.outfit_id == outfit.id
    ).delete()
    db.commit()
    return {"detail": "removed"}


@router.get("/interest", response_model=list[OutfitOut])
def list_interest(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OutfitOut]:
    """The interest section: all outfits this user liked, newest like first.

    A plain database read. It never regenerates an image (PRD 4.5).
    """
    likes = (
        db.query(Feedback)
        .filter(Feedback.user_id == user.id, Feedback.signal == FeedbackSignal.LIKE)
        .order_by(Feedback.created_at.desc())
        .all()
    )
    liked_ids = [f.outfit_id for f in likes]
    if not liked_ids:
        return []

    by_id = {o.id: o for o in db.query(Outfit).filter(Outfit.id.in_(liked_ids)).all()}
    ordered = [by_id[oid] for oid in liked_ids if oid in by_id]  # keep like-time order
    return _to_outfit_out(db, ordered)
