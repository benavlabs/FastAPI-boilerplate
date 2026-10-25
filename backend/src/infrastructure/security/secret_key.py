"""Whether a secret key reads as random, or as something a person typed."""

import math
import re
from collections import Counter

MINIMUM_SECRET_KEY_LENGTH = 32
MINIMUM_SECRET_KEY_ENTROPY_BITS = 64
LONGEST_REPEATED_BLOCK = 16
LONGEST_ORDERED_RUN = 7
DOMINANT_FRAGMENT_SHARE = 0.4
DOMINANT_WORD_SHARE = 0.25
REPEATED_BLOCK_SHARE = 0.6
KEYBOARD_RUN_SHARE = 0.6
SHORTEST_KEYBOARD_RUN = 4
WORD_COVERAGE_SHARE = 0.6
SHORTEST_COVERING_WORD = 3

KEYBOARD_ROWS = (
    "`1234567890-=",
    " qwertyuiop[]\\",
    " asdfghjkl;'",
    "  zxcvbnm,./",
)

PLACEHOLDER_FRAGMENTS = (
    "insecure",
    "change-me",
    "change-this",
    "changeme",
    "changethis",
    "default",
    "secret",
    "password",
    "qwerty",
    "example",
    "placeholder",
    "test",
    "development",
)

WEAK_WORDS = frozenset(
    (
        *PLACEHOLDER_FRAGMENTS,
        "abc123",
        "admin",
        "api",
        "app",
        "change",
        "demo",
        "dev",
        "jwt",
        "key",
        "local",
        "prod",
        "production",
        "sample",
        "session",
        "signing",
        "staging",
        "token",
        "123456",
    )
)


COMMON_WORDS = frozenset(
    (
        # infrastructure, environment and project words
        "access",
        "account",
        "admin",
        "api",
        "app",
        "application",
        "auth",
        "backend",
        "base",
        "client",
        "cloud",
        "cluster",
        "company",
        "config",
        "core",
        "data",
        "database",
        "deploy",
        "dev",
        "development",
        "docker",
        "env",
        "environment",
        "fastapi",
        "front",
        "frontend",
        "gateway",
        "internal",
        "jwt",
        "key",
        "live",
        "local",
        "login",
        "main",
        "master",
        "node",
        "pass",
        "password",
        "prod",
        "production",
        "project",
        "python",
        "redis",
        "release",
        "root",
        "secret",
        "secure",
        "server",
        "service",
        "session",
        "signing",
        "site",
        "staging",
        "super",
        "system",
        "test",
        "testing",
        "token",
        "user",
        "value",
        "web",
        # the words a passphrase of this kind leans on
        "all",
        "and",
        "any",
        "are",
        "for",
        "from",
        "have",
        "here",
        "how",
        "mine",
        "more",
        "most",
        "much",
        "new",
        "not",
        "now",
        "old",
        "one",
        "only",
        "our",
        "out",
        "own",
        "please",
        "really",
        "see",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "very",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        # passwords people reach for
        "angel",
        "baseball",
        "dragon",
        "football",
        "hello",
        "hunter",
        "iloveyou",
        "letmein",
        "monkey",
        "ninja",
        "princess",
        "shadow",
        "soccer",
        "sunshine",
        "trustno",
        "welcome",
        "whatever",
        # months and seasons
        "april",
        "august",
        "autumn",
        "december",
        "february",
        "january",
        "july",
        "june",
        "march",
        "november",
        "october",
        "september",
        "spring",
        "summer",
        "winter",
    )
)

_KEYBOARD_NEIGHBOURS: dict[str, set[str]] = {}


def _keyboard_neighbours() -> dict[str, set[str]]:
    """Which keys sit next to which, from the rows of a QWERTY keyboard."""
    if _KEYBOARD_NEIGHBOURS:
        return _KEYBOARD_NEIGHBOURS

    for row, keys in enumerate(KEYBOARD_ROWS):
        for column, key in enumerate(keys):
            if key == " ":
                continue

            around = set()
            for other_row in range(max(row - 1, 0), min(row + 2, len(KEYBOARD_ROWS))):
                for other_column in range(max(column - 1, 0), column + 2):
                    neighbour = KEYBOARD_ROWS[other_row][other_column : other_column + 1]
                    if neighbour not in ("", " ", key):
                        around.add(neighbour)

            _KEYBOARD_NEIGHBOURS[key] = around

    return _KEYBOARD_NEIGHBOURS


def _keyboard_run_share(value: str) -> float:
    """How much of the value is written by walking from one key to a neighbouring one."""
    neighbours = _keyboard_neighbours()
    lowered = value.lower()
    covered = run = 1

    runs = []
    for previous, current in zip(lowered, lowered[1:], strict=False):
        if current in neighbours.get(previous, ()):
            run += 1
        else:
            runs.append(run)
            run = 1
    runs.append(run)

    covered = sum(length for length in runs if length >= SHORTEST_KEYBOARD_RUN)

    return covered / len(value)


def _repeated_block_share(value: str) -> float:
    """How much of the value one short block, written out again, covers."""
    largest = 0.0

    for size in range(1, min(LONGEST_REPEATED_BLOCK, len(value) // 2) + 1):
        block = value[:size]
        repeats = 1
        while value.startswith(block * (repeats + 1)):
            repeats += 1

        if repeats > 1:
            largest = max(largest, repeats * size / len(value))

    return largest


def _word_coverage_share(value: str) -> float:
    """How much of the value is spelled out of words a person would recognise."""
    lowered = re.sub(r"[^a-z]+", "", value.lower())
    if not lowered:
        return 0.0

    covered = [0] * (len(lowered) + 1)
    for end in range(1, len(lowered) + 1):
        covered[end] = covered[end - 1]
        for start in range(max(end - 12, 0), end - SHORTEST_COVERING_WORD + 1):
            if lowered[start:end] in COMMON_WORDS:
                covered[end] = max(covered[end], covered[start] + (end - start))

    return covered[-1] / len(value)


def _entropy_bits(value: str) -> float:
    """The value's Shannon entropy in bits, from the symbols it actually uses."""
    counts = Counter(value)
    share = [count / len(value) for count in counts.values()]

    return -sum(part * math.log2(part) for part in share) * len(value)


def _repeats_a_short_block(value: str) -> bool:
    """Whether the value is one block of at most 16 characters, written out again."""
    for size in range(1, min(LONGEST_REPEATED_BLOCK, len(value) // 2) + 1):
        if len(value) % size == 0 and value == value[:size] * (len(value) // size):
            return True

    return False


def _longest_ordered_run(value: str) -> int:
    """The longest run of characters whose code points step by one, up or down."""
    longest = run = 1
    for step in (1, -1):
        run = 1
        for previous, current in zip(value, value[1:], strict=False):
            run = run + 1 if ord(current) - ord(previous) == step else 1
            longest = max(longest, run)

    return longest


def _words(value: str) -> list[str]:
    """The alphanumeric words a value is written from."""
    return [word for word in re.split(r"[^a-z0-9]+", value.lower()) if word]


def _weak_word_share(value: str) -> float:
    """How much of the value is spelled out of words that say it was typed by hand."""
    words = _words(value)
    if not words:
        return 0.0

    written = sum(len(word) for word in words)

    return sum(len(word) for word in words if word in WEAK_WORDS) / written


def is_weak_secret_key(secret: str) -> bool:
    """Whether a secret key is empty, too short, or reads as something other than random.

    A key is refused when it is empty, shorter than 32 characters, spells out a
    placeholder or hand-written words over a large part of its length, repeats one
    short block over most of its length, runs through eight consecutive code points,
    walks from key to neighbouring key over most of its length, reads as common words
    over most of its length, or carries less than 64 bits of entropy across the
    symbols it uses.

    Each rule is measured against a share of the whole value, so a generated key
    that happens to contain "test" or "1234" still passes.
    """
    if not secret:
        return True

    if len(secret) < MINIMUM_SECRET_KEY_LENGTH:
        return True

    if _dominant_fragment_share(secret) >= DOMINANT_FRAGMENT_SHARE:
        return True

    if _weak_word_share(secret) >= DOMINANT_WORD_SHARE:
        return True

    if _repeats_a_short_block(secret) or _repeated_block_share(secret) >= REPEATED_BLOCK_SHARE:
        return True

    if _longest_ordered_run(secret) > LONGEST_ORDERED_RUN:
        return True

    if _keyboard_run_share(secret) >= KEYBOARD_RUN_SHARE:
        return True

    if _word_coverage_share(secret) >= WORD_COVERAGE_SHARE:
        return True

    return _entropy_bits(secret) < MINIMUM_SECRET_KEY_ENTROPY_BITS


def _dominant_fragment_share(value: str) -> float:
    """How much of the value the largest placeholder fragment covers."""
    lowered = value.lower()

    return max(
        (lowered.count(fragment) * len(fragment) / len(lowered) for fragment in PLACEHOLDER_FRAGMENTS),
        default=0.0,
    )
