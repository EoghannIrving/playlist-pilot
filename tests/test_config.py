"""Tests for the configuration helper functions."""

import sys
import types

import pytest
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


def test_set_cache_ttls_updates_shared_dict(monkeypatch):
    """Updating cache TTLs should refresh the global TTL mapping."""
    cache_stub = _setup_cache_stub(monkeypatch)
    s = config.AppSettings()
    s.set_cache_ttls({"prompt": 42})
    assert cache_stub.CACHE_TTLS == {"prompt": 42}
    assert s.cache_ttls is cache_stub.CACHE_TTLS


def test_save_and_load_persists_apple_credentials(tmp_path, monkeypatch):
    """Apple Music credentials should be stored and reloaded."""

    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)
    to_save = config.AppSettings(apple_client_id="abc", apple_client_secret="xyz")

    config.save_settings(to_save)
    loaded = config.load_settings()

    assert loaded.apple_client_id == "abc"
    assert loaded.apple_client_secret == "xyz"


@pytest.mark.parametrize(
    "apple_client_id, apple_client_secret, missing",
    [
        ("id", "", "Apple Client Secret"),
        ("", "secret", "Apple Client ID"),
    ],
)
def test_validate_settings_requires_both_apple_fields(
    apple_client_id, apple_client_secret, missing
):
    """Validation should require both Apple fields when one is set."""

    s = config.AppSettings(
        jellyfin_url="u",
        jellyfin_api_key="k",
        jellyfin_user_id="id",
        openai_api_key="o",
        apple_client_id=apple_client_id,
        apple_client_secret=apple_client_secret,
    )
    with pytest.raises(ValueError) as exc:
        s.validate_settings()
    assert missing in str(exc.value)
