import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Stub missing modules
sys.modules["httpx"] = types.ModuleType("httpx")

cache_mod = types.ModuleType("diskcache")
class DummyCache(dict):
    def get(self, k, default=None):
        return super().get(k, default)
    def set(self, k, v, expire=None):
        self[k] = v
cache_mod.Cache = DummyCache
sys.modules["diskcache"] = cache_mod

cache_mgr_stub = types.ModuleType("utils.cache_manager")
cache_mgr_stub.lastfm_cache = DummyCache()
cache_mgr_stub.CACHE_TTLS = {"lastfm": 60}
sys.modules["utils.cache_manager"] = cache_mgr_stub

from services import lastfm
import pytest


def test_normalize():
    assert lastfm.normalize("Foo (Live)") == "foo"
    assert lastfm.normalize("A&B!") == "ab"


def test_enrich_with_lastfm(monkeypatch):
    async def fake_get_info(title, artist):
        return {"listeners": "5000", "album": {"releasedate": "1 Jan 2001", "title": "Test"}}

    async def fake_get_tags(title, artist):
        return ["rock", "indie"]

    monkeypatch.setattr(lastfm, "get_lastfm_track_info", fake_get_info)
    monkeypatch.setattr(lastfm, "get_lastfm_tags", fake_get_tags)

    import asyncio
    data = asyncio.run(lastfm.enrich_with_lastfm("Song", "Artist"))

    assert data["exists"] is True
    assert data["listeners"] == 5000
    assert data["releasedate"] == "1 Jan 2001"
    assert data["album"] == "Test"
    assert data["tags"] == ["rock", "indie"]
