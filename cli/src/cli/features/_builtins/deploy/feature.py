"""The deploy feature — generate Dockerfile-friendly compose files.

Three modes are supported in v1:

- ``local``: hot-reload dev stack (mounts source, exposes port 8000)
- ``prod``: production stack with multiple workers, ports exposed directly
- ``nginx``: ``prod`` plus an nginx reverse proxy on port 80

All modes target the existing multi-stage ``backend/Dockerfile`` —
no per-mode Dockerfile is generated. Modes only differ in the
compose file (and an optional nginx config).
"""

from __future__ import annotations

from ipaddress import ip_network
from pathlib import Path
from typing import Any

from ....lib.project import ProjectContext
from ...base import Feature, FeatureManifest, FeaturePlan, FileOp

SUPPORTED_MODES: tuple[str, ...] = ("local", "prod", "nginx")
DEFAULT_INTERNAL_SUBNET = "172.31.240.0/24"
SMALLEST_TRUSTED_PREFIX = {4: 8, 6: 48}

_TEMPLATES_ROOT = Path(__file__).parent / "templates"


def validated_subnet(value: str) -> str:
    """The subnet in the form ``ipaddress`` reads, refusing one that trusts too much.

    Takes a network of ``/8`` or smaller for IPv4, ``/48`` or smaller for IPv6.

    Raises:
        ValueError: ``value`` is not a network address, carries host bits, or covers
            more than the smallest prefix its family allows.
    """
    try:
        network = ip_network(value, strict=True)
    except ValueError as error:
        raise ValueError(f"{value!r} is not a network address, such as 172.31.240.0/24.") from error

    smallest = SMALLEST_TRUSTED_PREFIX[network.version]
    if network.prefixlen < smallest:
        raise ValueError(f"{value!r} covers {network.num_addresses} addresses; name a range of /{smallest} or smaller.")

    return str(network)


class DeployFeature(Feature):
    def manifest(self) -> FeatureManifest:
        return FeatureManifest(
            name="deploy",
            version="1.0",
            summary="Generate a docker-compose.yml for local, prod, or nginx-fronted deployments.",
        )

    def plan(self, params: dict[str, Any], project: ProjectContext) -> FeaturePlan:
        mode = params.get("mode")
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"Unsupported deploy mode: {mode!r}. Choose one of {SUPPORTED_MODES}.")

        project_name = params.get("project_name") or project.repo_root.name
        api_port = int(params.get("api_port", 8000))
        workers = int(params.get("workers", 4))
        postgres_image = params.get("postgres_image", "postgres:16-alpine")
        redis_image = params.get("redis_image", "redis:7-alpine")
        nginx_image = params.get("nginx_image", "nginx:1.27-alpine")
        backend_context = params.get("backend_context", "./backend")
        build_context = params.get("build_context", ".")
        backend_dockerfile = params.get("backend_dockerfile", "backend/Dockerfile")
        env_file = params.get("env_file", "./backend/.env")
        internal_subnet = validated_subnet(params.get("internal_subnet", DEFAULT_INTERNAL_SUBNET))

        context = {
            "mode": mode,
            "project_name": project_name,
            "api_port": api_port,
            "workers": workers,
            "postgres_image": postgres_image,
            "redis_image": redis_image,
            "nginx_image": nginx_image,
            "backend_context": backend_context,
            "build_context": build_context,
            "backend_dockerfile": backend_dockerfile,
            "env_file": env_file,
            "internal_subnet": internal_subnet,
        }

        compose_target = Path(params.get("compose_target") or (project.repo_root / "docker-compose.yml"))
        files: list[FileOp] = [
            FileOp(template=f"{mode}/docker-compose.yml.j2", target=compose_target),
        ]
        if mode == "nginx":
            nginx_target = Path(params.get("nginx_conf_target") or (project.repo_root / "nginx" / "default.conf"))
            files.append(FileOp(template="nginx/default.conf.j2", target=nginx_target))

        return FeaturePlan(
            manifest=self.manifest(),
            templates_root=_TEMPLATES_ROOT,
            template_context=context,
            files=tuple(files),
        )
