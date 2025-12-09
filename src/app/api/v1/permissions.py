from typing import Any

from fastapi import APIRouter, Depends, Request

from ...api.dependencies import get_current_superuser

router = APIRouter(tags=["permissions"])


@router.get("/permissions/tree", dependencies=[Depends(get_current_superuser)])
async def get_permission_tree(request: Request) -> list[dict[str, Any]]:
    """
    Get the permission tree of the system.
    Returns a list of all available routes and their methods.
    """
    routes = []
    # Iterate over all routes in the application
    for route in request.app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            methods = [m for m in route.methods if m not in ("HEAD", "OPTIONS")]
            if methods:
                routes.append({
                    "path": route.path,
                    "methods": methods,
                    "name": route.name
                })
    
    # Sort by path
    routes.sort(key=lambda x: x["path"])
    
    return routes
