#!/usr/bin/env python3
"""Taskiq scheduler entry point.

Run from ``backend/`` with
``taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler``.
"""

from taskiq import TaskiqScheduler

from .retries import schedule_sources
from .worker import default_broker

scheduler = TaskiqScheduler(broker=default_broker, sources=schedule_sources(default_broker))

__all__ = ["scheduler"]
