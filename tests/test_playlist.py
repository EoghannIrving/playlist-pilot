"""Tests for helper functions in ``core.playlist``."""

import ast
from pathlib import Path

from core.playlist import normalize_track  # add import


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
