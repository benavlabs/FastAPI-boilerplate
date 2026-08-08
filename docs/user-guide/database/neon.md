# Neon (Serverless Postgres)

[Neon](https://neon.com) is serverless Postgres — a managed database that scales compute to zero when idle and lets you branch a database like you branch code. It's a drop-in replacement for the local Postgres container: the boilerplate needs **one environment variable**, no code changes.

!!! info "Neon sponsors this project"
    Neon supports Fastro · The Benav Labs FastAPI Boilerplate with database credits for our open-source infrastructure. It's one option among many — the boilerplate runs on any Postgres 14+ (local, RDS, Cloud SQL, Supabase, your own box) — but it's the one we use and the one these instructions are tested against.

## When it's a good fit

- **You don't want a Postgres container.** No `docker compose up` for the database, no volume to reset.
- **Preview environments.** Each Neon branch is a copy-on-write clone of your data, created in seconds — one database per PR, per developer, per test run.
- **Bursty or low-traffic APIs.** Compute suspends while idle, so a staging environment nobody touched all weekend costs nothing to keep around.

Stick with the bundled Postgres container if you want offline development or a fully self-hosted stack.

## What it costs

There's a **free plan that isn't a trial** — no credit card, no expiry — which is enough to run this boilerplate's dev, staging, and hobby-project workloads. At the time of writing it includes, per project:

| | Free plan |
|---|---|
| Storage | 0.5 GB |
| Compute | 100 CU-hours/month, autoscaling up to 2 CU (8 GB RAM) |
| Projects / branches | 100 projects, 10 branches each |
| Network egress | 5 GB |
| Included regardless of plan | Autoscaling, branching, read replicas, connection pooling, extensions, API + CLI |

Because compute scales to zero, an idle staging database burns close to nothing of that CU-hour budget — the meter effectively runs only while you're querying.

!!! warning "What happens at the limit"
    Exceeding a monthly limit **suspends the compute until the next billing month** rather than generating a surprise bill. That's friendly for a side project and dangerous for anything you care about: production means a paid plan, or at minimum an alert on your usage. Check [neon.com/pricing](https://neon.com/pricing) for current numbers — the table above will drift.

## 1. Create a project

1. Sign up at [neon.com](https://neon.com) and create a project (pick the region closest to where your API runs — every query pays that round trip).
2. Open **Connection Details** in the dashboard and copy the connection string. It looks like this:

```text
postgresql://neondb_owner:npg_xxxxxxxx@ep-cool-darkness-123456-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

## 2. Convert it for asyncpg

The connection string Neon hands you is written for **libpq** (`psql`, psycopg). The boilerplate's app engine is **asyncpg**, which spells its options differently. Two edits:

| Neon gives you | Use instead | Why |
|---|---|---|
| `postgresql://` | `postgresql+asyncpg://` | Selects SQLAlchemy's async driver |
| `?sslmode=require&channel_binding=require` | `?ssl=require` | SQLAlchemy forwards unknown query params straight to `asyncpg.connect()`. It has no `sslmode` or `channel_binding` keyword — passing them raises `TypeError: connect() got an unexpected keyword argument 'sslmode'`. asyncpg calls the parameter `ssl`. |

The result, in `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_xxxxxxxx@ep-cool-darkness-123456-pooler.us-east-2.aws.neon.tech/neondb?ssl=require

# Let Alembic own the schema instead of creating tables at boot
CREATE_TABLES_ON_STARTUP=false
```

`DATABASE_URL` takes priority over the individual `POSTGRES_*` variables ([settings reference](../configuration/environment-variables.md#database)), so the rest of them are ignored once it's set — including the `POSTGRES_SERVER: postgres` that Compose injects. You can leave them at their defaults; the [production validator](../production.md#the-production-validator) reads the credentials out of `DATABASE_URL` when it's set, so a default `POSTGRES_PASSWORD` won't be mistaken for an insecure deployment. Nothing else in your config has to change.

!!! warning "Don't drop the `ssl` parameter"
    Over a TCP connection asyncpg defaults to `sslmode=prefer`: it will use TLS if the server offers it, but silently accepts an unencrypted connection otherwise, and never verifies the certificate. Being explicit with `ssl=require` means a downgrade fails loudly instead of quietly.

    `require` encrypts the connection but — exactly like libpq — does not verify the server's certificate. For full verification use `?ssl=verify-full` and point `PGSSLROOTCERT` at a CA bundle (asyncpg otherwise looks for `~/.postgresql/root.crt` and fails if it isn't there).

## 3. Run migrations and start

```bash
cd backend
uv run alembic upgrade head
uv run python -m scripts.setup_initial_data   # first admin user + default tier
uv run fastapi dev src/interfaces/main.py
```

Alembic reads the same `settings.DATABASE_URL` the app does (`backend/migrations/env.py`), so there's no second connection string to maintain.

## Pooled vs. direct endpoints

Neon gives every project two hostnames. The difference is the `-pooler` suffix:

```text
ep-cool-darkness-123456-pooler.us-east-2.aws.neon.tech   # pooled — via PgBouncer
ep-cool-darkness-123456.us-east-2.aws.neon.tech          # direct — straight to Postgres
```

**Use the pooled endpoint for the API and the Taskiq worker.** Both open a connection per request/task, which is exactly the churn PgBouncer absorbs, and it raises your usable connection ceiling far above what the compute alone allows.

**Use the direct endpoint for migrations and admin work.** Neon's PgBouncer runs in transaction mode, so session-level state doesn't survive between statements — `SET`/`RESET` (including `SET search_path`), `LISTEN`/`NOTIFY`, SQL-level `PREPARE`, and session-scoped advisory locks all behave differently there. Long multi-statement DDL is safer on a direct connection:

```bash
# One-off override for the migration only
DATABASE_URL="postgresql+asyncpg://neondb_owner:npg_xxxxxxxx@ep-cool-darkness-123456.us-east-2.aws.neon.tech/neondb?ssl=require" \
  uv run alembic upgrade head
```

## Handling scale-to-zero

An idle Neon compute suspends. Connections that were sitting in SQLAlchemy's pool are dead when it wakes, and the next request surfaces that as `SSL SYSCALL error: EOF detected` or `connection was closed in the middle of operation`.

`POSTGRES_POOL_PRE_PING` handles this and is **on by default** — every connection is tested before it's handed to a request, so a dead one is quietly replaced instead of failing the request. Pair it with `POSTGRES_POOL_RECYCLE` to retire connections before Neon does:

```env
POSTGRES_POOL_RECYCLE=300     # seconds; keep it under your scale-to-zero timeout
```

Trim the pool while you're there. `POSTGRES_POOL_SIZE` defaults to `20` per process, and the real number is `pool_size × workers × replicas` — see [Scaling considerations](../production.md#database). Against a small Neon compute, `5`–`10` is usually plenty:

```env
POSTGRES_POOL_SIZE=10
POSTGRES_MAX_OVERFLOW=5
```

The Taskiq worker needs none of this: it uses a `NullPool` and opens a fresh connection per task, so there's nothing pooled to go stale.

## Docker Compose without the local database

Once `DATABASE_URL` points at Neon, the `postgres` service in your generated compose file is dead weight. Delete the service, its volume, and the two `depends_on` entries that wait on it:

```yaml hl_lines="8 9"
services:
  api:
    env_file:
      - ./backend/.env
    environment:
      CACHE_REDIS_HOST: redis
    depends_on:
      # postgres:                  ← remove
      #   condition: service_healthy
      redis:
        condition: service_healthy
```

Redis still runs locally — Neon replaces Postgres only. Regenerating with `uv run bp deploy generate local` brings the Postgres service back, so keep the edit in mind after a regen.

## Database branching for previews

The reason to reach for Neon over a plain managed Postgres. A branch is a copy-on-write clone — full data, created in seconds, thrown away just as fast:

```bash
# One database per pull request
neon branches create --name pr-142 --parent main

# Print a connection string for it
neon connection-string pr-142
```

Feed that string into your preview environment's `DATABASE_URL` (converted as in step 2 — the CLI prints the libpq form) and the preview runs on real, isolated data. Delete the branch when the PR merges. The same trick works for integration tests that need a real Postgres: branch, migrate, run, delete.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: connect() got an unexpected keyword argument 'sslmode'` | libpq-style parameter left in the URL | Replace `sslmode=require&channel_binding=require` with `ssl=require` |
| `TypeError: connect() got an unexpected keyword argument 'channel_binding'` | Same | Same |
| `ProductionSecurityError: Database is using default credentials` | The password inside `DATABASE_URL` really is `postgres` | Rotate it in the Neon console and update the URL |
| `SSL SYSCALL error: EOF detected` after an idle period | Compute suspended, pooled connections went stale | Keep `POSTGRES_POOL_PRE_PING=true` and set `POSTGRES_POOL_RECYCLE` (see above) |
| First request after idle takes a few hundred ms | Compute resuming from zero | Expected; disable scale-to-zero on the branch if latency matters more than cost |
| `prepared statement "__asyncpg_stmt_x__" already exists` | Prepared-statement reuse across a transaction-mode pooler | Add `&prepared_statement_cache_size=0` to the URL, or use the direct endpoint |
| `password authentication failed` with a correct password | Special characters in the password aren't URL-encoded | Percent-encode them (`@` → `%40`, `#` → `%23`, …) |

## Related

- [Migrations](migrations.md) — Alembic workflow and the production confirm gate
- [Environment Variables](../configuration/environment-variables.md#database) — every database setting
- [Production Deployment](../production.md) — validator, pool sizing, scaling
- [Neon docs](https://neon.com/docs) — branching, autoscaling, the `neon` CLI
