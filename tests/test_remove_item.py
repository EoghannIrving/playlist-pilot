"""Tests for ``remove_item_from_playlist`` in ``services.jellyfin``."""

import asyncio
import importlib
import sys
import types

# pylint: disable=too-few-public-methods


class DummyResp:
    """Simple stand-in for ``httpx.Response``."""

    status_code = 204

    def raise_for_status(self):
        """Pretend to validate the response status."""
        return None


class DummyClient:
    """Async ``httpx`` client stub capturing call parameters."""

    def __init__(self):
        self.called = {}

    async def __aenter__(self):
        """Enter the asynchronous context."""
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Exit without handling exceptions."""
        return False

    async def delete(self, url, params=None, headers=None, timeout=None):
        """Record the call parameters and return a ``DummyResp``."""
        self.called["url"] = url
        self.called["params"] = params
        self.called["headers"] = headers
        self.called["timeout"] = timeout
        return DummyResp()


def test_remove_item_from_playlist(monkeypatch):
    """Jellyfin deletion call should use the correct URL and params."""

    httpx_stub = types.ModuleType("httpx")
    client = DummyClient()
    httpx_stub.AsyncClient = lambda *a, **kw: client
    monkeypatch.setitem(sys.modules, "httpx", httpx_stub)
    sys.modules.pop("services.jellyfin", None)
    jellyfin = importlib.import_module("services.jellyfin")
    jellyfin.settings.jellyfin_url = "http://jf"
    jellyfin.settings.jellyfin_api_key = "k"
    jellyfin.settings.jellyfin_user_id = "u"

    result = asyncio.get_event_loop().run_until_complete(
        jellyfin.remove_item_from_playlist("pl", "entry1")
    )
    assert result is True
    assert client.called["url"] == "http://jf/Playlists/pl/Items"
    assert client.called["params"]["EntryIds"] == "entry1"
    assert client.called["headers"]["X-Emby-Token"] == "k"
