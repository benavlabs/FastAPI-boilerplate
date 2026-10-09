"""The authentication transports this project registers beside the session one."""

from crudauth import Transport

from ..modules.api_keys.transport import APIKeyTransport

EXTRA_TRANSPORTS: tuple[Transport, ...] = (APIKeyTransport(),)
