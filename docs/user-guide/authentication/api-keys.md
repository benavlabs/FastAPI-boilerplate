# API Keys

A key is for a program: a script, a server, an integration calling the API without a browser and
without a password. It belongs to an account, carries a scope of its own, and can be revoked on its
own. Keys come with the api_keys feature; a project without that feature has no key routes, no
`X-API-Key` transport and no usage tables. See [Composable Features](../composable-features.md).

## Creating a key

Minting a key is something an account does while signed in: every `/api/v1/api-keys/` route takes a
session and refuses a key, so no key can mint another. The account's address must be verified as
well, since an unverified one may belong to somebody else; an account that hasn't confirmed its
address answers `403` ([recovery flows](index.md#recovery-flows-email) sends the link).

```bash
curl -X POST http://localhost:8000/api/v1/api-keys/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token-from-login-response>" \
  -d '{
    "name": "Nightly importer",
    "permissions": ["user.read"],
    "usage_limits": {"requests_per_minute": 60, "requests_per_day": 10000},
    "expires_at": "2027-01-01T00:00:00Z"
  }'
```

```json
{
  "id": 1,
  "api_key": "fai_7Qd3kP0r_… shown once",
  "key_prefix": "7Qd3kP0r",
  "name": "Nightly importer",
  "permissions": ["user.read"],
  "usage_limits": {"requests_per_minute": 60, "requests_per_day": 10000},
  "expires_at": "2027-01-01T00:00:00Z",
  "is_active": true,
  "last_used_at": null
}
```

The full key is in `api_key` and appears **only** in this response — nothing stores it, so a lost
key is replaced rather than recovered. `key_prefix` is the readable handle: it identifies the key in
a listing without being a credential.

| Field | What it does |
|---|---|
| `name` | yours, for telling keys apart |
| `permissions` | the key's scope: registry permission names, each one the caller holds ([what a key holds](#what-a-key-holds)) |
| `usage_limits` | requests per window ([usage limits](#usage-limits)) |
| `expires_at` | when the key stops working; optional, and can later be brought forward but never pushed back |
| `key_metadata` | anything your project wants to hang off the key; never returned by the create route. Capped at 16 levels of nesting and 8 KB stored, so a value no read can serialize cannot be written |

## Calling with a key

```bash
curl http://localhost:8000/api/v1/auth/me -H "X-API-Key: fai_7Qd3kP0r_…"
```

```json
{"user_id": 1, "username": "importer", "email": "…", "is_superuser": false, "scopes": ["user.read"], "via": "apikey"}
```

The request is authenticated as the key's owner, with `transport="apikey"` on the principal. No CSRF
token is needed — CSRF guards a cookie the browser attaches by itself, and a key is sent
deliberately — and the answer carries no cookie, so a key request never becomes a session. When a
request carries both a session cookie and a key, the session wins.

A key that is unknown, malformed, revoked, expired, whose row holds a column no schema can read, or
whose owner a soft delete has taken out answers `401`. So does one of those on a route that otherwise answers anonymous callers: a
credential that is present and wrong is not an absent one.

## What a key holds

A key-authenticated request holds **its owner's permissions, narrowed to the key's scope**. The
scope only ever narrows: a permission the owner loses disappears from the key at its next request,
and a key scoped to nothing holds nothing beyond naming its owner.

```bash
curl http://localhost:8000/api/v1/permissions/me -H "X-API-Key: fai_…"
# → {"permissions": ["user.read"]}
```

A key's scope may name only permissions its creator holds when it is minted, so a key is never
stronger than the credential that made it, and **a key is never a superuser** — the flag reaches
ownership checks no scope can express. [Permissions](permissions.md#what-a-key-holds) has the detail
and the reasoning.

## What a key cannot do

These routes take a session and nothing else, so a key can neither escalate through them nor erase
its own tracks:

| Route | Why |
|---|---|
| `POST /api/v1/auth/change-password` | an account changes its own password while signed in |
| `POST /api/v1/auth/email/change-request` | the same, for the address a recovery flow would use |
| `POST /api/v1/auth/logout`, `/logout-all` | a key holds no session to end |
| `GET /api/v1/auth/sessions`, `DELETE /api/v1/auth/sessions/{handle}` | a key holds no device to list or sign out |
| `DELETE /api/v1/users/{username}` | a key must not close the account that issued it |
| every `/api/v1/api-keys/` route | a key must not mint, read, rescope or revoke a key, its own included |

Ownership is a separate axis from the scope: a key acts on what its owner owns. That is not a
licence of its own, though. Editing the owner's own profile takes `user.update` in the key's scope
as well, so a key minted for reading cannot rename the account behind it, and the routes above are
refused whatever a key is scoped to. A scope names only what its owner holds, so this takes that
owner holding `user.update` too: the rbac feature is where an ordinary account gets it, from a role
carrying it, and with no permission source configured only a superuser's keys hold it
([Permissions](permissions.md#api-key-scope)).

## Usage limits

A key may carry a request count per window, any or all of three:

```json
{"requests_per_minute": 60, "requests_per_hour": 1000, "requests_per_day": 10000}
```

Nothing else is accepted — a name no window counts answers `422`, so a limit that would enforce
nothing cannot be stored. Each window is counted per key id through the limiter behind the login
lockout, so the counts are shared by every worker unless `RATE_LIMITER_BACKEND=memory`
([rate limiting](../rate-limiting/index.md)).

A key that fills a window answers `429` with `Retry-After`. That happens as the key authenticates,
so it covers every route the key could reach, including those the API throttle leaves alone. A key
with no limits is not counted at all, and counting fails open: a limiter that can't be reached lets
the request through rather than taking the API down with it.

A key carrying more than one window is counted against them shortest first, and the first window it
fills refuses it. So a refusal costs nothing in the longer windows. Take one minute's worth of 1 and
one day's worth of 10: ten requests inside a minute are answered once and refused nine times, and
leave nine of the ten for the rest of the day rather than none. The window that refuses is counted
either way.

`Retry-After` names the time until the last window the key is still full in rolls, which can be a
longer window than the one that refused. The longer windows are read for it and never counted, so
the header does not send a client back on the minute while the day it has spent still refuses it.

A key the transport cannot use answers `401`, and with the ratelimit feature present that
refusal spends the budget an anonymous caller from the same address spends on that path, so a
flood of junk keys is bounded the way anonymous traffic is. A key that does resolve keeps its
owner's own budget, which junk from the same address never spends.

A limit stored before this vocabulary existed — anything outside those three names, or a value that
isn't a positive whole number — reads back as it is and counts for nothing, the way a stored
permission the registry no longer knows grants nothing.
`uv run --no-sync python scripts/cleanup_api_key_json.py` from `backend/`, or
`docker compose exec api python -m scripts.cleanup_api_key_json` in the container, rewrites those
rows: it keeps the windows the limiter
counts and drops the rest, so what remains is exactly what gets enforced. It logs what each key
lost, so a limit that was meant — `{"requests_per_day": "1000"}`, say, which was never enforced
because the count is a string — can be set again as a number. A key whose row holds one of those
shapes answers `401` at authentication, with a warning naming the key, rather than answering `500`
on every request it makes; the owner's listing still answers `500` for that row until the repair
runs.

## What a key's usage records

Every request a key authenticates writes one row, and so does the first refusal each of its
windows answers:

```bash
curl http://localhost:8000/api/v1/api-keys/1/usage -b cookies.txt
curl http://localhost:8000/api/v1/api-keys/1/analytics -b cookies.txt
curl http://localhost:8000/api/v1/api-keys/summary/user -b cookies.txt
```

The row carries the path, the method, the status the client actually got, how long the request took,
the address and the user agent. Refusals are recorded too, so an owner can see a key being throttled
or failing: every `500` from a route that raised, and the first `429` each window answers from the
key's own limits. The refusals after that one are answered and counted but not written, so a client
holding a key at its limit costs the limiter alone rather than a row and a stamp for every request
it makes. A session request records nothing.

A request a route refuses *before* the key is authenticated is the exception: the session-only
routes try the session transport alone, so nothing there resolves the key, and whether such a
request leaves a row depends on what else the route resolves first — with the ratelimit feature
present, its per-caller throttle resolves every transport and the row appears. The answer the client
gets (`401`) is the same either way.

The write runs as a background task after the response, so no client waits for it, and the same task
stamps `last_used_at` and `last_used_ip` on the key. Authenticating a request therefore writes
nothing itself. "Last used" trails by however long that task takes, and a process that dies before
it runs doesn't record that request at all.

The stamp and the row are two writes taken one at a time, so one of them failing leaves the other
written, with the failure logged. `last_used_at` is when the request arrived, not when its write
landed, and a key already stamped later than that keeps the stamp it has. So of two requests whose
writes land out of order, the key names the later request, time and address together.

Both the row and the key record the address the trusted-proxy boundary resolved
(`TRUSTED_PROXY_HOPS`), not the socket's, so a deployment behind a proxy records its clients rather
than the proxy. A forwarding header is the client's to write, so the address is recorded only when
it is one the column holds: anything else, and a request with no address at all, is recorded as
nothing. A row the usage schema refuses is logged and dropped, so a request keeps the status its
handler gave it. The user agent is a header, so it is the client's to write as well: the row keeps
the first 512 characters of it, which is what the owner reads back.

## How long the usage rows are kept

`KEY_USAGE_RETENTION_DAYS` (default 90) says how many days of rows to keep. Each row carries the
caller's address and user agent, one row per request, so the table holds personal data at request
volume. `0` keeps every row and prunes nothing, and a value below `0` is refused as the settings
load.

The rate limiter counts in its own store and reads none of these rows, so pruning changes nothing
about what a key is allowed. The analytics routes read no further back than what is kept (`days` is
capped at the retention, and at 365 where nothing is pruned), and `total_requests` and
`total_cost_microcents` in the user summary are totals over that window rather than over the key's
life. A project that bills from these rows has to aggregate them somewhere of its own before they
are pruned; the boilerplate doesn't bill. A key's own `last_used_at` and `last_used_ip` are stamped
on the key, not read from these rows, so they survive every prune.

With the taskiq feature the prune is a scheduled task, `api_keys:prune_usage`, which the scheduler
enqueues at 03:00 UTC:

```sh
cd backend
uv run --no-sync taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler
```

Nothing is pruned unless that scheduler runs next to a worker. Without the taskiq feature, the same
prune is a script for a system cron:

```bash
cd backend
python scripts/prune_key_usage.py
```

Either way it deletes 10,000 rows per statement, committing each batch, and logs how many rows it
deleted in all. With a retention of `0` the task returns without reading a row and the script says
nothing is configured to prune.

## Revoking, expiring and rotating

```bash
# Narrow a key, or bring its expiry forward
curl -X PATCH http://localhost:8000/api/v1/api-keys/1 \
  -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-Token: <token>" \
  -d '{"permissions": [], "expires_at": "2026-11-01T00:00:00Z"}'

# Revoke it
curl -X DELETE http://localhost:8000/api/v1/api-keys/1 -b cookies.txt -H "X-CSRF-Token: <token>"
```

Revoking is one way: a revoked key cannot be reactivated, and an expiry can be brought forward but
never pushed back, so neither route can be used to widen a key quietly. Rotate by creating the new
key, moving the client onto it, then revoking the old one — both work at once, and the usage rows
show when the old one stops being called.

**Recovering an account revokes its keys.** Each key records the owner's credential generation
(`owner_token_version`) as it is minted, and a key from an older generation answers `401`. Three
things move that generation on, all of them someone taking the account back: changing the password,
completing a password reset, and claiming the account through an OAuth provider. So a key minted
from a stolen session dies when the owner resets their password, and a key minted under an address
somebody else later proves they own dies when they claim it.

Ending sessions is not one of those: `POST /auth/logout-all` signs every device out and leaves the
keys working, because a key holds no session. Revoke a key you believe has leaked.

## How a key is stored

A key is `secrets.token_urlsafe(48)` — 48 random bytes, 384 bits, generated by the server — stored as
`sha256$<digest>` of itself. The digest is deterministic, so a request finds its row through one
indexed lookup on `key_hash`.

!!! note "Why not a slow hash"
    A work factor (bcrypt, scrypt, Argon2) exists to make *guessing* expensive, which matters for a
    password a human chose. There is nothing to guess here: a key is server-generated randomness, so
    a slow hash buys no security — and it costs. An earlier version used scrypt, which made every
    request pay a derivation and, because `key_prefix` appears in listings, let anybody holding a
    prefix make the server pay it on junk requests. A code scanner may flag SHA-256 on something it
    reads as a password; for this column that reading is wrong. Account passwords in this project
    are hashed by crudauth with bcrypt and are not involved.

A key stored by an older version under a salted scrypt hash still authenticates, found by prefix
and verified the old way, and its row is rewritten as a digest the first time it is used. That
rewrite is a write of its own rather than part of the request's transaction, so a request that
fails afterwards leaves it done, and a rewrite that fails leaves the key valid with the next use
trying it again. Until then, every request carrying that key's prefix costs a derivation, not just
the ones its owner makes: the prefix is in the owner's listing, so whoever holds it can ask for
that work as often as they like. Only a row a request could authenticate with is verified against,
so a key that is revoked or has expired costs nothing, and a key that gets used costs nothing from
then on.

`uv run --no-sync python scripts/revoke_scrypt_api_keys.py` from `backend/`, or
`docker compose exec api python -m scripts.revoke_scrypt_api_keys` in the container, names the keys
still stored that way with the prefix and the name their owners see, so the owners can be told to
mint new ones. Run with `--revoke` it deactivates them, which ends the cost without waiting for a
key to be used, and leaves every key stored as a digest alone.

## `X-API-Key` in the interactive docs

`/docs` has no field for the key: the header is not declared as an OpenAPI security scheme. A global
declaration would claim every route accepts a key, which isn't true — the routes above refuse one —
and per-route declarations would have to be kept in step with those refusals by hand. To add one
anyway, give the routes that should advertise it a dependency of their own:

```python
from fastapi import Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@router.get("/widgets/", dependencies=[Security(api_key_header)])
async def list_widgets(...): ...
```

The transport authenticates the request either way; the scheme only tells the document, and Swagger,
that the header is expected.

## Key Files

| Component | Location |
|---|---|
| Transport (`X-API-Key`) | `backend/src/modules/api_keys/transport.py` |
| Service (minting, validation, usage) | `backend/src/modules/api_keys/service.py` |
| Usage recorder (middleware) | `backend/src/modules/api_keys/usage.py` |
| Limit windows | `backend/src/modules/api_keys/limits.py` |
| Retention and pruning | `backend/src/modules/api_keys/retention.py` |
| Scheduled prune (with taskiq) | `backend/src/modules/api_keys/tasks.py` |
| Prune script (without taskiq) | `backend/scripts/prune_key_usage.py` |
| Script for the keys still on scrypt | `backend/scripts/revoke_scrypt_api_keys.py` |
| Routes | `backend/src/modules/api_keys/routes.py` |
| Models (`APIKey`, `KeyUsage`) | `backend/src/modules/api_keys/models.py` |
| Transport registration | `backend/src/wiring/transports.py` |
