"""Who the accounts feature lets into the docs outside development."""

from src.infrastructure.auth.dependencies import get_current_superuser
from src.wiring.app import DOCS_GUARD


def test_accounts_guards_the_docs_with_a_superuser_check():
    """The app factory hides the docs when nothing is contributed, so this is the contribution."""
    assert DOCS_GUARD is get_current_superuser
