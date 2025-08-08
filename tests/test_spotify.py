"""Tests for Spotify metadata fetching and track enrichment."""

import asyncio

from config import settings
from core import playlist


def test_fetch_spotify_metadata_without_credentials(monkeypatch):
    """Return None when Spotify credentials are absent."""

    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    result = asyncio.run(playlist.fetch_spotify_metadata("Song", "Artist"))
    assert result is None


def test_enrich_track_uses_spotify(monkeypatch):
    """Ensure Spotify data is used to enrich tracks when credentials are present."""

    async def fake_fetch(title, artist):  # pylint: disable=unused-argument
        return {"album": "Album", "year": "2000", "duration_ms": 123000}

    monkeypatch.setattr(settings, "spotify_client_id", "id")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")
    monkeypatch.setattr(playlist, "fetch_spotify_metadata", fake_fetch)

    async def fake_lastfm(title, artist):  # pylint: disable=unused-argument
        return {"tags": [], "listeners": 0, "album": ""}

    monkeypatch.setattr(playlist, "enrich_with_lastfm", fake_lastfm)

    track = {
        "title": "Song",
        "artist": "Artist",
        "album": "",
        "year": "",
        "RunTimeTicks": 0,
        "Genres": [],
    }
    enriched = asyncio.run(playlist.enrich_track(track))
    assert enriched.album == "Album"
    assert enriched.RunTimeTicks == 123000 * 10000
    assert enriched.FinalYear == "2000"
