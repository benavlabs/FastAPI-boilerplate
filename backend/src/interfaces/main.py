from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response, status

from ..infrastructure.app_factory import create_application, lifespan_factory
from ..infrastructure.config.settings import get_settings
from ..infrastructure.logging import get_logger
from ..infrastructure.readiness import readiness_report
from ..infrastructure.security import validate_production_security
from ..interfaces.api import router
from ..wiring.app import DOCS_GUARD, INSTALLERS, LIFECYCLES, ROOT_ROUTERS
from ..wiring.hooks import CRITICAL_READINESS_CHECKS, INFORMATIONAL_READINESS_CHECKS

logger = get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan_with_security(app: FastAPI) -> AsyncGenerator[None, None]:
    """The app's lifespan, with the production security validation in front of it.

    Builds the factory's lifespan here, reading the startup settings this app honours.
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
    """Readiness: whether every dependency a request needs answers.

    Answers 503 while a critical dependency is unreachable, and 200 otherwise. An
    informational dependency, such as the cache or the broker, is reported and leaves
    the answer ready.
    """
    ready, dependencies = await readiness_report(CRITICAL_READINESS_CHECKS, INFORMATIONAL_READINESS_CHECKS)
    response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if ready else "not ready", "dependencies": dependencies}
