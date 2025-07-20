"""Unit tests for M3U parsing utilities."""

# pylint: disable=wrong-import-position

import sys
import types

# Stub optional dependencies to allow importing core.m3u without installing them
sys.modules.setdefault('httpx', types.ModuleType('httpx'))
services_stub = types.ModuleType('services.jellyfin')
services_stub.resolve_jellyfin_path = lambda *_a, **_kw: None
async def _dummy_search(*_a, **_kw):
    return None
services_stub.search_jellyfin_for_track = _dummy_search
sys.modules.setdefault('services.jellyfin', services_stub)
playlist_stub = types.ModuleType('core.playlist')
async def _dummy_enrich(*_a, **_kw):
    return {}
playlist_stub.enrich_track = _dummy_enrich
sys.modules.setdefault('core.playlist', playlist_stub)

from core.m3u import parse_track_text, infer_track_metadata_from_path  # pylint: disable=wrong-import-position


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
    meta = infer_track_metadata_from_path(r"C:\\Music\\Metallica\\Justice\\Metallica - One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}
