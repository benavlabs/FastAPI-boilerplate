"""What the generated compose files say about running this app behind a proxy."""

from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from cli.features._builtins.deploy.feature import DEFAULT_INTERNAL_SUBNET

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
    "internal_subnet": DEFAULT_INTERNAL_SUBNET,
    "taskiq": True,
}


def _render(template: str, mode: str = "nginx", **overrides) -> str:
    environment = Environment(loader=FileSystemLoader(TEMPLATES), keep_trailing_newline=True)

    return environment.get_template(template).render({**CONTEXT, "mode": mode, **overrides})


def _compose(mode: str, **overrides) -> dict:
    return yaml.safe_load(_render(f"{mode}/docker-compose.yml.j2", mode, **overrides))


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


def test_forwarded_headers_are_trusted_only_from_the_compose_network():
    """With a wildcard, uvicorn reads the leftmost X-Forwarded-For entry, which the client sets."""
    compose = _compose("nginx")

    assert compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"] == DEFAULT_INTERNAL_SUBNET
    assert compose["networks"]["default"]["ipam"]["config"] == [{"subnet": DEFAULT_INTERNAL_SUBNET}]


def test_nginx_hides_its_version():
    assert "server_tokens off;" in _render("nginx/default.conf.j2")


def test_the_local_compose_does_not_claim_a_proxy():
    """Nothing sits in front of it, so trusting forwarded headers would let a client forge its IP."""
    api = _compose("local")["services"]["api"]

    assert "TRUSTED_PROXY_HOPS" not in api.get("environment", {})


def test_the_local_compose_publishes_its_databases_to_the_host_only():
    """Both database ports are bound to the loopback address."""
    services = _compose("local")["services"]

    assert services["postgres"]["ports"] == ["127.0.0.1:5432:5432"]
    assert services["redis"]["ports"] == ["127.0.0.1:6379:6379"]


def test_nginx_sends_only_the_address_it_saw():
    """A client's own X-Forwarded-For must not reach the app as its address."""
    conf = _render("nginx/default.conf.j2")

    assert "proxy_set_header X-Forwarded-For $remote_addr;" in conf
    assert "$proxy_add_x_forwarded_for" not in conf


def test_the_compose_network_quotes_the_subnet():
    rendered = _render("nginx/docker-compose.yml.j2", "nginx")

    assert f'- subnet: "{DEFAULT_INTERNAL_SUBNET}"' in rendered


SCHEDULER_COMMAND = "taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler"


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_a_project_with_taskiq_gets_one_scheduler(mode: str):
    """Every schedule fires once per scheduler, so the stack runs a single one."""
    scheduler = _compose(mode)["services"]["scheduler"]

    assert SCHEDULER_COMMAND in " ".join(scheduler["command"].split())
    assert "deploy" not in scheduler


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_a_project_without_taskiq_gets_neither_worker_nor_scheduler(mode: str):
    services = _compose(mode, taskiq=False)["services"]

    assert "worker" not in services
    assert "scheduler" not in services
    assert "api" in services
