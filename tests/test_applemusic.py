"""Unit tests for the Apple Music service module."""

import asyncio
import respx

from config import settings
from services import applemusic


def test_get_developer_token(monkeypatch):
    """Apple Music token retrieval caches tokens."""
    monkeypatch.setitem(settings.__dict__, "apple_client_id", "id")
    monkeypatch.setitem(settings.__dict__, "apple_client_secret", "secret")
    applemusic._access_token = None

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.post("https://apple.music.com/api/token").respond(
                200, json={"access_token": "token"}
            )
            token1 = await applemusic._get_developer_token()
            token2 = await applemusic._get_developer_token()
            assert token1 == token2 == "token"
            assert mock.calls.call_count == 1

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())


def test_fetch_applemusic_metadata(monkeypatch):
    """Apple Music metadata is parsed correctly."""

    async def fake_token():  # pylint: disable=unused-argument
        return "token"

    monkeypatch.setattr(applemusic, "_get_developer_token", fake_token)

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://api.music.apple.com/v1/catalog/us/search").respond(
                200,
                json={
                    "results": {
                        "songs": {
                            "data": [
                                {
                                    "attributes": {
                                        "albumName": "Album",
                                        "releaseDate": "2020-05-10",
                                        "durationInMillis": 250000,
                                    }
                                }
                            ]
                        }
                    }
                },
            )
            metadata = await applemusic.fetch_applemusic_metadata("Song", "Artist")
            assert metadata == {
                "album": "Album",
                "year": "2020",
                "duration_ms": 250000,
            }

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())
