"""The error responses the documentation shows are the ones the app sends."""

import json
from pathlib import Path

from pydantic import ValidationError

from src.modules.common.constants import INVALID_REQUEST_MESSAGE
from src.modules.common.utils.error_handler import INVALID_REQUEST_SCHEMAS, where_and_why
from src.modules.user.schemas import UserCreate

REPO_ROOT = Path(__file__).resolve().parents[3]
EXCEPTIONS = REPO_ROOT / "docs" / "user-guide" / "api" / "exceptions.md"
CHANGELOG = REPO_ROOT / "docs" / "changelog.md"


def _properties(name: str) -> set[str]:
    return set(INVALID_REQUEST_SCHEMAS[name]["properties"])


def test_the_exceptions_page_shows_the_422_body_the_app_sends():
    section = EXCEPTIONS.read_text().split("### Validation error (422)", 1)[1]
    sent = json.loads(section.split("`", 2)[1])
    body = json.loads(section.split("```json\n", 1)[1].split("```", 1)[0])

    try:
        UserCreate.model_validate(sent)
    except ValidationError as refused:
        answered = [{**error, "loc": ["body", *error["loc"]]} for error in where_and_why(refused.errors())]
    else:
        answered = []

    assert set(body) == _properties("HTTPValidationError")
    assert body["detail"] == INVALID_REQUEST_MESSAGE
    assert body["errors"] == answered


def test_the_changelog_names_what_a_422_carries_and_leaves_out():
    unreleased = CHANGELOG.read_text().split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    entry = " ".join(unreleased.split("**A `422` says where and why each field failed.**", 1)[1].split("\n- **", 1)[0].split())

    assert all(f"`{name}`" in entry for name in _properties("HTTPValidationError") | _properties("ValidationError"))
    assert "`input`" in entry and "`ctx`" in entry
