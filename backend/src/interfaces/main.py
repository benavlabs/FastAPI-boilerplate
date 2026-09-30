from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response, status

from ..infrastructure.app_factory import create_application, lifespan_factory
from ..infrastructure.config.settings import get_settings
from ..infrastructure.logging import get_logger
from ..infrastructure.readiness import READY, probe
from ..infrastructure.security import validate_production_security
from ..interfaces.api import router
from ..wiring.app import DOCS_GUARD, INSTALLERS, LIFECYCLES, ROOT_ROUTERS
from ..wiring.hooks import READINESS_CHECKS

logger = get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan_with_security(app: FastAPI) -> AsyncGenerator[None, None]:
    """The app's lifespan, with the production security validation in front of it.

    Passing a lifespan of its own means the factory never builds one, so the
    startup settings this app honours have to be read here.
    """
    if settings.PRODUCTION_SECURITY_VALIDATION_ENABLED:
        validate_production_security(settings)

    default_lifespan = lifespan_factory(
        settings, create_tables_on_startup=settings.CREATE_TABLES_ON_STARTUP, lifecycles=LIFECYCLES
    )

    async with default_lifespan(app):
        yield


app = create_application(
    router=router,
    settings=settings,
    lifespan=lifespan_with_security,
    root_routers=ROOT_ROUTERS,
    installers=INSTALLERS,
    docs_guard=DOCS_GUARD,
)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Liveness: the process is up and serving. Checks nothing else."""
    return {"status": "healthy"}


@app.get("/health/ready", tags=["System"])
async def readiness_check(response: Response) -> dict[str, Any]:
    """Readiness: every dependency this project selected answers.

    Answers 503 while something it needs is unreachable, so a load balancer holds
    traffic back instead of sending it into failing requests.
    """
    dependencies = await probe(READINESS_CHECKS)
    ready = all(answer == READY for answer in dependencies.values())
    response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if ready else "not ready", "dependencies": dependencies}
