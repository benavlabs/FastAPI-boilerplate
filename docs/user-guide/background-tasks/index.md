# Background Tasks

The boilerplate runs background work with [Taskiq](https://taskiq-python.github.io/) — an async-native task queue with a Celery-like API and pluggable brokers. By default it runs against Redis, with RabbitMQ available as an alternative.

!!! tip "Building a full SaaS?"
    Background tasks are part of the free foundation. **[FastroAI](https://fastro.ai)** bundles them with Stripe payments, entitlements, transactional email, a frontend, and AI agents - all wired together and production-ready. [Ship your SaaS faster →](https://fastro.ai)

This page covers the actual setup that ships in `backend/src/infrastructure/taskiq/`, how to write and enqueue tasks, and how to run a worker.

## When to Use a Background Task

Reach for a task when an operation:

- Takes longer than a couple of seconds (image processing, PDF generation, large data exports)
- Calls an unreliable third party (don't make your API's latency depend on someone else's API)
- Sends an email, dispatches a webhook, or fans out notifications
- Recomputes an expensive aggregate that doesn't need to be live

Don't reach for a task when the operation needs to surface a result to the user immediately or when the failure modes are user-correctable in real time.

## What Ships Out of the Box

```text
backend/src/infrastructure/taskiq/
├── __init__.py        Exports default_broker, DBSession, register_task, task_registry
├── brokers.py         Builds the Redis or RabbitMQ broker from settings
├── app.py             Wires WORKER_STARTUP / WORKER_SHUTDOWN logging hooks
├── deps.py            DBSession dependency (TaskiqDepends-wrapped AsyncSession)
├── registry.py        Tiny in-process registry for monitoring
└── worker.py          Worker entry point: `default_broker`
```

Importantly: **no example task ships in the boilerplate.** The infrastructure is wired up; the modules are yours to add. `register_task` and `task_registry` are available for your own bookkeeping but are optional.

## Configuration

The relevant settings live in `TaskiqSettings` (`infrastructure/config/settings.py`) and read from `backend/.env`:

```env
# Toggle and broker selection
TASKIQ_ENABLED=true
TASKIQ_BROKER_TYPE=redis            # or "rabbitmq"

# Redis broker (when TASKIQ_BROKER_TYPE=redis)
TASKIQ_REDIS_HOST=redis             # use "localhost" without Docker
TASKIQ_REDIS_PORT=6379
TASKIQ_REDIS_DB=3                   # separate DB from CACHE / SESSION / RATE_LIMITER
TASKIQ_REDIS_PASSWORD=

# RabbitMQ broker (when TASKIQ_BROKER_TYPE=rabbitmq)
TASKIQ_RABBITMQ_HOST=localhost
TASKIQ_RABBITMQ_PORT=5672
TASKIQ_RABBITMQ_USER=guest
TASKIQ_RABBITMQ_PASSWORD=guest
TASKIQ_RABBITMQ_VHOST=/

# Worker tuning
TASKIQ_WORKER_CONCURRENCY=2
TASKIQ_MAX_TASKS_PER_WORKER=1000
```

The default `TASKIQ_REDIS_DB=3` keeps Taskiq isolated from Cache and Session (DB 0, shared) and the Rate Limiter (DB 1) — so `redis-cli FLUSHDB` on one doesn't trash the others.

If you pick `TASKIQ_BROKER_TYPE=rabbitmq`, install the optional broker:

```bash
uv add taskiq-aio-pika
```

The boilerplate already ships it as a dependency, but the `aio_pika` import is gated to keep Redis-only deployments lean.

## Writing a Task

Tasks live alongside the module they belong to, e.g. `modules/widgets/tasks.py`. The shape:

```python
# backend/src/modules/widgets/tasks.py
import logging
from typing import Any

from ...infrastructure.taskiq import DBSession, default_broker

logger = logging.getLogger(__name__)


@default_broker.task(task_name="widgets:rebuild_index")
async def rebuild_widget_index(
    owner_id: int,
    db: DBSession,
) -> dict[str, Any]:
    """Recompute the search index for a single owner's widgets."""
    logger.info("Rebuilding widget index for owner %s", owner_id)
    # ... do the work ...
    return {"owner_id": owner_id, "indexed": 42}
```

A few things worth knowing:

- **`task_name`** is optional but recommended. If you don't pass one, Taskiq uses `module.function_name` — fine for hobbyist setups, but a refactor that moves the function will silently break consumers. Pin a stable name.
- **`DBSession`** is the boilerplate's `Annotated[AsyncSession, TaskiqDepends(get_db_session)]`. Each task gets its own session backed by a `NullPool` engine — connections aren't shared with the API process and are closed at the end of the task.
- **Return values** can be retrieved via the result backend (Redis, by default). If you don't need the result, don't await it.
- **Logging** flows through your standard logger — there's no separate Taskiq logger to configure.

### Importing Tasks for Discovery

The Taskiq worker only knows about tasks whose modules have been imported. The cleanest pattern is to import every task module from a single entry point — usually wherever your `default_broker` lives or a dedicated `tasks/__init__.py`.

```python
# backend/src/infrastructure/taskiq/__init__.py (or similar)
from src.modules.widgets import tasks as _widget_tasks  # noqa: F401
from src.modules.users import tasks as _user_tasks      # noqa: F401
```

Without these imports, `widgets:rebuild_index.kiq(...)` will queue the message but no worker will know how to execute it.

## Enqueuing a Task

From a route handler, service method, or anywhere else in the app:

```python
from .tasks import rebuild_widget_index


@router.post("/widgets/{owner_id}/reindex", status_code=202)
async def trigger_reindex(owner_id: int) -> dict[str, str]:
    await rebuild_widget_index.kiq(owner_id=owner_id)
    return {"status": "queued"}
```

`.kiq(...)` is Taskiq's enqueue method — it serializes the kwargs, drops the message on the broker, and returns a `TaskiqResult` handle. **The handle is not awaited** in the typical "fire and forget" flow above — if you do want to wait, see [Awaiting Results](#awaiting-results) below.

A few important constraints:

- **All kwargs must be JSON-serializable.** Pass IDs, not ORM objects. Pass dicts, not Pydantic models that contain `datetime` (or convert via `.model_dump(mode="json")` first).
- **Don't pass database sessions.** The task gets its own via `DBSession`.
- **Don't pass HTTP request objects.** They don't survive serialization, and tasks shouldn't need them.

### Awaiting Results

If you genuinely need the result of a task before responding (rare — usually you'd compute synchronously instead), you can await it:

```python
result = await rebuild_widget_index.kiq(owner_id=owner_id)
value = await result.wait_result(timeout=30)
print(value.return_value)
```

This holds the API request open until the worker finishes. **Don't do this for slow tasks** — it defeats the purpose of using a queue. If a result is small and quick, return synchronously; if it's slow, return 202 and let the client poll.

### Scheduled & Delayed Tasks

Taskiq supports labels and a separate scheduler library (`taskiq-redis`'s scheduler source, `taskiq.scheduler.TaskiqScheduler`). The boilerplate doesn't ship a scheduler wired up — if you need cron-like scheduling, add `taskiq[scheduler]` to your worker setup. For one-off delays:

```python
await rebuild_widget_index.kicker().with_labels(delay=60).kiq(owner_id=owner_id)
```

(60-second delay before the worker picks it up, when supported by your broker — check the Taskiq docs for the labels you have.)

## Running a Worker

In development, run the worker in a separate terminal from the API:

```bash
cd backend
uv run taskiq worker infrastructure.taskiq.worker:default_broker
```

In Docker Compose, add a worker service that runs the same command. The worker needs the same Redis (or RabbitMQ) and the same database the API uses.

To tune concurrency:

```bash
uv run taskiq worker infrastructure.taskiq.worker:default_broker --workers 4
```

The `TASKIQ_WORKER_CONCURRENCY` env var configures the per-process concurrency; multiple `--workers` spawn additional processes. Pick the combination based on whether your tasks are I/O-bound (high concurrency, single process) or CPU-bound (multiple processes, low concurrency).

### Reloading on Code Changes

```bash
uv run taskiq worker infrastructure.taskiq.worker:default_broker --reload
```

Helpful in development. Don't run with `--reload` in production.

## Worker Lifecycle Hooks

The boilerplate already wires Taskiq's `WORKER_STARTUP` and `WORKER_SHUTDOWN` events for logging in `infrastructure/taskiq/app.py`:

```python
broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, startup_taskiq_worker)
broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, shutdown_taskiq_worker)
```

You can register additional handlers in your own setup — initialize a third-party SDK, prime an in-memory cache, push a metrics counter on shutdown, etc.

```python
from taskiq import TaskiqEvents
from taskiq.state import TaskiqState

from infrastructure.taskiq import default_broker


async def my_startup(state: TaskiqState) -> None:
    state.metrics_client = await build_metrics_client()


default_broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, my_startup)
```

The `state` object is shared across all tasks running in that worker process — useful for connection pools and clients that should be created once.

## Error Handling and Retries

Taskiq doesn't retry by default. If a task raises, the message is acknowledged and gone. To retry, use the built-in retry middleware:

```python
from taskiq import TaskiqMiddleware
from taskiq.middlewares import SimpleRetryMiddleware

from infrastructure.taskiq import default_broker

default_broker.add_middlewares(SimpleRetryMiddleware(default_retry_count=3))
```

Add this in your bootstrap (alongside the existing `configure_broker_lifecycle` call). With the middleware loaded, you can mark individual tasks for retry:

```python
@default_broker.task(retry_on_error=True, max_retries=3)
async def flaky_task(...): ...
```

For finer control (exponential backoff, dead-letter queues), check the [Taskiq middlewares docs](https://taskiq-python.github.io/guide/taskiq-middlewares.html). Whichever pattern you pick, **make tasks idempotent** — at-least-once delivery means the same task can run twice on partial failures.

## Monitoring

Taskiq doesn't ship a Flower-style dashboard, but you have a few options:

- **`task_registry`** (in `infrastructure/taskiq/registry.py`) is an in-process record of registered tasks for sanity-checking. Call `task_registry.get_tasks()` to list everything the worker knows about.
- **Logs** — every task logs through your standard logger; flow them into your existing log aggregation.
- **Result backend** — Redis stores task results for the configured TTL; you can read them back or scan with `redis-cli`.
- **External tools** — Taskiq has community projects for Prometheus metrics and admin UIs; see the [Taskiq docs](https://taskiq-python.github.io/) for what's current.

For most teams, structured logs plus alerting on error rates is enough. Add per-task counters to your existing metrics pipeline if you need finer visibility.

## Common Patterns

### Fan-Out

Trigger N independent tasks from a single API call:

```python
@router.post("/widgets/reindex-all")
async def reindex_all(owner_ids: list[int]) -> dict[str, int]:
    for owner_id in owner_ids:
        await rebuild_widget_index.kiq(owner_id=owner_id)
    return {"queued": len(owner_ids)}
```

### Pipeline (Task Chains)

When task B depends on task A's result, chain them inside the task itself rather than enqueuing A and waiting:

```python
@default_broker.task(task_name="widgets:fetch_then_index")
async def fetch_then_index(owner_id: int, db: DBSession) -> dict[str, int]:
    fetched = await fetch_remote_widgets(owner_id, db)
    await rebuild_widget_index.kiq(owner_id=owner_id)
    return {"fetched": fetched}
```

Avoid: `result = await task_a.kiq(...).wait_result(); await task_b.kiq(result, ...)` from a route handler — that holds the request open and serializes work that should be parallel.

### Email and Notifications

A canonical use case: hash the heavy work into a task, return 202 from the API:

```python
@default_broker.task(task_name="users:welcome_email")
async def send_welcome_email(user_id: int, db: DBSession) -> None:
    user = await user_service.get_by_id(user_id, db)
    await email_client.send(template="welcome", to=user["email"], context={...})


# In the route:
new_user = await user_service.create(payload, db)
await send_welcome_email.kiq(user_id=new_user["id"])
return new_user
```

The user is created synchronously; the email goes out from a worker. If the email service is down, the user account isn't blocked.

## Troubleshooting

### "Task is queued but never runs"

- Confirm the worker process is running and pointed at the same broker as your API
- Confirm the task's module is **imported** somewhere the worker bootstraps — Taskiq doesn't auto-discover tasks
- Check the worker logs for serialization errors on dequeue
- For Redis: `redis-cli LRANGE default 0 -1` (or your queue name) shows pending messages

### "Worker can't import my task module"

The worker imports the broker by module path. With the boilerplate's install layout (`[tool.setuptools.packages.find] where = ["src"]`), `infrastructure`, `modules`, etc. are top-level packages once you've run `uv sync` — so `infrastructure.taskiq.worker:default_broker` resolves cleanly. If you skipped install and are running from source, ensure `backend/src` is on `PYTHONPATH`.

### "Database connection errors in tasks"

Tasks use `DBSession`, which uses a separate engine with `poolclass=NullPool` (one connection per task, closed at the end). If you're seeing connection errors:

- Check `DATABASE_URL` is set in the worker's environment
- Make sure your Postgres `max_connections` accommodates both the API's pool and the worker's per-task connections (rough rule: `api_pool_size + worker_concurrency`)

### "Tasks fail silently"

Without a retry middleware, a failed task is acknowledged and gone. Either add retries (see above) or wrap your task body in a try/except that logs explicitly:

```python
@default_broker.task(task_name="widgets:rebuild_index")
async def rebuild_widget_index(owner_id: int, db: DBSession) -> dict[str, Any]:
    try:
        # ...
    except Exception:
        logger.exception("Widget index rebuild failed for owner %s", owner_id)
        raise
```

## Key Files

| Component             | Location                                                  |
|-----------------------|-----------------------------------------------------------|
| Broker factory        | `backend/src/infrastructure/taskiq/brokers.py`            |
| Worker entry point    | `backend/src/infrastructure/taskiq/worker.py`             |
| Lifecycle hooks       | `backend/src/infrastructure/taskiq/app.py`                |
| DB dependency         | `backend/src/infrastructure/taskiq/deps.py`               |
| Task registry         | `backend/src/infrastructure/taskiq/registry.py`           |
| Settings              | `backend/src/infrastructure/config/settings.py` (`TaskiqSettings`) |

## Next Steps

- **[Taskiq documentation](https://taskiq-python.github.io/)** — Authoritative reference for middlewares, schedulers, brokers
- **[Production](../production.md)** — Running the worker in production, scaling, supervision
- **[Caching → Cache Strategies](../caching/cache-strategies.md)** — Using Taskiq to schedule cache warming
