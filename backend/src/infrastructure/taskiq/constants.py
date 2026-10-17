"""Fixed values the taskiq feature uses."""

BROKER_RETRY_SECONDS = 5.0
"""Seconds between the attempts that reconnect an unreachable broker."""

BROKER_RETRY_TASK_NAME = "taskiq-broker-retry"
"""The name carried by the task those attempts run in."""
