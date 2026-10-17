"""The API router. Root-level mounts, such as OAuth, are installed by the app factory."""

from fastapi import APIRouter

from ...infrastructure.config.settings import settings
from .v1 import router as v1_router

router = APIRouter()
router.include_router(v1_router, prefix=settings.API_PREFIX)
