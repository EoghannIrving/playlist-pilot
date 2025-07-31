"""Tests for the ``_duration_from_ticks`` helper."""

import ast
import logging
from pathlib import Path


def _load_func(name):
    """Load a single function from ``core.playlist`` without side effects."""

    src = Path("core/playlist.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    module = ast.Module(body=[func], type_ignores=[])
    ns = {"logger": logging.getLogger("test")}
    exec(  # pylint: disable=exec-used
        compile(module, filename=f"<{name}>", mode="exec"),
        ns,
    )
    return ns[name]


duration_from_ticks = _load_func("_duration_from_ticks")


def test_duration_from_ticks_with_bpm():
    """BPM data should override the tick-based duration."""

    assert duration_from_ticks(50_000_000, {"duration": "300"}) == 300


def test_duration_from_ticks_invalid_bpm():
    """Invalid BPM values should fall back to tick duration."""

    assert duration_from_ticks(50_000_000, {"duration": "oops"}) == 5


def test_duration_from_ticks_missing():
    """No duration data should yield zero seconds."""

    assert duration_from_ticks(0, {"duration": None}) == 0
