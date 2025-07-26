"""Tests for ``remove_item_from_playlist`` in ``services.jellyfin``."""

import asyncio
import importlib
import sys
import types

# pylint: disable=too-few-public-methods


class DummyResp:
    """Simple stand-in for ``httpx.Response``."""

    def __init__(self, data=None, status_code=204):
        self._data = data or {}
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class DummyClient:
    """Async ``httpx`` client stub capturing call parameters."""

    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(
        self, method, url, headers=None, params=None, timeout=None, json=None
    ):
        """Record the call parameters and return a ``DummyResp``."""
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
                "json": json,
            }
        )
        if method == "GET":
            data = {"Items": [{"Id": "id1", "PlaylistItemId": "entry1"}]}
            return DummyResp(data=data, status_code=200)
        return DummyResp(status_code=204)

    async def get(self, url, headers=None, params=None, timeout=None):
        return await self.request(
            "GET", url, headers=headers, params=params, timeout=timeout
        )


class ClientFactory:
    """Return a fresh ``DummyClient`` each time ``AsyncClient`` is called."""

    def __init__(self):
        self.clients = []

    def __call__(self, *args, **kwargs):
        client = DummyClient()
        self.clients.append(client)
        return client


def test_remove_item_from_playlist(monkeypatch):
    """Jellyfin deletion call should use the correct URL params."""

    httpx_stub = types.ModuleType("httpx")
    factory = ClientFactory()
    httpx_stub.AsyncClient = factory
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
    # first call fetches playlist items
    assert factory.clients[0].calls[0]["method"] == "GET"
    assert (
        factory.clients[0].calls[0]["url"]
        == "http://jf/Users/u/Items?api_key=k&ParentId=pl"
    )

    delete_call = factory.clients[1].calls[0]
    assert delete_call["method"] == "DELETE"
    assert delete_call["url"] == "http://jf/Playlists/pl/Items"
    assert delete_call["params"]["EntryIds"] == "entry1"
    assert delete_call["params"]["UserId"] == "u"
    assert delete_call["headers"]["X-Emby-Token"] == "k"
    assert "Content-Type" not in delete_call["headers"]
