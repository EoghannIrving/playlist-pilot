import asyncio
import respx

from config import settings
from services import spotify, applemusic
from core import playlist


class DummyCache(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value, expire=None):
        self[key] = value


def test_spotify_metadata_caching(monkeypatch):
    monkeypatch.setattr(spotify, "spotify_cache", DummyCache())

    async def fake_token():
        return "token"

    monkeypatch.setattr(spotify, "_get_access_token", fake_token)

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://api.spotify.com/v1/search").respond(
                200,
                json={
                    "tracks": {
                        "items": [
                            {
                                "album": {
                                    "name": "Album",
                                    "release_date": "2000-01-01",
                                },
                                "duration_ms": 123000,
                            }
                        ]
                    }
                },
            )
            meta1 = await spotify.fetch_spotify_metadata("Song", "Artist")
            meta2 = await spotify.fetch_spotify_metadata("Song", "Artist")
            assert (
                meta1
                == meta2
                == {
                    "album": "Album",
                    "year": "2000",
                    "duration_ms": 123000,
                }
            )
            assert len(spotify.spotify_cache) == 1
            assert mock.calls.call_count == 1

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())


def test_apple_music_metadata_caching(monkeypatch):
    monkeypatch.setattr(applemusic, "apple_music_cache", DummyCache())

    async def fake_token():
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
            meta1 = await applemusic.fetch_applemusic_metadata("Song", "Artist")
            meta2 = await applemusic.fetch_applemusic_metadata("Song", "Artist")
            assert (
                meta1
                == meta2
                == {
                    "album": "Album",
                    "year": "2020",
                    "duration_ms": 250000,
                }
            )
            assert len(applemusic.apple_music_cache) == 1
            assert mock.calls.call_count == 1

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())


def test_enrich_track_falls_back_to_apple_music(monkeypatch):
    async def fake_spotify(title, artist):
        return None

    async def fake_apple(title, artist):
        return {"album": "Apple Album", "year": "1999", "duration_ms": 123000}

    async def fake_lastfm_data(title, artist):
        return {"tags": [], "listeners": 0, "album": ""}

    monkeypatch.setattr(settings, "spotify_client_id", "id")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")
    monkeypatch.setattr(settings, "apple_client_id", "id")
    monkeypatch.setattr(settings, "apple_client_secret", "secret")
    monkeypatch.setattr(playlist, "fetch_spotify_metadata", fake_spotify)
    monkeypatch.setattr(playlist, "fetch_applemusic_metadata", fake_apple)
    monkeypatch.setattr(playlist, "_get_lastfm_data", fake_lastfm_data)

    track = {
        "title": "Song",
        "artist": "Artist",
        "album": "",
        "year": "",
        "RunTimeTicks": 0,
        "Genres": [],
    }
    enriched = asyncio.run(playlist.enrich_track(track))
    asyncio.set_event_loop(asyncio.new_event_loop())
    assert enriched.album == "Apple Album"
    assert enriched.FinalYear == "1999"
    assert enriched.RunTimeTicks == 123000 * 10000
