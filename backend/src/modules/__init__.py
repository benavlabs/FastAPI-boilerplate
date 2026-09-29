"""The feature modules.

This init imports nothing: the settings composition imports every feature's
``settings`` module, which runs the inits above it, and importing app code that
reads settings from here would close that circle. Models register themselves when
their module is imported -- Alembic walks the packages, and the app reaches them
through its routers.
"""
