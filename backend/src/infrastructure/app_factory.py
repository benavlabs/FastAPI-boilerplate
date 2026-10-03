import json
import logging
from asyncio import Event
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Any

import anyio
import fastapi
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html

from ..modules.common.utils.error_handler import register_exception_handlers
from .composition import Lifecycle
from .config.settings import (
    EnvironmentOption,
    Settings,
    get_settings,
)
from .database.initialize import close_database
from .database.session import create_tables
from .middleware import ClientCacheMiddleware, SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


async def set_threadpool_tokens(number_of_tokens: int = 100) -> None:
    """Configure the number of threadpool tokens for anyio."""
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = number_of_tokens


def lifespan_factory(
    settings: Settings,
    create_tables_on_startup: bool = True,
    lifecycles: Sequence[Lifecycle] = (),
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Factory to create a lifespan async context manager for a FastAPI app.

    The database opens first and closes last. Each feature's ``Lifecycle`` then
    starts in order and is torn down in reverse, including when a later startup
    step raises. The caller says which ones: this module knows no feature.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        initialization_complete = Event()
        app.state.initialization_complete = initialization_complete

        await set_threadpool_tokens()

        async with AsyncExitStack() as teardown:
            teardown.push_async_callback(close_database)
            if create_tables_on_startup:
                await create_tables()

            for lifecycle in lifecycles:
                for shutdown in reversed(lifecycle.shutdown):
                    teardown.push_async_callback(shutdown)

                if lifecycle.startup is not None:
                    await lifecycle.startup()

            initialization_complete.set()

            yield

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
    docs_guard: Callable[..., Any] | None = None,
    root_routers: Sequence[APIRouter] = (),
    installers: Sequence[Callable[[FastAPI], None]] = (),
    lifecycles: Sequence[Lifecycle] = (),
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
    """Creates and configures a FastAPI application based on the provided settings.

    What the app mounts, installs and guards its docs with is passed in rather
    than read from the project's wiring, so the same factory can build a different
    project, and a test can build one with wiring of its own.
    """
    if settings is None:
        settings = get_settings()

    _create_tables_on_startup = (
        create_tables_on_startup if create_tables_on_startup is not None else settings.CREATE_TABLES_ON_STARTUP
    )
    _enable_cors = enable_cors if enable_cors is not None else settings.CORS_ENABLED

    _cors_origins: list[str] = cors_origins if cors_origins is not None else settings.CORS_ORIGINS_LIST

    _enable_docs_in_production = (
        enable_docs_in_production if enable_docs_in_production is not None else settings.ENABLE_DOCS_IN_PRODUCTION
    )
    _enable_gzip = enable_gzip if enable_gzip is not None else settings.GZIP_ENABLED
    _openapi_prefix = openapi_prefix if openapi_prefix is not None else settings.OPENAPI_PREFIX

    metadata: dict[str, Any] = {"openapi_prefix": _openapi_prefix}

    metadata["title"] = title or settings.API_TITLE or settings.APP_NAME

    summary_text = summary or settings.API_SUMMARY
    if summary_text:
        metadata["summary"] = summary_text

    metadata["description"] = description or settings.API_DESCRIPTION or settings.APP_DESCRIPTION
    metadata["version"] = version or settings.API_VERSION or settings.VERSION

    terms = terms_of_service or settings.API_TERMS_OF_SERVICE
    if terms:
        metadata["terms_of_service"] = terms

    if contact is not None:
        metadata["contact"] = contact
    else:
        contact_dict = {}
        if settings.API_CONTACT_NAME:
            contact_dict["name"] = settings.API_CONTACT_NAME
        if settings.API_CONTACT_EMAIL:
            contact_dict["email"] = settings.API_CONTACT_EMAIL
        if settings.API_CONTACT_URL:
            contact_dict["url"] = settings.API_CONTACT_URL
        if contact_dict:
            metadata["contact"] = contact_dict

    if license_info is not None:
        metadata["license_info"] = license_info
    else:
        if settings.API_LICENSE_NAME:
            license_dict = {"name": settings.API_LICENSE_NAME}
            if settings.API_LICENSE_IDENTIFIER:
                license_dict["identifier"] = settings.API_LICENSE_IDENTIFIER
            elif settings.API_LICENSE_URL:
                license_dict["url"] = settings.API_LICENSE_URL
            metadata["license_info"] = license_dict

    if openapi_tags is not None:
        metadata["openapi_tags"] = openapi_tags
    elif settings.API_TAGS_METADATA:
        try:
            metadata["openapi_tags"] = json.loads(settings.API_TAGS_METADATA)
        except json.JSONDecodeError:
            pass

    _docs_url = docs_url if docs_url is not None else settings.DOCS_URL
    _redoc_url = redoc_url if redoc_url is not None else settings.REDOC_URL
    _openapi_url = openapi_url if openapi_url is not None else settings.OPENAPI_URL

    metadata["docs_url"] = _docs_url
    metadata["redoc_url"] = _redoc_url
    metadata["openapi_url"] = _openapi_url

    kwargs.update(metadata)

    show_docs = settings.ENVIRONMENT != EnvironmentOption.PRODUCTION or _enable_docs_in_production

    is_production = settings.ENVIRONMENT == EnvironmentOption.PRODUCTION

    docs_dependency = None
    if show_docs:
        if is_production and _enable_docs_in_production:
            docs_dependency = docs_production_dependency if docs_production_dependency is not None else docs_guard
            show_docs = docs_dependency is not None
        elif settings.ENVIRONMENT == EnvironmentOption.STAGING:
            docs_dependency = docs_guard
            show_docs = docs_dependency is not None

    hide_docs = settings.ENVIRONMENT == EnvironmentOption.PRODUCTION and not _enable_docs_in_production
    serve_builtin_docs = not hide_docs and docs_dependency is None and show_docs
    if not serve_builtin_docs:
        kwargs.update({"docs_url": None, "redoc_url": None, "openapi_url": None})

    if lifespan is None:
        lifespan = lifespan_factory(settings, create_tables_on_startup=_create_tables_on_startup, lifecycles=lifecycles)

    application = FastAPI(lifespan=lifespan, **kwargs)

    register_exception_handlers(application)

    application.include_router(router)

    for root_router in root_routers:
        application.include_router(root_router)

    for install in installers:
        install(application)

    if settings.CLIENT_CACHE_ENABLED:
        application.add_middleware(ClientCacheMiddleware, max_age=settings.CLIENT_CACHE_MAX_AGE, api_prefix=settings.API_PREFIX)

    if _enable_cors and _cors_origins:
        methods = settings.CORS_ALLOW_METHODS
        headers = settings.CORS_ALLOW_HEADERS
        cors_settings_dict: dict[str, Any] = {
            "allow_origins": _cors_origins,
            "allow_credentials": settings.CORS_ALLOW_CREDENTIALS and "*" not in _cors_origins,
            "allow_methods": methods.split(",") if isinstance(methods, str) else methods,
            "allow_headers": headers.split(",") if isinstance(headers, str) else headers,
        }
        application.add_middleware(CORSMiddleware, **cors_settings_dict)

    if _enable_gzip:
        gzip_min_size = settings.GZIP_MINIMUM_SIZE
        application.add_middleware(GZipMiddleware, minimum_size=gzip_min_size)

    if settings.SECURITY_HEADERS_ENABLED:
        _environment = settings.ENVIRONMENT.value
        application.add_middleware(SecurityHeadersMiddleware, environment=_environment)

    if show_docs:
        docs_router = APIRouter()

        if docs_dependency is not None:
            docs_router = APIRouter(dependencies=[Depends(docs_dependency)])

        @docs_router.get(_docs_url, include_in_schema=False)
        async def get_swagger_documentation(request: Request) -> fastapi.responses.HTMLResponse:
            root_path: str = request.scope.get("root_path", "").rstrip("/")
            return get_swagger_ui_html(openapi_url=root_path + _openapi_url, title="docs")

        @docs_router.get(_redoc_url, include_in_schema=False)
        async def get_redoc_documentation(request: Request) -> fastapi.responses.HTMLResponse:
            root_path: str = request.scope.get("root_path", "").rstrip("/")
            return get_redoc_html(openapi_url=root_path + _openapi_url, title="redoc")

        @docs_router.get(_openapi_url, include_in_schema=False)
        async def openapi(request: Request) -> dict[str, Any]:
            root_path: str = request.scope.get("root_path", "").rstrip("/")
            served_urls = {server.get("url") for server in application.servers}
            if root_path and application.root_path_in_servers and root_path not in served_urls:
                application.servers.insert(0, {"url": root_path})

            return application.openapi()

        application.include_router(docs_router)

    return application
