"""Recording what a key-authenticated request did, after the response has gone out."""

import ipaddress
import time
from datetime import UTC, datetime

from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from ...infrastructure.database.session import local_session
from ...infrastructure.logging import get_logger
from .schemas import KeyUsageCreate
from .service import APIKeyService
from .transport import UsedKey, used_key

logger = get_logger()

ENDPOINT_MAX_LENGTH = 255
ADDRESS_MAX_LENGTH = 45


def _address(resolved: str | None) -> str | None:
    """The address the transport resolved, or ``None`` when it is not one a row can hold."""
    if resolved is None or len(resolved) > ADDRESS_MAX_LENGTH:
        return None

    try:
        ipaddress.ip_address(resolved)
    except ValueError:
        return None

    return resolved


async def record(used: UsedKey, usage: KeyUsageCreate, used_at: datetime) -> None:
    """Stamp the key as used and write one usage row, each through a session of its own.

    The request's session is closed by the time this runs, and a failure here is logged
    rather than raised: the response has already gone out, and losing a usage row must
    not look like a failed request. The two writes are taken one at a time, so one of
    them failing still leaves the other written.

    ``used_at`` is when the request arrived, which is what the key is stamped with.
    """
    await _stamp_the_key(used, used_at)
    await _write_the_usage_row(used, usage)


async def _stamp_the_key(used: UsedKey, used_at: datetime) -> None:
    """Stamp the key with the time the request arrived and the address it came from."""
    try:
        async with local_session() as db:
            await APIKeyService().note_use(api_key_id=used.api_key_id, used_from=used.client_ip, used_at=used_at, db=db)
    except Exception:
        logger.exception(f"Could not stamp API key {used.api_key_id} as used")


async def _write_the_usage_row(used: UsedKey, usage: KeyUsageCreate) -> None:
    """Write the row this request became."""
    try:
        async with local_session() as db:
            await APIKeyService().record_usage(api_key_id=used.api_key_id, user_id=used.owner_id, usage_data=usage, db=db)
    except Exception:
        logger.exception(f"Could not record usage for API key {used.api_key_id}")


class KeyUsageMiddleware(BaseHTTPMiddleware):
    """Attaches a usage row to every response the transport stamped with a key.

    The write runs as the response's background task, so the client waits for none of
    it, and a request that carried no key, or that a filled window refused and recorded
    already, is stamped with nothing and recorded as nothing. The key is stamped with the
    time the request arrived, read here rather than where the write lands. The address is
    the one the transport resolved, not the socket's, so a row behind a proxy names the
    client rather than the proxy, and anything that is not an address is recorded as none.

    A row the schema refuses is logged and dropped, so the client keeps the status the
    handler gave it. A task the route set runs as well: that one belongs to the route's
    own response, which this middleware's response streams rather than replaces.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        arrived = datetime.now(UTC)
        response = await call_next(request)
        used = used_key(request)
        if used is None:
            return response

        recorded = used._replace(client_ip=_address(used.client_ip))
        try:
            usage = KeyUsageCreate(
                api_key_id=recorded.api_key_id,
                user_id=recorded.owner_id,
                endpoint=request.url.path[:ENDPOINT_MAX_LENGTH],
                method=request.method,
                status_code=response.status_code,
                response_time_ms=int((time.perf_counter() - started) * 1000),
                ip_address=recorded.client_ip,
                user_agent=request.headers.get("user-agent"),
            )
        except Exception:
            logger.exception(f"Could not describe usage for API key {recorded.api_key_id}")

            return response

        response.background = BackgroundTask(record, recorded, usage, arrived)

        return response
