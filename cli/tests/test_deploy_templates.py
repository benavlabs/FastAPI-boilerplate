"""What the generated compose files say about running this app behind a proxy."""

from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[1] / "src/cli/features/_builtins/deploy/templates"

CONTEXT = {
    "mode": "nginx",
    "project_name": "example",
    "api_port": 8000,
    "workers": 4,
    "postgres_image": "postgres:16-alpine",
    "redis_image": "redis:7-alpine",
    "nginx_image": "nginx:1.27-alpine",
    "backend_context": "./backend",
    "build_context": ".",
    "backend_dockerfile": "backend/Dockerfile",
    "env_file": "./backend/.env",
}


def _compose(mode: str) -> dict:
    environment = Environment(loader=FileSystemLoader(TEMPLATES), keep_trailing_newline=True)
    rendered = environment.get_template(f"{mode}/docker-compose.yml.j2").render({**CONTEXT, "mode": mode})

    return yaml.safe_load(rendered)


@pytest.mark.parametrize("mode", ["prod", "nginx"])
def test_the_api_reports_whether_it_is_ready(mode: str):
    """Compose has no way to hold traffic back without one."""
    healthcheck = _compose(mode)["services"]["api"]["healthcheck"]

    assert "/health/ready" in " ".join(healthcheck["test"])


@pytest.mark.parametrize("mode", ["prod", "nginx"])
def test_the_worker_does_not_run_as_root(mode: str):
    """The base stage has no USER, so building the worker from it would run it as root."""
    assert _compose(mode)["services"]["worker"]["build"]["target"] == "prod"


def test_behind_nginx_the_app_is_told_how_many_proxies_it_sits_behind():
    """Without this every client looks like the nginx container, and one attacker locks everyone out."""
    api = _compose("nginx")["services"]["api"]["environment"]

    assert api["TRUSTED_PROXY_HOPS"] == "1"
    assert api["FORWARDED_ALLOW_IPS"] == "*"


def test_the_local_compose_does_not_claim_a_proxy():
    """Nothing sits in front of it, so trusting forwarded headers would let a client forge its IP."""
    api = _compose("local")["services"]["api"]

    assert "TRUSTED_PROXY_HOPS" not in api.get("environment", {})
