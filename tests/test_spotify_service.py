"""Unit tests for the Spotify service module."""

# pylint: disable=protected-access, duplicate-code

import asyncio

import respx

from config import settings
from services import spotify


def test_get_access_token(monkeypatch):
    """Spotify access token is fetched and cached."""
    monkeypatch.setattr(settings, "spotify_client_id", "id")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")
    spotify._access_token = None

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.post("https://accounts.spotify.com/api/token").respond(
                200, json={"access_token": "token"}
            )
            token1 = await spotify._get_access_token()
            token2 = await spotify._get_access_token()
            assert token1 == token2 == "token"
            assert mock.calls.call_count == 1

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())


def test_fetch_spotify_metadata(monkeypatch):
    """Spotify metadata is parsed correctly."""

    async def fake_token():  # pylint: disable=unused-argument
        return "token"

    spotify.spotify_cache.clear()
    monkeypatch.setattr(spotify, "_get_access_token", fake_token)

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get(
                "https://api.spotify.com/v1/search",
                params={
                    "q": "track:Song artist:Artist",
                    "type": "track",
                    "limit": 1,
                },
            ).respond(
                200,
                json={
                    "tracks": {
                        "items": [
                            {
                                "album": {
                                    "name": "Album",
                                    "release_date": "2011-09-09",
                                },
                                "duration_ms": 123000,
                            }
                        ]
                    }
                },
            )
            metadata = await spotify.fetch_spotify_metadata("Song", "Artist")
            assert metadata == {
                "album": "Album",
                "year": "2011",
                "duration_ms": 123000,
            }

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())
