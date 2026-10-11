#!/usr/bin/env python3
"""Taskiq worker entry point, which registers the tasks the worker runs.

Run from ``backend/`` with
``taskiq worker src.infrastructure.taskiq.worker:default_broker``. That command discovers
no tasks of its own, so every module ``TASK_MODULES`` lists is imported here; a task the
worker doesn't know is reported as unknown and its message is dropped. The scheduler entry
point imports this module, so it sees the same tasks.
"""

from importlib import import_module

from ...wiring.tasks import TASK_MODULES
from .app import configure_broker_lifecycle
from .brokers import default_broker

for module in TASK_MODULES:
    import_module(module)

configure_broker_lifecycle(default_broker)

__all__ = ["default_broker"]
