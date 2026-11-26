"""Every project import in a documentation code block names something that exists.

A sample that can't be pasted into a project is worse than no sample: the reader
finds out at the import line.

The sweep checks that the module and the name exist, not that a relative import
counts the right number of dots: a sample rarely says which file it belongs to.
A relative import of a single name, ``.schemas``, is left alone -- which of them it
means depends on the file it sits in.

``ILLUSTRATIVE_MODULES`` lists the modules the guides invent to show how a project of
your own would look.
"""

import ast
import importlib
import re
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "docs"
SRC_ROOT = REPO_ROOT / "backend" / "src"

PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)

ILLUSTRATIVE_MODULES = (
    "src.modules.widgets",
    "src.modules.reports",
    "src.modules.user.routes_v2",
    "src.interfaces.api.v2",
)


def _import_statements(block: str) -> Iterator[tuple[ast.ImportFrom, int]]:
    """Every ``from ... import ...`` in a code block, with the line it starts on."""
    lines = block.splitlines()
    index = 0
    while index < len(lines):
        statement = lines[index].strip()
        started_on = index
        if statement.startswith("from ") and " import " in statement:
            while statement.count("(") > statement.count(")") and index + 1 < len(lines):
                index += 1
                statement += " " + lines[index].strip()
            try:
                parsed = ast.parse(statement)
            except SyntaxError:
                index += 1
                continue
            for node in parsed.body:
                if isinstance(node, ast.ImportFrom):
                    yield node, started_on
        index += 1


def _unique(paths: list[Path]) -> Path | None:
    return paths[0] if len(paths) == 1 else None


def _module_path(node: ast.ImportFrom) -> Path | None:
    """The file a documented import points at, or ``None`` when no project module could.

    An absolute import names its module from ``src``. A relative one names a suffix of
    at least two parts, resolved when exactly one module, or one package that would
    hold it, matches.
    """
    parts = (node.module or "").split(".")
    if node.level == 0:
        if parts[0] != "src":
            return None
        parts = parts[1:]
    elif len(parts) < 2:
        return None

    if not parts:
        return None

    if node.level == 0:
        candidate = SRC_ROOT.joinpath(*parts)
        for existing in (candidate.with_suffix(".py"), candidate / "__init__.py"):
            if existing.exists():
                return existing

        return candidate.with_suffix(".py")

    suffix = "/".join(parts)
    modules = [path for path in SRC_ROOT.rglob(f"{parts[-1]}.py") if str(path).endswith(f"{suffix}.py")]
    modules += [path for path in SRC_ROOT.rglob(f"{parts[-1]}/__init__.py") if str(path).endswith(f"{suffix}/__init__.py")]
    if modules:
        return _unique(modules)

    holding = "/".join(parts[:-1])
    holders = [path for path in SRC_ROOT.rglob(parts[-2]) if path.is_dir() and str(path).endswith(holding)]
    holder = _unique(holders)

    return holder / f"{parts[-1]}.py" if holder else None


def _dotted(path: Path) -> str:
    return "src." + str(path.relative_to(SRC_ROOT).with_suffix("")).replace("/__init__", "").replace("/", ".")


def _documented_imports() -> Iterator[tuple[str, ast.ImportFrom, Path]]:
    """Every project import in a ``python`` block, with where it was written."""
    for document in sorted(DOCS_ROOT.rglob("*.md")):
        text = document.read_text()
        for block in PYTHON_BLOCK.finditer(text):
            first_line = text[: block.start(1)].count("\n") + 1
            for node, offset in _import_statements(block.group(1)):
                path = _module_path(node)
                if path is not None:
                    yield f"{document.relative_to(REPO_ROOT)}:{first_line + offset}", node, path


def _missing(where: str, node: ast.ImportFrom, path: Path) -> list[str]:
    dotted = _dotted(path)
    if dotted.startswith(ILLUSTRATIVE_MODULES):
        return []

    if not path.exists():
        return [f"{where}: no module {dotted}"]

    module = importlib.import_module(dotted)
    missing = []
    for alias in node.names:
        if hasattr(module, alias.name):
            continue
        try:
            importlib.import_module(f"{dotted}.{alias.name}")
        except ImportError:
            missing.append(f"{where}: {dotted} has no {alias.name}")

    return missing


def test_every_documented_project_import_resolves():
    broken = [entry for where, node, path in _documented_imports() for entry in _missing(where, node, path)]

    assert broken == []


def test_the_sweep_reads_the_samples_it_claims_to():
    """An extractor that quietly stopped matching would make the sweep above vacuous."""
    blocks = [block.group(1) for document in DOCS_ROOT.rglob("*.md") for block in PYTHON_BLOCK.finditer(document.read_text())]
    statements = [node for block in blocks for node, _ in _import_statements(block)]

    assert len(blocks) > 200
    assert len(statements) > 200
