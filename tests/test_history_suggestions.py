"""Tests for playlist history helper functions."""

import sys
import types
import importlib
import asyncio

from core import constants
from config import settings

# Disable import-outside-toplevel for tests where patching requires late imports
# pylint: disable=import-outside-toplevel


def _make_cache_stub():
    """Create a dummy cache module for monkeypatching."""
    module = types.ModuleType("utils.cache_manager")
    module.prompt_cache = DummyCache()
    module.yt_search_cache = DummyCache()
    module.lastfm_cache = DummyCache()
    module.playlist_cache = DummyCache()
    module.LASTFM_POP_CACHE = DummyCache()
    module.jellyfin_track_cache = DummyCache()
    module.bpm_cache = DummyCache()
    module.library_cache = DummyCache()
    module.CACHE_TTLS = {
        "prompt": 1,
        "youtube": 1,
        "lastfm": 1,
        "playlists": 1,
        "lastfm_popularity": 1,
        "jellyfin_tracks": 1,
        "bpm": 1,
        "full_library": 1,
    }
    return module


class DummyCache(dict):
    """Simple dictionary-based cache used for tests."""

    def get(self, key):
        """Return cached value for ``key``."""
        return super().get(key)

    def set(self, key, value, expire=None):
        """Store ``value`` for ``key``; ``expire`` is ignored."""
        _ = expire
        self[key] = value


def test_persist_history_and_load(monkeypatch, tmp_path):
    """Ensure suggestions are persisted and can be reloaded from history."""
    monkeypatch.setattr(constants, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "jellyfin_user_id", "user", raising=False)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    sys.modules["utils.cache_manager"] = _make_cache_stub()
    sys.modules.pop("core.m3u", None)
    sys.modules.pop("core.history", None)
    from core.m3u import persist_history_and_m3u
    from core.history import load_user_history

    suggestions = [
        {
            "text": "Song - Artist - Album - 2020 - Reason",
            "title": "Song",
            "artist": "Artist",
        }
    ]
    m3u = persist_history_and_m3u(suggestions, "Mix")
    assert m3u.exists()

    history = load_user_history("user")
    assert history
    assert history[0]["suggestions"] == suggestions
    assert "id" in history[0]


def test_enrich_suggestion_incomplete():
    """enrich_suggestion returns None for incomplete input."""
    sys.modules["utils.cache_manager"] = _make_cache_stub()
    sys.modules.pop("core.playlist", None)
    from core import playlist

    result = asyncio.get_event_loop().run_until_complete(
        playlist.enrich_suggestion({"text": "Bad", "title": "", "artist": ""})
    )
    assert result is None


def test_enrich_suggestion_service_failures(monkeypatch):
    """enrich_suggestion gracefully handles service failures."""

    async def fail(*_a, **_k):
        raise RuntimeError("fail")

    sys.modules["utils.cache_manager"] = _make_cache_stub()
    sys.modules.pop("core.playlist", None)
    from core import playlist

    monkeypatch.setattr(playlist, "fetch_jellyfin_track_metadata", fail)
    monkeypatch.setattr(playlist, "get_youtube_url_single", fail)
    monkeypatch.setattr(playlist, "enrich_track", fail)

    result = asyncio.get_event_loop().run_until_complete(
        playlist.enrich_suggestion(
            {
                "text": "Title - Artist - Album - 2020 - Reason",
                "title": "Title",
                "artist": "Artist",
            }
        )
    )
    assert result is None


def test_lastfm_info_failure(monkeypatch):
    """get_lastfm_track_info returns None on HTTP errors."""
    httpx_stub = types.ModuleType("httpx")

    class Client:
        """Minimal async client that always fails requests."""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_a, **_k):
            """Simulate a request failure."""
            raise RuntimeError("fail")

    httpx_stub.AsyncClient = lambda *a, **kw: Client()
    sys.modules["httpx"] = httpx_stub
    sys.modules["utils.cache_manager"] = _make_cache_stub()
    sys.modules.pop("services.lastfm", None)
    lastfm = importlib.import_module("services.lastfm")
    monkeypatch.setattr(lastfm, "lastfm_cache", DummyCache())
    monkeypatch.setattr(lastfm, "CACHE_TTLS", {"lastfm": 1})

    result = asyncio.get_event_loop().run_until_complete(
        lastfm.get_lastfm_track_info("Song", "Artist")
    )
    assert result is None
