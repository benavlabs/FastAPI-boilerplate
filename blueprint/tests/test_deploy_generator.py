"""The catalog's `[generators.deploy]` modes, defaults and subnet limits, against the pinned
`fastro make deploy`'s options and its legacy deploy module."""

import tomllib
from pathlib import Path

import click
import typer.main
from fastro import _legacy_deploy as deploy
from fastro.cli import app

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = tomllib.loads((REPO_ROOT / "blueprint.toml").read_text())["generators"]["deploy"]

FASTRO = typer.main.get_command(app)


def _make_deploy() -> click.Command:
    group = FASTRO
    assert isinstance(group, click.Group)
    make = group.commands["make"]
    assert isinstance(make, click.Group)

    return make.commands["deploy"]


def _params() -> dict[str, click.Parameter]:
    return {str(param.name): param for param in _make_deploy().params}


def test_the_deploy_modes_are_the_ones_fastro_takes():
    """A mode with no template tree would be offered and then fail; a tree with no mode is dead."""
    templates = REPO_ROOT / GENERATOR["templates"]
    mode = _params()["mode"]
    assert isinstance(mode.type, click.Choice)

    assert sorted(child.name for child in templates.iterdir() if child.is_dir()) == sorted(mode.type.choices)


def test_the_port_and_the_workers_default_to_fastros():
    params = _params()

    assert GENERATOR["params"]["api_port"]["default"] == params["api_port"].default
    assert GENERATOR["params"]["workers"]["default"] == params["workers"].default


def test_the_subnet_default_and_limits_are_fastros():
    subnet = GENERATOR["params"]["internal_subnet"]
    limits = subnet["max_prefix"]

    assert subnet["default"] == deploy.DEFAULT_INTERNAL_SUBNET == _params()["internal_subnet"].default
    assert {4: limits["v4"], 6: limits["v6"]} == deploy.SMALLEST_TRUSTED_PREFIX
