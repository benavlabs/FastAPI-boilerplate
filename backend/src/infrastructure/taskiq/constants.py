"""Fixed values the taskiq feature uses."""

BROKER_CONNECT_SECONDS = 5.0
"""Seconds an attempt to reach the broker may take before it counts as unreachable."""

BROKER_RETRY_SECONDS = 5.0
"""Seconds between the attempts that reconnect an unreachable broker."""

BROKER_RETRY_TASK_NAME = "taskiq-broker-retry"
"""The name carried by the task those attempts run in."""

RESULT_KEPT_SECONDS = 3600
"""Seconds a task's result stays in Redis before it expires."""

RETRY_MAX_DELAY_SECONDS = 600.0
"""The longest a delayed retry waits, however many attempts a task has already made."""

RETRY_SCHEDULE_PREFIX = "taskiq-retry"
"""What the Redis keys holding the retries waiting to be due are named after."""
