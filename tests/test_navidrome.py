"""Tests for the Navidrome adapter."""

import asyncio

import respx

from config import settings
from services.navidrome import NavidromeAdapter


def test_navidrome_adapter_capabilities():
    """The Navidrome adapter should report the expected capabilities."""
    adapter = NavidromeAdapter(url="http://nav", username="user", password="pass")
    assert adapter.backend_name() == "navidrome"
    assert adapter.requires_user_id() is False
    assert adapter.supports_lyrics() is True
    assert adapter.supports_path_resolution() is False


def test_navidrome_test_connection(monkeypatch):
    """Ping responses should validate Navidrome connectivity."""
    monkeypatch.setattr(settings, "media_url", "http://nav", raising=False)
    monkeypatch.setattr(settings, "media_username", "user", raising=False)
    monkeypatch.setattr(settings, "media_password", "pass", raising=False)

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            route = mock.get("http://nav/rest/ping.view").respond(
                200,
                json={"subsonic-response": {"status": "ok", "version": "1.16.1"}},
            )
            result = await NavidromeAdapter().test_connection()
            assert result["success"] is True
            request = route.calls[0].request
            assert request.url.params["u"] == "user"
            assert request.url.params["f"] == "json"

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())


def test_navidrome_list_audio_playlists(monkeypatch):
    """Playlist responses should be normalized correctly."""
    monkeypatch.setattr(settings, "media_url", "http://nav", raising=False)
    monkeypatch.setattr(settings, "media_username", "user", raising=False)
    monkeypatch.setattr(settings, "media_password", "pass", raising=False)

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get("http://nav/rest/getPlaylists.view").respond(
                200,
                json={
                    "subsonic-response": {
                        "status": "ok",
                        "playlists": {
                            "playlist": [{"id": "1", "name": "Mix", "songCount": 8}]
                        },
                    }
                },
            )
            playlists = await NavidromeAdapter().list_audio_playlists()
            assert playlists == [
                {"id": "1", "name": "Mix", "track_count": 8, "backend": "navidrome"}
            ]

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())


def test_navidrome_get_track_metadata(monkeypatch):
    """Search results should return the matching track metadata."""
    monkeypatch.setattr(settings, "media_url", "http://nav", raising=False)
    monkeypatch.setattr(settings, "media_username", "user", raising=False)
    monkeypatch.setattr(settings, "media_password", "pass", raising=False)

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get("http://nav/rest/search3.view").respond(
                200,
                json={
                    "subsonic-response": {
                        "status": "ok",
                        "searchResult3": {
                            "song": [
                                {"id": "x", "title": "Song", "artist": "Artist"},
                                {"id": "y", "title": "Other", "artist": "Else"},
                            ]
                        },
                    }
                },
            )
            metadata = await NavidromeAdapter().get_track_metadata("Song", "Artist")
            assert metadata == {"id": "x", "title": "Song", "artist": "Artist"}

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())
