"""Tests for helper functions in ``core.playlist``."""

import ast
from pathlib import Path


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
    exec(compile(module, filename="<extract_year>", mode="exec"), ns)
    return ns["extract_year"]


extract_year = _load_extract_year()


def test_extract_year_fallback_to_premiere():
    track = {"ProductionYear": None, "PremiereDate": "2023-05-01T00:00:00Z"}
    assert extract_year(track) == "2023"


def test_extract_year_production_year_used():
    track = {"ProductionYear": 1999, "PremiereDate": "2020-01-01"}
    assert extract_year(track) == "1999"
