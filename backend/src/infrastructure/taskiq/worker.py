#!/usr/bin/env python3
"""Taskiq worker entry point."""

from .app import configure_broker_lifecycle
from .brokers import default_broker

configure_broker_lifecycle(default_broker)

__all__ = ["default_broker"]

if __name__ == "__main__":
    # Run with: python -m taskiq worker infrastructure.taskiq.worker:default_broker
    pass
