#!/usr/bin/env python3
"""Taskiq worker entry point.

Run from ``backend/`` with
``taskiq worker src.infrastructure.taskiq.worker:default_broker``.
"""

from .app import configure_broker_lifecycle
from .brokers import default_broker

configure_broker_lifecycle(default_broker)

__all__ = ["default_broker"]
