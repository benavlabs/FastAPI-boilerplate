import json
import logging
from asyncio import Event
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import anyio
import fastapi
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from ..modules.common.utils.error_handler import register_exception_handlers
from .auth.dependencies import get_current_superuser
from .auth.setup import auth
from .cache.initialize import close_cache, initialize_cache
from .config.settings import (
    CacheSettings,
    DatabaseSettings,
    EnvironmentOption,
    EnvironmentSettings,
    RateLimiterSettings,
    Settings,
    get_settings,
)
from .database.session import create_tables
from .middleware import ClientCacheMiddleware, SecurityHeadersMiddleware
from .rate_limit.initialize import close_rate_limiter, initialize_rate_limiter
from .rate_limit.middleware import RateLimiterMiddleware

logger = logging.getLogger(__name__)


async def set_threadpool_tokens(number_of_tokens: int = 100) -> None:
    """Configure the number of threadpool tokens for anyio."""
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = number_of_tokens


def lifespan_factory(
    settings: Settings,
    create_tables_on_startup: bool = True,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Factory to create a lifespan async context manager for a FastAPI app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        initialization_complete = Event()
        app.state.initialization_complete = initialization_complete

        await set_threadpool_tokens()

        try:
            if isinstance(settings, DatabaseSettings) and create_tables_on_startup:
                await create_tables()

            if isinstance(settings, CacheSettings) and settings.CACHE_ENABLED:
                await initialize_cache()

            if isinstance(settings, RateLimiterSettings) and settings.RATE_LIMITER_ENABLED:
                await initialize_rate_limiter()

            await auth.initialize()

            initialization_complete.set()

            yield

        finally:
            await auth.shutdown()

            if isinstance(settings, CacheSettings) and settings.CACHE_ENABLED:
                await close_cache()

            if isinstance(settings, RateLimiterSettings) and settings.RATE_LIMITER_ENABLED:
                await close_rate_limiter()

    return lifespan


def create_application(
    router: APIRouter,
    settings: Settings | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
    create_tables_on_startup: bool | None = None,
    enable_cors: bool | None = None,
    cors_origins: list[str] | None = None,
    enable_docs_in_production: bool | None = None,
    docs_production_dependency: Callable[..., Any] | None = None,
    enable_gzip: bool | None = None,
    openapi_prefix: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    version: str | None = None,
    terms_of_service: str | None = None,
    contact: dict[str, str] | None = None,
    license_info: dict[str, str] | None = None,
    openapi_tags: list[dict[str, Any]] | None = None,
    docs_url: str | None = None,
    redoc_url: str | None = None,
    openapi_url: str | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Creates and configures a FastAPI application based on the provided settings."""
    if settings is None:
        settings = get_settings()

    _create_tables_on_startup = True
    if create_tables_on_startup is not None:
        _create_tables_on_startup = create_tables_on_startup
    elif hasattr(settings, "CREATE_TABLES_ON_STARTUP"):
        _create_tables_on_startup = settings.CREATE_TABLES_ON_STARTUP

    _enable_cors = True
    if enable_cors is not None:
        _enable_cors = enable_cors
    elif hasattr(settings, "CORS_ENABLED"):
        _enable_cors = settings.CORS_ENABLED

    _cors_origins: list[str] = ["*"]
    if cors_origins is not None:
        _cors_origins = cors_origins
    elif hasattr(settings, "CORS_ORIGINS_LIST"):
        _cors_origins = settings.CORS_ORIGINS_LIST

    _enable_docs_in_production = False
    if enable_docs_in_production is not None:
        _enable_docs_in_production = enable_docs_in_production
    elif hasattr(settings, "ENABLE_DOCS_IN_PRODUCTION"):
        _enable_docs_in_production = settings.ENABLE_DOCS_IN_PRODUCTION

    _enable_gzip = True
    if enable_gzip is not None:
        _enable_gzip = enable_gzip
    elif hasattr(settings, "GZIP_ENABLED"):
        _enable_gzip = settings.GZIP_ENABLED

    _openapi_prefix = ""
    if openapi_prefix is not None:
        _openapi_prefix = openapi_prefix
    elif hasattr(settings, "OPENAPI_PREFIX"):
        _openapi_prefix = settings.OPENAPI_PREFIX

    metadata: dict[str, Any] = {"openapi_prefix": _openapi_prefix}

    if title is not None:
        metadata["title"] = title
    elif hasattr(settings, "API_TITLE") and settings.API_TITLE:
        metadata["title"] = settings.API_TITLE
    elif hasattr(settings, "APP_NAME"):
        metadata["title"] = settings.APP_NAME

    if summary is not None:
        metadata["summary"] = summary
    elif hasattr(settings, "API_SUMMARY") and settings.API_SUMMARY:
        metadata["summary"] = settings.API_SUMMARY

    if description is not None:
        metadata["description"] = description
    elif hasattr(settings, "API_DESCRIPTION") and settings.API_DESCRIPTION:
        metadata["description"] = settings.API_DESCRIPTION
    elif hasattr(settings, "APP_DESCRIPTION"):
        metadata["description"] = settings.APP_DESCRIPTION

    if version is not None:
        metadata["version"] = version
    elif hasattr(settings, "API_VERSION") and settings.API_VERSION:
        metadata["version"] = settings.API_VERSION
    elif hasattr(settings, "VERSION"):
        metadata["version"] = settings.VERSION

    if terms_of_service is not None:
        metadata["terms_of_service"] = terms_of_service
    elif hasattr(settings, "API_TERMS_OF_SERVICE") and settings.API_TERMS_OF_SERVICE:
        metadata["terms_of_service"] = settings.API_TERMS_OF_SERVICE

    if contact is not None:
        metadata["contact"] = contact
    else:
        contact_dict = {}
        if hasattr(settings, "API_CONTACT_NAME") and settings.API_CONTACT_NAME:
            contact_dict["name"] = settings.API_CONTACT_NAME
        elif hasattr(settings, "CONTACT_NAME") and settings.CONTACT_NAME:
            contact_dict["name"] = settings.CONTACT_NAME
        if hasattr(settings, "API_CONTACT_EMAIL") and settings.API_CONTACT_EMAIL:
            contact_dict["email"] = settings.API_CONTACT_EMAIL
        elif hasattr(settings, "CONTACT_EMAIL") and settings.CONTACT_EMAIL:
            contact_dict["email"] = settings.CONTACT_EMAIL
        if hasattr(settings, "API_CONTACT_URL") and settings.API_CONTACT_URL:
            contact_dict["url"] = settings.API_CONTACT_URL
        if contact_dict:
            metadata["contact"] = contact_dict

    if license_info is not None:
        metadata["license_info"] = license_info
    else:
        license_dict = {}
        if hasattr(settings, "API_LICENSE_NAME") and settings.API_LICENSE_NAME:
            license_dict["name"] = settings.API_LICENSE_NAME
        elif hasattr(settings, "LICENSE_NAME") and settings.LICENSE_NAME:
            license_dict["name"] = settings.LICENSE_NAME
        if hasattr(settings, "API_LICENSE_URL") and settings.API_LICENSE_URL:
            license_dict["url"] = settings.API_LICENSE_URL
        if hasattr(settings, "API_LICENSE_IDENTIFIER") and settings.API_LICENSE_IDENTIFIER:
            license_dict["identifier"] = settings.API_LICENSE_IDENTIFIER
        if license_dict:
            metadata["license_info"] = license_dict

    if openapi_tags is not None:
        metadata["openapi_tags"] = openapi_tags
    elif hasattr(settings, "API_TAGS_METADATA") and settings.API_TAGS_METADATA:
        try:
            metadata["openapi_tags"] = json.loads(settings.API_TAGS_METADATA)
        except json.JSONDecodeError:
            pass

    _docs_url = "/docs"
    if docs_url is not None:
        _docs_url = docs_url
    elif hasattr(settings, "DOCS_URL"):
        _docs_url = settings.DOCS_URL

    _redoc_url = "/redoc"
    if redoc_url is not None:
        _redoc_url = redoc_url
    elif hasattr(settings, "REDOC_URL"):
        _redoc_url = settings.REDOC_URL

    _openapi_url = "/openapi.json"
    if openapi_url is not None:
        _openapi_url = openapi_url
    elif hasattr(settings, "OPENAPI_URL"):
        _openapi_url = settings.OPENAPI_URL

    metadata["docs_url"] = _docs_url
    metadata["redoc_url"] = _redoc_url
    metadata["openapi_url"] = _openapi_url

    kwargs.update(metadata)

    hide_docs = (
        isinstance(settings, EnvironmentSettings)
        and settings.ENVIRONMENT == EnvironmentOption.PRODUCTION
        and not _enable_docs_in_production
    )
    if hide_docs:
        kwargs.update({"docs_url": None, "redoc_url": None, "openapi_url": None})

    if lifespan is None:
        lifespan = lifespan_factory(settings, create_tables_on_startup=_create_tables_on_startup)

    application = FastAPI(lifespan=lifespan, **kwargs)

    register_exception_handlers(application)

    application.include_router(router)

    if isinstance(settings, RateLimiterSettings) and settings.RATE_LIMITER_ENABLED:
        application.add_middleware(RateLimiterMiddleware)

    if isinstance(settings, CacheSettings) and settings.CACHE_ENABLED and hasattr(settings, "CLIENT_CACHE_ENABLED"):
        if settings.CLIENT_CACHE_ENABLED:
            client_cache_max_age = getattr(settings, "CLIENT_CACHE_MAX_AGE", 60)
            application.add_middleware(ClientCacheMiddleware, max_age=client_cache_max_age)

    if _enable_cors:
        cors_settings_dict: dict[str, Any] = {
            "allow_origins": _cors_origins,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
        if hasattr(settings, "CORS_ALLOW_CREDENTIALS"):
            cors_settings_dict["allow_credentials"] = settings.CORS_ALLOW_CREDENTIALS
        if hasattr(settings, "CORS_ALLOW_METHODS"):
            methods = settings.CORS_ALLOW_METHODS
            cors_settings_dict["allow_methods"] = methods.split(",") if isinstance(methods, str) else methods
        if hasattr(settings, "CORS_ALLOW_HEADERS"):
            headers = settings.CORS_ALLOW_HEADERS
            cors_settings_dict["allow_headers"] = headers.split(",") if isinstance(headers, str) else headers
        application.add_middleware(CORSMiddleware, **cors_settings_dict)

    if _enable_gzip:
        gzip_min_size = getattr(settings, "GZIP_MINIMUM_SIZE", 1000) if hasattr(settings, "GZIP_MINIMUM_SIZE") else 1000
        application.add_middleware(GZipMiddleware, minimum_size=gzip_min_size)

    _security_headers_enabled = getattr(settings, "SECURITY_HEADERS_ENABLED", True)
    if _security_headers_enabled:
        _environment = settings.ENVIRONMENT.value if hasattr(settings, "ENVIRONMENT") else EnvironmentOption.DEVELOPMENT.value
        application.add_middleware(SecurityHeadersMiddleware, environment=_environment)

    show_docs = isinstance(settings, EnvironmentSettings) and (
        settings.ENVIRONMENT != EnvironmentOption.PRODUCTION or _enable_docs_in_production
    )

    if show_docs:
        docs_router = APIRouter()

        is_production = isinstance(settings, EnvironmentSettings) and settings.ENVIRONMENT == EnvironmentOption.PRODUCTION
        is_local = isinstance(settings, EnvironmentSettings) and settings.ENVIRONMENT == EnvironmentOption.LOCAL

        apply_dependency = False
        dependency_to_apply = None

        if is_production and _enable_docs_in_production:
            apply_dependency = True
            dependency_to_apply = (
                docs_production_dependency if docs_production_dependency is not None else get_current_superuser
            )
        elif not is_local and not is_production:
            apply_dependency = True
            dependency_to_apply = get_current_superuser

        if apply_dependency and dependency_to_apply is not None:
            docs_router = APIRouter(dependencies=[Depends(dependency_to_apply)])

        @docs_router.get("/docs", include_in_schema=False)
        async def get_swagger_documentation() -> fastapi.responses.HTMLResponse:
            return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

        @docs_router.get("/redoc", include_in_schema=False)
        async def get_redoc_documentation() -> fastapi.responses.HTMLResponse:
            return get_redoc_html(openapi_url="/openapi.json", title="redoc")

        @docs_router.get("/openapi.json", include_in_schema=False)
        async def openapi() -> dict[str, Any]:
            return get_openapi(
                title=metadata.get("title", "API"),
                version=metadata.get("version", "0.1.0"),
                description=metadata.get("description", ""),
                routes=application.routes,
            )

        application.include_router(docs_router)

    return application
