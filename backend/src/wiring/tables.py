"""Modules outside ``src/modules`` that declare tables on ``Base.metadata``.

Hand-maintained until the generator exists: imports and literals only.
"""

TABLE_MODULES: tuple[str, ...] = ("src.infrastructure.auth.store",)
