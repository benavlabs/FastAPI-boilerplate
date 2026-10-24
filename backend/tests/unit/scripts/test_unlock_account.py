"""Clearing the login lockout an account is held in.

The lock is keyed by the identifier a login submitted, counting failures from every
address, so anybody who knows a username can hold an account in it. The address's own
lock is whoever filled it, and expires; the account's is what this script clears.
"""

import itertools

import pytest
from crudauth.ratelimit.constants import LOCKOUT_NAMESPACE
from crudauth.utils import canonical_identifier
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import scripts.unlock_account as unlock_module
from scripts.seed_errors import SeedError
from scripts.unlock_account import unlock_account
from src.infrastructure.auth.setup import auth as crud_auth
from src.infrastructure.config.settings import settings
from src.modules.user.models import User

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("through_the_test_database")]

_addresses = (f"203.0.113.{number}" for number in itertools.count(1))


@pytest.fixture
def through_the_test_database(monkeypatch, db_session: AsyncSession):
    """The script opens its own session, which outside a test is the app's engine."""
    monkeypatch.setattr(
        unlock_module,
        "local_session",
        async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )


@pytest.fixture
def behind_a_proxy(monkeypatch):
    """Each login names its own client address, as a flood from many of them would."""
    monkeypatch.setattr(crud_auth.runtime, "trusted_proxy_hops", 1)


async def _login(client: AsyncClient, identifier: str, password: str) -> int:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": identifier, "password": password},
        headers={"X-Forwarded-For": next(_addresses)},
    )

    return response.status_code


async def _lock(client: AsyncClient, identifier: str) -> None:
    """Fill the identifier's failure budget, each attempt from an address of its own."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert await _login(client, identifier, "wrong-password") == 401


async def test_failures_from_one_address_after_another_lock_the_account(client: AsyncClient, test_user: dict, behind_a_proxy):
    """The per-identifier lock is the tradeoff: knowing a username is enough to hold it."""
    await _lock(client, test_user["username"])

    assert await _login(client, test_user["username"], test_user["password"]) == 429


@pytest.mark.parametrize("named_by", ["username", "email"])
async def test_the_script_clears_it(client: AsyncClient, test_user: dict, behind_a_proxy, named_by: str):
    """Either identifier names the account, since either is what an operator is given."""
    await _lock(client, test_user["username"])

    cleared = await unlock_account(test_user[named_by])

    assert cleared == (test_user["username"], test_user["email"])
    assert await _login(client, test_user["username"], test_user["password"]) == 200


async def test_the_identifier_the_lock_was_filled_under_is_cleared_too(client: AsyncClient, test_user: dict, behind_a_proxy):
    """A login submits either, so an account can be held under the one its owner never types."""
    await _lock(client, test_user["email"])

    await unlock_account(test_user["username"])

    assert await _login(client, test_user["email"], test_user["password"]) == 200


async def test_an_identifier_no_account_holds_is_refused(client: AsyncClient, test_user: dict):
    with pytest.raises(SeedError, match="No account holds"):
        await unlock_account("nobody-at-all")


class TestAClearThatDoesNotLand:
    """A recovery tool that reports success while the account stays locked is the worst case."""

    async def test_a_limiter_that_cannot_be_reached_is_an_error(self, client: AsyncClient, test_user: dict, monkeypatch):
        """``record_login_success`` logs the failure and returns, so the read has to catch it."""

        class Unreachable:
            async def delete(self, key: str) -> bool:
                raise ConnectionError("limiter is down")

            async def get_count(self, key: str) -> int:
                raise ConnectionError("limiter is down")

            async def get_ttl(self, key: str) -> int:
                raise ConnectionError("limiter is down")

            async def increment(self, key: str, amount: int, expire: int) -> int:
                raise ConnectionError("limiter is down")

        monkeypatch.setattr(crud_auth.runtime.lockout, "backend", Unreachable())

        with pytest.raises(SeedError, match="Could not reach the login limiter"):
            await unlock_account(test_user["username"])

    @pytest.mark.parametrize(("locked_for", "failures"), [(120, 0), (0, 5)])
    async def test_what_survives_the_clear_is_an_error(
        self, client: AsyncClient, test_user: dict, monkeypatch, locked_for: int, failures: int
    ):
        """What the backend reports after the clear, not what the clear was asked to do, is the answer.

        A lock still in place refuses the next login, and failures still counted at the cap
        lock it again on the first one.
        """

        class Unmoved:
            async def delete(self, key: str) -> bool:
                return True

            async def get_count(self, key: str) -> int:
                return failures

            async def get_ttl(self, key: str) -> int:
                return locked_for

            async def increment(self, key: str, amount: int, expire: int) -> int:
                return 1

        monkeypatch.setattr(crud_auth.runtime.lockout, "backend", Unmoved())

        with pytest.raises(SeedError, match="still holds the lock"):
            await unlock_account(test_user["username"])

    async def test_the_read_names_the_identifier_the_limiter_keyed_it_under(
        self, client: AsyncClient, test_user: dict, db_session: AsyncSession, monkeypatch
    ):
        """An address is keyed in its canonical form, so a read of what was typed would miss it."""
        stored = test_user["email"].upper()
        await db_session.execute(update(User).where(User.id == test_user["id"]).values(email=stored))
        await db_session.commit()
        locked = f"{LOCKOUT_NAMESPACE}:lock:user:{canonical_identifier(stored)}"

        class Unmoved:
            async def delete(self, key: str) -> bool:
                return True

            async def get_count(self, key: str) -> int:
                return 0

            async def get_ttl(self, key: str) -> int:
                return 120 if key == locked else 0

            async def increment(self, key: str, amount: int, expire: int) -> int:
                return 1

        monkeypatch.setattr(crud_auth.runtime.lockout, "backend", Unmoved())

        with pytest.raises(SeedError, match="still holds the lock"):
            await unlock_account(stored)


async def test_an_address_stored_before_it_was_canonicalised_still_names_the_account(
    client: AsyncClient, test_user: dict, db_session: AsyncSession, behind_a_proxy
):
    """A row from before the addresses were rewritten is matched ignoring case."""
    stored = test_user["email"].upper()
    await db_session.execute(update(User).where(User.id == test_user["id"]).values(email=stored))
    await db_session.commit()
    await _lock(client, test_user["username"])

    cleared = await unlock_account(stored)

    assert cleared == (test_user["username"], stored)
    assert await _login(client, test_user["username"], test_user["password"]) == 200
