# Composable Features

Every feature in this boilerplate can be removed. Not "commented out" or "left
unused" — deleted, along with its routes, models, settings, admin views, seeders and
tests, leaving a project that imports, lints, type-checks and passes its remaining
tests.

That works because features never import each other to plug in. A feature exposes
plain objects at stable paths, and one package collects them.

## The composition root

`backend/src/wiring/` is the only place features meet:

| File | What it lists |
|------|---------------|
| `app.py` | `ROUTER_MOUNTS`, `ROOT_ROUTERS`, `API_THROTTLE`, `LIFECYCLES`, `INSTALLERS`, `DOCS_GUARD` |
| `settings.py` | each feature's settings mixin, with the core last |
| `hooks.py` | `PERMISSION_SOURCES`, `RATE_LIMIT_RESOLVERS`, `TIER_DELETE_GUARDS`, `CRITICAL_READINESS_CHECKS`, `INFORMATIONAL_READINESS_CHECKS` |
| `models.py` | `UserModelExtensions`, `UserSchemaExtensions` |
| `admin.py` | `ADMIN_VIEWS` |

Two more live beside the code they drive: `backend/scripts/seeders.py` lists
`SEEDERS`, and `backend/tests/wiring.py` lists the fixture modules pytest loads.

Every one of these files is imports and names: each entry is either a value a
feature exposes or a literal naming where to mount it. No decisions are taken
here, so ruff, mypy and an IDE see exactly what a project wired. Anything
conditional — whether the OAuth router exists, for instance — belongs to the
feature that owns it, which exposes the answer for the wiring to list.

!!! note "Hand-maintained for now"
    A generator that writes these files from a catalog is planned. Until it exists,
    adding a feature means adding its entries here by hand.

## The shapes a feature contributes

`backend/src/infrastructure/composition.py` holds the types:

- `RouterMount(router, prefix, throttled)` — a router to mount under the API prefix.
- `Lifecycle(name, startup, shutdown)` — startup and shutdown work, run in wiring
  order and torn down in reverse.
- `PermissionSource` — answers which permissions a user holds.
- `RateLimitResolver` — answers the limit for a request, or `None` to decline.
- `TierDeleteGuard` — answers why a tier can't be deleted, or `None` to allow it.
- `ReadinessCheck(name, check)` — a dependency the app needs before it can serve.

A feature that wants to extend the `User` model contributes a mixin instead: see
`modules/tier/contrib.py`, which adds `tier_id` and `tier` without the user module
knowing that tiers exist.

## What each feature owns

| Feature | Needs | Owns |
|---------|-------|------|
| core | – | everything not listed below, including the permission registry |
| accounts | – | `infrastructure/auth/`, `modules/user/`, the first-superuser seeder |
| rbac | accounts | `modules/role/` |
| ratelimit | accounts | `infrastructure/ratelimit/` |
| tiers | accounts | `modules/tier/`, the default-tier seeder |
| tier_limits | tiers, ratelimit | `modules/rate_limit/` |
| api_keys | accounts | `modules/api_keys/` |
| admin | accounts | `interfaces/admin/`, `wiring/admin.py` |
| cache | – | `infrastructure/cache/` |
| taskiq | – | `infrastructure/taskiq/` |

A few files belong to a *combination*: `modules/user/admin.py` exists only with
accounts **and** admin, and `modules/tier/admin.py` only with tiers **and** admin.

## Checking that removal still works

`tools/removal_drill.py` builds a copy of the repository for a set of features,
deletes the paths of the ones left out, regenerates the wiring, and then checks
that the app imports, that every module imports, that ruff and mypy pass, and that
the remaining tests pass.

It runs on the interpreter that invoked it, so run it through uv (the checks need
the project's dependencies) and with Docker up (the tests use a Postgres container):

```sh
uv run --no-sync python tools/removal_drill.py                 # every preset
uv run --no-sync python tools/removal_drill.py accounts-only   # one of them
uv run --no-sync python tools/removal_drill.py --keep          # keep the scratch copies
```

The presets run in CI as a matrix:

| Preset | What it proves |
|--------|----------------|
| `core-only` | every feature can go at once |
| `accounts-only` | permission checks fall back to superuser-only without rbac |
| `accounts-rbac` | permissions work without tiers, throttling, cache or taskiq |
| `accounts-rbac-tiers` | tiers and the API throttle work without per-tier limits |
| `accounts-cache-taskiq` | the infrastructure features stand alone |
| `everything` | a regenerated wiring reproduces this repository |

The drill is also how a misplaced test gets caught: a test that quietly depends on
a feature it doesn't own fails in the preset that removes it.

## Writing a feature that can be removed

1. Keep everything the feature owns under its own paths, and add those paths to the
   drill's manifest.
2. Import another feature only if the table above says you need it.
3. To reach into another feature, contribute to a hook rather than importing it.
4. Put the feature's settings in its own `settings.py` and its fixtures in
   `tests/fixtures/`, then list both in the wiring.
5. Run the drill. If a preset that excludes your feature fails, something of yours
   is in a path the drill doesn't delete.
