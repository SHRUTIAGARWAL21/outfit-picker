"""The shapes of avatar requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AvatarCreate(BaseModel):
    """What the browser sends after uploading the base photo to Cloudinary."""

    public_id: str


class AvatarProfileUpdate(BaseModel):
    """User corrections to the extracted profile (PRD 4.2: view and correct)."""

    profile: dict


class AvatarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    base_image_url: str
    status: str
    created_at: datetime
    profile: dict | None = None
    failure_reason: str | None = None
