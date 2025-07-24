"""Unit tests for M3U parsing utilities."""

# pylint: disable=wrong-import-order,wrong-import-position

import asyncio
import importlib
from pathlib import Path
import sys
import types

from config import settings
from core import constants

# Stub optional dependencies to allow importing core.m3u without installing them
sys.modules.setdefault("httpx", types.ModuleType("httpx"))
initial_services_stub = types.ModuleType("services.jellyfin")
initial_services_stub.resolve_jellyfin_path = lambda *_a, **_kw: None  # type: ignore[attr-defined]


async def _dummy_fetch(*_a, **_kw):
    return None


initial_services_stub.fetch_jellyfin_track_metadata = _dummy_fetch  # type: ignore[attr-defined]
sys.modules.setdefault("services.jellyfin", initial_services_stub)
initial_playlist_stub = types.ModuleType("core.playlist")


async def _dummy_enrich(*_a, **_kw):
    return {}


initial_playlist_stub.enrich_track = _dummy_enrich  # type: ignore[attr-defined]
sys.modules.setdefault("core.playlist", initial_playlist_stub)
from core.m3u import (
    parse_track_text,
    infer_track_metadata_from_path,
    generate_proposed_path,
    _parse_title_artist,
)  # pylint: disable=wrong-import-position


def test_parse_track_text_basic():
    """Parse artist and title separated by dash."""
    artist, title = parse_track_text("Queen - Bohemian Rhapsody")
    assert artist == "Queen"
    assert title == "Bohemian Rhapsody"


def test_parse_track_text_fallback():
    """Fallback to Unknown when only title is provided."""
    artist, title = parse_track_text("Bohemian Rhapsody")
    assert artist == "Unknown"
    assert title == "Bohemian Rhapsody"


def test_parse_track_text_extra_parts():
    """Handle extra segments after artist and title."""
    artist, title = parse_track_text("Metallica - One - Live")
    assert artist == "Metallica"
    assert title == "One"


def test_parse_title_artist_full_line():
    """Extract title and artist from a suggestion line."""
    title, artist = _parse_title_artist("Song Name - Artist Name - Album - 2024")
    assert title == "Song Name"
    assert artist == "Artist Name"


def test_infer_metadata_artist_title():
    """Infer metadata from artist-title filename."""
    meta = infer_track_metadata_from_path("Music/Metallica/Justice/Metallica - One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}


def test_infer_metadata_numbered_track():
    """Handle tracks with numeric prefix."""
    meta = infer_track_metadata_from_path("Music/Metallica/Justice/01 - One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}


def test_infer_metadata_simple_title():
    """Infer metadata when only title present."""
    meta = infer_track_metadata_from_path("Music/Metallica/Justice/One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}


def test_infer_metadata_windows_path():
    """Support Windows path separators."""
    meta = infer_track_metadata_from_path(
        r"C:\\Music\\Metallica\\Justice\\Metallica - One.mp3"
    )
    assert meta == {"title": "One", "artist": "Metallica"}


def test_generate_proposed_path_sanitizes(monkeypatch, tmp_path):
    """Path components are sanitized to prevent traversal and invalid characters."""
    monkeypatch.setattr(settings, "music_library_root", str(tmp_path), raising=False)
    path = generate_proposed_path("../Artist<>", "My/Album*", "Song|Name?")
    assert path == f"{tmp_path}/Artist__/Album_/Song_Name_.mp3"


def _setup_roundtrip(monkeypatch, tmp_path, path_template):
    monkeypatch.setattr(constants, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "jellyfin_user_id", "user", raising=False)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    services_stub_local = types.ModuleType("services.jellyfin")

    async def dummy_resolve(title, artist, *_a, **_kw):
        return Path(path_template.format(artist=artist, title=title)).as_posix()

    async def dummy_fetch(*_a, **_kw):
        return {"Id": "1"}

    services_stub_local.resolve_jellyfin_path = dummy_resolve
    services_stub_local.fetch_jellyfin_track_metadata = dummy_fetch
    playlist_stub_local = types.ModuleType("core.playlist")

    async def dummy_enrich(track):
        return types.SimpleNamespace(**track, dict=lambda: track)

    playlist_stub_local.enrich_track = dummy_enrich
    monkeypatch.setitem(sys.modules, "services.jellyfin", services_stub_local)
    monkeypatch.setitem(sys.modules, "core.playlist", playlist_stub_local)
    sys.modules.pop("core.m3u", None)
    sys.modules.pop("core.history", None)
    m3u = importlib.import_module("core.m3u")
    history = importlib.import_module("core.history")
    return m3u, history


def _roundtrip(monkeypatch, tmp_path, path_template):
    m3u, history = _setup_roundtrip(monkeypatch, tmp_path, path_template)
    entry = {
        "suggestions": [
            {"text": "Title - Artist", "in_jellyfin": True, "album": "Album"}
        ]
    }
    loop = asyncio.get_event_loop()
    m3u_file = loop.run_until_complete(
        m3u.export_history_entry_as_m3u(entry, "url", "key")
    )
    loop.run_until_complete(m3u.import_m3u_as_history_entry(str(m3u_file)))
    hist = history.load_user_history("user")
    assert hist
    track = hist[0]["suggestions"][0]
    assert track["artist"] == "Artist"
    assert track["title"] == "Title"


def test_export_import_roundtrip_posix(monkeypatch, tmp_path):
    """Playlists round-trip using POSIX paths."""
    _roundtrip(monkeypatch, tmp_path, "/Music/{artist}/Album/{title}.mp3")


def test_export_import_roundtrip_windows(monkeypatch, tmp_path):
    """Playlists round-trip using Windows paths."""
    _roundtrip(monkeypatch, tmp_path, r"C:\Music\{artist}\Album\{title}.mp3")


def test_import_skips_failed_metadata(monkeypatch, tmp_path):
    """Import should continue when metadata fetch fails for a track."""
    monkeypatch.setattr(constants, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "jellyfin_user_id", "user", raising=False)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    services_stub = types.ModuleType("services.jellyfin")

    async def fetch(title, _artist):
        if title == "First":
            raise RuntimeError("fail")
        return {"Id": "ok"}

    services_stub.fetch_jellyfin_track_metadata = fetch
    services_stub.resolve_jellyfin_path = lambda *_a, **_kw: None
    playlist_stub = types.ModuleType("core.playlist")

    async def enrich(track):
        return types.SimpleNamespace(**track, dict=lambda: track)

    playlist_stub.enrich_track = enrich
    monkeypatch.setitem(sys.modules, "services.jellyfin", services_stub)
    monkeypatch.setitem(sys.modules, "core.playlist", playlist_stub)
    sys.modules.pop("core.m3u", None)
    sys.modules.pop("core.history", None)

    m3u = importlib.import_module("core.m3u")
    history = importlib.import_module("core.history")

    m3u_path = tmp_path / "list.m3u"
    m3u_path.write_text(
        "\n".join(
            [
                "Music/A/Album/A - First.mp3",
                "Music/B/Album/B - Second.mp3",
            ]
        ),
        encoding="utf-8",
    )
    loop = asyncio.get_event_loop()
    loop.run_until_complete(m3u.import_m3u_as_history_entry(str(m3u_path)))
    hist = history.load_user_history("user")
    assert hist
    suggestions = hist[0]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["title"] == "Second"
    assert suggestions[0]["artist"] == "B"


def test_import_handles_non_utf8(monkeypatch, tmp_path):
    """Import should succeed when the M3U file uses a non-UTF8 encoding."""
    m3u, history = _setup_roundtrip(
        monkeypatch, tmp_path, "/Music/{artist}/Album/{title}.mp3"
    )

    m3u_path = tmp_path / "latin1.m3u"
    m3u_path.write_text(
        "Music/Caf\xe9/Album/Artist - Title.mp3",
        encoding="latin-1",
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(m3u.import_m3u_as_history_entry(str(m3u_path)))
    hist = history.load_user_history("user")
    assert hist
    track = hist[0]["suggestions"][0]
    assert track["artist"] == "Artist"
    assert track["title"] == "Title"
