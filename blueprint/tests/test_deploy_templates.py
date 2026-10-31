"""What the generated compose files say about running this app behind a proxy.

The templates are rendered with the generator context of catalog spec 6.2, under
``StrictUndefined``: a template that reaches for anything the tool doesn't pass fails here.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "deploy"

INTERNAL_SUBNET = "172.31.240.0/24"
"""The default of the ``internal_subnet`` param."""

TASKIQ_SERVICES = ("scheduler", "worker")
"""What the taskiq feature puts in ``services``."""


def _context(
    features: tuple[str, ...] = ("accounts", "taskiq"),
    services: tuple[str, ...] = TASKIQ_SERVICES,
    **params: Any,
) -> dict[str, Any]:
    """The spec 6.2 context, as the tool builds it for a generator."""
    return {
        "project": {"name": "example", "slug": "example"},
        "blueprint": {"name": "fastro", "version": "0.20.0"},
        "fastro": {"version": "0.1.0"},
        "features": list(features),
        "options": {},
        "services": sorted(services),
        "params": {"api_port": 8000, "workers": 4, "internal_subnet": INTERNAL_SUBNET, **params},
        "has": lambda name: name in features,
    }


def _render(template: str, **overrides: Any) -> str:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )

    return environment.get_template(template).render(_context(**overrides))


def _compose(mode: str, **overrides: Any) -> dict:
    return yaml.safe_load(_render(f"{mode}/docker-compose.yml.j2", **overrides))


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

    assert compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"] == INTERNAL_SUBNET
    assert compose["networks"]["default"]["ipam"]["config"] == [{"subnet": INTERNAL_SUBNET}]


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
    rendered = _render("nginx/docker-compose.yml.j2")

    assert f'- subnet: "{INTERNAL_SUBNET}"' in rendered


SCHEDULER_COMMAND = "taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler"


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_a_project_with_taskiq_gets_one_scheduler(mode: str):
    """Every schedule fires once per scheduler, so the stack runs a single one."""
    scheduler = _compose(mode)["services"]["scheduler"]

    assert SCHEDULER_COMMAND in " ".join(scheduler["command"].split())
    assert "deploy" not in scheduler


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_a_project_without_taskiq_gets_neither_worker_nor_scheduler(mode: str):
    services = _compose(mode, features=("accounts",), services=())["services"]

    assert "worker" not in services
    assert "scheduler" not in services
    assert "api" in services


@pytest.mark.parametrize("mode", ["prod", "nginx"])
def test_the_migration_runner_waits_to_be_asked(mode: str):
    """A deploy runs it and only then restarts, so a failed migration leaves the old code serving."""
    migrate = _compose(mode)["services"]["migrate"]

    assert migrate["profiles"] == ["migrate"]
    assert migrate["build"]["target"] == "migrate"


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_nothing_depends_on_a_service_behind_a_profile(mode: str):
    """Compose refuses the whole project when a service it starts depends on a profiled one."""
    services = _compose(mode)["services"]
    behind_a_profile = {name for name, service in services.items() if service.get("profiles")}

    for name, service in services.items():
        assert behind_a_profile.isdisjoint(service.get("depends_on", {})), name


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_the_database_takes_its_credentials_from_the_environment_file(mode: str):
    """Compose interpolates ``${VAR}`` from the shell, never from ``env_file``, and
    ``environment`` wins over it: a password set in ``backend/.env``, which is where every page
    says to set it, was replaced in the container by the literal fallback.
    """
    postgres = _compose(mode)["services"]["postgres"]

    assert postgres["env_file"] == ["./backend/.env"]
    assert "${" not in yaml.safe_dump(postgres.get("environment", {}))


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_the_database_probe_reads_the_user_inside_the_container(mode: str):
    """A probe interpolated by compose asks for ``postgres`` whatever ``POSTGRES_USER`` says."""
    probe = " ".join(_compose(mode)["services"]["postgres"]["healthcheck"]["test"])

    assert "$${POSTGRES_USER" in probe


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_the_compose_project_is_named_after_the_project(mode: str):
    """The slug is what compose accepts as a project name, and what the nginx upstream is keyed on."""
    assert _compose(mode)["name"] == "example"


def test_the_api_runs_the_workers_the_params_asked_for():
    """``workers`` and ``api_port`` are generator params, so a flag has to reach the template."""
    compose = _compose("prod", workers=7, api_port=9001)

    assert compose["services"]["api"]["environment"]["WORKERS"] == "7"
    assert compose["services"]["api"]["ports"] == ["9001:8000"]


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_each_background_service_follows_its_own_entry(mode: str):
    """The blocks are keyed on ``services``, not on the feature, so one without the other works."""
    services = _compose(mode, services=("worker",))["services"]

    assert "worker" in services
    assert "scheduler" not in services
