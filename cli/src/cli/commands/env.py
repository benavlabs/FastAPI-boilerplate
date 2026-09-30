"""``bp env`` — inspect and prepare the runtime environment.

Two commands today:

- ``bp env gen-secret`` prints a 64-char hex string suitable for
  ``SECRET_KEY``. No filesystem I/O — pipe it into your secrets manager.

- ``bp env validate`` runs the production security validator against
  the current settings, regardless of the configured environment, and
  prints critical errors and warnings.
"""

from __future__ import annotations

import importlib
import secrets
import sys
from pathlib import Path
from types import ModuleType

import typer

from ..lib.prompts import error, info, success, warn


def _app_module(name: str) -> ModuleType:
    """Import a backend module by its ``src.`` path, putting ``backend/`` on the path first.

    The app is imported through a single root, ``src``, which the installed
    distribution does not expose: its packages are published from inside ``src/``.
    Resolving it here, when a command needs it, also keeps ``bp --help`` from
    paying for the app's settings and database imports.
    """
    backend = next((p / "backend" for p in (Path.cwd(), *Path.cwd().parents) if (p / "backend" / "src").is_dir()), None)
    if backend is None:
        error("No `backend/src` in this directory or above it: run this from inside a project.")
        raise typer.Exit(code=1)

    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    return importlib.import_module(name)


app = typer.Typer(no_args_is_help=True, help="Inspect and prepare the runtime environment.")


@app.command("gen-secret")
def gen_secret(
    bytes_: int = typer.Option(32, "--bytes", min=16, max=128, help="Number of random bytes (hex output is 2x)."),
) -> None:
    """Generate a high-entropy hex secret suitable for ``SECRET_KEY``."""
    typer.echo(secrets.token_hex(bytes_))


@app.command("validate")
def validate() -> None:
    """Run the production security validator against the current settings.

    Reports what production would refuse whatever ``ENVIRONMENT`` says, so a dev
    or staging config can be audited the same way prod is gated.
    """
    settings = _app_module("src.infrastructure.config.settings").get_settings()
    validator_module = _app_module("src.infrastructure.security.production_validator")
    ProductionSecurityValidator = validator_module.ProductionSecurityValidator

    critical_errors, captured_warnings = ProductionSecurityValidator(settings).audit()

    if not critical_errors and not captured_warnings:
        success("No issues found. Configuration would pass production validation.")
        return

    if critical_errors:
        error(f"Critical ({len(critical_errors)}):")
        for item in critical_errors:
            typer.secho(f"  • {item}", fg=typer.colors.RED)

    if captured_warnings:
        if critical_errors:
            info("")
        warn(f"Warnings ({len(captured_warnings)}):")
        for item in captured_warnings:
            typer.secho(f"  • {item}", fg=typer.colors.YELLOW)

    if critical_errors:
        raise typer.Exit(code=1)
