# Migrating Passwords

Moving an existing user base onto this boilerplate means moving their password hashes, and you
cannot turn a hash from one scheme into another — only the password itself can be rehashed, and you
do not have it. `legacy_verifiers` closes that gap: the old hashes come across as they are, and each
one is replaced with a crudauth hash the first time its owner signs in. Nobody resets a password,
and no password is stored in two schemes at once.

## Why the old hashes don't just work

crudauth stores `bcrypt(base64(sha256(password)))`. The SHA-256 step is a fixed-width transform, not
the work factor — bcrypt ignores input past 72 bytes, so hashing the password first makes the
comparison cover all of it. The consequence for a migration is that a hash another library wrote
with `bcrypt.hashpw(password, salt)` **never** matches crudauth's own check, even though both are
bcrypt. Those accounts would all answer `401` at login.

## Wiring a verifier

A verifier is `(plain_password, hashed_password) -> bool`. crudauth ships one for plain bcrypt:

```python
# infrastructure/auth/setup.py
from crudauth.utils import verify_plain_bcrypt

auth = CRUDAuth(
    ...,
    legacy_verifiers=[verify_plain_bcrypt],
)
```

At login, crudauth tries its own check first. Only if that fails does each verifier run, in a worker
thread. On a match the user is signed in and `hashed_password` is rewritten in crudauth's format, so
the verifier matters exactly once per account.

| Old scheme | What to pass |
|---|---|
| plain bcrypt (`bcrypt.hashpw`, `passlib`'s `bcrypt`) | `verify_plain_bcrypt` |
| passlib `bcrypt_sha256`, Django `BCryptSHA256PasswordHasher` | a verifier of your own: those pre-hash differently |
| Django's default PBKDF2, Argon2, scrypt, legacy MD5/SHA-1 | a verifier of your own, calling that library |

Write your own as a plain function and add it to the list:

```python
from passlib.hash import django_pbkdf2_sha256


def verify_django_pbkdf2(plain_password: str, hashed_password: str) -> bool:
    """Check a password against a hash Django's default hasher wrote."""
    try:
        return django_pbkdf2_sha256.verify(plain_password, hashed_password)
    except ValueError:
        return False


auth = CRUDAuth(..., legacy_verifiers=[verify_django_pbkdf2, verify_plain_bcrypt])
```

Several may be listed, which a migration from more than one source needs. A verifier that raises
counts as a non-match and is logged, so a broken one doesn't look like every migrated user typing
the wrong password — watch the log for `legacy verifier ... raised` after you deploy one.

!!! note "A verifier of your own can time how long a username takes"
    crudauth runs every verifier against a bcrypt dummy hash when the username is unknown, so a
    verifier for another scheme answers those instantly while a real migrated account pays its full
    cost. That difference tells a caller which usernames exist for as long as the verifier is
    configured, which is one more reason to remove it once the migration is done.
    `verify_plain_bcrypt` is unaffected: the dummy is bcrypt, so it costs the same either way.

!!! warning "A verifier must never accept a crudauth hash for anything but the real password"
    crudauth's own hashes are bcrypt, so a naive plain-bcrypt check would accept the base64 SHA-256
    digest crudauth bcrypts. An attacker holding an unsalted SHA-256 of a password — leaked from
    somewhere else entirely — could then type that digest and sign in. `verify_plain_bcrypt` refuses
    any password shaped like that digest (44 base64 characters decoding to 32 bytes) for exactly
    this reason. Keep the same guard in a verifier of your own, or verify with a library whose
    format cannot collide with bcrypt.

## Importing the rows

Copy each account's old hash straight into `user.hashed_password`. Nothing needs to mark it as
legacy: crudauth tries its own check first and falls back to the verifiers when that fails.

```python
await crud_users.create(
    db=db,
    object=UserCreateInternal(
        name=row.full_name,
        username=row.username,
        email=row.email,
        hashed_password=row.password,  # the old system's hash, as it is
    ),
)
```

Two things to know about what comes across:

- **The password policy isn't applied to a hash.** `PASSWORD_MIN_LENGTH` and the rest are checked
  when a password is *set* — registration, change, reset, `/set-password` — so a migrated password
  that wouldn't pass today still signs its owner in, and is rehashed as it is. Requiring the new
  policy means requiring a reset, not a verifier.
- **An account with no password** (one that only ever signed in with a provider) belongs in the
  database as `make_unusable_password()`, not as an empty string. `/api/v1/auth/login` then refuses
  it, and the account signs in with its provider or sets a password through the reset link, which
  proves the address first ([Passwords](sessions.md#passwords)).

## Finishing the migration

Each sign-in converts one account, so the verifier can go once every active account has signed in.
To see how far along you are, count the hashes that are not crudauth's. crudauth's are bcrypt over a
44-character base64 digest, which you cannot tell from a plain bcrypt hash by looking at it — so
record the migration at import time instead, in a column or a side table of your own, and clear each
row as its account signs in (crudauth's `on_after_login` hook is where to do it, next to
[the refusal audit](sessions.md#what-a-refusal-records)).

What is left after that are accounts that never came back. Expire them, or ask those users to reset
their password: `POST /api/v1/auth/password/reset-request` sends the email, and a reset writes a
crudauth hash like any other.

Keep the verifier only that long. It is a second way to verify a password, and every login that
fails crudauth's own check pays for it in a worker thread.

## Key Files

| Component | Location |
|---|---|
| `auth = CRUDAuth(...)`, where `legacy_verifiers` is passed | `backend/src/infrastructure/auth/setup.py` |
| `verify_plain_bcrypt`, `make_unusable_password` | crudauth's `crudauth.utils` |
| Tests covering a legacy sign-in and its rehash | `backend/tests/integration/auth/test_legacy_passwords.py` |

---

[← Sessions](sessions.md){ .md-button } [User Management →](user-management.md){ .md-button .md-button--primary }
