"""Tests for Jellyfin and GPT helper functions using lightweight stubs."""

import os
import sys
import types
import importlib
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Stub httpx for jellyfin service
class DummyResp:
    """Simple stand-in for ``httpx.Response``."""

    def __init__(self, items):
        self._items = items
        self.status_code = 200

    def json(self):
        return {"Items": self._items}

    def raise_for_status(self):
        """Pretend to validate the response status."""
        pass

class DummyClient:
    """Async client stub used by ``make_httpx_stub``."""

    def __init__(self, items):
        self._items = items

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, *_args, **_kwargs):
        return DummyResp(self._items)

def make_httpx_stub(items):
    module = types.ModuleType("httpx")
    module.AsyncClient = lambda *a, **kw: DummyClient(items)
    return module

# Stub diskcache Cache used by jellyfin module
class DummyCache(dict):
    """Minimal ``diskcache.Cache`` replacement used for tests."""

    def get(self, _key):
        return None

    def set(self, _key, value, expire=None):
        _ = expire  # accept ``expire`` keyword for compatibility
        self[_key] = value

sys.modules["diskcache"] = types.ModuleType("diskcache")
sys.modules["diskcache"].Cache = DummyCache

# Stub utils.cache_manager used inside jellyfin
cache_stub = types.ModuleType("utils.cache_manager")
cache_stub.jellyfin_track_cache = DummyCache()
cache_stub.CACHE_TTLS = {"jellyfin_tracks": 1}
sys.modules["utils.cache_manager"] = cache_stub


def test_search_jellyfin_track_found(monkeypatch):
    """Return ``True`` when the Jellyfin API finds a matching item."""
    sys.modules["httpx"] = make_httpx_stub([{"Name": "My Song", "Artists": ["My Artist"]}])
    sys.modules.pop("services.jellyfin", None)
    jellyfin = importlib.import_module("services.jellyfin")  # import after stubbing
    monkeypatch.setattr(jellyfin, "jellyfin_track_cache", DummyCache())
    found = asyncio.get_event_loop().run_until_complete(
        jellyfin.search_jellyfin_for_track("My Song", "My Artist")
    )
    assert found is True


def test_search_jellyfin_track_not_found(monkeypatch):
    """Return ``False`` when the Jellyfin API returns no results."""
    sys.modules["httpx"] = make_httpx_stub([])
    sys.modules.pop("services.jellyfin", None)
    jellyfin = importlib.import_module("services.jellyfin")
    monkeypatch.setattr(jellyfin, "jellyfin_track_cache", DummyCache())
    found = asyncio.get_event_loop().run_until_complete(
        jellyfin.search_jellyfin_for_track("Other", "Artist")
    )
    assert found is False


def test_parse_gpt_line():
    """Validate GPT line parsing and popularity descriptions."""
    # Stub openai so importing services.gpt succeeds
    openai_stub = types.ModuleType("openai")
    class Dummy:
        def __init__(self, **kwargs):
            pass
    openai_stub.OpenAI = Dummy
    openai_stub.AsyncOpenAI = Dummy
    openai_stub.OpenAIError = Exception
    sys.modules["openai"] = openai_stub
    # Stub utils.cache_manager for gpt
    gpt_cache_stub = types.ModuleType("utils.cache_manager")
    gpt_cache_stub.prompt_cache = DummyCache()
    gpt_cache_stub.lastfm_cache = DummyCache()
    gpt_cache_stub.CACHE_TTLS = {"prompt": 1}
    sys.modules["utils.cache_manager"] = gpt_cache_stub
    gpt_mod = importlib.import_module("services.gpt")
    parse_gpt_line = gpt_mod.parse_gpt_line
    describe_popularity = gpt_mod.describe_popularity

    title, artist = parse_gpt_line("Song - Artist - Album - 2020 - Reason")
    assert title == "Song"
    assert artist == "Artist"

    assert describe_popularity(95) == "Global smash hit"
    assert describe_popularity(75) == "Mainstream favorite"
    assert describe_popularity(55) == "Moderately mainstream"
    assert describe_popularity(35) == "Niche appeal"
    assert describe_popularity(10) == "Obscure or local"
