"""Constants for the user module."""

NAME_MAX_LENGTH = 30
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = r"^[a-z0-9_]+$"

# Each class a signup password must contain: the label its error message names it
# by, the ``AuthSettings`` flag that requires it, and the Unicode-aware predicate.
# Kept in step with crudauth's ``PasswordPolicy`` classification.
PASSWORD_CHARACTER_CLASSES = (
    ("lowercase letter", "PASSWORD_REQUIRE_LOWERCASE", str.islower),
    ("uppercase letter", "PASSWORD_REQUIRE_UPPERCASE", str.isupper),
    ("number", "PASSWORD_REQUIRE_DIGIT", str.isdecimal),
    ("special character", "PASSWORD_REQUIRE_SPECIAL", lambda character: not character.isalnum()),
)

