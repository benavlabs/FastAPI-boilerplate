"""The infrastructure layer.

Kept import-free: the settings composition imports feature settings modules from
inside this package, so anything imported here would run while the settings object
is still being built. Import the submodule you need.
"""
