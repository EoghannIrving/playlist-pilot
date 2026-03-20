"""Tests for the ``services.lastfm`` helpers."""

import asyncio
import sys
import types
import importlib


def _load_lastfm_module(monkeypatch):
    """Import ``services.lastfm`` with stubbed dependencies."""

    monkeypatch.setitem(sys.modules, "httpx", types.ModuleType("httpx"))
    config_stub = types.ModuleType("config")
    config_stub.settings = types.SimpleNamespace(
        lastfm_api_key="", http_timeout_short=1, http_timeout_long=1
    )
    monkeypatch.setitem(sys.modules, "config", config_stub)
    cache_stub = types.ModuleType("utils.cache_manager")
    cache_stub.lastfm_cache = types.SimpleNamespace(
        get=lambda _k: None, set=lambda *_a, **_kw: None
    )
    cache_stub.CACHE_TTLS = {"lastfm": 1}
    monkeypatch.setitem(sys.modules, "utils.cache_manager", cache_stub)
    sys.modules.pop("services.lastfm", None)
    return importlib.import_module("services.lastfm")


def _load_normalize(monkeypatch):
    """Return the ``normalize`` helper from a stubbed lastfm module."""
    lastfm = _load_lastfm_module(monkeypatch)
    return lastfm.normalize


def test_normalize_basic(monkeypatch):
    """Parenthetical content and punctuation are removed."""
    normalize = _load_normalize(monkeypatch)
    assert normalize("Song Title (Live)") == "song title"


def test_normalize_multiple_parens(monkeypatch):
    """Repeated parentheses should be stripped without slowdown."""
    normalize = _load_normalize(monkeypatch)
    text = "(((Example)))"
    assert normalize(text) == ""


def test_normalize_long_spaces(monkeypatch):
    """Many spaces should not impact performance or output."""
    normalize = _load_normalize(monkeypatch)
    text = " " * 500 + "Example"
    assert normalize(text) == "example"


def test_normalize_long_open_parens(monkeypatch):
    """Strings starting with numerous '(' characters are handled."""
    normalize = _load_normalize(monkeypatch)
    text = "(" * 500 + "Example"
    assert normalize(text) == "example"


def test_normalize_accents(monkeypatch):
    """Accented characters should be converted to their ASCII equivalents."""
    normalize = _load_normalize(monkeypatch)
    assert normalize("Beyonc\u00e9") == "beyonce"


def test_enrich_with_lastfm_handles_missing_track_info(monkeypatch):
    """Track enrichment should still succeed when Last.fm lookup returns None."""
    lastfm = _load_lastfm_module(monkeypatch)

    async def fake_track_info(*_args, **_kwargs):
        return None

    async def fake_tags(*_args, **_kwargs):
        return ["holiday", "seasonal"]

    async def fake_artist_tags(*_args, **_kwargs):
        return ["crooner"]

    monkeypatch.setattr(lastfm, "get_lastfm_track_info", fake_track_info)
    monkeypatch.setattr(lastfm, "get_lastfm_tags", fake_tags)
    monkeypatch.setattr(lastfm, "get_lastfm_artist_tags", fake_artist_tags)

    result = asyncio.run(lastfm.enrich_with_lastfm("Song", "Artist"))
    assert result["listeners"] == 0
    assert result["album"] == ""
    assert result["releasedate"] == ""
    assert result["tags"] == ["holiday", "seasonal"]
    assert result["genre_tags"] == ["holiday", "seasonal", "crooner"]


def test_enrich_with_lastfm_merges_track_info_tags(monkeypatch):
    """Track-info tags should supplement sparse ``getTopTags`` responses."""
    lastfm = _load_lastfm_module(monkeypatch)

    async def fake_track_info(*_args, **_kwargs):
        return {
            "listeners": "42",
            "album": {"title": "Album", "releasedate": "1 Jan 1983"},
            "toptags": {
                "tag": [{"name": "new wave"}, {"name": "synth-pop"}, {"name": "pop"}]
            },
        }

    async def fake_tags(*_args, **_kwargs):
        return []

    async def fake_artist_tags(*_args, **_kwargs):
        return ["pop"]

    monkeypatch.setattr(lastfm, "get_lastfm_track_info", fake_track_info)
    monkeypatch.setattr(lastfm, "get_lastfm_tags", fake_tags)
    monkeypatch.setattr(lastfm, "get_lastfm_artist_tags", fake_artist_tags)

    result = asyncio.run(lastfm.enrich_with_lastfm("Song", "Artist"))

    assert result["listeners"] == 42
    assert result["album"] == "Album"
    assert result["releasedate"] == "1 Jan 1983"
    assert result["tags"] == ["new wave", "synth-pop", "pop"]
    assert result["genre_tags"] == ["new wave", "synth-pop", "pop"]
