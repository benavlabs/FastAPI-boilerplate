"""What the fastro page states about fastro's commands and the compose files they write.

At the pin, `fastro make deploy` renders fastro's own legacy templates, not this repository's
`[generators.deploy]`, so the page's facts about what a mode writes are read from those.
"""

import importlib.util
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import click
import pytest
import typer.main
import yaml
from fastro import _legacy_deploy as deploy
from fastro.cli import app
from fastro.commands import env
from fastro.lib.render import Renderer

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = REPO_ROOT / "docs" / "user-guide" / "fastro.md"
PRODUCTION = REPO_ROOT / "docs" / "user-guide" / "production.md"
CATALOG = tomllib.loads((REPO_ROOT / "blueprint.toml").read_text())

FASTRO = typer.main.get_command(app)
MAKE_DEPLOY = "## Writing the compose files: `fastro make deploy`"


def _command(*words: str) -> click.Command:
    command: click.Command = FASTRO
    for word in words:
        assert isinstance(command, click.Group)
        command = command.commands[word]

    return command


def _section(heading: str) -> str:
    text = PAGE.read_text()
    assert heading in text, heading

    return " ".join(text.split(heading, 1)[1].split("\n## ", 1)[0].split())


def _rows() -> list[list[str]]:
    """The body rows of the tables under `fastro make deploy`, as their cells."""
    text = PAGE.read_text().split(MAKE_DEPLOY, 1)[1].split("\n## ", 1)[0]
    rows = [line for line in text.splitlines() if line.startswith("|") and not re.fullmatch(r"\|[-| ]+\|", line)]
    headers = ("| Mode |", "| Option |")

    return [[cell.strip() for cell in row.strip("|").split("|")] for row in rows if not row.startswith(headers)]


def _ticked(cell: str) -> list[str]:
    return re.findall(r"`([^`]+)`", cell)


def _mode_rows() -> dict[str, list[str]]:
    return {_ticked(row[0])[0]: row for row in _rows() if not row[0].startswith("`-")}


def _option_rows() -> list[list[str]]:
    return [row for row in _rows() if row[0].startswith("`-")]


def _plan(mode: str, root: Path, taskiq: bool = True, api_port: int = 8000, workers: int = 4, **params: Any) -> deploy.Plan:
    backend = root / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    if taskiq:
        (backend / deploy.TASKIQ_PACKAGE).mkdir(parents=True)
    project = SimpleNamespace(repo_root=root, backend_dir=backend)

    return deploy.plan(mode, cast(Any, project), root, api_port=api_port, workers=workers, **params)


def _rendered(plan: deploy.Plan) -> dict[str, str]:
    renderer = Renderer(deploy.TEMPLATES)

    return {render.target.name: renderer.render(render.template, plan.context) for render in plan.files}


def _services(mode: str, root: Path, taskiq: bool = True) -> dict[str, Any]:
    return dict(yaml.safe_load(_rendered(_plan(mode, root, taskiq))["docker-compose.yml"])["services"])


def test_the_page_names_the_modes_fastro_takes():
    mode = next(param for param in _command("make", "deploy").params if param.name == "mode")
    assert isinstance(mode.type, click.Choice)

    assert sorted(_mode_rows()) == sorted(mode.type.choices)


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_each_mode_writes_the_files_and_the_stack_its_row_names(mode: str, tmp_path: Path):
    row = _mode_rows()[mode]
    plan = _plan(mode, tmp_path)
    services = _services(mode, tmp_path / "rendered")
    stage = re.search(r"`(\w+)` stage", row[1])
    port = re.search(r"\bport (\d+)\b", row[1])
    published = services.get("nginx", {}).get("ports", [])

    assert sorted(str(render.target.relative_to(tmp_path)) for render in plan.files) == sorted(_ticked(row[2]))
    assert stage, row
    assert services["api"]["build"]["target"] == stage[1]
    assert ("`migrate`" in row[1]) == ("migrate" in services)
    assert ("Postgres" in row[1]) == ("postgres" in services)
    assert ("Redis" in row[1]) == ("redis" in services)
    assert (f"{port[1]}:{port[1]}" in published) if port else not published


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_a_project_with_taskiq_gets_a_worker_and_one_scheduler_in_every_mode(mode: str, tmp_path: Path):
    with_taskiq = _services(mode, tmp_path / "with")
    without = _services(mode, tmp_path / "without", taskiq=False)

    assert "taskiq feature also gets a `worker` and one `scheduler` in every mode" in _section(MAKE_DEPLOY)
    assert {"worker", "scheduler"} <= set(with_taskiq)
    assert with_taskiq["scheduler"].get("deploy", {}).get("replicas", 1) == 1
    assert not {"worker", "scheduler"} & set(without)


def test_the_options_and_their_defaults_are_the_ones_fastro_has():
    options = {param.opts[0]: param for param in _command("make", "deploy").params if isinstance(param, click.Option)}
    stated = {_ticked(row[0])[0]: row for row in _option_rows()}

    assert sorted(stated) == sorted(options)
    for flag, row in stated.items():
        option = options[flag]
        assert sorted(_ticked(row[0])) == sorted(option.opts), flag
        if option.is_flag:
            assert row[1] == "", flag
        elif option.default is None:
            assert (flag, row[1]) == ("--output-dir", "the repository root")
        else:
            assert row[1] == f"`{option.default}`", flag


def test_the_subnet_limits_are_the_catalogs_and_fastros():
    limits = CATALOG["generators"]["deploy"]["params"]["internal_subnet"]["max_prefix"]

    assert {4: limits["v4"], 6: limits["v6"]} == deploy.SMALLEST_TRUSTED_PREFIX
    assert f"`/{limits['v4']}` or smaller for IPv4, and `/{limits['v6']}` or smaller for IPv6" in _section(MAKE_DEPLOY)
    assert f"`/{limits['v4']}` (IPv4) or `/{limits['v6']}` (IPv6)" in PRODUCTION.read_text()


@pytest.mark.parametrize(
    ("subnet", "refused"),
    [
        ("172.31.240.1/24", True),
        ("*", True),
        ("10.0.0.0/7", True),
        ("fd00::/47", True),
        ("10.0.0.0/8", False),
        ("fd00::/48", False),
    ],
)
def test_the_subnet_refusals_the_pages_name(subnet: str, refused: bool):
    try:
        deploy.validated_subnet(subnet)
    except ValueError:
        assert refused, subnet
    else:
        assert not refused, subnet


def test_the_nginx_subnet_is_the_network_and_the_peers_uvicorn_trusts(tmp_path: Path):
    subnet = "10.89.0.0/24"
    compose = yaml.safe_load(_rendered(_plan("nginx", tmp_path, internal_subnet=subnet))["docker-compose.yml"])
    networks = [config["subnet"] for network in compose["networks"].values() for config in network["ipam"]["config"]]
    environment = compose["services"]["api"]["environment"]
    trusted = (
        environment["FORWARDED_ALLOW_IPS"]
        if isinstance(environment, dict)
        else dict(entry.split("=", 1) for entry in environment)["FORWARDED_ALLOW_IPS"]
    )
    section = _section(MAKE_DEPLOY)

    assert networks == [subnet]
    assert trusted == subnet
    assert "`FORWARDED_ALLOW_IPS`" in section and "compose network's subnet" in section


@pytest.mark.parametrize(("mode", "refused"), [("nginx", True), ("local", False), ("prod", False)])
def test_only_nginx_reads_the_subnet(mode: str, refused: bool):
    run = subprocess.run(
        [sys.executable, "-m", "fastro", "make", "deploy", mode, "--internal-subnet", "*", "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert (run.returncode != 0) is refused, run.stdout + run.stderr
    assert "`local` and `prod` always use the default network" in _section(MAKE_DEPLOY)


def test_the_secret_size_is_the_one_fastro_takes():
    size = next(param for param in _command("env", "secret").params if param.name == "bytes_")
    assert isinstance(size.type, click.IntRange)
    section = _section("## Preparing the environment: `fastro env`")

    assert f"from `{size.type.min}` to `{size.type.max}`, `{size.default}` by default" in section
    assert f"so {2 * size.default} hex characters" in section


def test_every_command_the_page_heads_a_section_with_is_one_fastro_has():
    headed = re.findall(r"^#+ .*?`fastro ([a-z ]+)`", PAGE.read_text(), re.M)

    assert headed
    for words in headed:
        _command(*words.split())


def _modes_named(cell: str) -> set[str]:
    named = re.search(r"for ((?:`\w+`(?: and )?)+)$", cell)

    return set(_ticked(named[1])) if named else {"local", "prod", "nginx"}


@pytest.mark.parametrize("mode", ["local", "prod", "nginx"])
def test_the_port_and_the_workers_reach_the_modes_their_rows_name(mode: str, tmp_path: Path):
    rows = {_ticked(row[0])[0]: row for row in _option_rows()}
    rendered = _rendered(_plan(mode, tmp_path, api_port=9123, workers=7))
    api = yaml.safe_load(rendered["docker-compose.yml"])["services"]["api"]
    environment = api.get("environment", {})

    if mode in _modes_named(rows["--api-port"][2]):
        assert api["ports"] == ["9123:8000"]
    else:
        assert "ports" not in api
        assert "9123" not in "".join(rendered.values())
    if mode in _modes_named(rows["--workers"][2]):
        assert environment["WORKERS"] == "7"
    else:
        assert "WORKERS" not in environment


def test_the_env_commands_run_the_scripts_the_page_names():
    section = _section("## Preparing the environment: `fastro env`")

    for module in (env.GEN_SECRET_MODULE, env.VALIDATE_MODULE):
        assert f"`{module}`" in section
        assert (REPO_ROOT / "backend" / f"{module.replace('.', '/')}.py").is_file()


@pytest.mark.parametrize(("found", "code"), [((["critical"], ["warning"]), 1), (([], ["warning"]), 0)])
def test_validate_exits_and_reports_the_way_the_page_says(
    found: tuple[list[str], list[str]], code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "backend"))
    spec = importlib.util.spec_from_file_location("validate_env", REPO_ROOT / "backend" / "scripts" / "validate_env.py")
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(script, "audit", lambda: found)

    exited = script.main()
    printed = capsys.readouterr().out
    section = _section("## Preparing the environment: `fastro env`")

    assert exited == code
    assert "exits 1 when anything is critical and 0 otherwise" in section
    assert "critical findings first" in section
    if found[0]:
        assert printed.index("Critical") < printed.index("Warnings")


BLUEPRINT_REPO = "## In the blueprint repository: `fastro sync` and `fastro blueprint`"


def test_the_wiring_the_page_names_is_where_sync_writes():
    named = re.search(r"`\[\[wiring\]\]` tables list, most of them under `([^`]+)`", _section(BLUEPRINT_REPO))
    assert named
    paths = [wiring["path"] for wiring in CATALOG["wiring"]]

    assert (REPO_ROOT / named[1]).is_dir()
    assert 2 * sum(path.startswith(named[1]) for path in paths) > len(paths)


def test_the_root_dev_group_installs_fastro():
    root = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    dev = [re.split(r"[\s<>=!~\[;@]", specifier, maxsplit=1)[0] for specifier in root["dependency-groups"]["dev"]]

    assert "fastro" in dev
    assert "The root dev group installs it" in _section("# Generating and updating projects with fastro")
