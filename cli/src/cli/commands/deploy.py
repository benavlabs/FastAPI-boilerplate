"""``bp deploy`` — generate deployment artifacts.

Today this is just a wrapper around the in-tree ``deploy`` feature.
Other deploy-adjacent commands (``bp deploy nginx-tls``, ``bp deploy
github-actions``) can mount here as siblings.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer

from ..features._builtins.deploy.feature import DEFAULT_INTERNAL_SUBNET
from ..features.installer import FeatureInstaller
from ..features.registry import get_feature
from ..lib.project import discover_project
from ..lib.prompts import error, info

app = typer.Typer(no_args_is_help=True, help="Generate deployment artifacts.")


class DeployMode(StrEnum):
    local = "local"
    prod = "prod"
    nginx = "nginx"


@app.command("generate")
def generate(
    mode: DeployMode = typer.Argument(
        ...,
        help="Deployment mode to generate. Pick `local` for hot-reload dev, `prod` for "
        "single-host production, `nginx` for production behind a reverse proxy.",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Where to write the compose file. Defaults to the repo root.",
    ),
    api_port: int = typer.Option(8000, "--api-port", help="Host port to publish the API on."),
    workers: int = typer.Option(4, "--workers", help="Number of API workers (prod / nginx only)."),
    internal_subnet: str = typer.Option(
        DEFAULT_INTERNAL_SUBNET,
        "--internal-subnet",
        help="Subnet for the compose network, and the only peers uvicorn takes forwarded headers from (nginx only).",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files without asking."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Assume yes for all prompts."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be written, don't touch disk."),
) -> None:
    """Generate ``docker-compose.yml`` (and ``nginx/default.conf`` for nginx mode)."""
    project = discover_project(output_dir)
    feature = get_feature("deploy")
    if feature is None:  # pragma: no cover — built-in feature, always present
        error("deploy feature is not registered.")
        raise typer.Exit(code=1)

    target_root = (output_dir or project.repo_root).resolve()
    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)

    params: dict = {
        "mode": mode.value,
        "api_port": api_port,
        "workers": workers,
        "compose_target": target_root / "docker-compose.yml",
    }
    if mode == DeployMode.nginx:
        params["nginx_conf_target"] = target_root / "nginx" / "default.conf"
        params["internal_subnet"] = internal_subnet

    try:
        plan = feature.plan(params, project)
    except ValueError as failure:
        error(f"--internal-subnet: {failure}")
        raise typer.Exit(code=1) from failure

    installer = FeatureInstaller(dry_run=dry_run, assume_yes=force or yes)
    info(f"deploy: generating '{mode.value}' compose for {project.repo_root}")
    result = installer.apply(plan)

    if result.files_skipped:
        info("")
        info(f"{len(result.files_skipped)} file(s) skipped.")
    if dry_run:
        info("")
        info("dry-run complete — no files were written.")
        return

    info("")
    info("done. Next steps:")
    if mode == DeployMode.local:
        info("  docker compose up --build")
    elif mode == DeployMode.prod:
        info("  cp backend/.env.example backend/.env  # if you haven't already")
        info("  docker compose up -d --build")
    else:
        info("  cp backend/.env.example backend/.env  # if you haven't already")
        info("  docker compose up -d --build")
        info("  curl -i http://localhost/health/ready")
