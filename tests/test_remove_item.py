import asyncio
import importlib
import sys
import types


class DummyResp:
    status_code = 204

    def raise_for_status(self):
        return None


class DummyClient:
    def __init__(self):
        self.called = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def delete(self, url, params=None, timeout=None):
        self.called["url"] = url
        self.called["params"] = params
        self.called["timeout"] = timeout
        return DummyResp()


def test_remove_item_from_playlist(monkeypatch):
    httpx_stub = types.ModuleType("httpx")
    client = DummyClient()
    httpx_stub.AsyncClient = lambda *a, **kw: client
    sys.modules["httpx"] = httpx_stub
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
    assert client.called["params"]["entryIds"] == "entry1"
