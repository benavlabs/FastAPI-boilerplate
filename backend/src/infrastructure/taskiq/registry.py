"""Simple task registry for development and monitoring."""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Simple registry to track registered tasks for development and monitoring."""

    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}
        self._stats: dict[str, int] = defaultdict(int)
        self._registered_at = datetime.now()

    def register_task(self, task_name: str, broker_name: str, task_func: Any) -> None:
        """Register a task with the registry.

        Args:
            task_name: Name of the task
            broker_name: Name of the broker the task is registered with
            task_func: The task function
        """
        self._tasks[task_name] = {
            "broker": broker_name,
            "function": task_func.__name__ if hasattr(task_func, "__name__") else str(task_func),
            "module": getattr(task_func, "__module__", None),
            "registered_at": datetime.now(),
        }
        self._stats["total_tasks"] += 1
        logger.debug(f"Registered task: {task_name} on broker: {broker_name}")

    def get_tasks(self) -> dict[str, dict[str, Any]]:
        """Get all registered tasks."""
        return self._tasks.copy()

    def get_task_names(self) -> list[str]:
        """Get list of all task names."""
        return list(self._tasks.keys())

    def get_tasks_by_broker(self, broker_name: str) -> list[str]:
        """Get tasks registered with a specific broker."""
        return [task_name for task_name, task_info in self._tasks.items() if task_info["broker"] == broker_name]

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_tasks": self._stats["total_tasks"],
            "registry_created_at": self._registered_at,
            "tasks_by_broker": {
                broker: len([t for t in self._tasks.values() if t["broker"] == broker])
                for broker in {t["broker"] for t in self._tasks.values()}
            },
        }


task_registry = TaskRegistry()


def register_task(task_name: str, broker_name: str, task_func: Any) -> None:
    """Register a task with the global registry."""
    task_registry.register_task(task_name, broker_name, task_func)
