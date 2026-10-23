# Observability

The boilerplate ships no tracing and no metrics exporter. What it does ship is the material an
exporter needs: structured logs, a support id on every failed request, readiness over each
dependency, and a row per API-key request. This page says what that material is, and how to put
[Logfire](https://logfire.pydantic.dev) — OpenTelemetry with Pydantic's SDK on top — in front of it
without changing any of it.

## What the project already emits

| Signal | Where it comes from | What it tells you |
|---|---|---|
| Application logs | `infrastructure/logging/`, through `get_logger()` | `LOG_FORMAT=json` writes one JSON object per line; `LOG_LEVEL` and the console/file handlers are settings ([Logging in Production](production.md#logging-in-production)) |
| A support id per failed request | the catch-all error handler | the id in the `500` body appears in the log line for that request, which is what ties a user's report to the server side |
| Refused sign-ins | `infrastructure/auth/audit.py` | one `WARNING` per refusal and per lockout, with the reason and the caller's address ([what a refusal records](authentication/sessions.md#what-a-refusal-records)) |
| Dependency health | `GET /health/ready` | ready or not ready per poll, and a log line naming whatever was unreachable ([Health and Readiness](production.md#health-and-readiness)) |
| API-key traffic | the `key_usage` table | path, method, status, duration, address and user agent per key request, queryable per key ([API Keys](authentication/api-keys.md#what-a-keys-usage-records)) |

Two gaps are worth knowing before you add anything: log lines carry **no request id** unless you
wire one (`infrastructure/logging/` ships `set_correlation_id()` and `add_correlation_id_filter()`,
and nothing installs them), and nothing measures latency per route. Tracing fills both — a span per
request, with the database queries under it.

## Adding Logfire

Logfire is a dependency and three calls. It is not wired here, so this is a recipe rather than a
feature:

```bash
cd backend && uv add "logfire[fastapi,sqlalchemy,redis,httpx,asyncpg]"
```

Put the configuration in one module of its own, `src/infrastructure/observability.py`:

```python
"""Tracing, off until LOGFIRE_TOKEN is set."""

import logging

import logfire
from fastapi import FastAPI

from .config.settings import settings
from .database.session import get_engine


def configure_tracing() -> None:
    """Configure Logfire and instrument the clients this app talks through."""
    logfire.configure(
        service_name="api",
        environment=settings.ENVIRONMENT.value,
        send_to_logfire="if-token-present",
        console=False,
    )
    logfire.instrument_sqlalchemy(engine=get_engine())
    logfire.instrument_redis()
    logfire.instrument_httpx()
    logging.getLogger().addHandler(logfire.LogfireLoggingHandler())


def install(app: FastAPI) -> None:
    """Trace every request this app serves, except the probes."""
    logfire.instrument_fastapi(app, excluded_urls=["/health", "/health/ready"])
```

Then wire it where this app is composed, in `src/interfaces/main.py`:

```python
from ..infrastructure.observability import configure_tracing, install as tracing_install

configure_tracing()

app = create_application(
    router=router,
    settings=settings,
    lifespan=lifespan_with_security,
    root_routers=ROOT_ROUTERS,
    installers=(*INSTALLERS, tracing_install),
    docs_guard=DOCS_GUARD,
)
```

Not `src/wiring/app.py`. The removal drill generates the wiring modules from
`tools/removal_drill.py`, and `tests/unit/test_removal_drill.py` compares what it generates with
what the project committed, so an installer written into `INSTALLERS` by hand fails that test.
`main.py` is the composition root, and nothing regenerates it. A project that would rather have
the generator know about this one makes it a feature
([below](#if-you-turn-this-into-a-feature)).

`send_to_logfire="if-token-present"` is what keeps it off: with no `LOGFIRE_TOKEN` in the
environment, nothing leaves the process, which is the same rule every other optional thing in this
project follows — a setting that enables something is off when unset. `LOGFIRE_TOKEN`,
`LOGFIRE_SERVICE_NAME` and `LOGFIRE_ENVIRONMENT` are read from the environment, so the values above
are defaults a deployment can override without touching the code.

!!! note "The worker is a second process"
    `taskiq worker src.infrastructure.taskiq.worker:default_broker` never imports `main.py`,
    so none of the above runs there. Call `configure_tracing()` in
    `src/infrastructure/taskiq/worker.py` as well, with `service_name="worker"`, and the two
    processes report separately. A task enqueued by a request is not joined to that request's trace
    unless you propagate the context yourself (`logfire.propagate`).

## What not to send

Instrumentation sees everything the app touches, so the defaults above are the careful ones:

- **`capture_headers` is off by default** in `instrument_fastapi`, and leaving it off keeps the
  `Cookie` and `X-API-Key` headers out of your traces. Turning it on sends a session cookie — a
  live credential — to a third party on every request.
- **Query parameters are not statements.** `instrument_sqlalchemy` does not record bound
  parameters, and `instrument_redis(capture_statement=True)` / `instrument_asyncpg(capture_parameters=True)`
  would record the values your queries carry: email addresses, hashed passwords, session ids. Leave
  both off.
- **Logfire scrubs by pattern.** Anything whose key matches `password`, `secret`, `api[._ -]?key`
  and the rest of its defaults is redacted; extend it with
  `logfire.configure(scrubbing=logfire.ScrubbingOptions(extra_patterns=["token", "csrf"]))`. Pattern
  scrubbing is a safety net, not a policy: it cannot know that `identifier` in a refused-login line
  is a username.
- **The refusal audit lines name identifiers.** They name only identifiers an account has
  ([why](authentication/sessions.md#what-a-refusal-records)), but those are usernames and email
  addresses, so forwarding the log through `LogfireLoggingHandler` sends them. A deployment that
  must not export them narrows the two functions in `infrastructure/auth/audit.py`, or leaves the
  logging handler out and exports traces alone.
- **Probes are noise.** `/health` and `/health/ready` are polled every few seconds by every
  orchestrator; `excluded_urls` keeps them out, which is also why the readiness check's own log
  lines are the better signal for a dependency outage. Those entries are regular expressions, joined
  and matched with `re.search` against the whole URL — `scheme://host/path`, without the query
  string — so `"/health"` covers both probes, and any other path containing `/health`. Anchoring
  with `^` matches nothing, because the string starts with the scheme and host; to limit it to the
  two probes, end-anchor instead: `excluded_urls=[r"/health(/ready)?$"]`.

## Sampling and cost

A span per request plus a span per query is a lot of spans. `logfire.configure(sampling=...)` takes
[`SamplingOptions`](https://logfire.pydantic.dev/docs/guides/advanced/sampling/) — a head rate, or
tail sampling that keeps every trace with an error and a fraction of the rest, which is the shape
worth starting from. `min_level` drops low-level records before they are built.

## Doing without Logfire

Nothing above is Logfire-specific except the SDK: it writes OpenTelemetry, so the same recipe with
`opentelemetry-instrumentation-fastapi` and an OTLP exporter reports to any collector. To send to
another OpenTelemetry backend instead, set `send_to_logfire=False` and point the standard
`OTEL_EXPORTER_OTLP_ENDPOINT` (and `OTEL_EXPORTER_OTLP_HEADERS`) at your collector; the
instrumentation above stays as it is. If you want metrics without traces,
`logfire.instrument_system_metrics()` covers the process, and the readiness endpoint plus your
proxy's own access logs already cover whether the app is up and how fast it answers.

## If you turn this into a feature

A project that wants observability to be removable like the others gives it a `FEATURES` entry in
`tools/removal_drill.py` — the `observability` module, its tests, and its contribution to
`src/wiring/app.py` — and settings that are off when unset. See
[Composable Features](composable-features.md).

## Key Files

| Component | Location |
|---|---|
| Logging configuration and formatters | `backend/src/infrastructure/logging/` |
| Readiness checks and their report | `backend/src/infrastructure/readiness.py`, `backend/src/wiring/hooks.py` |
| Refused-login audit hooks | `backend/src/infrastructure/auth/audit.py` |
| API-key usage rows | `backend/src/modules/api_keys/usage.py` |
| The catch-all handler and its support id | `backend/src/modules/common/utils/error_handler.py` |
| Where this recipe wires its installer | `backend/src/interfaces/main.py` |
| Where a feature's installer is wired | `backend/src/wiring/app.py` |

---

[← Production](production.md){ .md-button } [Composable Features →](composable-features.md){ .md-button .md-button--primary }
