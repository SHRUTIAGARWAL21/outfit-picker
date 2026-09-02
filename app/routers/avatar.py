"""Avatar routes: upload a base photo, read it back, correct the profile.

Same upload flow as garments (PRD 6.1): the browser uploads straight to
Cloudinary with a signed slip, then tells us the id; we confirm it exists and
queue the profile extraction. There is at most one avatar per user, so a second
upload replaces the first.
"""

import cloudinary.api
import cloudinary.exceptions
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.storage import avatar_folder, sign_avatar_upload
from app.db import get_db
from app.models import Avatar, AvatarStatus, User
from app.schemas.avatar import AvatarCreate, AvatarGenerate, AvatarProfileUpdate, AvatarResponse
from app.workers.tasks import extract_avatar_profile_task, generate_avatar_task

router = APIRouter(prefix="/avatar", tags=["avatar"])


@router.post("/upload-signature")
def create_upload_signature(user: User = Depends(get_current_user)) -> dict:
    """Hand the logged-in user a signed slip to upload their base photo."""
    return sign_avatar_upload(str(user.id))


@router.post("", response_model=AvatarResponse, status_code=status.HTTP_201_CREATED)
def set_avatar(
    payload: AvatarCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Avatar:
    """Record the uploaded base photo and queue its profile extraction.

    If the user already has an avatar, this replaces the image and re-runs.
    """
    # Ownership: the id must sit inside THIS user's avatar folder.
    if not payload.public_id.startswith(avatar_folder(str(user.id)) + "/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image id")

    # Confirm the file really exists in Cloudinary, and get its real URL.
    try:
        resource = cloudinary.api.resource(payload.public_id)
    except cloudinary.exceptions.NotFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload not found in storage",
        ) from None

    # One avatar per user: update the existing row, or create the first one.
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).one_or_none()
    if avatar is None:
        avatar = Avatar(
            user_id=user.id,
            base_image_url=resource["secure_url"],
            base_image_public_id=payload.public_id,
        )
        db.add(avatar)
    else:
        avatar.base_image_url = resource["secure_url"]
        avatar.base_image_public_id = payload.public_id
        avatar.status = AvatarStatus.PENDING
        avatar.profile_json = None
        avatar.failure_reason = None

    db.commit()
    db.refresh(avatar)

    try:
        extract_avatar_profile_task.delay(str(avatar.id))
    except Exception:
        pass  # broker blip: the row is saved; recovery can re-queue later

    return avatar


@router.post("/generate", response_model=AvatarResponse, status_code=status.HTTP_201_CREATED)
def generate_avatar(
    payload: AvatarGenerate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Avatar:
    """The no-photo path: create an avatar from a few selections (PRD 4.2).

    We save the row now (no image yet) and a worker generates the image and reads
    its profile. One avatar per user, so this replaces any existing one.
    """
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).one_or_none()
    if avatar is None:
        avatar = Avatar(user_id=user.id, status=AvatarStatus.PENDING)
        db.add(avatar)
    else:
        avatar.status = AvatarStatus.PENDING
        avatar.base_image_url = None
        avatar.base_image_public_id = None
        avatar.profile_json = None
        avatar.failure_reason = None

    db.commit()
    db.refresh(avatar)

    try:
        generate_avatar_task.delay(str(avatar.id), payload.model_dump())
    except Exception:
        pass

    return avatar


@router.get("", response_model=AvatarResponse)
def get_avatar(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Avatar:
    """Return this user's avatar, or 404 if they have not created one yet."""
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).one_or_none()
    if avatar is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar yet")
    return avatar


@router.patch("", response_model=AvatarResponse)
def update_avatar_profile(
    payload: AvatarProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Avatar:
    """Let the user correct the extracted profile values (PRD 4.2)."""
    avatar = db.query(Avatar).filter(Avatar.user_id == user.id).one_or_none()
    if avatar is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar yet")

    # Merge the corrections over whatever the model extracted.
    merged = dict(avatar.profile_json or {})
    merged.update(payload.profile)
    avatar.profile_json = merged
    db.commit()
    db.refresh(avatar)
    return avatar
