"""What the image carries, for the commands the documentation runs inside a container.

Nothing in CI builds the image, so this reads the Dockerfile. A script the documentation
runs as ``docker compose exec api python -m scripts.<name>`` has to be in there: without
it the command answers ``No module named 'scripts'``.

The module form is also the only one that works in there. The container's working
directory is ``/app/src`` while the scripts are at ``/app/scripts``, so
``python scripts/<name>.py`` answers ``can't open file '/app/src/scripts/<name>.py'``.
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
DOCS_ROOT = REPO_ROOT / "docs"
SCRIPTS = REPO_ROOT / "backend" / "scripts"

BASE_STAGE = re.compile(r"^FROM .*? AS base$(.*?)^FROM ", re.DOTALL | re.MULTILINE)
RUN_IN_A_CONTAINER = re.compile(r"docker compose (?:exec|run)[^\n`]*python -m (scripts\.\w+)")
A_PATH_IN_A_CONTAINER = re.compile(r"docker compose (?:exec|run)[^\n`]*python +(scripts/[\w.]+)")


def _base_stage() -> str:
    """The stage every other one builds on, so what it copies is in all of them."""
    found = BASE_STAGE.search(DOCKERFILE.read_text())
    assert found is not None, "no base stage in the Dockerfile"

    return found.group(1)


def test_the_image_carries_the_scripts_and_the_migrations():
    stage = _base_stage()

    assert "COPY backend/scripts ./scripts" in stage
    assert "COPY backend/migrations ./migrations" in stage
    assert "COPY backend/alembic.ini ." in stage


def test_alembic_finds_its_configuration_from_the_working_directory_the_stages_use():
    """``docker compose exec api alembic upgrade head`` runs from ``/app/src``, where there is none."""
    stage = _base_stage()

    assert "ENV ALEMBIC_CONFIG=/app/alembic.ini" in stage


def test_every_script_the_docs_run_in_a_container_exists():
    """The module name in the documented command has to name a file the image copies."""
    documented = {module for page in DOCS_ROOT.rglob("*.md") for module in RUN_IN_A_CONTAINER.findall(page.read_text())}

    assert documented, "no documented in-container script run found"
    assert [module for module in sorted(documented) if not (SCRIPTS / f"{module.split('.')[1]}.py").exists()] == []


def test_no_documented_container_command_runs_a_script_by_path():
    """``/app/src`` is the working directory in there, and the scripts are at ``/app/scripts``."""
    by_path = {
        f"{page.relative_to(DOCS_ROOT)}: {match}"
        for page in DOCS_ROOT.rglob("*.md")
        for match in A_PATH_IN_A_CONTAINER.findall(page.read_text())
    }

    assert sorted(by_path) == []


DOCKERIGNORE = REPO_ROOT / ".dockerignore"

SECRET_FILES = [".env", ".env.production", ".env.local", "backend/.env", "backend/.env.production", "backend/.env.staging"]
"""Files a reader writes secrets into, at the root and next to ``backend/.env.example``."""


def _pattern(pattern: str) -> re.Pattern[str]:
    """A ``.dockerignore`` pattern as Docker matches it: ``**`` any number of directories, ``*`` and
    ``?`` within one path segment."""
    expression = ""
    position = 0
    while position < len(pattern):
        if pattern.startswith("**/", position):
            expression += "(?:.*/)?"
            position += 3
        elif pattern.startswith("**", position):
            expression += ".*"
            position += 2
        elif pattern[position] == "*":
            expression += "[^/]*"
            position += 1
        elif pattern[position] == "?":
            expression += "[^/]"
            position += 1
        else:
            expression += re.escape(pattern[position])
            position += 1

    return re.compile(expression)


def _sent_to_docker(path: str, dockerignore: str) -> bool:
    """Whether ``docker build .`` sends ``path`` in its context: the last pattern that matches the path,
    or a directory above it, decides, and a ``!`` pattern lets it back in."""
    parts = path.split("/")
    candidates = ["/".join(parts[: end + 1]) for end in range(len(parts))]
    sent = True
    for line in dockerignore.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        keep = line.startswith("!")
        pattern = _pattern(line.removeprefix("!").strip().strip("/"))
        if any(pattern.fullmatch(candidate) for candidate in candidates):
            sent = keep

    return sent


def test_the_dockerignore_reader_matches_as_docker_does():
    rules = "docs/\n**/.env\n**/*.pyc\n!keep.pyc\n"

    assert not _sent_to_docker("docs/index.md", rules)
    assert not _sent_to_docker(".env", rules)
    assert not _sent_to_docker("backend/.env", rules)
    assert not _sent_to_docker("a/b/c.pyc", rules)
    assert _sent_to_docker("keep.pyc", rules)
    assert _sent_to_docker("backend/.env.example", rules)
    assert not _sent_to_docker("b.pyc", "*.pyc\n")
    assert _sent_to_docker("a/b.pyc", "*.pyc\n")
    assert not _sent_to_docker("a.pyc", "?.pyc\n")
    assert _sent_to_docker("a/b", "a?b\n")


def test_the_build_context_holds_no_secret_file():
    """``docker build .`` sends the context to the daemon whatever the Dockerfile copies, so a secret
    file there leaves the machine and lands in any image a later ``COPY . .`` makes."""
    rules = DOCKERIGNORE.read_text()
    on_disk = [
        path.relative_to(REPO_ROOT).as_posix()
        for pattern in (".env", ".env.*")
        for path in REPO_ROOT.rglob(pattern)
        if path.is_file() and not path.relative_to(REPO_ROOT).parts[0].startswith(".venv")
    ]
    secrets = [path for path in {*SECRET_FILES, *on_disk} if Path(path).name != ".env.example"]

    assert [path for path in sorted(secrets) if _sent_to_docker(path, rules)] == []


def test_the_build_context_keeps_the_example_and_what_the_dockerfile_copies():
    """Every tracked file under what the Dockerfile copies, the migration template and the tests'
    data among them, or the image is missing it."""
    rules = DOCKERIGNORE.read_text()
    copied = re.findall(r"^COPY (?!--from)(.+?) \S+$", DOCKERFILE.read_text(), re.M)
    sources = [source for line in copied for source in line.split()]
    files = subprocess.run(["git", "ls-files", "--", *sources], cwd=REPO_ROOT, capture_output=True, text=True, check=True)

    assert {"backend/src", "backend/alembic.ini"} <= set(sources)
    assert _sent_to_docker("backend/.env.example", rules)
    assert "backend/migrations/script.py.mako" in files.stdout.split()
    assert [path for path in files.stdout.split() if not _sent_to_docker(path, rules)] == []
