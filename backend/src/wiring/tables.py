"""Modules outside ``src/modules`` that declare tables on ``Base.metadata``.

Written by the generator in `tools/removal_drill.py`, which a test compares this file against:
imports and literals only.
"""

TABLE_MODULES: tuple[str, ...] = ("src.infrastructure.auth.store",)
