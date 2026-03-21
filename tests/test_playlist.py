"""Tests for helper functions in ``core.playlist``."""

import ast
import asyncio
from pathlib import Path
from core.models import EnrichedTrack

import core.playlist as playlist_module
from core.playlist import normalize_track


def _load_extract_year():
    """Load the ``extract_year`` function from ``core.playlist`` without importing the module."""
    src = Path("core/playlist.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "extract_year"
    )
    module = ast.Module(body=[func], type_ignores=[])
    ns = {}
    exec(  # pylint: disable=exec-used
        compile(module, filename="<extract_year>", mode="exec"), ns
    )
    return ns["extract_year"]


extract_year = _load_extract_year()


def test_extract_year_fallback_to_premiere():
    """Fallback to ``PremiereDate`` when ``ProductionYear`` is missing."""
    track = {"ProductionYear": None, "PremiereDate": "2023-05-01T00:00:00Z"}
    assert extract_year(track) == "2023"


def test_extract_year_production_year_used():
    """Use ``ProductionYear`` when present."""
    track = {"ProductionYear": 1999, "PremiereDate": "2020-01-01"}
    assert extract_year(track) == "1999"


def test_normalize_track_prefers_first_artist_entry():
    """Artist should resolve from the first Artists entry when AlbumArtist missing."""
    raw = {"Name": "Test Song", "Artists": ["Lead Artist", "Second Artist"]}
    normalized = normalize_track(raw)
    assert normalized.artist == "Lead Artist"
    assert normalized.title == "Test Song"


def test_normalize_track_defaults_missing_artist():
    """Tracks without any artist metadata should fall back to Unknown Artist."""
    raw = {"Name": "Minimal Song"}
    normalized = normalize_track(raw)
    assert normalized.artist == "Unknown Artist"
    assert normalized.title == "Minimal Song"


def test_normalize_track_handles_artist_dict_entries():
    """Artist dictionaries should be parsed for their name fields."""
    raw = {"Name": "Dict Song", "Artists": [{"Name": "Dict Artist"}]}
    normalized = normalize_track(raw)
    assert normalized.artist == "Dict Artist"
    assert normalized.title == "Dict Song"


def test_normalize_genre_supports_common_navidrome_subgenres():
    """Common Last.fm/Navidrome subgenre tags should map to known genres."""
    assert playlist_module.normalize_genre("synth-pop") == "synthpop"
    assert playlist_module.filter_valid_genre(["sophisti-pop"]) == "pop"
    assert playlist_module.filter_valid_genre(["new wave revival"]) == "new wave"


def test_fetch_audio_playlists_uses_media_server_factory(monkeypatch):
    """Playlist fetches should go through the media-server factory."""

    class DummyServer:
        async def list_audio_playlists(self):
            return [
                {
                    "id": "pl1",
                    "name": "Alpha",
                    "track_count": None,
                    "backend": "jellyfin",
                }
            ]

    monkeypatch.setattr(playlist_module, "get_media_server", lambda: DummyServer())

    result = asyncio.run(playlist_module.fetch_audio_playlists())

    assert result == {"playlists": [{"name": "Alpha", "id": "pl1"}]}


def test_enrich_suggestion_preserves_gpt_year_for_decade(monkeypatch):
    """Suggestion enrichment should pass the GPT-parsed year into track enrichment."""

    async def fake_fetch_metadata(_title, _artist):
        return None

    async def fake_youtube(_query):
        return ("video-id", "https://youtube.example/watch?v=video-id")

    async def fake_enrich_track(parsed):
        assert parsed["year"] == "1984"
        return EnrichedTrack(
            title=parsed["title"],
            artist=parsed["artist"],
            year=parsed["year"],
            genre="rock",
            mood="Chill",
            mood_confidence=0.8,
            tempo=120,
            decade="1980s",
            duration=242,
            popularity=100,
            FinalYear="1984",
        )

    monkeypatch.setattr(
        playlist_module, "fetch_jellyfin_track_metadata", fake_fetch_metadata
    )
    monkeypatch.setattr(playlist_module, "get_youtube_url_single", fake_youtube)
    monkeypatch.setattr(playlist_module, "enrich_track", fake_enrich_track)

    suggestion = {
        "title": "Dancing in the Dark",
        "artist": "Bruce Springsteen",
        "text": "Dancing in the Dark - Bruce Springsteen - Born in the U.S.A. - 1984 - Reason",
        "year": 1984,
        "fit_score": 91.0,
        "fit_breakdown": {"fit_score": 91.0},
    }

    result = asyncio.run(playlist_module.enrich_suggestion(suggestion))

    assert result is not None
    assert result["FinalYear"] == "1984"
    assert result["decade"] == "1980s"
    assert result["fit_score"] == 91.0
    assert result["fit_breakdown"] == {"fit_score": 91.0}


def test_resolve_lyrics_for_enrich_prefers_local_lrc_sidecar(monkeypatch):
    """Local .lrc files should be used when inline lyrics are missing."""

    class DummyServer:
        def supports_lyrics(self):
            return True

        async def get_lyrics(self, _item_id):
            return "backend lyrics"

    monkeypatch.setattr(playlist_module, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        playlist_module,
        "read_lrc_for_track",
        lambda path: "[00:01.00]Only you\n[00:02.00]Give me all your love",
    )
    monkeypatch.setattr(
        playlist_module,
        "strip_lrc_timecodes",
        lambda text: "Only you\nGive me all your love",
    )

    track = {
        "title": "Only You",
        "artist": "Yazoo",
        "Path": "/music/Yazoo/Only You.flac",
        "Id": "song-1",
    }

    result = asyncio.run(playlist_module.resolve_lyrics_for_enrich(track))

    assert result == "Only you\nGive me all your love"


def test_resolve_lyrics_for_enrich_falls_back_to_backend(monkeypatch):
    """Backend lyrics should be used when no local sidecar is present."""

    class DummyServer:
        def supports_lyrics(self):
            return True

        async def get_lyrics(self, item_id):
            assert item_id == "song-2"
            return "Backend lyric line"

    monkeypatch.setattr(playlist_module, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(playlist_module, "read_lrc_for_track", lambda path: None)

    track = {
        "title": "Breakout",
        "artist": "Swing Out Sister",
        "Id": "song-2",
        "Path": "/music/Swing Out Sister/Breakout.flac",
    }

    result = asyncio.run(playlist_module.resolve_lyrics_for_enrich(track))

    assert result == "Backend lyric line"
