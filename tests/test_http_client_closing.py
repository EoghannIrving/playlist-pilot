"""Tests for shared HTTP client closing."""

import asyncio
import importlib
import sys

import httpx


def test_aclose_http_clients_closes_clients() -> None:
    """Shared HTTP clients are closed when ``aclose_http_clients`` is called."""

    async def _run() -> None:
        sys.modules["httpx"] = httpx
        sys.modules.pop("utils.http_client", None)
        http_client_module = importlib.import_module("utils.http_client")
        long_client = http_client_module.get_http_client()
        short_client = http_client_module.get_http_client(short=True)

        assert not long_client.is_closed
        assert not short_client.is_closed

        await http_client_module.aclose_http_clients()

        assert long_client.is_closed
        assert short_client.is_closed

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())
