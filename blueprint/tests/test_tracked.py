"""Every scan reads the files git tracks, as fastro does, and nothing else.

Run in a tracked copy: untracked files that would trip a scan change nothing, nor does a tracked
file deleted and not yet staged, and a file taken out of the index but left on disk counts as gone
wherever it is declared or named.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from retired import OLD_COMMAND, OLD_PACKAGE
from tracked import git, is_tracked_dir, is_tracked_file, tracked_copy, tracked_names, tracked_under

STRAYS = {
    "docs/stray.md": f"# Stray\n\n[Nowhere](nowhere.md)\n\nRun `{OLD_COMMAND} deploy`.\n",
    "blueprint/overlay/stray.md.j2": "{{ nothing_the_tool_passes }}\n",
    "blueprint/templates/deploy/stray-mode/stray.j2": "stray\n",
    "backend/src/infrastructure/config/project.py": 'NAME = "stray"\n',
    f"docs/{OLD_PACKAGE}/index.md": "# Gone\n",
}
"""Untracked files, each of which a scan reading the disk trips over."""

DELETED = "CONTRIBUTING.md"
"""A tracked file deleted from the disk and not staged: git still lists it, and a copy of the
tracked files that took it would fail."""

STRAYED_OVER = [
    "blueprint/tests/test_docs_links.py",
    "blueprint/tests/test_overlay.py",
    "blueprint/tests/test_deploy_generator.py",
    "blueprint/tests/test_retired_cli.py",
    "blueprint/tests/test_project_name.py",
    "blueprint/tests/test_tracked.py::test_the_tracked_tree_holds_the_tracked_files",
]

UNTRACKED = [
    "CODE_OF_CONDUCT.md",
    ".github/",
    "backend/src/modules/tier/",
    "backend/src/interfaces/main.py",
    "backend/src/infrastructure/database/health.py",
    "backend/src/wiring/",
    "backend/scripts/validate_env.py",
    "blueprint/templates/deploy/",
    "blueprint/overlay/",
    "docs/user-guide/fastro.md",
]
"""Paths taken out of the index and left on disk."""

LINKED_INSTEAD = ("docs/user-guide/fastro.md", "../index.md")
"""An untracked path left as a link to a tracked page, which reaches no project whatever it points at.
It stands in for the page only once the checks that read the page have run."""

LINKED_OVER = "blueprint/tests/test_docs_links.py"
"""The file whose checks run only once the link is in place."""

REFUSED = {
    "backend/tests/unit/test_blueprint_catalog.py": [
        "test_every_blueprint_only_path_is_one_this_repo_has[CODE_OF_CONDUCT.md]",
        "test_every_blueprint_only_path_is_written_the_way_the_spec_reads_them[.github/]",
        "test_every_blueprint_only_path_is_one_this_repo_has[.github/]",
        "test_every_feature_path_is_one_this_repo_has[backend/src/modules/tier]",
        "test_a_directory_is_spelled_as_a_subtree_and_a_file_is_not[tiers]",
        "test_the_app_the_verification_imports_is_this_project_s_own",
        "test_every_core_contribution_names_something_that_exists[src.infrastructure.database.health:schema_readiness]",
        "test_every_wiring_file_is_under_the_python_root_and_is_a_file[backend/src/wiring/app.py]",
        "test_every_command_runs_a_module_this_repo_can_run[env validate]",
        "test_every_generators_templates_are_a_directory_this_repo_has[deploy]",
    ],
    "blueprint/tests/test_fastro_page.py": [
        "test_the_env_commands_run_the_scripts_the_page_names",
        "test_the_wiring_the_page_names_is_where_sync_writes",
    ],
    "blueprint/tests/test_deploy_generator.py": [
        "test_the_deploy_modes_are_the_template_trees_and_the_ones_fastro_offers",
        "test_the_nginx_config_sits_where_the_nginx_compose_file_mounts_it",
    ],
    "blueprint/tests/test_overlay.py": ["test_the_overlay_is_where_the_catalog_says"],
    "blueprint/tests/test_docs_links.py": [
        "test_every_redirect_leaves_a_page_that_is_gone_for_one_that_is_there",
        "test_every_page_is_in_the_nav_and_every_nav_entry_is_a_page",
        "test_every_relative_link_lands_on_a_file_and_a_heading[getting-started/index.md:",
    ],
}
"""The checks each untracked path has to fail, by the file that holds them."""


def _pytest(copy: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("PYTEST")}

    return subprocess.run(
        [sys.executable, "-m", "pytest", *arguments, "-q", "-rf", "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=copy,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_untracked_files_change_no_scan_and_untracked_paths_are_gone(tmp_path: Path):
    copy = tracked_copy(tmp_path / "blueprint")
    for name, text in STRAYS.items():
        (copy / name).parent.mkdir(parents=True, exist_ok=True)
        (copy / name).write_text(text)

    (copy / DELETED).unlink()

    assert not git("ls-files", *STRAYS, cwd=copy)
    assert git("ls-files", "--deleted", cwd=copy).split() == [DELETED]

    strayed = _pytest(copy, *STRAYED_OVER)

    assert strayed.returncode == 0, strayed.stdout[-4000:]

    for name in STRAYS:
        (copy / name).unlink()
    git("checkout", "--", DELETED, cwd=copy)

    for path in UNTRACKED:
        git("rm", "-r", "-q", "--cached", path, cwd=copy)
    _assert_refused(copy, {file: checks for file, checks in REFUSED.items() if file != LINKED_OVER})

    link, target = LINKED_INSTEAD
    (copy / link).unlink()
    (copy / link).symlink_to(target)
    _assert_refused(copy, {LINKED_OVER: REFUSED[LINKED_OVER]})


def _assert_refused(copy: Path, refusing: dict[str, list[str]]) -> None:
    names = sorted({check.split("[")[0] for checks in refusing.values() for check in checks})
    refused = _pytest(copy, *refusing, "-k", " or ".join(names))
    failed = re.findall(r"^FAILED (\S+::\S+(?: \S+)?)", refused.stdout, re.M)

    for file, checks in refusing.items():
        for check in checks:
            assert any(found.startswith(f"{file}::{check}") for found in failed), (check, refused.stdout[-4000:])


def test_an_untracked_link_to_a_tracked_file_is_not_tracked(tmp_path: Path):
    """git tracks a link as the link, so one nobody added reaches no project, whatever it points at."""
    copy = tracked_copy(tmp_path / "blueprint")
    (copy / "docs" / "alias.md").symlink_to("index.md")
    (copy / "docs" / "user").symlink_to("user-guide")

    assert is_tracked_file(copy / "docs" / "index.md", root=copy)
    assert not is_tracked_file(copy / "docs" / "alias.md", root=copy)
    assert not is_tracked_dir(copy / "docs" / "user", root=copy)
    assert not tracked_under(copy / "docs" / "user", root=copy)


def test_a_path_outside_the_repository_is_not_tracked(tmp_path: Path):
    copy = tracked_copy(tmp_path / "blueprint")

    assert not is_tracked_file(copy / ".." / "blueprint" / ".." / "elsewhere.md", root=copy)
    assert not is_tracked_dir(tmp_path, root=copy)
    assert not tracked_under(tmp_path, root=copy)


def test_the_tracked_tree_holds_the_tracked_files(tracked_tree: Path):
    assert {path.relative_to(tracked_tree).as_posix() for path in tracked_tree.rglob("*") if path.is_file()} == tracked_names()


def test_the_root_is_a_directory_holding_every_tracked_file(tmp_path: Path):
    copy = tracked_copy(tmp_path / "blueprint")

    assert is_tracked_dir(copy, root=copy)
    assert {path.relative_to(copy).as_posix() for path in tracked_under(copy, root=copy)} == tracked_names(copy)
