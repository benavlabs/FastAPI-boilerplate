"""Constants for the user module."""

NAME_MAX_LENGTH = 30
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = r"^[a-z0-9_]+$"

# Each class a signup password must contain, named as its error message names it.
PASSWORD_CHARACTER_CLASSES = (
    ("lowercase letter", str.islower),
    ("uppercase letter", str.isupper),
    ("number", str.isdecimal),
    ("special character", lambda character: not character.isalnum()),
)
