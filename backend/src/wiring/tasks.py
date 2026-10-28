"""The modules whose background tasks the worker registers.

Written by the generator in `tools/removal_drill.py`, which a test compares this file against:
imports and literals only. A task the worker reports as unknown drops its message, so a module
declaring one belongs in this list.
"""

TASK_MODULES: tuple[str, ...] = (
    "src.infrastructure.taskiq.email",
    "src.modules.api_keys.tasks",
)
