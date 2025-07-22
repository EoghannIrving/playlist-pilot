"""Tests for additional helpers in ``core.playlist`` and ``utils.helpers``."""

import ast
from pathlib import Path
import types
import pytest

from core import constants
from core.history import (
    save_whole_user_history,
    load_user_history,
    extract_date_from_label,
)


def _load_helpers_func(name):
    """Load a function from ``utils.helpers`` without importing the module."""
    src = Path("utils/helpers.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    module = ast.Module(body=[func], type_ignores=[])
    ns = {
        "settings": types.SimpleNamespace(jellyfin_user_id="user"),
        "load_user_history": load_user_history,
        "extract_date_from_label": extract_date_from_label,
    }
    exec(compile(module, filename=f"<helpers.{name}>", mode="exec"), ns)
    return ns[name]


load_sorted_history = _load_helpers_func("load_sorted_history")


def _load_func(name):
    """Load a function from ``core.playlist`` without importing the module."""
    src = Path("core/playlist.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    assigns = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "GENRE_SYNONYMS" for t in n.targets)
    ]
    module = ast.Module(body=assigns + [func], type_ignores=[])
    ns = {}
    exec(compile(module, filename=f"<{name}>", mode="exec"), ns)
    return ns[name]


parse_suggestion_line = _load_func("parse_suggestion_line")
infer_decade = _load_func("infer_decade")
normalize_genre = _load_func("normalize_genre")
estimate_tempo = _load_func("estimate_tempo")
extract_tag_value = _load_func("extract_tag_value")


def test_parse_suggestion_line_valid():
    text, reason = parse_suggestion_line("Song - Artist - Album - 2023 - Good")
    assert text == "Song - Artist - Album - 2023"
    assert reason == "Good"


def test_parse_suggestion_line_invalid():
    with pytest.raises(ValueError):
        parse_suggestion_line("Bad Line")


def test_infer_decade_and_normalize_genre():
    assert infer_decade("1994") == "1990s"
    assert infer_decade("oops") == "Unknown"
    assert normalize_genre("Alternative Rock") == "alternative"


def test_estimate_tempo_basic():
    assert estimate_tempo(250, "electronic") == 140
    assert estimate_tempo(400, "rock") == 120
    assert estimate_tempo(200, "hip hop") == 90
    assert estimate_tempo(500, "ambient") == 70


def test_extract_tag_value():
    tags = ["tempo:120", "mood:happy"]
    assert extract_tag_value(tags, "tempo") == "120"
    assert extract_tag_value(tags, "missing") is None


def test_load_sorted_history(monkeypatch, tmp_path):
    monkeypatch.setattr(constants, "USER_DATA_DIR", tmp_path)
    entries = [
        {"id": "1", "label": "Mix - 2023-01-01 10:00", "suggestions": []},
        {"id": "2", "label": "Mix - 2023-02-01 10:00", "suggestions": []},
    ]
    save_whole_user_history("user", entries)
    sorted_hist = load_sorted_history("user")
    assert sorted_hist[0]["id"] == "2"
