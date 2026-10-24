"""The modules whose background tasks the worker registers.

Hand-maintained until the generator exists: imports and literals only. A task the worker
reports as unknown drops its message, so a module declaring one belongs in this list.
"""

TASK_MODULES: tuple[str, ...] = ("src.infrastructure.taskiq.email", "src.modules.api_keys.tasks")
