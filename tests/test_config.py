"""Tests for the configuration helper functions."""

import sys
import types

import config

# pylint: disable=no-member,too-few-public-methods


def test_load_settings_creates_file(tmp_path, monkeypatch):
    """``load_settings`` should create a new file with defaults."""

    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)

    settings = config.load_settings()

    assert settings_file.exists()
    assert settings_file.read_text(encoding="utf-8") == "{}"
    assert isinstance(settings, config.AppSettings)


def test_load_settings_handles_invalid_json(tmp_path, monkeypatch):
    """An invalid JSON file should be reset and not raise an error."""

    settings_file = tmp_path / "settings.json"
    settings_file.write_text("bad json", encoding="utf-8")
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)

    settings = config.load_settings()

    assert settings_file.read_text(encoding="utf-8") == "{}"
    assert isinstance(settings, config.AppSettings)


class DummyCache:
    """Minimal cache object tracking ``clear`` calls."""

    def __init__(self):
        self.cleared = False

    def clear(self):
        """Mark this cache as cleared."""
        self.cleared = True


def _setup_cache_stub(monkeypatch):
    """Create and register a fake ``utils.cache_manager`` module."""

    cache_stub = types.ModuleType("utils.cache_manager")
    cache_stub.prompt_cache = DummyCache()
    cache_stub.yt_search_cache = DummyCache()
    cache_stub.lastfm_cache = DummyCache()
    cache_stub.playlist_cache = DummyCache()
    cache_stub.LASTFM_POP_CACHE = DummyCache()
    cache_stub.jellyfin_track_cache = DummyCache()
    cache_stub.bpm_cache = DummyCache()
    cache_stub.library_cache = DummyCache()
    cache_stub.CACHE_TTLS = {}
    monkeypatch.setitem(sys.modules, "utils.cache_manager", cache_stub)
    return cache_stub


def test_clear_single_cache(monkeypatch):
    """Only the specified cache should be cleared."""
    cache_stub = _setup_cache_stub(monkeypatch)
    config.AppSettings().clear_cache("prompt")
    assert cache_stub.prompt_cache.cleared
    assert not cache_stub.yt_search_cache.cleared


def test_clear_all_caches(monkeypatch):
    """Calling without arguments clears every cache."""
    cache_stub = _setup_cache_stub(monkeypatch)
    config.AppSettings().clear_cache()
    caches = [
        cache_stub.prompt_cache,
        cache_stub.yt_search_cache,
        cache_stub.lastfm_cache,
        cache_stub.playlist_cache,
        cache_stub.LASTFM_POP_CACHE,
        cache_stub.jellyfin_track_cache,
        cache_stub.bpm_cache,
        cache_stub.library_cache,
    ]
    assert all(c.cleared for c in caches)
