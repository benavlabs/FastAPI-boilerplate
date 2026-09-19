"""The password policy every password-writing path enforces, built from settings."""

from crudauth import PasswordPolicy

from ..config.settings import settings

password_policy = PasswordPolicy(
    min_length=settings.PASSWORD_MIN_LENGTH,
    require_uppercase=settings.PASSWORD_REQUIRE_UPPERCASE,
    require_lowercase=settings.PASSWORD_REQUIRE_LOWERCASE,
    require_digit=settings.PASSWORD_REQUIRE_DIGIT,
    require_special=settings.PASSWORD_REQUIRE_SPECIAL,
)
