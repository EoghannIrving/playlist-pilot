"""Tests for Jellyfin helpers and adapter behavior."""

import asyncio

import services.jellyfin as jellyfin_module
from services.jellyfin import JellyfinAdapter, strip_lrc_timecodes


def test_strip_timecodes_basic():
    """Timecodes preceding lyrics should be removed."""
    line = "[01:23.45]Lyrics"
    assert strip_lrc_timecodes(line) == "Lyrics"


def test_strip_timecodes_preserves_annotation():
    """Annotation brackets without timecodes remain unchanged."""
    line = "[Chorus]"
    assert strip_lrc_timecodes(line) == "[Chorus]"


def test_strip_timecodes_combined_with_annotation():
    """Only timecodes are stripped when combined with annotations."""
    line = "[02:03.45][Chorus]Lyrics"
    assert strip_lrc_timecodes(line) == "[Chorus]Lyrics"


def test_jellyfin_adapter_capabilities():
    """The Jellyfin adapter should report its static capabilities."""
    adapter = JellyfinAdapter()
    assert adapter.backend_name() == "jellyfin"
    assert adapter.requires_user_id() is True
    assert adapter.supports_lyrics() is True
    assert adapter.supports_path_resolution() is True


def test_jellyfin_adapter_delegates_track_metadata(monkeypatch):
    """Track metadata requests should delegate to the existing helper."""

    async def fake_fetch(title, artist):
        assert title == "Song"
        assert artist == "Artist"
        return {"Id": "123"}

    monkeypatch.setattr(jellyfin_module, "fetch_jellyfin_track_metadata", fake_fetch)
    adapter = JellyfinAdapter()
    result = asyncio.run(adapter.get_track_metadata("Song", "Artist"))
    assert result == {"Id": "123"}
