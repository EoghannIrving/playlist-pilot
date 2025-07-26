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

    async def request(self, method, url, headers=None, json=None, timeout=None):
        """Record the call parameters and return a ``DummyResp``."""
        self.called["method"] = method
        self.called["url"] = url
        self.called["headers"] = headers
        self.called["json"] = json
        self.called["timeout"] = timeout
        return DummyResp()


def test_remove_item_from_playlist(monkeypatch):
    """Jellyfin deletion call should use the correct URL and JSON body."""

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
    assert client.called["method"] == "DELETE"
    assert client.called["url"] == "http://jf/Playlists/pl/Items"
    assert client.called["json"]["EntryIds"] == ["entry1"]
    assert client.called["headers"]["X-Emby-Token"] == "k"
    assert client.called["headers"]["Content-Type"] == "application/json"
