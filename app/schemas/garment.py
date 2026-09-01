"""The shapes of garment requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadSignatureResponse(BaseModel):
    """The 'authorization slip' we hand the browser so it can upload directly
    to Cloudinary. None of this is secret — the secret stayed on the server and
    was only used to compute `signature`."""

    cloud_name: str
    api_key: str
    timestamp: int
    folder: str
    signature: str
    upload_url: str


class GarmentCreate(BaseModel):
    """What the browser sends AFTER uploading to Cloudinary.

    Only the public_id — deliberately NOT the image URL. We don't trust a
    client-supplied URL (PRD 11.7); the server looks the id up in Cloudinary and
    derives the real URL itself.
    """

    public_id: str


class GarmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_url: str
    status: str
    created_at: datetime

    # Filled in once the worker (Step 3) finishes. Null while PENDING/PROCESSING.
    attributes: dict | None = None
    # Set only when status is FAILED, so the user knows why (PRD 4.3).
    failure_reason: str | None = None
