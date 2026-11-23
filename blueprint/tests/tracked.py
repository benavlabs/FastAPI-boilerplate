"""The files git tracks and still has, which is all fastro reads a blueprint from (`git ls-files`
less `--deleted`). A scan that reads anything else lets an untracked venv, build or cache change
its result."""

import fnmatch
import functools
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def git(*arguments: str, cwd: Path) -> str:
    settings = ["user.name=test", "user.email=test@example.com", "commit.gpgsign=false", "core.hooksPath=/dev/null"]
    command = ["git", *(part for setting in settings for part in ("-c", setting)), *arguments]

    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True).stdout


@functools.cache
def tracked_names(root: Path = REPO_ROOT) -> frozenset[str]:
    """Every tracked file under ``root`` that is still there, by its path from ``root``."""
    listed = set(filter(None, git("ls-files", "-z", cwd=root).split("\0")))

    return frozenset(listed - set(git("ls-files", "-z", "--deleted", cwd=root).split("\0")))


def _from_root(path: Path, root: Path) -> str | None:
    """``path`` from ``root``, with ``.`` and ``..`` folded but no symlink followed, since git
    tracks a link as the link: ``None`` when it lies outside ``root``."""
    normal = Path(os.path.normpath(os.path.abspath(path)))

    return normal.relative_to(root).as_posix() if normal.is_relative_to(root) else None


def is_tracked_file(path: Path, root: Path = REPO_ROOT) -> bool:
    return _from_root(path, root) in tracked_names(root)


def _prefix(directory: Path, root: Path) -> str | None:
    """What the path of every tracked file below ``directory`` starts with: nothing for ``root``."""
    relative = _from_root(directory, root)

    return None if relative is None else "" if relative == "." else f"{relative}/"


def is_tracked_dir(path: Path, root: Path = REPO_ROOT) -> bool:
    """Whether ``path`` holds a tracked file, which is what git, and fastro, call a directory."""
    prefix = _prefix(path, root)

    return prefix is not None and any(name.startswith(prefix) for name in tracked_names(root))


def tracked_under(directory: Path, pattern: str = "*", root: Path = REPO_ROOT) -> list[Path]:
    """The tracked files below ``directory``, at any depth, whose names match ``pattern``."""
    prefix = _prefix(directory, root)

    return sorted(
        root / name
        for name in tracked_names(root)
        if prefix is not None and name.startswith(prefix) and fnmatch.fnmatch(name.rsplit("/", 1)[-1], pattern)
    )


def tracked_copy(destination: Path, root: Path = REPO_ROOT) -> Path:
    """A git repository holding the files git tracks under ``root`` and nothing else."""
    for name in tracked_names(root):
        (destination / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, destination / name)
    git("init", "-q", cwd=destination)
    git("add", "-A", cwd=destination)
    git("commit", "-q", "-m", "tracked", cwd=destination)

    return destination
