"""Which dependencies this project lets hold traffic back."""

from src.wiring.hooks import CRITICAL_READINESS_CHECKS, INFORMATIONAL_READINESS_CHECKS

NEVER_CRITICAL = {"cache", "task_broker"}


def _names(checks) -> set[str]:
    return {check.name for check in checks}


def test_the_database_holds_traffic_back():
    assert "database" in _names(CRITICAL_READINESS_CHECKS)


def test_the_cache_and_the_broker_do_not():
    """No request the app serves waits on either."""
    assert _names(CRITICAL_READINESS_CHECKS) & NEVER_CRITICAL == set()
    assert _names(INFORMATIONAL_READINESS_CHECKS) <= NEVER_CRITICAL


def test_no_check_is_in_both_lists():
    assert _names(CRITICAL_READINESS_CHECKS) & _names(INFORMATIONAL_READINESS_CHECKS) == set()
