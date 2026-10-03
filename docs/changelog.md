# Fastro - The Benav Labs FastAPI boilerplate Changelog

## Introduction

The Changelog documents all notable changes to the Fastro FastAPI boilerplate, organized by version. For releases before v0.18.0, see [GitHub releases](https://github.com/benavlabs/FastAPI-boilerplate/releases).

For the full narrative on each release — rationale, decisions, migration guide — see the corresponding GitHub release page.

___

## Unreleased - Composable Features

Every feature in the boilerplate can now be removed: its routes, models, settings, admin views,
seeders and tests come out together, and the project still imports, lints, type-checks and passes
the remaining tests. `tools/removal_drill.py` proves it for six presets, and CI runs them as a
matrix. The round that followed fixed what a re-review of the refactor found.

---

#### Added

- **crudauth's account routes**, mounted under `/api/v1/auth`: `POST /change-password` (verifies the
  current password, then revokes the account's other sessions) and `GET /me`. `set-password` is
  deliberately not mounted, so an account that signs in with a provider still has no password.
- **`src/wiring/`, the composition root.** `app.py`, `settings.py`, `hooks.py`, `models.py` and
  `admin.py` list what this project selected; `backend/scripts/seeders.py` and
  `backend/tests/wiring.py` do the same for seeders and fixtures. See
  [Composable Features](user-guide/composable-features.md).
- **Contribution shapes** in `infrastructure/composition.py`: `RouterMount`, `Lifecycle`,
  `PermissionSource`, `RateLimitResolver`, `TierDeleteGuard`, `TierDeleteRelease`, `ReadinessCheck`.
- **`tools/removal_drill.py`** — builds the repository without each feature and runs five checks
  (the app imports, every module imports, ruff, mypy, tests) per preset.
- **`GET /health/ready`** — answers `503` while a dependency the project selected is unreachable:
  the database, and the cache, the login lockout's Redis, the session store and the task broker for
  the features it has. Checks run together, each with a two-second timeout; the report is reused for
  a couple of seconds, and two checks pointed at one server are asked once. `GET /health` stays a
  liveness probe that touches nothing.
- **`FORWARDED_ALLOW_IPS`** is now documented, and the generated nginx stack puts the containers on
  a fixed subnet and trusts forwarded headers only from it
  (`bp deploy generate nginx --internal-subnet …`).
- **`LOG_FORMAT`** now decides the formatter, with each environment's format as the default.

#### Changed

- **Emails are stored canonically** (lowercased, as crudauth looks them up), on signup, on update and
  in the admin panel. `UserService.get_by_email` canonicalises its lookup, so seeding a superuser
  with a mixed-case `ADMIN_EMAIL` is idempotent.
- **Tier rate limits match the route template** the request hit (`/api/v1/users/{username}`), not the
  concrete path, and soft-deleted rows no longer apply.
- **Page sizes are bounded**: every listing takes `page` and `items_per_page` from one shared
  dependency, capped at 100, and sorts with an id tie-break.
- **An API key's `expires_at` must carry a UTC offset.**
- **API-key routes answer through schemas** — creating a key no longer returns its hash.
- **An explicit `null`** for a column the row requires is refused with `422`; the guarded names come
  from the model, so a new column can't be forgotten.
- **Creating tables imports every model first**, so `scripts/create_tables.py` and
  `scripts/setup_initial_data.py` create the whole schema.
- **`get_logger()` names the logger after its caller's module**, so per-module levels and the
  structured `module` field work.
- **Structured log lines escape quoted values**, so client text can't forge a field.
- **The admin panel's session cookie** is its own middleware, scoped to `/admin`, `Secure` outside
  local and development, and valid for 8 hours. Changing a user's address in the panel clears
  `email_verified`.
- **The secret-key check** measures placeholders, hand-written words, repeated blocks (whole or with
  a remainder), ordered runs, walks across neighbouring keyboard keys, and words anyone would
  recognise, each against a share of the whole value, plus an entropy floor. No key was refused in 100,000
  samples of each of `token_hex(16)`, `token_hex(32)`, `token_urlsafe(24)` and `token_urlsafe(32)`,
  while `"12345678" * 4`,
  `qwertyuiopasdfghjklzxcvbnm123456`, `1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik,`, `"monkey" * 5 + "12"`,
  `hunter2hunter2hunter2hunter2hunter22`, `Summer2026!Summer2026!Summer2026!!`,
  `MyCompanyApiSigningKeyForProd2026` and `thisismysupersecurekeyforthisapp` never do.
- **The API metadata defaults are empty**, so a generated project's OpenAPI document carries no
  contact, licence or URL it didn't configure, and emits a licence `identifier` or `url`, never both.
- **The database name, the RabbitMQ vhost and every Redis URL** are escaped or refused rather than
  rendered raw.
- **CI** lints and type-checks `backend/scripts` and `backend/migrations`, type-checks `tools`, pins
  Python on the sync step, and runs the removal drills.
- **The generated local stack publishes Postgres and Redis on `127.0.0.1` only**, and the Taskiq
  Redis result backend stores results as JSON instead of pickles.
- **`GET /health/ready` gates on the dependencies a request needs.** The wiring lists them in
  `CRITICAL_READINESS_CHECKS` (the database, and the login lockout's Redis and the session store
  with accounts) and `INFORMATIONAL_READINESS_CHECKS` (the cache and the task broker). A critical
  check that fails answers `503`; an informational one is logged and leaves the answer `200`.
- **The readiness body carries the overall status only**, and probes that arrive together share one
  run of the checks. Which dependency answered what goes to the log, written by the probe that ran
  them.
- **`ADMIN_BASE_URL` decides where the panel is mounted**, and the admin session cookie is scoped to
  the path each request arrived through, prefix included (`--root-path /svc` gives `/svc/admin`).
  Moving the panel, or serving the app under a prefix, no longer leaves every admin request bouncing
  back to the login form.
- **The generated nginx vhost replaces `X-Forwarded-For`** with the address it saw
  (`$remote_addr`), rather than appending to whatever the client sent, and
  `--internal-subnet` is refused unless it names a network address of `/8` or smaller for IPv4, or
  `/48` or smaller for IPv6 - a wildcard, a `/0`, or a value with host bits set no longer reaches
  the compose file. The subnet is quoted in
  the generated YAML.
- **The input that used to answer `500` now answers `422`.** `page` is capped at `2**31 - 1`, so the
  offset stays a number the database can read; an API key's id is bounded to the range its `Integer`
  column covers; an `expires_at` whose offset moves it past the dates a datetime can hold is refused;
  and text that is not valid Unicode - a lone surrogate in a password or `current_password` - is
  refused before it reaches a hash or a write.
- **A soft-deleted tier keeps its soft-deleted users.** `TierService.delete` no longer clears
  `user.tier_id` on rows a soft delete had already removed - only `permanent_delete` does, where the
  foreign key requires it - and a soft-deleted user no longer blocks either delete. A soft-deleted
  rate limit no longer blocks a tier delete either; a permanent delete removes those rows through
  `TIER_DELETE_RELEASES`, a new contribution point in `src/wiring/hooks.py` for whatever a feature
  keeps for a tier.
- **The admin panel really refuses a deleted tier.** sqladmin hands the form's selection over as a
  primary key, so the old check never fired: the panel now loads the tier and refuses a soft-deleted
  one, the picker lists only live tiers, and the Tiers listing counts what it shows.
- **A soft-deleted tier or rate limit no longer reaches `GET /api/v1/users/{username}/rate-limits`.**
  Both joins exclude deleted rows, and a user left pointing at a deleted tier reports no tier and no
  limits instead of the deleted one's.
- **The readiness checks name their servers more carefully.** Two checks pointed at one server are
  asked once whatever database index or password follows the port; a cache in the process
  (`CACHE_BACKEND=memory`) names no server at all; the memcached check asks on a connection of its
  own and closes it, rather than handing the app's pool back a connection with an unread reply; a
  report answers only for the checks it was taken for; and a check whose target can't be named is
  still asked, with the failure logged.
- **The seed scripts run on their own.** `python scripts/create_first_superuser.py` and
  `python scripts/create_first_tier.py` import the models before touching the ORM, and report a
  failure as one line with exit code `1` - admin settings that don't describe an account, a password
  the policy refuses, a taken username, or a database they can't reach. The message for a taken
  `ADMIN_EMAIL` names the setting rather than the address.
- **Creating an API key answers with its own schema.** The response carries the row as the read
  schema reports it plus the full key, with `key_metadata` and `last_used_ip` excluded;
  `GET /api/v1/api-keys/{id}` still reports both.
- **Another user's public profile carries the display fields only.** `GET /api/v1/users/{username}`
  answers with `id`, `name`, `username` and `profile_image_url`; the fields features add to the read
  schemas, such as `tier_id`, stay on `/users/me`, on `/users/{username}/tier` for the owner or a
  superuser, and on the superuser endpoints.
- **The admin panel's CSV export writes formula-like cells as text.** Text starting with `=`, `+`,
  `-`, `@`, a tab or a carriage return is prefixed with an apostrophe, so a name typed at signup
  can't become a formula in a spreadsheet. Numbers, dates and `None` are written unchanged.
- **Failed statements report their SQL without their values.** The engine is built with
  `hide_parameters=True`, and the catch-all handler logs the method, path and support id without the
  exception text, so a failing insert no longer writes a password hash to the log. An email address
  longer than the column (50 characters) answers `422` instead of `500`.

#### Removed

- `CSRFException`, which nothing raised.
- Settings nothing read: `LOG_CORRELATION_ID`, `LOG_INCLUDE_STACKTRACE`, `LOG_PERFORMANCE_METRICS`,
  `LOG_SQL_QUERIES`, `LOG_STRUCTURED_CONTEXT`, `DEFAULT_CACHE_EXPIRATION`,
  `TASKIQ_WORKER_CONCURRENCY`, `TASKIQ_MAX_TASKS_PER_WORKER`, `POSTGRES_SYNC_PREFIX`,
  `PRODUCTION_SECURITY_STRICT_MODE`, `TASKIQ_ENABLED`.
- `handle_exception`: routes let domain errors propagate to the global handler.
- The `env` option in the pytest config, which needed a plugin the project doesn't install.

#### Breaking Changes

- **Changing your own email address now requires the account's current password** in the `PATCH
  /api/v1/users/{username}` body (`current_password`), and answers `403` without it. Every change
  that needs the password counts against the same budget as `POST /api/v1/auth/change-password`,
  correct passwords included: 5 per hour per account, then `429`. So an account can change its
  address at most five times an hour. An account with no usable password (provider sign-in only)
  can't change its address at all. A superuser changing someone else's address is unchanged: no
  password, no limit. The address change still clears `email_verified`, which is what made a stolen
  session enough to take an account over through a provider login.
- **The caller-resolving dependency aliases moved** from `infrastructure/dependencies.py` to
  `infrastructure/auth/deps.py`: `CurrentUserDep`, `CurrentSuperUserDep`, `OptionalUserDep`,
  `CurrentPrincipalDep`, `CurrentPermissionsDep`, `OAuth2FormDep`. `AsyncSessionDep` stays.
- **An empty `CORS_ORIGINS` now allows no cross-origin request**, where it used to mean "any origin".
  A `*` origin never gets credentials, and is refused outright in production.
- **Rate-limit rows that name a concrete path stop matching.** Rewrite them as the route template
  the router declares (`/api/v1/users/{username}`); a row for `/api/v1/users/42` will never apply.
- **`items_per_page` above 100 answers `422`** on every listing, including the API-key usage history,
  which allowed 1000, and `page` above `2147483647` answers `422` as well.
- **An API key's id outside `1..2147483647` answers `422`**, where the request used to reach the
  database and fail there.
- **An `expires_at` that cannot be expressed in UTC answers `422`**, and so does string input that is
  not valid Unicode.
- **A naive `expires_at` on an API key answers `422`.** Send an offset (`2030-01-01T00:00:00+00:00`).
- **Emails are stored lowercased.** Rows written before this change keep their original case; the
  uniqueness check and the login lookup both use the canonical form, so a mixed-case row can still be
  matched by a differently-cased signup. A data migration for existing rows is a decision, not part
  of this change.
- **`API_CONTACT_URL`, `API_LICENSE_IDENTIFIER`, `CONTACT_NAME`, `CONTACT_EMAIL`, `LICENSE_NAME` and
  `API_SUMMARY` default to empty.** Set them to put your own identity in the OpenAPI document.
- **`HTTPException` and friends** import from `infrastructure/http_exceptions.py`
  (was `infrastructure/auth/http_exceptions.py`).
- **The settings listed under Removed are gone.** An `.env` that still sets them is ignored; nothing
  read them.
- **`POSTGRES_DB` may not contain `/`, `?`, `#` or `@`.** SQLAlchemy reads the name literally, so such
  a name would have connected somewhere else; set `DATABASE_URL` instead.
- **`GET /health/ready` answers `{"status": "ready"}` or `{"status": "not ready"}` and no longer
  lists the dependencies.** A dashboard that read `dependencies` from the body reads the log instead;
  the probe that runs the checks names whatever it found unreachable.
- **`READINESS_CHECKS` is now two tuples**, `CRITICAL_READINESS_CHECKS` and
  `INFORMATIONAL_READINESS_CHECKS` (`src/wiring/hooks.py`). A project that added its own check
  lists it in whichever group fits. A cache or broker outage no longer answers `503`, so an alert
  that watched `/health/ready` for one needs to watch the log line or the reported dependencies
  instead.
- **Task results are stored as JSON**, not pickles. The Redis result backend no longer unpickles what
  it reads, so a result key written by an older worker can't be read back. Drain the queue and clear
  the result keys before deploying both sides.
- **A stricter `SECRET_KEY` check can stop a production deploy that used to start.** A key that
  repeats a block, walks the keyboard, or reads as ordinary words is now refused, where before only
  whole repeats and placeholders were. Generate one with `bp env gen-secret` (or
  `python -c 'import secrets; print(secrets.token_urlsafe(32))'`) and roll it before deploying -
  rotating `SECRET_KEY` invalidates existing sessions and admin logins.
- **Regenerate an nginx stack** (`bp deploy generate nginx`) to get the `X-Forwarded-For` change.
  Until then a client can send its own `X-Forwarded-For`, and uvicorn - trusting the compose
  network - reports it as `request.client`.
- **Regenerate a local stack** (`bp deploy generate local`) to publish Postgres and Redis on
  `127.0.0.1` only. An existing `docker-compose.yml` keeps offering a password-less database to
  everyone on the network.
- **`POST /api/v1/api-keys/` no longer returns `key_metadata` or `last_used_ip`.** Read them from
  `GET /api/v1/api-keys/{id}`; a key that has just been created has no `last_used_ip` anyway.
- **`GET /api/v1/users/{username}` no longer returns `tier_id`.** A user's tier is now visible only
  to that user, through `/users/me` or `GET /api/v1/users/{username}/tier`, and to superusers, who
  can read any user's tier through the same route. A client that read another user's tier from their
  profile can no longer see it.

___

## 0.19.0 - June 23, 2026 - The crudauth Migration

Three changes since v0.18.0: route dependency injection moved to centralized `Annotated[...]` type aliases ([#261](https://github.com/benavlabs/FastAPI-boilerplate/pull/261)), the app metadata (`APP_NAME` / `APP_DESCRIPTION` / `VERSION`) became environment-configurable, and — the headline — the vendored authentication stack was replaced with the [`crudauth`](https://pypi.org/project/crudauth/) library.

**The crudauth migration.** The vendored authentication stack — the in-tree `SessionManager`, its storage backends, the OAuth provider framework, and the token/password utilities — has been replaced with crudauth. The boilerplate now keeps only the wiring: a single `auth = CRUDAuth(...)` singleton in `infrastructure/auth/setup.py`, the FastAPI dependencies that wrap it, the OAuth building blocks, and the route handlers. Session validation, CSRF, login lockout, and session storage all live in the library.

**Annotated type-alias DI** ([#261](https://github.com/benavlabs/FastAPI-boilerplate/pull/261), by [@emiliano-gandini-outeda](https://github.com/emiliano-gandini-outeda)). Route signatures moved from inline `Depends(...)` to centralized `Annotated[..., Depends(...)]` aliases in `infrastructure/dependencies.py`, with per-module `dependencies.py` files holding the service aliases for `user`, `tier`, `rate_limit`, and `api_keys`.

This is a **breaking** change for anyone importing from the old auth modules or relying on the removed settings. See Breaking Changes below for the migration.

---

#### Added

- **`crudauth` library integration** by [@igorbenav](https://github.com/igorbenav)
  - `auth = CRUDAuth(...)` composition root in `infrastructure/auth/setup.py`; the app lifespan calls `auth.initialize()` / `auth.shutdown()`
  - New `Principal`-based dependencies `get_current_principal` / `get_optional_principal` alongside the dict-returning `get_current_user` / `get_optional_user` / `get_current_superuser`
- **`TRUSTED_PROXY_HOPS` setting** (default `0`) — number of trusted reverse proxies in front of the app, used by crudauth to resolve the real client IP for login lockout. Set `1` behind a single nginx/Caddy.
- **`User.is_active` property** — derived from `not is_deleted`; crudauth reads it during login so soft-deleted users can't authenticate.
- **Annotated type-alias dependency injection** ([#261](https://github.com/benavlabs/FastAPI-boilerplate/pull/261)) by [@emiliano-gandini-outeda](https://github.com/emiliano-gandini-outeda) — centralized `Annotated[..., Depends(...)]` aliases in `infrastructure/dependencies.py` and per-module `dependencies.py` (`user`, `tier`, `rate_limit`, `api_keys`) with service aliases; route signatures migrated to use them.

#### Changed

- Auth dependencies now import from `infrastructure.auth.dependencies` (was `infrastructure.auth.session.dependencies`).
- `get_password_hash` / `verify_password` now come `from crudauth` (was `infrastructure.auth.utils`).
- Login lockout now returns **`429 Too Many Requests` with a `Retry-After` header** (was a generic `401`). It is throttled internally by crudauth (escalating per-IP / per-identifier), not via env vars.
- OAuth providers are now configured through crudauth's built-in OAuth router in `infrastructure/auth/setup.py` rather than hand-rolled callback wiring. Google remains wired.
- `APP_NAME`, `APP_DESCRIPTION`, and `VERSION` are now environment-configurable (read via `config(...)`; previously hardcoded).
- `/check-auth` now answers anonymous callers with `{"authenticated": false}` instead of raising `401` ([#261](https://github.com/benavlabs/FastAPI-boilerplate/pull/261)).

#### Removed

- The vendored session stack: `SessionManager`, the memory/redis/memcached session backends, session storage/schemas/dependencies, and the user-agent parsing helpers.
- The in-tree OAuth package (provider framework, factory, `providers/google.py`, `providers/github.py`, services) and `auth/utils.py` / `auth/constants.py`.
- The **memcached session backend** — sessions now support only `redis` and `memory`. (The general cache and rate limiter still support memcached.)
- The GitHub OAuth provider file. The `User` model keeps its `github_id` / `oauth_provider` columns, so the data model still anticipates GitHub, but no provider or routes ship.
- Settings `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `SESSION_COOKIE_MAX_AGE`, `LOGIN_MAX_ATTEMPTS`, and `LOGIN_WINDOW_MINUTES`.
- The dependency aliases `SessionManagerDep`, `CurrentSessionDataDep`, `OptionalSessionDataDep`, `GoogleOAuthProviderDep`, and `OAuthStateStorageDep`.

#### Breaking Changes

- **Imports moved.** Replace `from ...infrastructure.auth.session.dependencies import ...` with `from ...infrastructure.auth.dependencies import ...`, and import `get_password_hash` / `verify_password` from `crudauth`.
- **Removed settings.** Delete `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `SESSION_COOKIE_MAX_AGE`, `LOGIN_MAX_ATTEMPTS`, and `LOGIN_WINDOW_MINUTES` from your environment — they no longer exist. Add `TRUSTED_PROXY_HOPS` if you run behind a proxy.
- **Login lockout response changed** from `401` to `429` + `Retry-After`; update any client that special-cased the old status/message.
- **`SESSION_BACKEND=memcached` is no longer valid** — switch to `redis` or `memory`.
- **`SessionManager` and friends are gone.** Code that called the session manager directly (e.g. listing a user's sessions) must move to crudauth's session APIs.

**Full release notes**: https://github.com/benavlabs/FastAPI-boilerplate/releases/tag/v0.19.0
**Full changelog**: https://github.com/benavlabs/FastAPI-boilerplate/compare/v0.18.0...v0.19.0

___

## 0.18.0 - May 24, 2026 - The Pluggable Restructure

This is the release we promised in v0.17.0; the one that tears the layout apart and rebuilds it as a real plugin system. If you've been pinned to v0.17.0 waiting for it, this is your moment.

A heads-up before we go further: **the diff is enormous**; v0.17.0 → v0.18.0 is not the kind of upgrade you run `git pull` for. The Python package moved, auth changed completely, workers changed, the admin panel changed, there's a new CLI in a new workspace member. We didn't do this lightly.

### Why this release is so different

We didn't iterate on the v0.17.0 codebase to get here. We **rebased the project on the [fastroai-template](https://fastro.ai) structure**.

fastroai-template is the production-tested template we use internally (and sell) for AI SaaS products. It's been running real apps for months and the structural choices (three-layer architecture, vertical-slice modules, server-side sessions, SQLAdmin, Taskiq, swappable infrastructure) have proven themselves under load. Reinventing all of that for FastAPI-boilerplate would have meant another six months of polish; rebasing meant we could ship the good parts on day one.

The trade-off is that fastroai-template carries a lot of stuff this boilerplate's audience doesn't necessarily need: a Stripe integration, subscription/credits/entitlements modeling, AI agent orchestration, usage tracking with cost calculation, OAuth-specific provisioning for SaaS, an Astro frontend. Excellent for an AI SaaS starter, wrong for a general FastAPI boilerplate.

**So this release is fastroai-template minus the SaaS/AI parts, plus a plugin system that fastroai-template doesn't have.** What's left is the structural skeleton; the parts that any FastAPI app needs and that we've watched hold up in real use:

- The three-layer split (`interfaces/`, `infrastructure/`, `modules/`)
- Vertical-slice modules (`user/`, `tier/`, `api_keys/`, `rate_limit/`)
- Server-side sessions + CSRF, OAuth (Google wired, GitHub scaffolded)
- SQLAdmin, Taskiq, swappable cache/session/rate-limit backends
- The production security validator that refuses to boot with insecure defaults

The new part, the one fastroai-template doesn't have, is **`bp` — a plugin-aware CLI**. fastroai-template ships everything in-tree because that's appropriate for an AI SaaS starter. FastAPI-boilerplate's whole pitch is "use what you need, drop what you don't", and that pitch only works if dropping things and adding things are first-class operations. The `bp.commands` and `bp.features` entry points are how external Python packages contribute new commands and feature generators without touching the core. Build a Stripe plugin, a Prometheus plugin, a CRUD-generator plugin, they all ship as separate packages.

### If you can stay on v0.17.0, consider it

For brand-new projects, v0.18.0 is the better starting point. For existing apps with significant custom code on v0.17.0, the honest answer is: **the migration path is "copy your business logic into the new structure"**, not a sed-style find-and-replace. If your fork has diverged from v0.17.0 in non-trivial ways, pinning to v0.17.0 may be the right call. We'll keep v0.17.0 around as a tag forever.

For the full migration guide and per-section detail, see the [full release notes on GitHub](https://github.com/benavlabs/FastAPI-boilerplate/releases/tag/v0.18.0).

---

#### Added

- **Three-layer architecture** by [@igorbenav](https://github.com/igorbenav)
  - `backend/src/{interfaces,infrastructure,modules}/` split
  - Vertical-slice modules: each domain owns its full vertical (`models`, `schemas`, `crud`, `service`, `routes`, `enums`)
  - Modules shipped: `user`, `tier`, `api_keys`, `rate_limit`, `common`

- **uv workspace split** by [@igorbenav](https://github.com/igorbenav)
  - Workspace root with two members: `backend/` (deployable) and `cli/` (developer tool)
  - Single shared `.venv`; prod Dockerfile only copies `backend/src/`
  - Install with `uv sync --all-packages --all-extras` from the repo root

- **`bp` CLI with plugin extension points** by [@igorbenav](https://github.com/igorbenav)
  - `bp.commands` — external Typer sub-apps mount under the root
  - `bp.features` — external feature generators with manifest + plan + rollback
  - In-tree commands: `bp deploy generate {local,prod,nginx}`, `bp env gen-secret`, `bp env validate`
  - Built-in `deploy` feature with Jinja templates for compose + nginx

- **OAuth provider framework** by [@igorbenav](https://github.com/igorbenav), [@LucasQR](https://github.com/LucasQR)
  - Google end-to-end (callback creates session, sets cookie)
  - GitHub scaffolded with the same provider/factory shape
  - Documentation at `docs/user-guide/authentication/`

- **API keys module** by [@igorbenav](https://github.com/igorbenav)
  - Named keys with permissions and usage limits
  - Per-call usage recording for analytics
  - scrypt hashing with per-row salt (CodeQL strong-KDF compliant)
  - Lookup via indexed `key_prefix` column with constant-time verify

- **Production security validator** by [@igorbenav](https://github.com/igorbenav)
  - Startup gate that refuses to boot prod with insecure defaults
  - Checks `SECRET_KEY`, DB credentials, CORS policy, session flags, debug mode, admin credentials and Redis passwords
  - `bp env validate` runs the same checks against any config

- **Server-side sessions** by [@igorbenav](https://github.com/igorbenav)
  - Opaque session IDs in `HttpOnly` cookies
  - Backed by Redis (default), Memcached, or in-memory
  - CSRF enforced by default for state-changing endpoints
  - Documentation at `docs/user-guide/authentication/sessions.md`

- **Swappable infrastructure backends** by [@igorbenav](https://github.com/igorbenav)
  - Cache, rate limit, session storage all behind ABCs in `*/base.py`
  - Concrete backends in `*/backends/{redis,memcached,memory}.py`
  - Env-selectable: `SESSION_BACKEND`, `CACHE_BACKEND`, `RATE_LIMITER_BACKEND`

- **Multi-stage Dockerfile** by [@igorbenav](https://github.com/igorbenav)
  - `dev` / `migrate` / `prod` stages from a single `backend/Dockerfile`
  - Uses `uv export` against the lockfile for reproducible builds with hash verification
  - Pinned uv version (`0.9.9`) for build reproducibility

- **Python 3.14 dependency compatibility** by [@carlosplanchon](https://github.com/carlosplanchon)
  - Dependency bumps that compile and run on Python 3.14

- **CI workflows for the workspace** by [@igorbenav](https://github.com/igorbenav)
  - `tests.yml`, `linting.yml`, `type-checking.yml`, `docs.yml` covering both members
  - Least-privilege `permissions: contents: read` on all workflows (`docs.yml` additionally has `pages: write` and `id-token: write`)

#### Changed

- **JWT → server-side sessions** by [@igorbenav](https://github.com/igorbenav)
  - JWT access tokens, refresh tokens, and the `token_blacklist` table removed
  - API surface is cookie-based now; clients sending `Authorization: Bearer` are rejected

- **CRUDAdmin → SQLAdmin** by [@igorbenav](https://github.com/igorbenav)
  - Custom admin panel replaced with SQLAdmin
  - `DataclassModelMixin` added for `MappedAsDataclass` model compatibility
  - Env: `CRUD_ADMIN_*` removed; use `ADMIN_ENABLED` (uses main `SECRET_KEY`)

- **ARQ → Taskiq** by [@igorbenav](https://github.com/igorbenav)
  - Async-native worker stack with Redis or RabbitMQ broker
  - Worker command: `taskiq worker infrastructure.taskiq.worker:default_broker`
  - `DBSession` dependency injection in tasks

- **MkDocs → Zensical** by [@igorbenav](https://github.com/igorbenav)
  - Docs site generator swapped; configured via `zensical.toml`
  - Local: `uvx zensical serve`; build: `uvx zensical build`
  - Deploy via `.github/workflows/docs.yml` to GitHub Pages

- **Settings layout** by [@igorbenav](https://github.com/igorbenav)
  - Composed setting groups (`AuthSettings`, `CacheSettings`, `RateLimiterSettings`, etc.) in `infrastructure/config/settings.py`
  - `get_settings()` returns the composed `Settings` instance
  - Most env var names stable; a few moved between groups

#### Security

- **Dropped `python-jose` / `ecdsa`** by [@igorbenav](https://github.com/igorbenav)
  - Removed unused `fastsecure` dep, which was pulling in `python-jose` and `ecdsa`
  - Addresses the Minerva timing attack on P-256 in python-ecdsa (the project explicitly won't fix it; switching to `cryptography` was the upstream recommendation)
  - `bcrypt` is now a direct dependency (was transitive via `fastsecure`)

- **Bumped `idna` to 3.16** by [@igorbenav](https://github.com/igorbenav)
  - Fixes CVE-2024-3651 bypass for crafted inputs to `idna.encode()`

- **Bumped `sqladmin` to 0.26.0** by [@igorbenav](https://github.com/igorbenav)
  - Fixes the `ajax_lookup` authorization bypass

- **scrypt for API key hashing** by [@igorbenav](https://github.com/igorbenav)
  - Per-row salt, format `scrypt$N$r$p$salt$derived`
  - Compliance with CodeQL's strong-KDF allowlist
  - Constant-time verify via `hmac.compare_digest`

- **Workflow permissions tightened** by [@igorbenav](https://github.com/igorbenav)
  - All CI workflows now declare explicit `permissions:` blocks
  - Read-only on test/lint/type-check; targeted writes only where needed

#### Improved

- **Full documentation rewrite** by [@igorbenav](https://github.com/igorbenav), [@LucasQR](https://github.com/LucasQR), [@emiliano-gandini-outeda](https://github.com/emiliano-gandini-outeda)
  - Every page under `docs/user-guide/` rewritten for the new structure
  - New `docs/cli/` section: `index.md`, `commands.md`, `plugins.md`
  - New `docs/user-guide/authentication/sessions.md`
  - README slimmed but still self-contained

- **Lint enforcement: `PLC0415`** by [@igorbenav](https://github.com/igorbenav)
  - No deferred imports anywhere — all imports at module top
  - Surfaced and resolved a circular import in session storage by extracting `AbstractSessionStorage` to `auth/session/base.py`

- **README polish** by [@carlosplanchon](https://github.com/carlosplanchon)
  - Installation scripts moved out of Gists into the repo
  - DeepWiki documentation link added

#### Removed

- **`src/app/` layout** — replaced by `backend/src/{interfaces,infrastructure,modules}/`
- **JWT auth + `token_blacklist` table** — replaced by server-side sessions
- **CRUDAdmin views** — replaced by SQLAdmin
- **ARQ workers** — replaced by Taskiq
- **Deployment scripts** (`setup.py`, `scripts/{local_with_uvicorn,gunicorn_managing_uvicorn_workers,production_with_nginx}/`) — replaced by `bp deploy generate`
- **`mkdocs.yml`** — replaced by `zensical.toml`
- **Demo `posts` module** — pure demo code, not needed
- **`backend/uv.lock`** — stale duplicate of workspace `uv.lock`

#### Breaking Changes

⚠️ Eight breaking changes. The migration path for forks with significant custom code is "copy your business logic into the new structure" — there is no sed-style find-and-replace.

| Change | Impact | Migration |
|---|---|---|
| `src/app/` layout removed | Imports break at import time | Manual restructure into `modules/<name>/` |
| JWT removed | `Authorization: Bearer` clients rejected | Switch clients to cookie auth |
| CRUDAdmin → SQLAdmin | Custom admin views need porting | Port to `ModelView` shape |
| ARQ → Taskiq | Workers need re-registration | Rewrite tasks as `@broker.task` async functions |
| API key hash format | Existing keys won't validate | Users must regenerate |
| Settings composition | Env var names mostly stable; a few moved | Diff `.env.example` |
| Sync command | `cd backend && uv sync --extra dev` produces broken venv | Use `uv sync --all-packages --all-extras` from repo root |
| Deployment scaffolder | `./setup.py local` removed | `uv run --no-sync bp deploy generate {local,prod,nginx}` |

For brand-new projects, v0.18.0 is the better starting point. For existing apps with significant custom code on v0.17.0, **pinning to v0.17.0 may be the right call** — that tag stays supported.

#### New Co-Maintainers

- [@carlosplanchon](https://github.com/carlosplanchon) and [@emiliano-gandini-outeda](https://github.com/emiliano-gandini-outeda) are now officially helping maintain and improve the boilerplate.

**Full release notes**: https://github.com/benavlabs/FastAPI-boilerplate/releases/tag/v0.18.0
**Full changelog**: https://github.com/benavlabs/FastAPI-boilerplate/compare/v0.17.0...v0.18.0
