"""Shared HTTP clients with preconfigured timeouts."""

from __future__ import annotations

import importlib

import httpx

from config import settings


_client_long: httpx.AsyncClient | None = None
_client_short: httpx.AsyncClient | None = None
_httpx_module = httpx


def get_http_client(short: bool = False) -> httpx.AsyncClient:
    """Return a shared :class:`httpx.AsyncClient` instance.

    Args:
        short: Return the client configured with the short timeout.

    Returns:
        httpx.AsyncClient: The reusable client.
    """

    global _client_long, _client_short, _httpx_module  # pylint: disable=global-statement

    current_httpx = importlib.import_module("httpx")

    if short:
        if _client_short is None or _httpx_module is not current_httpx:
            _client_short = current_httpx.AsyncClient(
                timeout=settings.http_timeout_short
            )
            _httpx_module = current_httpx
        return _client_short

    if _client_long is None or _httpx_module is not current_httpx:
        _client_long = current_httpx.AsyncClient(timeout=settings.http_timeout_long)
        _httpx_module = current_httpx
    return _client_long


async def aclose_http_clients() -> None:
    """Close any instantiated HTTP clients."""

    global _client_long, _client_short  # pylint: disable=global-statement

    if _client_long is not None:
        await _client_long.aclose()
        _client_long = None

    if _client_short is not None:
        await _client_short.aclose()
        _client_short = None
