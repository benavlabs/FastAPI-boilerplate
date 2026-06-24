# Fastro - The Benav Labs FastAPI boilerplate Changelog

## Introduction

The Changelog documents all notable changes to the Fastro FastAPI boilerplate, organized by version. For releases before v0.18.0, see [GitHub releases](https://github.com/benavlabs/FastAPI-boilerplate/releases).

For the full narrative on each release — rationale, decisions, migration guide — see the corresponding GitHub release page.

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
- OAuth providers are now registered via crudauth's `OAuthProviderFactory` in `infrastructure/auth/oauth.py` rather than as separate `oauth/providers/<name>.py` files. Google remains wired.
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
  - Checks `SECRET_KEY`, DB credentials, CORS policy, session flags, debug mode, `CREATE_TABLES_ON_STARTUP`
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
| Deployment scaffolder | `./setup.py local` removed | `uv run bp deploy generate {local,prod,nginx}` |

For brand-new projects, v0.18.0 is the better starting point. For existing apps with significant custom code on v0.17.0, **pinning to v0.17.0 may be the right call** — that tag stays supported.

#### New Co-Maintainers

- [@carlosplanchon](https://github.com/carlosplanchon) and [@emiliano-gandini-outeda](https://github.com/emiliano-gandini-outeda) are now officially helping maintain and improve the boilerplate.

**Full release notes**: https://github.com/benavlabs/FastAPI-boilerplate/releases/tag/v0.18.0
**Full changelog**: https://github.com/benavlabs/FastAPI-boilerplate/compare/v0.17.0...v0.18.0
