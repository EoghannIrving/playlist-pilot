"""Tests for get_full_audio_library excluding incomplete entries."""

import asyncio
from core import playlist


class DummyCache(dict):
    """Simple dictionary-based cache used for tests."""

    def get(self, key):
        """Return cached value for ``key``."""
        return super().get(key)

    def set(self, key, value, expire=None):
        """Store ``value`` for ``key``; ``expire`` is ignored."""
        _ = expire
        self[key] = value


async def fake_jf_get(*_args, **_kwargs):
    """Return items with some missing fields."""
    return {
        "Items": [
            {"Name": "Song 1", "AlbumArtist": "Artist 1"},
            {"Name": "Song 2", "AlbumArtist": None},
            {"Name": None, "AlbumArtist": "Artist 3"},
            {"AlbumArtist": "Artist 4"},
            {"Name": "Song 5"},
        ]
    }


async def fake_jf_get_invalid_types(*_args, **_kwargs):
    """Return items with empty strings or non-string fields."""
    return {
        "Items": [
            {"Name": "Song 1", "AlbumArtist": "Artist 1"},
            {"Name": "", "AlbumArtist": "Artist 2"},
            {"Name": "Song 3", "AlbumArtist": ""},
            {"Name": 123, "AlbumArtist": "Artist 4"},
            {"Name": "Song 5", "AlbumArtist": ["Artist 5"]},
            {"Name": "  Song 6  ", "AlbumArtist": " Artist 6 "},
        ]
    }


def test_get_full_audio_library_skips_incomplete(monkeypatch):
    """Entries missing Name or AlbumArtist should be excluded."""
    monkeypatch.setattr(playlist, "jf_get", fake_jf_get)
    monkeypatch.setattr(playlist, "library_cache", DummyCache())
    monkeypatch.setattr(playlist.settings, "jellyfin_user_id", "user", raising=False)
    result = asyncio.get_event_loop().run_until_complete(
        playlist.get_full_audio_library(force_refresh=True)
    )
    assert result == ["Song 1 - Artist 1"]


def test_get_full_audio_library_strips_and_validates(monkeypatch):
    """Ensure empty or non-string fields are excluded and whitespace trimmed."""
    monkeypatch.setattr(playlist, "jf_get", fake_jf_get_invalid_types)
    monkeypatch.setattr(playlist, "library_cache", DummyCache())
    monkeypatch.setattr(playlist.settings, "jellyfin_user_id", "user", raising=False)
    result = asyncio.get_event_loop().run_until_complete(
        playlist.get_full_audio_library(force_refresh=True)
    )
    assert result == ["Song 1 - Artist 1", "Song 6 - Artist 6"]
