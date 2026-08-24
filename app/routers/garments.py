"""Wardrobe routes: get an upload slip, record an upload, list garments.

This is PRD Step 2: uploads, rows, and statuses only. There is NO AI here yet —
every new garment simply sits at status PENDING. A worker will move it along in
Step 3.
"""

import cloudinary.api
import cloudinary.exceptions
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.storage import garment_folder, sign_upload
from app.db import get_db
from app.models import Garment, User
from app.schemas.garment import GarmentCreate, GarmentResponse, UploadSignatureResponse

router = APIRouter(prefix="/garments", tags=["garments"])


@router.post("/upload-signature", response_model=UploadSignatureResponse)
def create_upload_signature(user: User = Depends(get_current_user)) -> dict:
    """Hand the logged-in user a signed slip to upload one image to Cloudinary.

    Requires login (Depends(get_current_user)). The slip is tied to this user's
    own folder, so uploads land in garments/<their id>/.
    """
    return sign_upload(str(user.id))


@router.post("", response_model=GarmentResponse, status_code=status.HTTP_201_CREATED)
def create_garment(
    payload: GarmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Garment:
    """Record a finished upload as a PENDING garment row.

    We do NOT trust the client. We check the id sits in this user's folder, then
    ask Cloudinary to confirm the file really exists and give us its real URL.
    """
    # 1. Ownership: the id must be inside THIS user's garment folder. Stops a
    #    logged-in user from claiming someone else's uploaded image.
    if not payload.public_id.startswith(garment_folder(str(user.id)) + "/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image id")

    # 2. Existence + authoritative URL: ask Cloudinary directly, rather than
    #    believing a URL the client typed.
    try:
        resource = cloudinary.api.resource(payload.public_id)
    except cloudinary.exceptions.NotFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload not found in storage",
        ) from None

    # 3. Save the row. Status defaults to PENDING (no AI yet).
    garment = Garment(
        user_id=user.id,
        image_url=resource["secure_url"],
        cloudinary_public_id=payload.public_id,
    )
    db.add(garment)
    db.commit()
    db.refresh(garment)
    return garment


@router.get("", response_model=list[GarmentResponse])
def list_garments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Garment]:
    """List this user's wardrobe, newest first."""
    return (
        db.query(Garment)
        .filter(Garment.user_id == user.id)
        .order_by(Garment.created_at.desc())
        .all()
    )
