"""Audit this environment the way production would.

Run it from ``backend/``:

    python -m scripts.validate_env

The settings are audited as a copy whose ``ENVIRONMENT`` reads ``production``, whatever the
configured one says, so a development or staging configuration is held to the gate that
stops a production boot, and a finding that names an environment names the one it was
checked for.

It exits 1 when anything critical is found, and 0 otherwise. Warnings are printed and
exit 0: they are worth reading, not worth refusing a boot over.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from src.infrastructure.config.settings import EnvironmentOption, get_settings  # noqa: E402
from src.infrastructure.security.production_validator import ProductionSecurityValidator  # noqa: E402


def audit() -> tuple[list[str], list[str]]:
    """The critical findings and the warnings, for these settings read as production."""
    as_production = get_settings().model_copy(update={"ENVIRONMENT": EnvironmentOption.PRODUCTION})

    return ProductionSecurityValidator(as_production).audit()


def report(critical: list[str], warnings: list[str]) -> None:
    """Print what the audit found, grouped, or say that it found nothing."""
    if not critical and not warnings:
        print("No issues found. Configuration would pass production validation.")

        return

    if critical:
        print(f"Critical ({len(critical)}):")
        for finding in critical:
            print(f"  • {finding}")

    if warnings:
        if critical:
            print()
        print(f"Warnings ({len(warnings)}):")
        for finding in warnings:
            print(f"  • {finding}")


def main() -> int:
    critical, warnings = audit()
    report(critical, warnings)

    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
