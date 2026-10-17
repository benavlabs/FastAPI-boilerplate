#!/usr/bin/env python3
"""Taskiq scheduler entry point.

Run from ``backend/`` with
``taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler``.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from .worker import default_broker

scheduler = TaskiqScheduler(broker=default_broker, sources=[LabelScheduleSource(default_broker)])

__all__ = ["scheduler"]
