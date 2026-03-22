"""Unit tests for the MusicBrainz service."""

import asyncio

import respx

from config import settings
from services import musicbrainz


def test_match_recording_prefers_original_candidate(monkeypatch):
    """MusicBrainz matching should prefer the original recording over compilations."""
    monkeypatch.setattr(settings, "musicbrainz_enabled", True)
    musicbrainz.musicbrainz_cache.clear()

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://musicbrainz.org/ws/2/recording").respond(
                200,
                json={
                    "recordings": [
                        {
                            "id": "mb-original",
                            "title": "Pure",
                            "first-release-date": "1989-01-01",
                            "artist-credit": [{"name": "The Lightning Seeds"}],
                            "release-group": {
                                "id": "rg-original",
                                "primary-type": "Album",
                            },
                            "releases": [{"title": "Cloudcuckooland"}],
                        },
                        {
                            "id": "mb-compilation",
                            "title": "Pure (Remastered)",
                            "first-release-date": "2003-01-01",
                            "artist-credit": [{"name": "The Lightning Seeds"}],
                            "release-group": {
                                "id": "rg-comp",
                                "primary-type": "Compilation",
                            },
                            "releases": [
                                {"title": "Like You Do... Best of the Lightning Seeds"}
                            ],
                        },
                    ]
                },
            )
            mock.get("https://musicbrainz.org/ws/2/recording/mb-original").respond(
                200,
                json={
                    "id": "mb-original",
                    "title": "Pure",
                    "first-release-date": "1989-01-01",
                    "artist-credit": [{"name": "The Lightning Seeds"}],
                    "release-group": {"id": "rg-original", "primary-type": "Album"},
                    "genres": [{"name": "pop"}],
                    "tags": [{"name": "sophisti-pop"}],
                    "releases": [{"title": "Cloudcuckooland"}],
                },
            )

            result = await musicbrainz.match_recording(
                "Pure",
                "The Lightning Seeds",
                album="Like You Do... Best of the Lightning Seeds",
                year="2003",
            )

            assert result["recording_id"] == "mb-original"
            assert result["original_year"] == "1989"
            assert "sophisti-pop" in result["genre_tags"]

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())
