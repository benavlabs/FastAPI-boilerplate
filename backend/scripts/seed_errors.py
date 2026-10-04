"""The failure a seeder reports instead of a traceback."""


class SeedError(RuntimeError):
    """Raised when the environment can't produce the row a seeder is meant to seed."""
