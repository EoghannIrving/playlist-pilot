"""Unit tests for the ListenBrainz service."""

import asyncio

import respx

from config import settings
from services import listenbrainz


def test_get_recording_tags_parses_metadata_payload(monkeypatch):
    """ListenBrainz recording tags should be extracted from the metadata payload."""
    monkeypatch.setattr(settings, "listenbrainz_enabled", True)
    listenbrainz.listenbrainz_cache.clear()

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get(
                "https://api.listenbrainz.org/1/metadata/recording/mbid-1"
            ).respond(
                200,
                json={
                    "payload": {
                        "recording": {
                            "tags": [
                                {"tag": "new wave"},
                                {"tag": "synth-pop"},
                            ]
                        }
                    }
                },
            )
            tags = await listenbrainz.get_recording_tags("mbid-1")
            assert tags == ["new wave", "synth-pop"]

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())


def test_get_release_group_tags_parses_metadata_payload(monkeypatch):
    """ListenBrainz release-group tags should be extracted from the metadata payload."""
    monkeypatch.setattr(settings, "listenbrainz_enabled", True)
    listenbrainz.listenbrainz_cache.clear()

    async def main():
        with respx.mock(assert_all_called=True) as mock:
            mock.get(
                "https://api.listenbrainz.org/1/metadata/release-group/rg-1"
            ).respond(
                200,
                json={
                    "payload": {
                        "release_group": {
                            "tags": [
                                {"tag": "pop"},
                                {"tag": "new romantic"},
                            ]
                        }
                    }
                },
            )
            tags = await listenbrainz.get_release_group_tags("rg-1")
            assert tags == ["pop", "new romantic"]

    asyncio.run(main())
    asyncio.set_event_loop(asyncio.new_event_loop())
