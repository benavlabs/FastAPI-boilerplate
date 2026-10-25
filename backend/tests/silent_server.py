"""A server that accepts a connection and never answers, for the readiness probes.

A probe is meant to give up on a server that takes the connection and then says nothing.
Pointing a test at an address nothing listens on can't show that: a router or the local
stack usually answers with a refusal, which the probe reports instead of timing out, so
the test fails whenever the network happens to behave that way. A socket on localhost that
accepts and stays silent blocks the probe for the same reason a wedged server would, with
nothing outside the machine involved.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

HOST = "127.0.0.1"


@asynccontextmanager
async def silent_server() -> AsyncIterator[int]:
    """The port of a server that reads whatever it is sent and never replies.

    It returns once the client goes away, so nothing is left running after the probe
    gives up and closes its socket.
    """

    async def hold(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read()
        writer.close()

    server = await asyncio.start_server(hold, HOST, 0)
    try:
        yield int(server.sockets[0].getsockname()[1])
    finally:
        server.close()
        await server.wait_closed()
