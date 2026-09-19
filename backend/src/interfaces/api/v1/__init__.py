from fastapi import APIRouter, Depends

from ....infrastructure.auth.routes import router as auth_router
from ....infrastructure.auth.setup import api_rate_limit_dependency
from ....modules.api_keys.routes import router as api_keys_router
from ....modules.rate_limit.routes import router as rate_limits_router
from ....modules.tier.routes import router as tiers_router
from ....modules.user.routes import router as users_router

rate_limit_dependencies = [Depends(api_rate_limit_dependency)]
router = APIRouter(prefix="/v1")
router.include_router(users_router, prefix="/users", dependencies=rate_limit_dependencies)
router.include_router(tiers_router, prefix="/tiers", dependencies=rate_limit_dependencies)
router.include_router(rate_limits_router, prefix="/rate-limits", dependencies=rate_limit_dependencies)
router.include_router(auth_router, prefix="/auth")
router.include_router(api_keys_router, prefix="/api-keys", dependencies=rate_limit_dependencies)
