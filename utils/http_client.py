"""Shared HTTP clients with preconfigured timeouts."""

from __future__ import annotations

import importlib

import httpx

from config import settings


_CLIENT_LONG: httpx.AsyncClient | None = None
_CLIENT_SHORT: httpx.AsyncClient | None = None
_HTTPX_MODULE = httpx


def get_http_client(short: bool = False) -> httpx.AsyncClient:
    """Return a shared :class:`httpx.AsyncClient` instance.

    Args:
        short: Return the client configured with the short timeout.

    Returns:
        httpx.AsyncClient: The reusable client.
    """

    global _CLIENT_LONG, _CLIENT_SHORT, _HTTPX_MODULE  # pylint: disable=global-statement

    current_httpx = importlib.import_module("httpx")

    if short:
        if _CLIENT_SHORT is None or _HTTPX_MODULE is not current_httpx:
            _CLIENT_SHORT = current_httpx.AsyncClient(
                timeout=settings.http_timeout_short
            )
            _HTTPX_MODULE = current_httpx
        return _CLIENT_SHORT

    if _CLIENT_LONG is None or _HTTPX_MODULE is not current_httpx:
        _CLIENT_LONG = current_httpx.AsyncClient(timeout=settings.http_timeout_long)
        _HTTPX_MODULE = current_httpx
    return _CLIENT_LONG


async def aclose_http_clients() -> None:
    """Close any instantiated HTTP clients."""

    global _CLIENT_LONG, _CLIENT_SHORT  # pylint: disable=global-statement

    if _CLIENT_LONG is not None:
        await _CLIENT_LONG.aclose()
        _CLIENT_LONG = None

    if _CLIENT_SHORT is not None:
        await _CLIENT_SHORT.aclose()
        _CLIENT_SHORT = None
