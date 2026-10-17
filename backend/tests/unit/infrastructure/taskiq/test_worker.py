"""What the worker entry point registers, in a project of any shape."""

import ast
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4]

_WORKER_TASKS = """
import src.infrastructure.taskiq.worker as worker

registered = sorted(worker.default_broker.get_all_tasks())

from importlib import import_module

from src.wiring.tasks import TASK_MODULES

declared = set()
for name in TASK_MODULES:
    module = import_module(name)
    declared |= {task.task_name for task in vars(module).values() if hasattr(task, "task_name")}

print("DECLARED", sorted(declared))
print("REGISTERED", registered)
"""


def _cold_worker() -> tuple[list[str], list[str]]:
    """The tasks a ``taskiq worker`` process would find, and the ones the wiring names.

    The registry is read before anything else is imported, because importing a task module
    is what registers its tasks.
    """
    environment = {**os.environ, "PYTHONPATH": str(BACKEND)}

    result = subprocess.run([sys.executable, "-c", _WORKER_TASKS], cwd=BACKEND, env=environment, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    reported = {
        label: ast.literal_eval(names)
        for label, _, names in (line.partition(" ") for line in result.stdout.splitlines())
        if label in ("DECLARED", "REGISTERED")
    }
    return reported["DECLARED"], reported["REGISTERED"]


def test_the_worker_registers_every_task_the_wiring_names_and_no_others():
    """Whatever this project selected: a task the worker doesn't know drops its messages."""
    declared, registered = _cold_worker()

    assert registered == declared
