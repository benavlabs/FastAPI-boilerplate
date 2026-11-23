"""Every CRUD object names its model and schemas, so mypy refuses a wrong one.

fastcrud's ``FastCRUD`` is generic over the model, the create, update, internal update, delete and
select schemas; left bare, every argument is ``Any``. Its filters are keyword arguments of any
name, so what mypy can catch is the schema handed to ``create`` or ``update`` and a field a schema
doesn't declare.
"""

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND.parent
SRC = BACKEND / "src"
HISTORY = REPO_ROOT / "docs" / "changelog.md"
FENCED_PYTHON = re.compile(r"^\s*```python\n(.*?)^\s*```", re.M | re.S)
PUBLIC_CREATE = re.compile(r"^\s*(\w+) = (\w+Create)\(", re.M)
CREATE_CALL = re.compile(r"\bcrud_\w+\.create\(")

WRONG_CALLS = """
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.tier.crud import crud_tiers
from src.modules.tier.schemas import TierCreateInternal
from src.modules.user.crud import crud_users
from src.modules.user.schemas import UserCreate, UserUpdate


async def wrong(db: AsyncSession, user: UserCreate) -> None:
    await crud_users.create(db=db, object=user)
    await crud_tiers.update(db=db, object=UserUpdate(name="Someone"), id=1)
    TierCreateInternal(name="free", not_a_field=1)
"""
"""The public create schema handed to `create`, another module's schema handed to `update`, and a
field the schema doesn't declare: each line is one mypy refuses."""

UNUPDATED = {"crud_key_usage"}
"""CRUD objects nothing updates, whose update type is `BaseModel` for want of a schema."""


def _tracked(directory: Path, suffix: str) -> list[Path]:
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    names = set(filter(None, listed.stdout.split("\0")))
    deleted = subprocess.run(["git", "ls-files", "-z", "--deleted"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    names -= set(deleted.stdout.split("\0"))

    return sorted(REPO_ROOT / name for name in names if (REPO_ROOT / name).is_relative_to(directory) and name.endswith(suffix))


def _bare(node: ast.AST | None) -> bool:
    return (isinstance(node, ast.Name) and node.id == "FastCRUD") or (
        isinstance(node, ast.Attribute) and node.attr == "FastCRUD"
    )


def _declarations(source: str) -> dict[str, list[ast.expr]]:
    """Each ``name = FastCRUD[...](...)`` in ``source``, by name, with the types it names."""
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            called = node.value.func
            if isinstance(called, ast.Subscript) and _bare(called.value) and isinstance(called.slice, ast.Tuple):
                found[ast.unparse(node.targets[0])] = called.slice.elts

    return found


def _schema_names(source: str) -> set[str]:
    return {
        alias.asname or alias.name
        for node in ast.parse(source).body
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "schemas"
        for alias in node.names
    }


def _bare_constructions(source: str) -> list[int]:
    """The lines that call ``FastCRUD(...)`` without naming its types first, or annotate a name with
    the bare class, which makes every argument ``Any`` again whatever the call names."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if (isinstance(node, ast.Call) and _bare(node.func)) or (isinstance(node, ast.AnnAssign) and _bare(node.annotation))
    ]


def test_mypy_refuses_the_wrong_schema_and_an_undeclared_field(tmp_path: Path):
    scratch = tmp_path / "wrong_calls.py"
    scratch.write_text(WRONG_CALLS)

    checked = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file", "pyproject.toml", "--no-incremental", str(scratch)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    errors = [line for line in checked.stdout.splitlines() if ": error:" in line]

    assert any(":11:" in line and '"create"' in line and "UserCreate" in line for line in errors), checked.stdout
    assert any(":12:" in line and '"update"' in line and "UserUpdate" in line for line in errors), checked.stdout
    assert any(":13:" in line and '"not_a_field"' in line for line in errors), checked.stdout


@pytest.mark.parametrize("path", _tracked(SRC, ".py"), ids=lambda path: path.relative_to(SRC).as_posix())
def test_every_crud_object_in_the_code_names_its_types(path: Path):
    assert _bare_constructions(path.read_text()) == []


def _subscripted(source: str) -> int:
    return sum(isinstance(node, ast.Subscript) and _bare(node.value) for node in ast.walk(ast.parse(source)))


@pytest.mark.parametrize("path", _tracked(SRC, "crud.py"), ids=lambda path: path.relative_to(SRC).as_posix())
def test_every_crud_object_is_a_plain_declaration(path: Path):
    """``name = FastCRUD[...](Model)``, the one form the rule below reads: an annotation, or types
    named on one line and called on another, would go unread."""
    source = path.read_text()

    assert _declarations(source)
    assert _subscripted(source) == len(_declarations(source))


@pytest.mark.parametrize("path", _tracked(SRC, "crud.py"), ids=lambda path: path.relative_to(SRC).as_posix())
def test_create_and_update_take_the_module_s_own_schemas(path: Path):
    """`Any` or `BaseModel` there would satisfy the subscript and check nothing."""
    source = path.read_text()
    schemas = _schema_names(source)
    defined = {node.name for node in ast.parse(path.with_name("schemas.py").read_text()).body if isinstance(node, ast.ClassDef)}

    for name, types in _declarations(source).items():
        create, update = types[1], types[2]
        assert isinstance(create, ast.Name) and create.id in schemas, (name, ast.unparse(create))
        assert f"{create.id}Internal" not in defined, f"{name} creates with the public {create.id}"
        if name not in UNUPDATED:
            named = {node.id for node in ast.walk(update) if isinstance(node, ast.Name)}
            assert named and named <= schemas, (name, ast.unparse(update))


def test_the_code_builds_crud_objects():
    """The rule above has something to read."""
    assert sum("FastCRUD[" in path.read_text() for path in _tracked(SRC, ".py")) >= 5


def test_every_crud_object_the_docs_show_names_its_types():
    """In code, a table or a comment alike. The changelog keeps its history."""
    found = [
        f"{page.relative_to(REPO_ROOT)}: {line.strip()}"
        for page in [*_tracked(REPO_ROOT / "docs", ".md"), REPO_ROOT / "README.md"]
        if page != HISTORY
        for line in page.read_text().splitlines()
        if re.search(r"\bFastCRUD\(|:\s*FastCRUD\s*=", line)
    ]

    assert found == []


def test_the_crud_page_names_the_setting_that_refuses_an_undeclared_field():
    settings = tomllib.loads((BACKEND / "pyproject.toml").read_text())

    assert settings["tool"]["pydantic-mypy"]["init_forbid_extra"] is True
    assert "`init_forbid_extra`" in (REPO_ROOT / "docs" / "user-guide" / "database" / "crud.md").read_text()


CRUD_BLOCK = re.compile(r"^```python\n# (?:backend/src/)?(modules/\w+/crud\.py)\n(.*?)^```", re.M | re.S)


def test_every_crud_file_the_docs_show_is_the_file_the_code_has():
    shown = [
        (page, match[1], match[2])
        for page in (REPO_ROOT / "docs" / "user-guide" / "database").glob("*.md")
        for match in CRUD_BLOCK.finditer(page.read_text())
    ]

    assert len(shown) >= 3
    for page, module, text in shown:
        assert text == (SRC / module).read_text(), (page.name, module)


def _create_arguments(block: str) -> list[str]:
    """The argument text of each ``crud_*.create(...)`` call in ``block``, to its own closing paren."""
    found = []
    for call in CREATE_CALL.finditer(block):
        depth, start = 1, call.end()
        for index in range(start, len(block)):
            depth += {"(": 1, ")": -1}.get(block[index], 0)
            if depth == 0:
                found.append(block[start:index])
                break

    return found


def test_no_example_hands_create_the_public_schema():
    """`create` takes the internal schema, which carries what the server sets; mypy refuses the
    public one, and so does pydantic when the internal fields are passed to it."""
    found = [
        f"{page.relative_to(REPO_ROOT)}: create({arguments})"
        for page in _tracked(REPO_ROOT / "docs", ".md")
        if page != HISTORY
        for block in FENCED_PYTHON.findall(page.read_text())
        for arguments in _create_arguments(block)
        if re.search(r"\bobject=\w+Create\(", arguments)
        or any(re.search(rf"\bobject={name}\b", arguments) for name, _ in PUBLIC_CREATE.findall(block))
    ]

    assert found == []
