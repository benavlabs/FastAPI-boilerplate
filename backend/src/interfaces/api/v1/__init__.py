"""The /api/v1 router, assembled from the routers the selected features contribute."""

from fastapi import APIRouter

from ....wiring.app import API_THROTTLE, ROUTER_MOUNTS

router = APIRouter(prefix="/v1")

for mount in ROUTER_MOUNTS:
    router.include_router(
        mount.router,
        prefix=mount.prefix,
        dependencies=list(API_THROTTLE) if mount.throttled else [],
    )
