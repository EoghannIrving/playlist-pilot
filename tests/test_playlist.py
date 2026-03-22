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
    assert playlist_module.filter_valid_genre(["sophisti-pop"]) == "sophisti-pop"
    assert playlist_module.filter_valid_genre(["new wave revival"]) == "new wave"
    assert playlist_module.normalize_genre("celtic") == "celtic folk"
    assert playlist_module.normalize_genre("folk rock") == "folk rock"
    assert playlist_module.normalize_genre("sea shanty") == "sea shanty"
    assert playlist_module.normalize_genre("scottish") == "scottish folk"
    assert playlist_module.normalize_genre("folk-pop") == "folk pop"
    assert playlist_module.normalize_genre("new romantic") == "new romantic"
    assert playlist_module.normalize_genre("music") == ""
    assert playlist_module.genre_family("folk rock") == "folk"
    assert playlist_module.genre_family("folk pop") == "folk"
    assert playlist_module.genre_family("new romantic") == "new wave"


def test_merge_genre_tags_ignores_non_genre_music_label():
    """Generic labels like ``Music`` should not surface as the selected genre."""
    selected, family, context = playlist_module._merge_genre_tags(
        backend_genres=["Music"],
        lastfm_tags=[],
        musicbrainz_tags=[],
        listenbrainz_tags=["sea shanty", "scottish"],
    )

    assert selected in {"sea shanty", "scottish folk"}
    assert family == "folk"
    assert "Music" in context


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


def test_classify_mood_uses_context_fallback_for_unresolved_track(monkeypatch):
    """Unknown moods with usable context should get one constrained fallback pass."""
    monkeypatch.setattr(playlist_module.settings, "lyrics_enabled", True)
    call_count = {"count": 0}

    def fake_combine(tag_scores, bpm_scores, lyrics_scores=None, context_scores=None):
        del tag_scores, bpm_scores, context_scores
        call_count["count"] += 1
        if call_count["count"] == 1:
            return ("unknown", 0.0)
        if lyrics_scores and lyrics_scores.get("nostalgic"):
            return ("nostalgic", 0.62)
        return ("unknown", 0.0)

    monkeypatch.setattr(playlist_module, "combine_mood_scores", fake_combine)
    monkeypatch.setattr(
        playlist_module,
        "resolve_lyrics_for_enrich",
        lambda parsed: asyncio.sleep(0, result="Take me home across the sea"),
    )
    monkeypatch.setattr(
        playlist_module,
        "analyze_mood_from_lyrics",
        lambda lyrics: None,
    )
    monkeypatch.setattr(
        playlist_module,
        "analyze_mood_from_track_context",
        lambda title, artist, genres, year, lyrics: "nostalgic",
    )

    parsed = playlist_module.Track(
        title="Home",
        artist="Nathan Evans",
        year="2024",
        Genres=["folk"],
    )

    mood, confidence = asyncio.run(
        playlist_module._classify_mood(
            parsed,
            tags=[],
            bpm_data={"bpm": 100},
            context_genres=["folk", "celtic"],
            context_year="2024",
        )
    )

    assert mood == "nostalgic"
    assert confidence > 0.3
    assert call_count["count"] == 2


def test_enrich_track_prefers_original_year_over_backend_compilation_year(monkeypatch):
    """Original-year resolution should beat compilation-era backend metadata."""

    async def fake_lastfm(_title, _artist):
        return {
            "tags": ["new wave"],
            "genre_tags": ["new wave"],
            "listeners": 1000,
            "album": "Like You Do... Best of the Lightning Seeds",
            "releasedate": "",
        }

    async def fake_bpm(_artist, _title):
        return {"bpm": 100, "year": 2003}

    monkeypatch.setattr(playlist_module, "_get_lastfm_data", fake_lastfm)
    monkeypatch.setattr(playlist_module, "_fetch_bpm_data", fake_bpm)
    monkeypatch.setattr(
        playlist_module,
        "_get_musicbrainz_data",
        lambda title, artist, album, year: asyncio.sleep(
            0,
            result={
                "recording_id": "mb-recording",
                "release_group_id": "mb-release-group",
                "original_year": "1989",
                "genre_tags": ["sophisti-pop"],
                "score": 14.2,
            },
        ),
    )
    monkeypatch.setattr(
        playlist_module,
        "_get_listenbrainz_tags",
        lambda recording_id, release_group_id: asyncio.sleep(
            0, result=["pop", "new wave"]
        ),
    )
    monkeypatch.setattr(
        playlist_module,
        "resolve_library_audio_path",
        lambda path: Path(
            "/Movies/Music/The Lightning Seeds/Like You Do… Best of the Lightning Seeds/08 The Lightning Seeds - Pure.flac"
        ),
    )
    monkeypatch.setattr(
        playlist_module,
        "read_track_tags",
        lambda path: {"year": "1989", "path": path},
    )
    monkeypatch.setattr(
        playlist_module,
        "mood_scores_from_lastfm_tags",
        lambda tags: {"uplifting": 1.0} if tags else {},
    )
    monkeypatch.setattr(
        playlist_module,
        "mood_scores_from_bpm_data",
        lambda bpm_data: {"uplifting": 0.5} if bpm_data else {},
    )
    monkeypatch.setattr(
        playlist_module,
        "mood_scores_from_context",
        lambda genres, year, bpm: {"uplifting": 0.3} if genres and year and bpm else {},
    )
    monkeypatch.setattr(
        playlist_module,
        "combine_mood_scores",
        lambda tag_scores, bpm_scores, lyrics_scores=None, context_scores=None: (
            "uplifting",
            0.8,
        ),
    )

    track = playlist_module.Track(
        title="Pure",
        artist="The Lightning Seeds",
        album="Like You Do... Best of the Lightning Seeds",
        year="2003",
        Genres=["pop"],
        Path="The Lightning Seeds/Like You Do… Best of the Lightning Seeds/01-08 - Pure.flac",
    )

    result = asyncio.run(playlist_module.enrich_track(track))

    assert result.FinalYear == "1989"
    assert result.decade == "1980s"
    assert "file_tags: 1989" in result.year_flag
    assert "musicbrainz: 1989" in result.year_flag


def test_enrich_track_uses_listenbrainz_tags_for_genre_resolution(monkeypatch):
    """ListenBrainz and MusicBrainz tags should improve genre selection."""

    async def fake_lastfm(_title, _artist):
        return {
            "tags": ["1980s"],
            "genre_tags": ["1980s"],
            "listeners": 50,
            "album": "",
            "releasedate": "",
        }

    async def fake_bpm(_artist, _title):
        return {"bpm": 118}

    monkeypatch.setattr(playlist_module, "_get_lastfm_data", fake_lastfm)
    monkeypatch.setattr(playlist_module, "_fetch_bpm_data", fake_bpm)
    monkeypatch.setattr(
        playlist_module,
        "_get_musicbrainz_data",
        lambda title, artist, album, year: asyncio.sleep(
            0,
            result={
                "recording_id": "mb-recording",
                "release_group_id": "mb-release-group",
                "original_year": "1985",
                "genre_tags": ["synth-pop"],
                "score": 15.0,
            },
        ),
    )
    monkeypatch.setattr(
        playlist_module,
        "_get_listenbrainz_tags",
        lambda recording_id, release_group_id: asyncio.sleep(
            0, result=["new romantic", "new wave"]
        ),
    )
    monkeypatch.setattr(
        playlist_module,
        "_get_file_tag_year",
        lambda parsed: asyncio.sleep(0, result=""),
    )
    monkeypatch.setattr(
        playlist_module,
        "combine_mood_scores",
        lambda tag_scores, bpm_scores, lyrics_scores=None, context_scores=None: (
            "party",
            0.7,
        ),
    )

    track = playlist_module.Track(
        title="Only You",
        artist="Yazoo",
        Genres=[],
        year="",
    )

    result = asyncio.run(playlist_module.enrich_track(track))

    assert result.genre == "new romantic"
    assert result.genre_family == "new wave"
    assert result.FinalYear == "1985"


def test_enrich_track_uses_genre_context_fallback_when_sources_are_unknown(monkeypatch):
    """Unknown genres should get one constrained fallback pass before staying blank."""

    async def fake_lastfm(_title, _artist):
        return {
            "tags": [],
            "genre_tags": [],
            "listeners": 10,
            "album": "",
            "releasedate": "",
        }

    async def fake_bpm(_artist, _title):
        return {"bpm": 100}

    monkeypatch.setattr(playlist_module, "_get_lastfm_data", fake_lastfm)
    monkeypatch.setattr(playlist_module, "_fetch_bpm_data", fake_bpm)
    monkeypatch.setattr(
        playlist_module,
        "_get_musicbrainz_data",
        lambda title, artist, album, year: asyncio.sleep(
            0,
            result={
                "recording_id": "",
                "release_group_id": "",
                "original_year": "2022",
                "genre_tags": [],
                "score": 0.0,
            },
        ),
    )
    monkeypatch.setattr(
        playlist_module,
        "_get_listenbrainz_tags",
        lambda recording_id, release_group_id: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        playlist_module,
        "_get_file_tag_year",
        lambda parsed: asyncio.sleep(0, result=""),
    )
    monkeypatch.setattr(
        playlist_module,
        "analyze_genre_from_track_context",
        lambda title, artist, album, year, tags: "celtic folk",
    )
    monkeypatch.setattr(
        playlist_module,
        "combine_mood_scores",
        lambda tag_scores, bpm_scores, lyrics_scores=None, context_scores=None: (
            "nostalgic",
            0.6,
        ),
    )

    track = playlist_module.Track(
        title="Heather on the Hill",
        artist="Nathan Evans",
        Genres=[],
        year="",
    )

    result = asyncio.run(playlist_module.enrich_track(track))

    assert result.genre == "celtic folk"
    assert result.genre_family == "folk"
