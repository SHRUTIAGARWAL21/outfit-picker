"""The shapes of recommendation requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecommendationCreate(BaseModel):
    """What the user sends to ask for outfits."""

    prompt_text: str = Field(min_length=1, max_length=1000)
    occasion: str | None = None  # optional: office, party, gym, ...


class GarmentBrief(BaseModel):
    """Just enough of a garment to show it inside an outfit."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_url: str
    attributes: dict | None = None


class OutfitOut(BaseModel):
    """One ranked outfit in the answer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rank: int
    reason: str
    render_status: str
    render_url: str | None = None
    garment_ids: list[uuid.UUID]
    # Filled in by the router so the caller sees the actual pieces, not just ids.
    garments: list[GarmentBrief] = []


class RequestOut(BaseModel):
    """A recommendation request plus its outfits (empty until the worker finishes)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt_text: str
    status: str
    created_at: datetime
    outfits: list[OutfitOut] = []
