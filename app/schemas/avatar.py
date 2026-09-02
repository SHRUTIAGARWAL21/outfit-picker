"""The shapes of avatar requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AvatarCreate(BaseModel):
    """What the browser sends after uploading the base photo to Cloudinary."""

    public_id: str


class AvatarGenerate(BaseModel):
    """The no-photo path: build an animated avatar from selections (PRD 4.2)."""

    body_type: str
    height: str
    gender_presentation: str
    skin_tone: str
    hair_length: str
    hair_texture: str
    hair_color: str
    eye_color: str


class AvatarProfileUpdate(BaseModel):
    """User corrections to the extracted profile (PRD 4.2: view and correct)."""

    profile: dict


class AvatarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    base_image_url: str | None = None
    status: str
    created_at: datetime
    profile: dict | None = None
    failure_reason: str | None = None
