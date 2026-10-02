"""Prove a feature can be removed: build a project without it and check it holds up.

Copies the repository to a scratch directory, deletes the paths of every feature
the preset leaves out, regenerates ``src/wiring/*``, ``scripts/seeders.py`` and
``tests/wiring.py`` for what remains, then checks that the app imports, that ruff
passes and that the remaining tests pass.

    python tools/removal_drill.py                 # every preset
    python tools/removal_drill.py accounts-only   # one of them
    python tools/removal_drill.py --keep          # leave the scratch copies behind
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Feature:
    """What a feature owns, and what it contributes to the wiring."""

    paths: tuple[str, ...] = ()
    combination_paths: dict[str, tuple[str, ...]] = field(default_factory=dict)


FEATURES: dict[str, Feature] = {
    "accounts": Feature(
        paths=(
            "backend/src/infrastructure/auth",
            "backend/src/modules/user",
            "backend/scripts/create_first_superuser.py",
            "backend/tests/unit/scripts/test_create_first_superuser.py",
            "backend/tests/fixtures/accounts.py",
            "backend/tests/integration/auth",
            "backend/tests/integration/api/v1/users",
            "backend/tests/integration/accounts",
            "backend/tests/unit/infrastructure/auth",
            "backend/tests/unit/modules/user",
        ),
    ),
    "rbac": Feature(
        paths=(
            "backend/src/modules/role",
            "backend/tests/unit/modules/role",
            "backend/tests/integration/rbac",
        ),
    ),
    "ratelimit": Feature(
        paths=(
            "backend/src/infrastructure/ratelimit",
            "backend/tests/unit/infrastructure/ratelimit",
            "backend/tests/integration/ratelimit",
        ),
    ),
    "tiers": Feature(
        paths=(
            "backend/src/modules/tier",
            "backend/scripts/create_first_tier.py",
            "backend/tests/fixtures/tiers.py",
            "backend/tests/unit/modules/tier",
            "backend/tests/integration/tiers",
        ),
        combination_paths={
            "admin": (
                "backend/src/modules/tier/admin.py",
                "backend/tests/unit/modules/tier/test_admin.py",
            )
        },
    ),
    "tier_limits": Feature(
        paths=(
            "backend/src/modules/rate_limit",
            "backend/tests/unit/modules/rate_limit",
            "backend/tests/integration/tier_limits",
        ),
    ),
    "api_keys": Feature(
        paths=(
            "backend/src/modules/api_keys",
            "backend/tests/unit/modules/api_keys",
            "backend/tests/integration/api/v1/api_keys",
        ),
    ),
    "admin": Feature(
        paths=(
            "backend/src/interfaces/admin",
            "backend/tests/unit/interfaces/admin",
            "backend/src/wiring/admin.py",
        ),
        combination_paths={
            "accounts": (
                "backend/src/modules/user/admin.py",
                "backend/tests/unit/modules/user/test_admin.py",
            ),
            "tiers": (
                "backend/src/modules/tier/admin.py",
                "backend/tests/unit/modules/tier/test_admin.py",
            ),
        },
    ),
    "cache": Feature(
        paths=(
            "backend/src/infrastructure/cache",
            "backend/tests/unit/infrastructure/cache",
        ),
    ),
    "taskiq": Feature(
        paths=(
            "backend/src/infrastructure/taskiq",
            "backend/tests/unit/infrastructure/taskiq",
        ),
    ),
}

REQUIRES = {
    "rbac": ("accounts",),
    "ratelimit": ("accounts",),
    "tiers": ("accounts",),
    "tier_limits": ("tiers", "ratelimit"),
    "api_keys": ("accounts",),
    "admin": ("accounts",),
}

PRESETS: dict[str, tuple[str, ...]] = {
    "core-only": (),
    "accounts-only": ("accounts",),
    "accounts-rbac": ("accounts", "rbac"),
    "accounts-rbac-tiers": ("accounts", "rbac", "tiers", "ratelimit"),
    "accounts-cache-taskiq": ("accounts", "cache", "taskiq"),
    "everything": tuple(FEATURES),
}


COPY_EXCLUDES = (
    ".git",
    ".venv",
    ".env",
    "bp-and-fastro",
    "site",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
)


def _selected_from(features: tuple[str, ...]) -> set[str]:
    """``features`` and everything they need, all the way down."""
    chosen = set(features)
    pending = list(chosen)
    while pending:
        for required in REQUIRES.get(pending.pop(), ()):
            if required not in chosen:
                chosen.add(required)
                pending.append(required)

    return chosen


def _selected(preset: str) -> set[str]:
    """The preset's features, and everything they need."""
    return _selected_from(PRESETS[preset])


def _wiring_settings(chosen: set[str]) -> str:
    mixins = [
        (
            "accounts",
            "from ..infrastructure.auth.settings import AccountsSettings",
            "AccountsSettings",
        ),
        (
            "ratelimit",
            "from ..infrastructure.ratelimit.settings import RateLimitSettings",
            "RateLimitSettings",
        ),
        ("tiers", "from ..modules.tier.settings import TierSettings", "TierSettings"),
        (
            "admin",
            "from ..interfaces.admin.settings import SQLAdminSettings",
            "SQLAdminSettings",
        ),
        (
            "cache",
            "from ..infrastructure.cache.settings import CacheSettings",
            "CacheSettings",
        ),
        (
            "taskiq",
            "from ..infrastructure.taskiq.settings import TaskiqSettings",
            "TaskiqSettings",
        ),
    ]
    imports = ["from ..infrastructure.config.base import CoreSettings"]
    bases = []
    for feature, line, name in mixins:
        if feature in chosen:
            imports.append(line)
            bases.append(name)
    bases.append("CoreSettings")
    body = ",\n    ".join(bases)
    return (
        '"""The project\'s settings: each selected feature\'s mixin on top of the core."""\n\n'
        + "\n".join(sorted(imports))
        + f"\n\n\nclass Settings(\n    {body},\n):\n"
        '    """The settings of every selected feature, on top of the core."""\n\n\nsettings = Settings()\n'
    )


def _wiring_app(chosen: set[str]) -> str:
    imports = [
        "from collections.abc import Callable",
        "from typing import Any",
        "",
        "from fastapi import APIRouter, Depends, FastAPI",
        "",
        "from ..infrastructure.composition import Lifecycle, RouterMount",
    ]
    mounts: list[str] = []
    root_routers = "()"
    throttle = "()"
    lifecycles: list[str] = []
    installers: list[str] = []
    docs_guard = "None"

    if "accounts" in chosen:
        imports += [
            "from ..infrastructure.auth.dependencies import get_current_superuser",
            "from ..infrastructure.auth.install import install as accounts_install",
            "from ..infrastructure.auth.routes import root_routers as accounts_root_routers",
            "from ..infrastructure.auth.routes import router as auth_router",
            "from ..infrastructure.auth.setup import lifecycle as accounts_lifecycle",
            "from ..modules.user.routes import router as users_router",
        ]
        mounts += [
            'RouterMount(users_router, "/users", throttled=True)',
            'RouterMount(auth_router, "/auth", throttled=False)',
        ]
        root_routers = "accounts_root_routers"
        lifecycles.append("accounts_lifecycle")
        installers.append("accounts_install")
        docs_guard = "get_current_superuser"
    if "ratelimit" in chosen:
        imports.append("from ..infrastructure.ratelimit.dependency import api_rate_limit_dependency")
        throttle = "(Depends(api_rate_limit_dependency),)"
    if "tiers" in chosen:
        imports += [
            "from ..modules.tier.routes import router as tiers_router",
            "from ..modules.tier.routes import user_tier_router",
        ]
        mounts += [
            'RouterMount(user_tier_router, "/users", throttled=True)',
            'RouterMount(tiers_router, "/tiers", throttled=True)',
        ]
    if "tier_limits" in chosen:
        imports += [
            "from ..modules.rate_limit.routes import router as rate_limits_router",
            "from ..modules.rate_limit.routes import user_rate_limits_router",
        ]
        mounts += [
            'RouterMount(user_rate_limits_router, "/users", throttled=True)',
            'RouterMount(rate_limits_router, "/rate-limits", throttled=True)',
        ]
    if "api_keys" in chosen:
        imports.append("from ..modules.api_keys.routes import router as api_keys_router")
        mounts.append('RouterMount(api_keys_router, "/api-keys", throttled=True)')
    if "cache" in chosen:
        imports.append("from ..infrastructure.cache.initialize import lifecycle as cache_lifecycle")
        lifecycles.append("cache_lifecycle")
    if "admin" in chosen:
        imports.append("from ..interfaces.admin.initialize import install as admin_install")
        installers.append("admin_install")

    def tuple_of(items: list[str]) -> str:
        return "(\n    " + ",\n    ".join(items) + ",\n)" if items else "()"

    return (
        '"""The composition root: what the app mounts, starts and installs."""\n\n'
        + "\n".join(imports)
        + f"\n\nROUTER_MOUNTS: tuple[RouterMount, ...] = {tuple_of(mounts)}\n"
        f"ROOT_ROUTERS: tuple[APIRouter, ...] = {root_routers}\n"
        f"API_THROTTLE: tuple[Any, ...] = {throttle}\n"
        f"LIFECYCLES: tuple[Lifecycle, ...] = {tuple_of(lifecycles)}\n"
        f"INSTALLERS: tuple[Callable[[FastAPI], None], ...] = {tuple_of(installers)}\n"
        f"DOCS_GUARD: Callable[..., Any] | None = {docs_guard}\n"
    )


def _wiring_hooks(chosen: set[str]) -> str:
    imports = [
        "from ..infrastructure.composition import PermissionSource, RateLimitResolver, ReadinessCheck, TierDeleteGuard",
        "from ..infrastructure.database.health import readiness as database_readiness",
    ]
    sources = "()"
    resolvers = "()"
    guards = "()"
    critical = ["database_readiness"]
    informational: list[str] = []

    if "rbac" in chosen:
        imports.append("from ..modules.role.sources import role_permissions")
        sources = "(role_permissions,)"
    if "tier_limits" in chosen:
        imports.append("from ..modules.rate_limit.hooks import rate_limits_reference_tier, tier_rate_limit")
        resolvers = "(tier_rate_limit,)"
        guards = "(rate_limits_reference_tier,)"
    if "accounts" in chosen:
        imports.append("from ..infrastructure.auth.health import limiter_readiness, sessions_readiness")
        critical.extend(["limiter_readiness", "sessions_readiness"])
    if "cache" in chosen:
        imports.append("from ..infrastructure.cache.health import readiness as cache_readiness")
        informational.append("cache_readiness")
    if "taskiq" in chosen:
        imports.append("from ..infrastructure.taskiq.health import readiness as broker_readiness")
        informational.append("broker_readiness")

    critical_checks = "(" + ", ".join(critical) + ",)"
    informational_checks = ("(" + ", ".join(informational) + ",)") if informational else "()"

    return (
        '''"""The contributions features make to each other\'s extension points."""\n\n'''
        + "\n".join(sorted(imports))
        + f"\n\nPERMISSION_SOURCES: tuple[PermissionSource, ...] = {sources}\n"
        f"RATE_LIMIT_RESOLVERS: tuple[RateLimitResolver, ...] = {resolvers}\n"
        f"TIER_DELETE_GUARDS: tuple[TierDeleteGuard, ...] = {guards}\n"
        f"CRITICAL_READINESS_CHECKS: tuple[ReadinessCheck, ...] = {critical_checks}\n"
        f"INFORMATIONAL_READINESS_CHECKS: tuple[ReadinessCheck, ...] = {informational_checks}\n"
    )


def _wiring_models(chosen: set[str]) -> str:
    imports = ["from pydantic import BaseModel"]
    model_bases, schema_bases = [], []
    if "rbac" in chosen:
        imports.append("from ..modules.role.contrib import UserRoleColumns")
        model_bases.append("UserRoleColumns")
    if "tiers" in chosen:
        imports.append("from ..modules.tier.contrib import UserTierColumns, UserTierFields")
        model_bases.append("UserTierColumns")
        schema_bases.append("UserTierFields")
    model_line = ", ".join(model_bases) if model_bases else ""
    schema_line = ", ".join(schema_bases) if schema_bases else "BaseModel"
    return (
        '"""Extension points of the user model: what other features add to ``User``."""\n\n'
        + "\n".join(sorted(imports))
        + f"\n\n\nclass UserModelExtensions({model_line}):\n"
        '    """Columns and relationships other features add to ``User``."""\n\n\n'
        f"class UserSchemaExtensions({schema_line}):\n"
        '    """Fields other features add to the user read schemas."""\n'
    )


def _wiring_admin(chosen: set[str]) -> str:
    imports, views = [], []
    if "accounts" in chosen:
        imports.append("from ..modules.user.admin import UserAdmin")
        views.append("UserAdmin")
    if "tiers" in chosen:
        imports.append("from ..modules.tier.admin import TierAdmin")
        views.append("TierAdmin")
    body = "(\n    " + ",\n    ".join(views) + ",\n)" if views else "()"
    return (
        '"""The model views the admin panel registers."""\n\n'
        + "\n".join(sorted(imports))
        + f"\n\nADMIN_VIEWS: tuple[type, ...] = {body}\n"
    )


def _seeders(chosen: set[str]) -> str:
    imports, seeds = [], []
    if "tiers" in chosen:
        imports.append("from scripts.create_first_tier import create_first_tier")
        seeds.append("create_first_tier")
    if "accounts" in chosen:
        imports.append("from scripts.create_first_superuser import create_first_superuser")
        seeds.append("create_first_superuser")
    body = "(\n    " + ",\n    ".join(seeds) + ",\n)" if seeds else "()"
    return (
        '"""The initial-data steps ``scripts/setup_initial_data.py`` runs, in order."""\n\n'
        + "\n".join(sorted(imports))
        + f"\n\nSEEDERS = {body}\n"
    )


def _tests_wiring(chosen: set[str]) -> str:
    plugins = []
    if "accounts" in chosen:
        plugins.append('"tests.fixtures.accounts"')
    if "tiers" in chosen:
        plugins.append('"tests.fixtures.tiers"')
    body = "[\n    " + ",\n    ".join(plugins) + ",\n]" if plugins else "[]"
    return f'"""Fixture modules of the selected features, loaded by ``tests/conftest.py``."""\n\nPYTEST_PLUGINS = {body}\n'


def build(preset: str, into: Path) -> Path:
    """Copy the repo into ``into`` and strip it down to ``preset``."""
    chosen = _selected(preset)
    project = into / preset
    shutil.copytree(
        REPO,
        project,
        ignore=shutil.ignore_patterns(*COPY_EXCLUDES),
    )

    for name, feature in FEATURES.items():
        if name in chosen:
            for partner, paths in feature.combination_paths.items():
                if partner not in chosen:
                    for path in paths:
                        _remove(project / path)
            continue
        for path in feature.paths:
            _remove(project / path)
        for paths in feature.combination_paths.values():
            for path in paths:
                _remove(project / path)

    (project / "backend/src/wiring/settings.py").write_text(_wiring_settings(chosen))
    (project / "backend/src/wiring/app.py").write_text(_wiring_app(chosen))
    (project / "backend/src/wiring/hooks.py").write_text(_wiring_hooks(chosen))
    (project / "backend/src/wiring/models.py").write_text(_wiring_models(chosen))
    if "admin" in chosen:
        (project / "backend/src/wiring/admin.py").write_text(_wiring_admin(chosen))
    (project / "backend/scripts/seeders.py").write_text(_seeders(chosen))
    (project / "backend/tests/wiring.py").write_text(_tests_wiring(chosen))

    _format(project)

    return project


def _format(project: Path) -> None:
    """A generator emits formatted code; so does this one."""
    generated = ["src/wiring", "scripts/seeders.py", "tests/wiring.py"]
    for command in (["--fix", "-q"], ["--select", "I", "--fix", "-q"]):
        subprocess.run(
            [sys.executable, "-m", "ruff", "check", *command, *generated],
            cwd=project / "backend",
            capture_output=True,
        )
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "-q", *generated],
        cwd=project / "backend",
        capture_output=True,
    )


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


_IMPORT_EVERY_MODULE = """
import importlib, pathlib, sys

broken = []
for path in sorted(pathlib.Path("src").rglob("*.py")):
    module = ".".join(path.with_suffix("").parts).removesuffix(".__init__")
    try:
        importlib.import_module(module)
    except Exception as error:
        broken.append(f"{module}: {type(error).__name__}: {error}")

if broken:
    sys.exit("modules left behind by the removed features: " + "; ".join(broken))

print("every module imports")
"""


def check(project: Path, python: Path) -> list[tuple[str, bool, str]]:
    """Import the app and every module, lint it, and run whatever tests are left.

    Importing every module matters: a file no feature imports any more still ships,
    and would fail only whenever someone reached for it.
    """
    backend = project / "backend"
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(backend),
        "ENVIRONMENT": "local",
        "SECRET_KEY": "drill-secret-key",
        "SESSION_BACKEND": "memory",
        "RATE_LIMITER_BACKEND": "memory",
        "HOME": str(Path.home()),
    }
    quiet = "import warnings, logging; warnings.simplefilter('ignore'); logging.disable(50); "
    steps = [
        ("app imports", [str(python), "-c", quiet + "import src.interfaces.main"]),
        ("every module imports", [str(python), "-c", quiet + _IMPORT_EVERY_MODULE]),
        ("ruff", [str(python), "-m", "ruff", "check", "src", "tests"]),
        ("mypy", [str(python), "-m", "mypy", "src", "--config-file", "pyproject.toml"]),
        ("tests", [str(python), "-m", "pytest", "tests", "-q", "-p", "no:randomly"]),
    ]
    results = []
    for name, command in steps:
        completed = subprocess.run(command, cwd=backend, env=environment, capture_output=True, text=True)
        output = (completed.stdout + completed.stderr).strip().splitlines()
        results.append((name, completed.returncode == 0, output[-1] if output else ""))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("presets", nargs="*", metavar="PRESET", help=f"one or more of: {', '.join(PRESETS)}")
    parser.add_argument("--keep", action="store_true", help="leave the scratch copies on disk")
    arguments = parser.parse_args()

    unknown = [preset for preset in arguments.presets if preset not in PRESETS]
    if unknown:
        parser.error(f"unknown preset(s) {', '.join(unknown)}; choose from {', '.join(PRESETS)}")

    python = Path(sys.executable)
    scratch = Path(tempfile.mkdtemp(prefix="removal-drill-"))
    failures = 0
    try:
        for preset in arguments.presets or PRESETS:
            project = build(preset, scratch)
            print(f"\n=== {preset}: {', '.join(sorted(_selected(preset))) or 'core only'}")
            for name, ok, last_line in check(project, python):
                print(f"  {'PASS' if ok else 'FAIL'}  {name:12} {last_line}")
                failures += not ok
    finally:
        if arguments.keep:
            print(f"\nscratch copies left in {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
