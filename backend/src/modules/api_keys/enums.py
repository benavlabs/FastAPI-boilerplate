"""API Key management enums."""

from enum import StrEnum


class HTTPMethod(StrEnum):
    """HTTP method enumeration for API key usage tracking."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
