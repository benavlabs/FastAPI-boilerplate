"""What the generated compose files say about running this app behind a proxy.

The templates are rendered with the generator context of catalog spec 6.2, under
``StrictUndefined``: a template that reaches for anything the tool doesn't pass fails here.
"""

import ast
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parents[2]

CATALOG = tomllib.loads((REPO_ROOT / "blueprint.toml").read_text())

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "deploy"

INTERNAL_SUBNET = "172.31.240.0/24"
"""The default of the ``internal_subnet`` param."""

TASKIQ_SERVICES = ("scheduler", "worker")
"""What the taskiq feature puts in ``services``."""

MODES = ("local", "prod", "nginx")

APP_CONTAINERS = ("api", "worker", "scheduler")
"""The containers that run the project's code, and so connect to what a choice brings."""

HOST_SETTINGS = {"memcached": "CACHE_MEMCACHED_HOST", "rabbitmq": "TASKIQ_RABBITMQ_HOST"}
"""The setting that points the app at each service an option's value brings."""


def _context(
    features: tuple[str, ...] = ("accounts", "taskiq"),
    services: tuple[str, ...] = TASKIQ_SERVICES,
    options: dict[str, str] | None = None,
    **params: Any,
) -> dict[str, Any]:
    """The spec 6.2 context, as the tool builds it for a generator."""
    return {
        "project": {"name": "example", "slug": "example"},
        "blueprint": {"name": CATALOG["blueprint"]["name"], "version": CATALOG["blueprint"]["version"]},
        "fastro": {"version": "0.1.0"},
        "features": list(features),
        "options": options or {},
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
    assert "server_tokens off;" in _render("nginx/nginx/default.conf.j2")


def test_the_local_compose_does_not_claim_a_proxy():
    """Nothing sits in front of it, so trusting forwarded headers would let a client forge its IP."""
    api = _compose("local")["services"]["api"]

    assert "TRUSTED_PROXY_HOPS" not in api.get("environment", {})


def test_the_local_compose_publishes_its_databases_to_the_host_only():
    """Every port but the API's is bound to the loopback address, whichever services the choices bring."""
    services = _compose("local", services=(*TASKIQ_SERVICES, *_option_services()))["services"]
    published = {name: service["ports"] for name, service in services.items() if name != "api" and "ports" in service}

    assert published["postgres"] == ["127.0.0.1:5432:5432"]
    assert published["redis"] == ["127.0.0.1:6379:6379"]
    assert set(_option_services()) <= set(published)
    for name, ports in published.items():
        assert all(port.startswith("127.0.0.1:") for port in ports), name


def test_nginx_sends_only_the_address_it_saw():
    """A client's own X-Forwarded-For must not reach the app as its address."""
    conf = _render("nginx/nginx/default.conf.j2")

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


def _option_services() -> list[str]:
    """Every service some option's value brings."""
    return sorted(
        {
            service
            for feature in CATALOG["features"].values()
            for option in feature.get("options", {}).values()
            for services in option.get("services", {}).values()
            for service in services
        }
    )


def _catalog_services(features: tuple[str, ...], options: dict[str, str]) -> set[str]:
    """What spec 6.2 puts in ``services``: each chosen feature's own and its options' for the values chosen."""
    services: set[str] = set()
    for name in features:
        feature = CATALOG["features"][name]
        assert all("services" not in when for when in feature.get("when", [])), f"{name}: read the when's condition"
        services.update(feature.get("services", []))
        for option_name, option in feature.get("options", {}).items():
            chosen = options.get(f"{name}.{option_name}", option["default"])
            services.update(option.get("services", {}).get(chosen, []))

    return services


def _selections() -> Iterator[tuple[tuple[str, ...], dict[str, str]]]:
    """No feature, then each feature that brings services at its defaults and at every value of every option."""
    yield (), {}
    for name, feature in CATALOG["features"].items():
        options = feature.get("options", {})
        if not feature.get("services") and not any(option.get("services") for option in options.values()):
            continue
        yield (name,), {}
        for option_name, option in options.items():
            for choice in option["choices"]:
                yield (name,), {f"{name}.{option_name}": choice}


SELECTIONS = list(_selections())


def _selection_id(features: tuple[str, ...], options: dict[str, str]) -> str:
    return ",".join([*features, *(f"{option}={value}" for option, value in options.items())]) or "none"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(("features", "options"), SELECTIONS, ids=[_selection_id(*selection) for selection in SELECTIONS])
def test_the_compose_runs_the_services_the_catalog_gives_each_choice(
    mode: str, features: tuple[str, ...], options: dict[str, str]
):
    """A service the catalog names that no template renders never starts, and the app waits on it or can't reach it."""
    base = set(_compose(mode, features=(), services=())["services"])
    services = _catalog_services(features, options)
    compose = _compose(mode, features=features, options=options, services=tuple(sorted(services)))

    assert base.isdisjoint(_option_services())
    assert set(compose["services"]) - base == services
    for name, service in compose["services"].items():
        assert set(service.get("depends_on", {})) <= set(compose["services"]), name
        for volume in service.get("volumes", []):
            source = volume.split(":")[0]
            assert source.startswith(".") or source in (compose.get("volumes") or {}), (name, source)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("brought", _option_services())
def test_each_app_container_is_pointed_at_and_waits_for_a_service_a_choice_brings(mode: str, brought: str):
    """The settings default to localhost, which inside a container is the container itself."""
    services = _compose(mode, services=(*TASKIQ_SERVICES, brought))["services"]

    assert services[brought]["healthcheck"]
    for name in APP_CONTAINERS:
        assert services[name]["environment"][HOST_SETTINGS[brought]] == brought, name
        assert services[name]["depends_on"][brought] == {"condition": "service_healthy"}, name


@pytest.mark.parametrize("mode", ["prod", "nginx"])
@pytest.mark.parametrize("brought", _option_services())
def test_a_production_stack_keeps_a_service_a_choice_brings_off_the_host_and_restarts_it(mode: str, brought: str):
    """Neither Memcached nor a broker on the compose network has to be reachable from outside it."""
    service = _compose(mode, services=(*TASKIQ_SERVICES, brought))["services"][brought]

    assert "ports" not in service
    assert service["restart"] == "unless-stopped"


@pytest.mark.parametrize("mode", MODES)
def test_without_the_choice_no_app_container_names_its_service(mode: str):
    services = _compose(mode)["services"]

    for name in APP_CONTAINERS:
        for brought, setting in HOST_SETTINGS.items():
            assert setting not in services[name]["environment"], name
            assert brought not in services[name]["depends_on"], name


TASKIQ_SETTINGS = REPO_ROOT / "backend" / "src" / "infrastructure" / "taskiq" / "settings.py"

BROKER_START = r'((?:RABBITMQ_DEFAULT_\w+="\$\$\{TASKIQ_RABBITMQ_\w+:-[^"]*\}" )+)exec docker-entrypoint\.sh rabbitmq-server'
"""Assignments that prefix the ``exec``, so the image's entrypoint is started with them in its environment."""


@pytest.mark.parametrize("mode", MODES)
def test_the_broker_takes_its_credentials_from_the_environment_file(mode: str):
    """The image creates the user it is handed, so it has to be the one the app logs in as from ``backend/.env``;
    compose would read ``${VAR}`` from the shell instead.
    """
    rabbitmq = _compose(mode, services=(*TASKIQ_SERVICES, "rabbitmq"))["services"]["rabbitmq"]
    shell, flag, script = rabbitmq["entrypoint"]
    handed = re.fullmatch(BROKER_START, script)

    assert (shell, flag) == ("sh", "-c")
    assert "command" not in rabbitmq
    assert rabbitmq["env_file"] == ["./backend/.env"]
    assert not re.search(r"(?<!\$)\$\{", yaml.safe_dump(rabbitmq))
    assert handed is not None
    assert re.findall(r'(RABBITMQ_DEFAULT_\w+)="\$\$\{(TASKIQ_RABBITMQ_\w+):-([^"]*)\}"', handed[1]) == [
        ("RABBITMQ_DEFAULT_USER", "TASKIQ_RABBITMQ_USER", _setting_default("TASKIQ_RABBITMQ_USER")),
        ("RABBITMQ_DEFAULT_PASS", "TASKIQ_RABBITMQ_PASSWORD", _setting_default("TASKIQ_RABBITMQ_PASSWORD")),
        ("RABBITMQ_DEFAULT_VHOST", "TASKIQ_RABBITMQ_VHOST", _setting_default("TASKIQ_RABBITMQ_VHOST")),
    ]


def _setting_default(name: str) -> str:
    """The default ``TaskiqSettings`` gives ``name``, which the app logs in with when ``backend/.env`` leaves it out."""
    tree = ast.parse(TASKIQ_SETTINGS.read_text())
    (default,) = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
        and isinstance(node.value, ast.Constant)
    ]
    assert isinstance(default, str), (name, default)

    return default


@pytest.mark.parametrize("mode", MODES)
def test_the_broker_keeps_its_queues_across_a_recreate(mode: str):
    """RabbitMQ keeps its data under its node name, which follows the hostname a recreated container would change."""
    compose = _compose(mode, services=(*TASKIQ_SERVICES, "rabbitmq"))
    rabbitmq = compose["services"]["rabbitmq"]

    assert rabbitmq["hostname"] == "rabbitmq"
    assert any(volume.endswith(":/var/lib/rabbitmq") for volume in rabbitmq["volumes"])


DOCKER_PAGE = REPO_ROOT / "docs" / "user-guide" / "configuration" / "docker-setup.md"


def _bringing_choice(service: str) -> str:
    """The ``feature.option=value`` whose value brings ``service``."""
    (choice,) = [
        f"{feature_name}.{option_name}={value}"
        for feature_name, feature in CATALOG["features"].items()
        for option_name, option in feature.get("options", {}).items()
        for value, services in option.get("services", {}).items()
        if service in services
    ]
    return choice


@pytest.mark.parametrize("brought", _option_services())
def test_the_docker_page_names_the_choice_that_brings_each_service_and_shows_none_to_add(brought: str):
    """The generated file already runs it, so a block to paste in would run it twice or differently."""
    page = DOCKER_PAGE.read_text()
    entry = re.search(rf"^### `{brought}`.*?(?=^#)", page, re.M | re.S)
    service = _compose("local", services=(*TASKIQ_SERVICES, brought))["services"][brought]
    volumes = [volume.split(":")[0] for volume in service.get("volumes", [])]

    assert entry is not None
    assert f"`{_bringing_choice(brought)}`" in entry[0]
    assert f"`{service['image']}`" in entry[0]
    assert f"`{HOST_SETTINGS[brought]}={brought}`" in entry[0]
    assert all(f"`{volume}`" in entry[0] for volume in volumes)
    assert not re.search(rf"^```ya?ml\n(?:(?!^```).)*?^\s+{brought}:\s*$", page, re.M | re.S)


def test_the_docker_page_says_how_to_change_the_broker_user_once_it_exists():
    """The image creates the user only in an empty data volume, so a later change to ``backend/.env`` alone
    leaves the app logging in as a user the broker doesn't have."""
    entry = re.search(r"^### `rabbitmq`.*?(?=^#)", DOCKER_PAGE.read_text(), re.M | re.S)

    assert entry is not None
    assert "`rabbitmqctl`" in entry[0]
    assert "`docker compose down -v`" in entry[0]
