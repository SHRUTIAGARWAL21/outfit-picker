"""Collecting the models here means Alembic (and the rest of the app) can see
every table by importing this one module. As we add tables, we import them here.
"""

from app.models.base import Base
from app.models.garment import Garment, GarmentStatus
from app.models.recommendation import Outfit, OutfitRequest, RenderStatus, RequestStatus
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Garment",
    "GarmentStatus",
    "OutfitRequest",
    "Outfit",
    "RequestStatus",
    "RenderStatus",
]
