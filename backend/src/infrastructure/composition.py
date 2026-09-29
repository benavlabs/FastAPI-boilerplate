"""The shapes a feature contributes to the app; ``src/wiring`` lists the instances.

Features never import each other to plug in. A feature exposes plain objects of
these types at a stable path, the wiring imports the ones this project selected,
and the core reads them from there.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter


@dataclass(frozen=True)
class RouterMount:
    """Mount ``router`` under the API prefix; ``throttled`` puts it behind the API rate limit."""

    router: APIRouter
    prefix: str
    throttled: bool = True


@dataclass(frozen=True)
class Lifecycle:
    """Startup and shutdown work a feature needs, run in wiring order and torn down in reverse."""

    name: str
    startup: Callable[[], Awaitable[Any]] | None = None
    shutdown: tuple[Callable[[], Awaitable[Any]], ...] = field(default_factory=tuple)
