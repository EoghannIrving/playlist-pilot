"""Tests for additional helpers in ``core.playlist`` and ``utils.helpers``."""

# pylint: disable=exec-used

import ast
from pathlib import Path
import types
import asyncio
import pytest

from utils import helpers
from core import constants
from core.history import (
    save_whole_user_history,
    load_user_history,
    extract_date_from_label,
)


def _load_helpers_func(name):
    """Load a function from ``utils.helpers`` without importing the module."""
    src = Path("utils/helpers.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    module = ast.Module(body=[func], type_ignores=[])
    ns = {
        "settings": types.SimpleNamespace(jellyfin_user_id="user"),
        "load_user_history": load_user_history,
        "extract_date_from_label": extract_date_from_label,
    }
    exec(
        compile(module, filename=f"<helpers.{name}>", mode="exec"), ns
    )  # pylint: disable=exec-used
    return ns[name]


load_sorted_history = _load_helpers_func("load_sorted_history")


def _load_func(name):
    """Load a function from ``core.playlist`` without importing the module."""
    src = Path("core/playlist.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    assigns = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "GENRE_SYNONYMS" for t in n.targets)
    ]
    module = ast.Module(body=assigns + [func], type_ignores=[])
    ns = {}
    exec(
        compile(module, filename=f"<{name}>", mode="exec"), ns
    )  # pylint: disable=exec-used
    return ns[name]


parse_suggestion_line = _load_func("parse_suggestion_line")
infer_decade = _load_func("infer_decade")
normalize_genre = _load_func("normalize_genre")
estimate_tempo = _load_func("estimate_tempo")
extract_tag_value = _load_func("extract_tag_value")


def test_parse_suggestion_line_valid():
    """`parse_suggestion_line` returns the text and reason for valid lines."""
    text, reason = parse_suggestion_line("Song - Artist - Album - 2023 - Good")
    assert text == "Song - Artist - Album - 2023"
    assert reason == "Good"


def test_parse_suggestion_line_invalid():
    """Invalid lines should raise ``ValueError``."""
    with pytest.raises(ValueError):
        parse_suggestion_line("Bad Line")


def test_infer_decade_and_normalize_genre():
    """`infer_decade` and `normalize_genre` basic behaviour."""
    assert infer_decade("1994") == "1990s"
    assert infer_decade("oops") == "Unknown"
    assert normalize_genre("Alternative Rock") == "alternative"


def test_normalize_genre_none():
    """``normalize_genre`` should return an empty string for ``None`` input."""
    assert normalize_genre(None) == ""


def test_estimate_tempo_basic():
    """Ensure tempo estimation falls back to expected defaults."""
    assert estimate_tempo(250, "electronic") == 140
    assert estimate_tempo(400, "rock") == 120
    assert estimate_tempo(200, "hip hop") == 90
    assert estimate_tempo(500, "ambient") == 70


def test_extract_tag_value():
    """`extract_tag_value` should pull the value for a named tag."""
    tags = ["tempo:120", "mood:happy", "Tempo:130"]
    assert extract_tag_value(tags, "tempo") == "120"
    assert extract_tag_value(tags, "missing") is None
    assert extract_tag_value(["Tempo:120"], "tempo") == "120"


def test_load_sorted_history(monkeypatch, tmp_path):
    """``load_sorted_history`` should return entries sorted by date desc."""
    monkeypatch.setattr(constants, "USER_DATA_DIR", tmp_path)
    entries = [
        {"id": "1", "label": "Mix - 2023-01-01 10:00", "suggestions": []},
        {"id": "2", "label": "Mix - 2023-02-01 10:00", "suggestions": []},
    ]
    save_whole_user_history("user", entries)
    sorted_hist = load_sorted_history("user")
    assert sorted_hist[0]["id"] == "2"


class DummyCache(dict):
    """Minimal cache stub for helper tests."""

    def get(self, key):
        """Return cached value for ``key``."""
        return super().get(key)

    def set(self, key, value, expire=None):
        """Store ``value`` for ``key``; ``expire`` is ignored."""
        _ = expire
        self[key] = value

    def delete(self, key):
        """Delete ``key`` when present."""
        self.pop(key, None)


def test_get_cached_playlists_uses_cache_for_jellyfin(monkeypatch):
    """Jellyfin-backed playlist lookups should reuse the cached result."""

    calls = []

    async def fake_fetch(user_id):
        calls.append(user_id)
        return {"playlists": [{"id": str(len(calls)), "name": "Mix"}]}

    monkeypatch.setattr(helpers, "playlist_cache", DummyCache())
    monkeypatch.setattr(helpers, "fetch_audio_playlists", fake_fetch)
    monkeypatch.setattr(helpers, "CACHE_TTLS", {"playlists": 60})
    monkeypatch.setattr(helpers.settings, "media_backend", "jellyfin", raising=False)

    first = asyncio.run(helpers.get_cached_playlists("user-1"))
    second = asyncio.run(helpers.get_cached_playlists("user-1"))

    assert first == second
    assert calls == ["user-1"]


def test_get_cached_playlists_force_refresh_bypasses_cache(monkeypatch):
    """Forced refresh should fetch fresh playlist data even with a cache entry."""

    calls = []

    async def fake_fetch(user_id):
        calls.append(user_id)
        return {"playlists": [{"id": str(len(calls)), "name": f"Mix {len(calls)}"}]}

    monkeypatch.setattr(helpers, "playlist_cache", DummyCache())
    monkeypatch.setattr(helpers, "fetch_audio_playlists", fake_fetch)
    monkeypatch.setattr(helpers, "CACHE_TTLS", {"playlists": 60})
    monkeypatch.setattr(helpers.settings, "media_backend", "jellyfin", raising=False)

    first = asyncio.run(helpers.get_cached_playlists("user-1"))
    refreshed = asyncio.run(helpers.get_cached_playlists("user-1", force_refresh=True))

    assert first != refreshed
    assert calls == ["user-1", "user-1"]


def test_get_cached_playlists_bypasses_cache_for_navidrome(monkeypatch):
    """Navidrome-backed playlist lookups should not rely on stale cache data."""

    calls = []

    async def fake_fetch(user_id):
        calls.append(user_id)
        return {"playlists": [{"id": str(len(calls)), "name": f"Mix {len(calls)}"}]}

    monkeypatch.setattr(helpers, "playlist_cache", DummyCache())
    monkeypatch.setattr(helpers, "fetch_audio_playlists", fake_fetch)
    monkeypatch.setattr(helpers, "CACHE_TTLS", {"playlists": 60})
    monkeypatch.setattr(helpers.settings, "media_backend", "navidrome", raising=False)

    first = asyncio.run(helpers.get_cached_playlists("user-1"))
    second = asyncio.run(helpers.get_cached_playlists("user-1"))

    assert first != second
    assert calls == ["user-1", "user-1"]
