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
├── __init__.py        Docstring only: the package is kept import-free
├── brokers.py         Builds the Redis or RabbitMQ broker from settings
├── app.py             WORKER_STARTUP / WORKER_SHUTDOWN handlers (logging, engine disposal)
├── lifecycle.py       Opens and closes the broker in the API process
├── email.py           The email:send task, and the sender that enqueues it
├── scheduler.py       Scheduler entry point: the schedules tasks declare in labels
├── deps.py            DBSession dependency (TaskiqDepends-wrapped AsyncSession)
└── worker.py          Worker entry point: registers the handlers on `default_broker`
```

One task ships: `email:send`, which delivers the account emails (`infrastructure/taskiq/email.py`), so no request waits on a mail server. Beyond it the infrastructure is wired up and the task modules are yours to add.

## Configuration

The relevant settings live in `TaskiqSettings` (`infrastructure/config/settings.py`) and read from `backend/.env`:

```env
# Broker selection
TASKIQ_BROKER_TYPE=redis            # or "rabbitmq"

# Retries
TASKIQ_DEFAULT_RETRY_COUNT=3        # runs in all, for a task that asks; 0 turns retries off

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
```

The default `TASKIQ_REDIS_DB=3` keeps Taskiq isolated from the Cache (DB 0), the Rate Limiter (DB 1), and Sessions (DB 2) — so `redis-cli FLUSHDB` on one doesn't trash the others.

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

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession

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

The Taskiq worker only knows about tasks whose modules have been imported. Import every task module
from the worker entry point, `src/infrastructure/taskiq/worker.py` — the package's `__init__.py` is
deliberately import-free, so adding them there would pull app code into the settings import path.

```python
# backend/src/infrastructure/taskiq/worker.py
from .app import configure_broker_lifecycle
from .brokers import default_broker
from src.modules.widgets import tasks as _widget_tasks  # noqa: F401
from src.modules.reports import tasks as _report_tasks  # noqa: F401

configure_broker_lifecycle(default_broker)

__all__ = ["default_broker"]
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

The connection `.kiq(...)` publishes over is opened by the app's lifespan: the taskiq feature
contributes a `Lifecycle` (`infrastructure/taskiq/lifecycle.py`) that `src/wiring/app.py` lists, so
the broker starts before the API serves and is closed on shutdown. With RabbitMQ, enqueueing without
it raises `SendTaskError` from taskiq's `NoStartupError`; the Redis broker happens to work either
way, since it opens its pool when it is built.

A broker that is down doesn't keep the API down. If the connection fails at startup the app logs a
warning, serves anyway, and retries every `BROKER_RETRY_SECONDS` (`infrastructure/taskiq/constants.py`)
until one attempt connects — repeat failures at `DEBUG`, one `INFO` line when it does. Each failed
attempt is closed again, so nothing a half-finished startup opened is left behind.
`.kiq(...)` raises `SendTaskError` while the broker is down, so a route that
enqueues should decide what a queued-work outage means for its response. `GET /health/ready` reports
the broker as an informational check — it reads the live state of the connection the app holds, so
it answers unavailable while that connection is being opened or reconnected after an outage, ready
once it is up, and never a `503` either way.

A few important constraints:

- **All kwargs must be JSON-serializable.** Pass IDs, not ORM objects. Pass dicts, not Pydantic models that contain `datetime` (or convert via `.model_dump(mode="json")` first).
- **Don't pass database sessions.** The task gets its own via `DBSession`.
- **Don't pass HTTP request objects.** They don't survive serialization, and tasks shouldn't need them.
- **Return values go through the same JSON step.** `datetime`, `UUID` and Pydantic models come back
  as their JSON forms - a `datetime` returns as an ISO string, not a `datetime` - and an arbitrary
  object such as an ORM row fails with `PydanticSerializationError` when the worker writes its result.

### Awaiting Results

If you genuinely need the result of a task before responding (rare — usually you'd compute synchronously instead), you can await it:

```python
result = await rebuild_widget_index.kiq(owner_id=owner_id)
value = await result.wait_result(timeout=30)
print(value.return_value)
```

This holds the API request open until the worker finishes. **Don't do this for slow tasks** — it defeats the purpose of using a queue. If a result is small and quick, return synchronously; if it's slow, return 202 and let the client poll.

### Scheduled Tasks

A task says when it should run in its own `schedule` label:

```python
@default_broker.task(task_name="widgets:rebuild_index", schedule=[{"cron": "*/5 * * * *"}])
async def rebuild_widget_index(db: DBSession) -> None: ...
```

`infrastructure/taskiq/scheduler.py` is the entry point that reads those labels — a `TaskiqScheduler`
over Taskiq's `LabelScheduleSource`, pointed at the same broker and the same task imports as
`worker.py`:

```sh
cd backend
uv run --no-sync taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler
```

`bp deploy generate` writes it as a `scheduler` service alongside the worker, for a project that
carries the taskiq feature.

**Run exactly one scheduler.** Each one fires every schedule it finds, so a second replica means
every cron entry is enqueued twice. The worker is the one to scale out instead: `--workers`, or more
replicas of the worker service.

A schedule can also be an interval or a one-off time (`{"interval": 60}`, `{"time": datetime(...)}`),
and `args` / `kwargs` in the same entry are passed to the task. Schedule ids are generated at
startup, so they change every time the scheduler restarts.

### Delayed Tasks

```python
await rebuild_widget_index.kicker().with_labels(delay=60).kiq(owner_id=owner_id)
```

Whether that 60 seconds is honoured is the broker's business, and neither broker this project builds
honours it as it stands: the Redis `ListQueueBroker` ignores the label and the worker picks the task
up at once, and the RabbitMQ broker raises unless it was given a delay queue or the
delayed-message-exchange plugin. Use a schedule for work that has to wait.

## Running a Worker

In development, run the worker in a separate terminal from the API:

```bash
cd backend
uv run --no-sync taskiq worker src.infrastructure.taskiq.worker:default_broker
```

In Docker Compose, add a worker service that runs the same command. The worker needs the same Redis (or RabbitMQ) and the same database the API uses.

To tune concurrency:

```bash
uv run --no-sync taskiq worker src.infrastructure.taskiq.worker:default_broker --workers 4
```

`--workers` spawns additional worker processes, and taskiq's own `--max-async-tasks` sets how many
tasks one process runs at a time. Pick the combination based on whether your tasks are I/O-bound
(high concurrency, single process) or CPU-bound (multiple processes, low concurrency).

### Reloading on Code Changes

```bash
uv run --no-sync taskiq worker src.infrastructure.taskiq.worker:default_broker --reload
```

Helpful in development. `--reload` needs `taskiq[reload]` from the `dev` extra, which is why the
command asks for it. Don't run with `--reload` in production.

## Worker Lifecycle Hooks

The worker entry point registers Taskiq's `WORKER_STARTUP` and `WORKER_SHUTDOWN` handlers from `infrastructure/taskiq/app.py`:

```python
# backend/src/infrastructure/taskiq/worker.py
from .app import configure_broker_lifecycle
from .brokers import default_broker

configure_broker_lifecycle(default_broker)
```

The shutdown handler disposes the worker's `NullPool` engine. Registration happens only in `worker.py`, so the API process, which opens the broker to enqueue tasks, never runs worker handlers: taskiq picks the `WORKER_*` events over the `CLIENT_*` ones only in a process the worker CLI started.

Register additional handlers in `worker.py` or in a module it imports: initialize a third-party SDK, prime an in-memory cache, push a metrics counter on shutdown, etc.

```python
from taskiq import TaskiqEvents
from taskiq.state import TaskiqState

from src.infrastructure.taskiq.brokers import default_broker


async def my_startup(state: TaskiqState) -> None:
    state.metrics_client = await build_metrics_client()


default_broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, my_startup)
```

The `state` object is shared across all tasks running in that worker process — useful for connection pools and clients that should be created once.

## Error Handling and Retries

The worker loads Taskiq's `SimpleRetryMiddleware` (`configure_broker_lifecycle`,
`infrastructure/taskiq/app.py`), but retrying is opt-in per task: a task that doesn't ask for it
runs once, and if it raises the message is acknowledged and gone.

```python
@default_broker.task(task_name="widgets:rebuild_index", retry_on_error=True)
async def rebuild_widget_index(...): ...
```

`TASKIQ_DEFAULT_RETRY_COUNT` (default 3) is how many times such a task runs **in all**, the first
attempt included — so two retries by default, and `0` turns retries off for every task. A single
task can say so for itself:

```python
@default_broker.task(task_name="widgets:reconcile", retry_on_error=True, max_retries=5)
async def reconcile_widgets(...): ...
```

Retries are immediate: the message is requeued the moment the task fails, so a task tripped up by a
brief network blip or a rate limit spends its attempts within milliseconds. Taskiq also ships
`SmartRetryMiddleware`, which adds a delay, exponential backoff and jitter, but its delay needs
somewhere to hold the message: a `schedule_source` with a scheduler running, or a RabbitMQ broker
built with a delay queue or the delayed-message-exchange plugin. On the Redis broker this project
builds, the `delay` label is ignored and the retry is immediate again; on its RabbitMQ broker,
publishing with a delay raises until one of those is configured.

For dead-letter queues and middlewares of your own, check the [Taskiq middlewares docs](https://taskiq-python.github.io/guide/taskiq-middlewares.html). Whichever pattern you pick, **make tasks idempotent** — at-least-once delivery means the same task can run twice on partial failures.

## Monitoring

Taskiq doesn't ship a Flower-style dashboard, but you have a few options:

- **`default_broker.get_all_tasks()`** lists every task the process has imported, name to task — the same registry the worker and the scheduler read.
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
- For RabbitMQ: `rabbitmqctl list_queues` shows the `taskiq` queue the broker declares, with its
  message count

### "Worker can't import my task module"

The worker imports the broker by module path, and the app has one import root: `src`. Run the worker from `backend/`, so that directory is on `sys.path` and `src.infrastructure.taskiq.worker:default_broker` resolves. In the image, `PYTHONPATH=/app:/app/src` covers it.

### "Database connection errors in tasks"

Tasks use `DBSession`, which uses a separate engine with `poolclass=NullPool` (one connection per task, closed at the end). If you're seeing connection errors:

- Check `DATABASE_URL` is set in the worker's environment
- Make sure your Postgres `max_connections` accommodates both the API's pool and the worker's per-task connections (rough rule: `api_pool_size + worker_concurrency`)

### "Tasks fail silently"

A task that doesn't ask for retries is acknowledged and gone when it raises. Either label it `retry_on_error=True` (see above) or wrap your task body in a try/except that logs explicitly:

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

| Component              | Location                                                           |
|------------------------|--------------------------------------------------------------------|
| Broker factory         | `backend/src/infrastructure/taskiq/brokers.py`                     |
| Worker entry point     | `backend/src/infrastructure/taskiq/worker.py`                      |
| Worker lifecycle hooks | `backend/src/infrastructure/taskiq/app.py`                         |
| Broker lifecycle (API) | `backend/src/infrastructure/taskiq/lifecycle.py`                   |
| DB dependency          | `backend/src/infrastructure/taskiq/deps.py`                        |
| Settings               | `backend/src/infrastructure/config/settings.py` (`TaskiqSettings`) |

## Next Steps

- **[Taskiq documentation](https://taskiq-python.github.io/)** — Authoritative reference for middlewares, schedulers, brokers
- **[Production](../production.md)** — Running the worker in production, scaling, supervision
- **[Caching → Cache Strategies](../caching/cache-strategies.md)** — Using Taskiq to schedule cache warming
