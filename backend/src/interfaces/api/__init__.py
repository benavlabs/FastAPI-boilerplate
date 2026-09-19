from fastapi import APIRouter

from ...infrastructure.auth.setup import auth
from .v1 import router as v1_router

router = APIRouter()
router.include_router(v1_router, prefix="/api")

if auth.oauth is not None:
    router.include_router(auth.oauth_router)
