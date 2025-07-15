import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import types

# Stub optional dependencies to allow importing core.m3u without installing them
sys.modules.setdefault('httpx', types.ModuleType('httpx'))
services_stub = types.ModuleType('services.jellyfin')
services_stub.resolve_jellyfin_path = lambda *a, **kw: None
services_stub.search_jellyfin_for_track = lambda *a, **kw: None
sys.modules.setdefault('services.jellyfin', services_stub)
playlist_stub = types.ModuleType('core.playlist')
playlist_stub.enrich_track = lambda *a, **kw: {}
sys.modules.setdefault('core.playlist', playlist_stub)

from core.m3u import parse_track_text, infer_track_metadata_from_path


def test_parse_track_text_basic():
    artist, title = parse_track_text("Queen - Bohemian Rhapsody")
    assert artist == "Queen"
    assert title == "Bohemian Rhapsody"


def test_parse_track_text_fallback():
    artist, title = parse_track_text("Bohemian Rhapsody")
    assert artist == "Unknown"
    assert title == "Bohemian Rhapsody"


def test_parse_track_text_extra_parts():
    artist, title = parse_track_text("Metallica - One - Live")
    assert artist == "Metallica"
    assert title == "One"


def test_infer_metadata_artist_title():
    meta = infer_track_metadata_from_path("Music/Metallica/Justice/Metallica - One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}


def test_infer_metadata_numbered_track():
    meta = infer_track_metadata_from_path("Music/Metallica/Justice/01 - One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}


def test_infer_metadata_simple_title():
    meta = infer_track_metadata_from_path("Music/Metallica/Justice/One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}


def test_infer_metadata_windows_path():
    meta = infer_track_metadata_from_path(r"C:\\Music\\Metallica\\Justice\\Metallica - One.mp3")
    assert meta == {"title": "One", "artist": "Metallica"}
