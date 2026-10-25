# Admin Panel Configuration

The admin panel has a deliberately small surface area: it's a [SQLAdmin](https://github.com/smithyhq/sqladmin) instance gated by a username/password from environment variables. Configuration boils down to a handful of `.env` values.

## Environment Variables

```env
# Toggle the admin panel (default: true)
ADMIN_ENABLED=true

# Admin login credentials — must BOTH be set, otherwise login always fails
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Change-Me-Now-1!

# Used for admin session encryption (same SECRET_KEY as the rest of the app)
SECRET_KEY=<openssl rand -hex 32>
```

That's the whole admin-specific config. Everything else (engine, models, mount path) is hardcoded in `src/interfaces/admin/initialize.py` for simplicity.

### Backing Settings Classes

The variables map to two settings classes in `src/infrastructure/config/settings.py`:

- **`AdminSettings`** — `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DEFAULT_TIER_NAME`. Used by both the admin panel login *and* `scripts/setup_initial_data.py` to bootstrap the first superuser.
- **`SQLAdminSettings`** — `ADMIN_ENABLED`. Single toggle for the admin panel.

## What Happens at Startup

1. The app factory calls the admin feature's `install(app)`, which the wiring lists among its installers
2. If `ADMIN_ENABLED=false`, the function returns `None` and the admin panel is **not mounted**
3. Otherwise, an `AdminAuth` backend is constructed using `SECRET_KEY`
4. A SQLAdmin `Admin` instance is created against the app's existing database `engine`
5. The views listed in `src/wiring/admin.py` are registered: `UserAdmin`, `TierAdmin` and the three role views, each shipped by its own feature
6. The admin app is mounted at `/admin`

## Login Authentication

Login flow (in `interfaces/admin/auth.py`):

```python
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        settings = get_settings()
        if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
            return False

        address = get_client_ip(request, settings.TRUSTED_PROXY_HOPS)
        counted_against = f"{LOCKOUT_PREFIX}:{address}"
        # panel_lockout counts this address, every_address_lockout counts them all;
        # either one locked refuses before the password is read
        ...
```

Notes:

- Credentials come from environment variables, **not the database**. Restart the app to change them,
  which signs out every session that was created against the old pair.
- **Admin login is disabled until both `ADMIN_USERNAME` and `ADMIN_PASSWORD` are set.** With the empty defaults, every login attempt fails — an empty form submission does not authenticate.
- Only one admin login is supported. There's no multi-admin user table.
- **Failures are counted in a lockout of the panel's own**, against the client address and the
  identifier `admin-panel:<address>`, with the thresholds in `LOGIN_MAX_ATTEMPTS`,
  `LOGIN_ATTEMPT_WINDOW_SECONDS`, `LOGIN_LOCKOUT_BASE_SECONDS` and `LOGIN_LOCKOUT_MAX_SECONDS`. A
  locked address is refused before its password is compared. The counters live under the panel's own
  key prefix, so one address has separate budgets at the two doors and nothing sent to
  `/api/v1/auth/login` can lock the panel out; the cost is that the panel is no longer slowed by an
  address already failing at the API's door. Behind a proxy, set `TRUSTED_PROXY_HOPS`, or every
  caller is counted as the proxy.
- **A second budget is shared by every address**, at five times `LOGIN_MAX_ATTEMPTS` in the same
  window (25 with the defaults). One password stands behind the panel, so without it a caller
  changing address guesses at that password without limit, each new address arriving with a full
  budget of its own. A login that succeeds gives back the attempt it made and leaves the failures
  that came from elsewhere counted.
- **Past the shared budget the panel refuses every address**, including one it has counted nothing
  against, for `LOGIN_LOCKOUT_BASE_SECONDS` (300s). Those failures keep counting for the rest of the
  900s window, so the first attempt after that lock ends, whoever sends it, locks the panel again
  for twice as long, and so on up to `LOGIN_LOCKOUT_MAX_SECONDS` (3600s); the rounds it has climbed
  are kept for an hour, and that hour starts again with every lockout. So a spray of about 26
  attempts can keep the panel shut for close to an hour, and every retry while it is shut, the
  operator's included, makes it longer. Each of those retries is also counted against the address it
  came from, so five of the operator's own tries lock their address too, with its own escalation.
  That is a door an attacker can close on purpose, which is the trade for a password that can be
  guessed at 25 times a window, and one more reason to keep the panel off the public internet
  ([Production Hardening](#production-hardening)).
- **To open the panel before the lockout ends**, clear the shared counters. They sit under the
  `admin-panel:rl:all:` key prefix, and the per-address ones under `admin-panel:rl:`, which the
  pattern below covers as well:

    ```bash
    # RATE_LIMITER_BACKEND=redis, on RATE_LIMITER_REDIS_DB (1 by default)
    redis-cli -n 1 --scan --pattern 'admin-panel:rl:*' | xargs redis-cli -n 1 del

    # RATE_LIMITER_BACKEND=database
    psql -c "delete from crudauth_counters where key like 'admin-panel:rl:%'"
    ```

    With `RATE_LIMITER_BACKEND=memory` the counters are in the process, so restarting it clears
    them. Clearing them gives the attacker their 25 guesses back, so change `ADMIN_PASSWORD` if the
    lockout is what a spray caused.
- **Each refusal is logged** on the `src.infrastructure.auth.audit` logger, in the lines a refused
  API login writes, naming the door, the caller and the username where the panel has that one:
  `login refused at the admin panel: 'admin' from 203.0.113.7 (curl/8.4.0); invalid_credentials`.
  See [what a refusal records](../authentication/sessions.md#what-a-refusal-records).
- Both credentials are compared with `hmac.compare_digest`, so a wrong guess costs the same time
  whatever its first bytes were.
- The session is signed with `SECRET_KEY` via the `SessionMiddleware` the panel mounts for itself.
- **A session lasts eight hours from the login that created it**, however busy the operator has
  been. It carries the time it was issued and a fingerprint of `ADMIN_USERNAME:ADMIN_PASSWORD`,
  derived with scrypt and salted with `SECRET_KEY`, and `authenticate` refuses it once either the
  eight hours are up or the fingerprint stops matching the configured credentials. The cookie is
  readable by whoever holds it, so the work factor is what keeps a password an operator chose out of
  reach of a word list run by somebody who also has the key. It is derived as the panel is built and
  kept for as long as the credentials it was made from, so no request waits for it. A refused
  session is cleared, so the browser stops sending the cookie. A session carrying neither field,
  which is what a cookie from a build before this one holds, is refused as well.
- Signing out clears the session (`request.session.clear()`), and takes a `POST`.

If you need multiple admin operators, see [User Management](user-management.md) for ways to extend this.

### Requests from another site

sqladmin carries no CSRF token, so two things stand between a signed-in operator and another site
driving the panel from their browser:

- **The cookie is `SameSite=Strict`**, so the browser sends it on nothing another site starts, a
  top-level link included. A link into the panel from elsewhere lands on the login page for that
  reason; opening the panel from the browser's own address bar signs you back in without asking for
  the password again. What `Strict` does not cover is a sibling subdomain: `other.example.com` is
  the same *site* as `admin.example.com`, so the cookie travels on its requests, which is why the
  guard below exists.
- **`SameOriginOnly` answers `403` to a request from elsewhere that could change something**
  (`interfaces/admin/origin.py`, mounted in front of the panel's session). That is `POST`, `PUT`,
  `PATCH` and `DELETE`, and also a `GET` of an action route (`/{identity}/action/{slug}`), since
  sqladmin serves every [`@action`](adding-models.md#bulk-actions) on a `GET` and the panel's own
  pages reach them through plain links. Each is refused unless the browser's `Sec-Fetch-Site` says
  `same-origin` or `none`, or the request's `Origin` names the host it arrived at. Every other
  `GET` is untouched, so links into the panel and its pages still work. A request carrying neither
  header is allowed, which is what keeps curl and scripts working: no site can make a browser send
  a request with no origin at all.

**Signing out takes a `POST`** for the same reason. sqladmin serves logout on `GET` and links to it
from every page, so anything that made the operator's browser fetch that URL signed them out, and
`SameSite=Lax` sent the cookie along. `/admin/logout` now answers a `GET` with a one-button form and
clears the session only on the `POST` that form sends, which the guard above holds to the panel's own
origin. The sidebar link still leads there; a bookmark or a link from elsewhere reaches the form
rather than signing anybody out.

## Mount Path

`ADMIN_BASE_URL` decides where the panel is mounted, and defaults to `/admin`:

```env
ADMIN_BASE_URL=/management
```

One setting feeds both the mount (`Admin(base_url=...)`) and the session cookie's `path`, so a panel
moved elsewhere keeps its login. Written with or without the slashes (`management`, `/management/`)
it comes out the same; a value that names no path at all is refused at startup.

Behind a proxy that serves the app under a prefix, the cookie follows the prefix too. A prefix set
with `--root-path /svc` reaches the app per request, so the panel scopes the cookie to the path the
request arrived through: `/svc/admin` with the default setting. Nothing needs configuring for that.

If you change it, also update any internal links in your frontend or operational docs.

!!! warning "Upgrading from a build before the cookie was scoped"

    Admin sessions created when the cookie had `path=/` keep being sent to every path until they
    expire (8 hours), and logging out only clears the cookie at the new path. Browsers send the
    longer-path cookie first and Starlette keeps the last value, so an old `path=/` cookie can
    outlive a logout. Clear the `admin_session` cookie in your browser once after upgrading, or
    change `SECRET_KEY` to invalidate every old admin session at once — which also signs every
    account out of the API, since crudauth keys its session store with `SECRET_KEY` too.

## Database Connection

SQLAdmin reuses the **same SQLAlchemy engine** the rest of the app uses (imported from `infrastructure/database/session.py`). There's no separate admin database connection or pool to configure.

## Session Cookies

The admin login uses Starlette's `SessionMiddleware`, which `AdminAuth` mounts on the panel's own
routes (`src/interfaces/admin/auth.py`). The API never carries it, so an API request never decodes
an admin cookie:

```python
self.middlewares = [
    Middleware(SameOriginOnly),
    Middleware(
        RootPathSessionMiddleware,
        base_url=base_url or admin_base_url(),
        secret_key=secret_key,
        session_cookie="admin_session",
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="strict",
        https_only=not local,
    ),
]
```

Cookie behavior:

- HTTP-only, signed with `SECRET_KEY`, named `admin_session`
- Scoped to the panel's mount path (`ADMIN_BASE_URL`, plus the app's `root_path`), so it isn't sent with API requests
- Same-site `strict`, so it travels on nothing another site starts
- `Secure` outside `local` and `development`
- Expires after 8 hours (`SESSION_MAX_AGE_SECONDS`)

Starlette re-signs the cookie whenever something writes to the session, which a
[flashed message](adding-models.md#bulk-actions) does, and that starts its `Max-Age` and its
signature's clock again. So the cookie's own expiry is not what bounds a session: the time the
session records at login is, and the panel refuses a session eight hours past it whatever the
cookie says. Changing either credential refuses every session created against the old pair,
which is the panel's only way of revoking one.

For production behind HTTPS, you'll typically want to:

1. Terminate TLS at the proxy / load balancer
2. Strip `/admin` from public-facing routing entirely (see [Production Hardening](#production-hardening) below)

## Development vs Production

### Development

The default `.env.example` is already development-ready:

```env
ENVIRONMENT=development
ADMIN_ENABLED=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Change-Me-Now-1!
SECRET_KEY=insecure-secret-key-change-this-in-production
```

Open <http://localhost:8000/admin>, log in, and you have access to Users and Tiers.

### Production Hardening

Three options, ordered by aggressiveness:

1. **Disable entirely**
    ```env
    ADMIN_ENABLED=false
    ```
    Simplest. The admin panel never mounts. Run admin tasks via scripts (`uv run --no-sync python -m scripts.setup_initial_data`, custom one-offs) or temporary overrides.

2. **Restrict at the proxy/load balancer**
    Keep `ADMIN_ENABLED=true` but only allow the `/admin` path from your VPN's CIDR range or a specific IP allowlist. The app stays the same; the network blocks public access.

3. **Use a strong unique password**
    If you can't restrict at the network layer, treat `ADMIN_PASSWORD` like a production secret:
    - Pull from a secrets manager at deploy time, never commit
    - Rotate periodically
    - Use a long, high-entropy password (the production security validator refuses to start the app if `SECRET_KEY` is the placeholder, or if the admin panel is enabled with empty credentials; weak admin passwords are logged as warnings)

The Production Security Validator (`infrastructure/security/`) checks several things at startup when `ENVIRONMENT=production`, including that `ADMIN_USERNAME`/`ADMIN_PASSWORD` are set whenever `ADMIN_ENABLED=true`. Be deliberate about what you set.

## Environment Detection

The admin panel itself doesn't change behavior between `local` / `development` / `staging` / `production` — it's the same SQLAdmin app. What changes is the surrounding environment:

- **Cookie security**: `https_only` follows `ENVIRONMENT` — off in `local` and `development`, on everywhere else
- **Logging**: admin actions go through the same logger configured by `infrastructure/logging/`
- **Session backend**: the panel's cookie is self-contained and signed, not the API's `SESSION_BACKEND` (Redis/memory). Restart-resilience for the *admin* login isn't relevant — admins re-log-in fine.

## Troubleshooting

### `/admin` returns 404
Check `ADMIN_ENABLED`. If it's `false` (or unset and Pydantic resolves to a falsy value), the admin app isn't mounted. Verify with:

```bash
cd backend
uv run --no-sync python -c "from src.infrastructure.config.settings import get_settings; print(get_settings().ADMIN_ENABLED)"
```

### Login form keeps rejecting credentials
- Confirm `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `backend/.env` match what you're typing
- Restart the app after changing env vars (settings are read at startup)
- If running in Docker, confirm the env vars are actually reaching the container (`docker compose exec api env | grep ADMIN_`)

### Admin session keeps logging out
The cookie expires 8 hours after login. To change that, edit `SESSION_MAX_AGE_SECONDS` in
`src/interfaces/admin/auth.py`:

```python
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8
```

### Wrong `engine` connection / "no such table"
The admin uses the same engine as the API, which means it requires `CREATE_TABLES_ON_STARTUP=true` (the default in local and development) or applied Alembic migrations. If `/admin` shows views but they're empty / error, check:

```bash
cd backend
uv run --no-sync alembic current
```

## Next Steps

- **[Adding Models](adding-models.md)** — Register your own models with the admin
- **[User Management](user-management.md)** — Extending admin authentication
- **[Production](../production.md)** — Production hardening checklist
