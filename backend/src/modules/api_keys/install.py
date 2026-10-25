"""What the api_keys feature adds to the app."""

from fastapi import FastAPI

from .usage import KeyUsageMiddleware


def install(app: FastAPI) -> None:
    """Record a usage row for every request an API key authenticated."""
    app.add_middleware(KeyUsageMiddleware)
