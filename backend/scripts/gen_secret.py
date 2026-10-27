"""Print a secret key the project's own rules accept.

Run it from ``backend/``:

    python -m scripts.gen_secret [--bytes 32]

``SECRET_KEY`` signs the session cookies, the CSRF tokens and the admin panel's session,
and production refuses a key its rules read as something a person typed. A draw of random
bytes can land on such a key: about one hex key in twelve million runs through eight
consecutive digits. So this draws again while the rules refuse what it drew, and prints the
last draw either way, which keeps it from drawing for ever.

It reads no configuration and touches no database, so it works before there is a ``.env``
to put the key in. The rules are loaded from their own file rather than through
``src.infrastructure.security``, whose import configures logging and writes a line to
stdout: the key is meant to be piped, and a log line would be piped with it.
"""

import argparse
import importlib.util
import secrets
from pathlib import Path
from types import ModuleType

RULES_PATH = Path(__file__).parent.parent / "src" / "infrastructure" / "security" / "secret_key.py"
"""The project's own secret-key rules, the ones production refuses a key by."""


def _rules() -> ModuleType:
    """The rules module, loaded from its file so nothing around it is imported."""
    spec = importlib.util.spec_from_file_location("secret_key_rules", RULES_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"No secret-key rules at {RULES_PATH}.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


is_weak_secret_key = _rules().is_weak_secret_key

DRAWS = 8
"""How many keys are drawn at most; the last one is printed whatever the rules say."""

DEFAULT_BYTES = 32
SMALLEST_BYTES = 16
LARGEST_BYTES = 128


def generate(byte_count: int = DEFAULT_BYTES) -> str:
    """A hex key of ``byte_count`` random bytes, redrawn while the rules refuse it."""
    candidate = secrets.token_hex(byte_count)
    for _ in range(DRAWS - 1):
        if not is_weak_secret_key(candidate):
            break
        candidate = secrets.token_hex(byte_count)

    return candidate


def parse_byte_count(value: str) -> int:
    """``value`` as a byte count the key may be drawn from.

    Raises:
        argparse.ArgumentTypeError: it isn't a number, or sits outside the range.
    """
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number of bytes.") from error

    if not SMALLEST_BYTES <= count <= LARGEST_BYTES:
        raise argparse.ArgumentTypeError(f"{count} is outside {SMALLEST_BYTES} to {LARGEST_BYTES}.")

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a secret key suitable for SECRET_KEY.")
    parser.add_argument(
        "--bytes",
        dest="byte_count",
        type=parse_byte_count,
        default=DEFAULT_BYTES,
        help=f"Random bytes to draw, {SMALLEST_BYTES} to {LARGEST_BYTES}; the hex output is twice as long.",
    )

    print(generate(parser.parse_args().byte_count))


if __name__ == "__main__":
    main()
