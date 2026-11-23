"""The catalog's `[generators.deploy]` modes, against the template trees and what `fastro make deploy` offers."""

import subprocess
import sys
import tomllib

from tracked import REPO_ROOT, is_tracked_file, tracked_under

GENERATOR = tomllib.loads((REPO_ROOT / "blueprint.toml").read_text())["generators"]["deploy"]


def test_the_deploy_modes_are_the_template_trees_and_the_ones_fastro_offers():
    """A mode with no template tree would be offered and then fail; a tree with no mode is dead."""
    templates = REPO_ROOT / GENERATOR["templates"]
    offered = subprocess.run(
        [sys.executable, "-m", "fastro", "make", "deploy", "--help"], cwd=REPO_ROOT, capture_output=True, text=True
    )

    trees = {path.relative_to(templates).parts[0] for path in tracked_under(templates) if path.parent != templates}

    assert sorted(trees) == sorted(GENERATOR["modes"])
    assert f"Modes: {', '.join(GENERATOR['modes'])}" in offered.stdout


def test_the_nginx_config_sits_where_the_nginx_compose_file_mounts_it():
    """Files are written relative to the mode's tree, and the compose file mounts ./nginx/default.conf."""
    tree = REPO_ROOT / GENERATOR["templates"] / "nginx"
    compose = (tree / "docker-compose.yml.j2").read_text()

    assert is_tracked_file(tree / "nginx" / "default.conf.j2")
    assert "./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" in compose
