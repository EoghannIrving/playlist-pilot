"""Tests for minimal FastAPI route helpers."""

# pylint: disable=exec-used

import ast
from pathlib import Path
import asyncio
import types
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile
from api.schemas import AnalysisExportRequest
from api.forms import SettingsForm
from api.routes import settings_routes, analysis_routes
from api.schemas import (
    VerifyEntryRequest,
    ExportTrackMetadataRequest,
    TrackMetadata,
    SuggestFromAnalyzedRequest,
    SuggestedSeedTrack,
    AddTrackToPlaylistRequest,
)


def _extract_health_check():
    """Load the ``health_check`` coroutine from ``api.routes`` without importing."""
    src = Path("api/routes/monitoring_routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"
    )
    func.decorator_list = []
    module = ast.Module(body=[func], type_ignores=[])
    ns = {}
    exec(
        compile(module, filename="<health>", mode="exec"), ns
    )  # pylint: disable=exec-used
    return ns["health_check"]


def test_health_check():
    """``health_check`` should return the expected status dictionary."""
    health_check = _extract_health_check()
    result = asyncio.run(health_check())
    assert result == {"status": "ok"}


def _extract_export_m3u():
    """Return the ``export_m3u`` coroutine without side effects."""
    src = Path("api/routes/analysis_routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "export_m3u"
    )
    func.decorator_list = []
    module = ast.Module(body=[func], type_ignores=[])
    ns = {
        "HTTPException": HTTPException,
        "BackgroundTask": object,
        "FileResponse": object,
        "resolve_jellyfin_path": lambda *a, **k: None,
        "settings": object,
        "uuid": __import__("uuid"),
        "tempfile": __import__("tempfile"),
        "Path": Path,
        "Request": object,
        "AnalysisExportRequest": AnalysisExportRequest,
    }
    exec(compile(module, filename="<export_m3u>", mode="exec"), ns)
    return ns["export_m3u"]


def _extract_import_m3u_file():
    """Return ``import_m3u_file`` coroutine without importing ``api.routes``."""
    src = Path("api/routes/analysis_routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "import_m3u_file"
    )
    func.decorator_list = []
    func.args.defaults = []
    func.args.kw_defaults = []
    for arg in func.args.args[:2]:
        arg.annotation = None
    func.returns = None
    module = ast.Module(body=[func], type_ignores=[])
    ns = {
        "HTTPException": HTTPException,
        "import_m3u_as_history_entry": lambda _: None,
        "cleanup_temp_file": lambda _: None,
        "tempfile": __import__("tempfile"),
        "shutil": __import__("shutil"),
        "Path": Path,
        "RedirectResponse": type("Resp", (), {}),
    }
    exec(compile(module, filename="<import_m3u_file>", mode="exec"), ns)
    return ns["import_m3u_file"]


def test_export_m3u_no_tracks():
    """``export_m3u`` should reject empty track lists."""
    export_m3u = _extract_export_m3u()

    async def dummy_json():
        """Return an empty track list in request body."""
        return {"name": "x", "tracks": []}

    dummy_req = types.SimpleNamespace(json=dummy_json)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(export_m3u(dummy_req))
    assert exc.value.status_code == 400


def test_import_m3u_file_invalid_extension(tmp_path):
    """Invalid file extensions should result in ``HTTPException``."""
    dummy_file = UploadFile(tmp_path / "test.txt", filename="test.txt")
    dummy_req = types.SimpleNamespace(headers={})
    dummy_payload = types.SimpleNamespace(m3u_file=dummy_file)
    import_m3u = _extract_import_m3u_file()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(import_m3u(dummy_req, dummy_payload))
    assert exc.value.status_code == 400


def test_verify_playlist_entry_uses_media_server(monkeypatch):
    """Verify-entry should resolve tracks through the adapter."""

    class DummyServer:
        async def get_playlist_tracks(self, _playlist_id):
            return [{"PlaylistItemId": "entry-1", "Name": "Song"}]

    monkeypatch.setattr(settings_routes, "get_media_server", lambda: DummyServer())

    result = asyncio.run(
        settings_routes.verify_playlist_entry(
            VerifyEntryRequest(playlist_id="playlist", entry_id="entry-1")
        )
    )

    assert result.success is True
    assert result.track["Name"] == "Song"


def test_update_settings_prefers_generic_media_fields(monkeypatch):
    """Settings updates should persist generic media fields and use adapter users."""

    class DummyServer:
        async def list_users(self):
            return [{"id": "u1", "name": "User One"}]

    captured = {}

    def fake_template_response(_template, context):
        captured.update(context)
        return context

    async def fake_models(_key):
        return ["gpt-4o-mini"]

    monkeypatch.setattr(settings_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        settings_routes.templates, "TemplateResponse", fake_template_response
    )
    monkeypatch.setattr(settings_routes, "fetch_openai_models", fake_models)
    monkeypatch.setattr(settings_routes, "get_log_excerpt", lambda: "logs")
    monkeypatch.setattr(settings_routes, "save_settings", lambda _settings: None)

    form_data = SettingsForm(
        media_backend="jellyfin",
        media_url="http://media",
        media_api_key="media-key",
        media_user_id="media-user",
        jellyfin_url="http://legacy",
        jellyfin_api_key="legacy-key",
        jellyfin_user_id="legacy-user",
        openai_api_key="openai",
        cache_ttls={},
        getsongbpm_headers={},
    )

    result = asyncio.run(
        settings_routes.update_settings(
            request=types.SimpleNamespace(),
            form_data=form_data,
        )
    )

    assert result["media_server_users"] == {"User One": "u1"}
    assert settings_routes.settings.media_url == "http://media"
    assert settings_routes.settings.media_api_key == "media-key"
    assert settings_routes.settings.media_user_id == "media-user"


def test_sort_openai_models_prefers_recent_general_models():
    """Newest general GPT models should appear before older or specialized entries."""
    models = [
        "gpt-4o-mini",
        "gpt-5-nano",
        "gpt-5.2",
        "gpt-5-mini",
        "gpt-5.2-chat-latest",
        "gpt-4.1",
        "gpt-4o-realtime-preview",
    ]

    result = settings_routes._sort_openai_models(models)

    assert result[:4] == [
        "gpt-5.2-chat-latest",
        "gpt-5.2",
        "gpt-5-mini",
        "gpt-5-nano",
    ]
    assert result[-1] == "gpt-4o-realtime-preview"


def test_get_track_tags_reads_from_validated_library_path(monkeypatch, tmp_path):
    """Track tag reads should resolve through the media server and local file path."""
    music_root = tmp_path / "music"
    music_root.mkdir()
    track_path = music_root / "song.mp3"
    track_path.write_text("stub", encoding="utf-8")

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Song"
            assert artist == "Artist"
            return {"Path": str(track_path)}

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", str(music_root))
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Artist",
            "genre": "Folk",
            "year": "2024",
            "bpm": 100,
            "mood": "Nostalgic",
            "path": path,
        },
    )

    result = asyncio.run(analysis_routes.get_track_tags(title="Song", artist="Artist"))

    assert result.title == "Song"
    assert result.path == str(track_path.resolve())


def test_update_track_tags_writes_to_validated_library_path(monkeypatch, tmp_path):
    """Track tag updates should write through the validated file path."""
    music_root = tmp_path / "music"
    music_root.mkdir()
    track_path = music_root / "song.mp3"
    track_path.write_text("stub", encoding="utf-8")
    captured = {}

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Song"
            assert artist == "Artist"
            return {"Path": str(track_path)}

    def fake_write(path, payload):
        captured["path"] = path
        captured["payload"] = payload

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", str(music_root))
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(analysis_routes, "write_track_tags", fake_write)
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Edited Song",
            "artist": "Edited Artist",
            "album": "Edited Album",
            "album_artist": "Edited Artist",
            "genre": "Pop",
            "year": "2025",
            "bpm": 120,
            "mood": "Uplifting",
            "path": path,
        },
    )

    result = asyncio.run(
        analysis_routes.update_track_tags(
            analysis_routes.UpdateTrackTagsRequest(
                lookup_title="Song",
                lookup_artist="Artist",
                title="Edited Song",
                artist="Edited Artist",
                album="Edited Album",
                album_artist="Edited Artist",
                genre="Pop",
                year="2025",
                bpm=120,
                mood="Uplifting",
            )
        )
    )

    assert captured["path"] == str(track_path.resolve())
    assert captured["payload"]["title"] == "Edited Song"
    assert result.title == "Edited Song"


def test_get_track_tags_accepts_container_style_relative_library_root(
    monkeypatch, tmp_path
):
    """A relative root like ``Movies/Music`` should resolve to ``/Movies/Music`` when mounted there."""
    container_root = Path("/Movies/Music")
    track_path = container_root / "Artist" / "song.mp3"

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Song"
            assert artist == "Artist"
            return {"Path": str(track_path)}

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", "Movies/Music")
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Song",
            "artist": "Artist",
            "album": "",
            "album_artist": "",
            "genre": "",
            "year": "",
            "bpm": None,
            "mood": "",
            "path": path,
        },
    )

    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/Movies/Music")
    monkeypatch.setattr(Path, "is_file", lambda self: str(self) == str(track_path))

    result = asyncio.run(analysis_routes.get_track_tags(title="Song", artist="Artist"))

    assert result.path == str(track_path.resolve())


def test_get_track_tags_resolves_relative_backend_path_under_library_root(
    monkeypatch, tmp_path
):
    """Relative backend paths should be interpreted under the configured library root."""
    music_root = tmp_path / "music"
    artist_dir = music_root / "Artist Folder"
    artist_dir.mkdir(parents=True)
    track_path = artist_dir / "song.mp3"
    track_path.write_text("stub", encoding="utf-8")

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Song"
            assert artist == "Artist"
            return {"Path": "Artist Folder/song.mp3"}

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", str(music_root))
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Song",
            "artist": "Artist",
            "album": "",
            "album_artist": "",
            "genre": "",
            "year": "",
            "bpm": None,
            "mood": "",
            "path": path,
        },
    )

    result = asyncio.run(analysis_routes.get_track_tags(title="Song", artist="Artist"))

    assert result.path == str(track_path.resolve())


def test_get_track_tags_matches_unicode_path_variants(monkeypatch, tmp_path):
    """Path validation should match filesystem entries when punctuation variants differ."""
    music_root = tmp_path / "music"
    album_dir = (
        music_root / "The Lightning Seeds" / "Like You Do… Best of the Lightning Seeds"
    )
    album_dir.mkdir(parents=True)
    track_path = album_dir / "Pure.flac"
    track_path.write_text("stub", encoding="utf-8")

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Pure"
            assert artist == "The Lightning Seeds"
            return {
                "Path": "The Lightning Seeds/Like You Do... Best of the Lightning Seeds/Pure.flac"
            }

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", str(music_root))
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Pure",
            "artist": "The Lightning Seeds",
            "album": "Like You Do… Best of the Lightning Seeds",
            "album_artist": "The Lightning Seeds",
            "genre": "Pop",
            "year": "1997",
            "bpm": 100,
            "mood": "Nostalgic",
            "path": path,
        },
    )

    result = asyncio.run(
        analysis_routes.get_track_tags(title="Pure", artist="The Lightning Seeds")
    )

    assert result.path == str(track_path.resolve())


def test_get_track_tags_matches_filename_variants_within_album(monkeypatch, tmp_path):
    """Filename mismatches should resolve to a unique audio file in the album directory."""
    music_root = tmp_path / "music"
    album_dir = (
        music_root / "The Lightning Seeds" / "Like You Do… Best of the Lightning Seeds"
    )
    album_dir.mkdir(parents=True)
    track_path = album_dir / "08 The Lightning Seeds - Pure.flac"
    track_path.write_text("stub", encoding="utf-8")

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Pure"
            assert artist == "The Lightning Seeds"
            return {
                "Path": "The Lightning Seeds/Like You Do… Best of the Lightning Seeds/01-08 - Pure.flac"
            }

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", str(music_root))
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Pure",
            "artist": "The Lightning Seeds",
            "album": "Like You Do… Best of the Lightning Seeds",
            "album_artist": "The Lightning Seeds",
            "genre": "Pop",
            "year": "1997",
            "bpm": 100,
            "mood": "Nostalgic",
            "path": path,
        },
    )

    result = asyncio.run(
        analysis_routes.get_track_tags(title="Pure", artist="The Lightning Seeds")
    )

    assert result.path == str(track_path.resolve())


def test_get_track_tags_matches_parenthetical_filename_variants(monkeypatch, tmp_path):
    """Filename matching should tolerate punctuation and extra artist text in the real file."""
    music_root = tmp_path / "music"
    album_dir = music_root / "Eurythmics" / "Ultimate Collection"
    album_dir.mkdir(parents=True)
    track_path = album_dir / "03 Eurythmics - Sweet Dreams Are Made Of This.flac"
    track_path.write_text("stub", encoding="utf-8")

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Sweet Dreams (Are Made of This)"
            assert artist == "Eurythmics"
            return {
                "Path": "Eurythmics/Ultimate Collection/01-03 - Sweet Dreams (Are Made of This).flac"
            }

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", str(music_root))
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Sweet Dreams (Are Made of This)",
            "artist": "Eurythmics",
            "album": "Ultimate Collection",
            "album_artist": "Eurythmics",
            "genre": "Pop",
            "year": "1983",
            "bpm": 120,
            "mood": "Nostalgic",
            "path": path,
        },
    )

    result = asyncio.run(
        analysis_routes.get_track_tags(
            title="Sweet Dreams (Are Made of This)",
            artist="Eurythmics",
        )
    )

    assert result.path == str(track_path.resolve())


def test_get_track_tags_matches_directory_variants_with_colons(monkeypatch, tmp_path):
    """Directory matching should tolerate punctuation and edition-label differences."""
    music_root = tmp_path / "music"
    album_dir = music_root / "Nathan Evans" / "1994 (Deluxe)"
    album_dir.mkdir(parents=True)
    track_path = album_dir / "04 Heather on the Hill.flac"
    track_path.write_text("stub", encoding="utf-8")

    class DummyServer:
        async def get_track_metadata(self, title, artist):
            assert title == "Heather on the Hill"
            assert artist == "Nathan Evans"
            return {
                "Path": "Nathan Evans/1994: Deluxe Edition/04 - Heather on the Hill.flac"
            }

    monkeypatch.setattr(analysis_routes.settings, "music_library_root", str(music_root))
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        analysis_routes,
        "read_track_tags",
        lambda path: {
            "title": "Heather on the Hill",
            "artist": "Nathan Evans",
            "album": "1994 (Deluxe)",
            "album_artist": "Nathan Evans",
            "genre": "Folk",
            "year": "2022",
            "bpm": 100,
            "mood": "Romantic",
            "path": path,
        },
    )

    result = asyncio.run(
        analysis_routes.get_track_tags(
            title="Heather on the Hill",
            artist="Nathan Evans",
        )
    )

    assert result.path == str(track_path.resolve())


def test_trigger_media_server_rescan_returns_started(monkeypatch):
    """The rescan endpoint should return backend scan metadata when supported."""

    class DummyServer:
        async def trigger_library_scan(self):
            return {"status": "started", "scanning": True, "count": 42}

    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())

    result = asyncio.run(analysis_routes.trigger_media_server_rescan())

    assert result.status == "started"
    assert result.scanning is True
    assert result.count == 42


def test_trigger_media_server_rescan_rejects_unsupported_backend(monkeypatch):
    """The rescan endpoint should reject unsupported backends cleanly."""

    class DummyServer:
        async def trigger_library_scan(self):
            return {"status": "unsupported"}

    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(analysis_routes.trigger_media_server_rescan())
    assert exc.value.status_code == 400


def test_test_jellyfin_route_supports_navidrome_backend(monkeypatch):
    """The transitional test route should support Navidrome credentials."""

    class DummyAdapter:
        async def test_connection(self):
            return {"success": True, "status": 200, "data": {"status": "ok"}}

    monkeypatch.setattr(
        settings_routes,
        "NavidromeAdapter",
        lambda **_kwargs: DummyAdapter(),
    )

    result = asyncio.run(
        settings_routes.test_jellyfin(
            settings_routes.JellyfinTestRequest(
                backend="navidrome",
                url="http://nav",
                username="user",
                password="pass",
            )
        )
    )

    assert result.success is True
    assert result.status == 200


def test_test_media_server_route_supports_navidrome_backend(monkeypatch):
    """The backend-neutral test route should support Navidrome credentials."""

    class DummyAdapter:
        async def test_connection(self):
            return {"success": True, "status": 200, "data": {"status": "ok"}}

    monkeypatch.setattr(
        settings_routes,
        "NavidromeAdapter",
        lambda **_kwargs: DummyAdapter(),
    )

    result = asyncio.run(
        settings_routes.test_media_server(
            settings_routes.JellyfinTestRequest(
                backend="navidrome",
                url="http://nav",
                username="user",
                password="pass",
            )
        )
    )

    assert result.success is True
    assert result.status == 200


def test_index_passes_refresh_to_playlist_cache(monkeypatch):
    """Index should forward the refresh flag to the playlist cache helper."""

    captured = {}

    async def fake_get_cached_playlists(user_id, force_refresh=False):
        captured["user_id"] = user_id
        captured["force_refresh"] = force_refresh
        return {"playlists": [], "error": None}

    def fake_template_response(_template, context):
        return context

    monkeypatch.setattr(
        analysis_routes, "get_cached_playlists", fake_get_cached_playlists
    )
    monkeypatch.setattr(analysis_routes, "current_user_scope", lambda: "user-1")
    monkeypatch.setattr(
        analysis_routes, "load_sorted_history", lambda _user_id=None: []
    )
    monkeypatch.setattr(
        analysis_routes.templates, "TemplateResponse", fake_template_response
    )
    monkeypatch.setattr(
        analysis_routes.settings.__class__,
        "validate_settings",
        lambda _self: None,
        raising=False,
    )

    result = asyncio.run(
        analysis_routes.index(
            types.SimpleNamespace(url=types.SimpleNamespace(path="/")), refresh=True
        )
    )

    assert captured == {"user_id": "user-1", "force_refresh": True}
    assert result["refresh_requested"] is True


def test_show_analysis_page_passes_refresh_to_playlist_cache(monkeypatch):
    """Analyze page should support forcing a fresh server playlist fetch."""

    captured = {}

    async def fake_get_cached_playlists(user_id, force_refresh=False):
        captured["user_id"] = user_id
        captured["force_refresh"] = force_refresh
        return {"playlists": [], "error": None}

    def fake_template_response(_template, context):
        return context

    monkeypatch.setattr(
        analysis_routes, "get_cached_playlists", fake_get_cached_playlists
    )
    monkeypatch.setattr(analysis_routes, "current_user_scope", lambda: "user-1")
    monkeypatch.setattr(
        analysis_routes, "load_sorted_history", lambda _user_id=None: []
    )
    monkeypatch.setattr(
        analysis_routes.templates, "TemplateResponse", fake_template_response
    )

    result = asyncio.run(
        analysis_routes.show_analysis_page(
            types.SimpleNamespace(url=types.SimpleNamespace(path="/analyze")),
            refresh=True,
        )
    )

    assert captured == {"user_id": "user-1", "force_refresh": True}
    assert result["refresh_requested"] is True


def test_export_track_metadata_writes_file_tags_for_navidrome(monkeypatch):
    """Navidrome-backed metadata export should write directly to the file path."""

    captured = {}

    class DummyServer:
        async def get_track_metadata(self, _title, _artist):
            return {"Path": "/music/song.mp3", "Album": ""}

    def fake_write_track_tags(file_path, track):
        captured["file_path"] = file_path
        captured["track"] = track

    monkeypatch.setattr(
        analysis_routes.settings, "media_backend", "navidrome", raising=False
    )
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(analysis_routes, "write_track_tags", fake_write_track_tags)

    result = asyncio.run(
        analysis_routes.export_track_metadata(
            ExportTrackMetadataRequest(
                track=TrackMetadata(
                    title="Song",
                    artist="Artist",
                    album="New Album",
                    genre="rock",
                    mood="happy",
                    tempo=120,
                )
            )
        )
    )

    assert result.message == "Metadata for track 'Song' exported to file tags."
    assert captured["file_path"] == "/music/song.mp3"
    assert captured["track"]["album"] == "New Album"
    assert captured["track"]["genre"] == "rock"


def test_export_track_metadata_navidrome_album_conflict(monkeypatch):
    """Navidrome file-tag export should preserve album overwrite confirmation."""

    class DummyServer:
        async def get_track_metadata(self, _title, _artist):
            return {"Path": "/music/song.mp3", "Album": "Old Album"}

    monkeypatch.setattr(
        analysis_routes.settings, "media_backend", "navidrome", raising=False
    )
    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())

    response = asyncio.run(
        analysis_routes.export_track_metadata(
            ExportTrackMetadataRequest(
                track=TrackMetadata(
                    title="Song",
                    artist="Artist",
                    album="New Album",
                )
            )
        )
    )

    assert response.status_code == 409


def test_suggest_from_analyzed_preserves_enriched_track_metadata(monkeypatch):
    """Suggestion generation should keep enriched track fields past request parsing."""

    captured = {}

    async def fake_build_payload(_request):
        return SuggestFromAnalyzedRequest(
            playlist_name="80s",
            text_summary="Profile summary",
            source_backend="navidrome",
            source_playlist_id="playlist-123",
            tracks=[
                SuggestedSeedTrack(
                    title="Only You",
                    artist="Yazoo",
                    genre="new wave",
                    mood="romantic",
                    tempo=100,
                    decade="1980s",
                    popularity=12345,
                    combined_popularity=81.2,
                    FinalYear="1982",
                    in_library=True,
                )
            ],
        )

    def fake_summarize_tracks(tracks):
        captured["summary_tracks"] = tracks
        return {
            "dominant_genre": "new wave",
            "mood_profile": {"romantic": "100%"},
            "tempo_avg": 100,
            "decades": {"1980s": "100%"},
            "avg_popularity": 80,
        }

    async def fake_fetch_gpt_suggestions(
        tracks, summary, suggestion_count, profile_summary="", playlist_name=""
    ):
        captured["gpt_tracks"] = tracks
        captured["gpt_summary"] = summary
        captured["gpt_profile_summary"] = profile_summary
        captured["gpt_suggestion_count"] = suggestion_count
        captured["gpt_playlist_name"] = playlist_name
        return []

    async def fake_enrich_and_score_suggestions(_suggestions):
        return []

    def fake_persist_history_and_m3u(
        _suggestions,
        _playlist_name,
        source_backend=None,
        source_playlist_id=None,
    ):
        captured["persist_source_backend"] = source_backend
        captured["persist_source_playlist_id"] = source_playlist_id
        return Path("/tmp/test.m3u")

    monkeypatch.setattr(analysis_routes, "_build_suggest_payload", fake_build_payload)
    monkeypatch.setattr(analysis_routes, "summarize_tracks", fake_summarize_tracks)
    monkeypatch.setattr(
        analysis_routes, "fetch_gpt_suggestions", fake_fetch_gpt_suggestions
    )
    monkeypatch.setattr(
        analysis_routes,
        "enrich_and_score_suggestions",
        fake_enrich_and_score_suggestions,
    )
    monkeypatch.setattr(
        analysis_routes,
        "persist_history_and_m3u",
        fake_persist_history_and_m3u,
    )
    monkeypatch.setattr(
        analysis_routes.templates,
        "TemplateResponse",
        lambda _template, context: context,
    )

    request = types.SimpleNamespace(headers={"accept": "text/html"})
    result = asyncio.run(analysis_routes.suggest_from_analyzed(request))

    assert captured["summary_tracks"][0]["genre"] == "new wave"
    assert captured["summary_tracks"][0]["mood"] == "romantic"
    assert captured["summary_tracks"][0]["tempo"] == 100
    assert captured["summary_tracks"][0]["decade"] == "1980s"
    assert captured["gpt_tracks"][0]["FinalYear"] == "1982"
    assert captured["gpt_profile_summary"] == "Profile summary"
    assert captured["gpt_suggestion_count"] == 10
    assert captured["gpt_playlist_name"] == "80s"
    assert captured["persist_source_backend"] == "navidrome"
    assert captured["persist_source_playlist_id"] == "playlist-123"
    assert result["Dominant_Genre"] == "new wave"
    assert result["source_backend"] == "navidrome"
    assert result["source_playlist_id"] == "playlist-123"


def test_add_track_to_server_playlist_navidrome(monkeypatch):
    """Navidrome add-to-playlist actions should proxy through the media adapter."""

    class DummyServer:
        def backend_name(self):
            return "navidrome"

        async def add_track_to_playlist(self, playlist_id, track_id):
            assert playlist_id == "playlist-123"
            assert track_id == "track-456"
            return {"status": "added", "playlist_id": playlist_id}

    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())

    result = asyncio.run(
        analysis_routes.add_track_to_server_playlist(
            "playlist-123",
            AddTrackToPlaylistRequest(track_id="track-456"),
        )
    )

    assert result.status == "added"
    assert result.playlist_id == "playlist-123"
    assert result.track_id == "track-456"


def test_add_track_to_server_playlist_rejects_unsupported_backend(monkeypatch):
    """Direct add-to-playlist should be rejected for non-Navidrome backends."""

    class DummyServer:
        def backend_name(self):
            return "jellyfin"

    monkeypatch.setattr(analysis_routes, "get_media_server", lambda: DummyServer())

    result = asyncio.run(
        analysis_routes.add_track_to_server_playlist(
            "playlist-123",
            AddTrackToPlaylistRequest(track_id="track-456"),
        )
    )

    assert result.status == "unsupported"
    assert "Navidrome" in (result.error or "")
