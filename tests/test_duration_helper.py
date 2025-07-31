import ast
from pathlib import Path
import logging


def _load_func(name):
    src = Path("core/playlist.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    module = ast.Module(body=[func], type_ignores=[])
    ns = {"logger": logging.getLogger("test")}
    exec(compile(module, filename=f"<{name}>", mode="exec"), ns)
    return ns[name]


duration_from_ticks = _load_func("_duration_from_ticks")


def test_duration_from_ticks_with_bpm():
    assert duration_from_ticks(50_000_000, {"duration": "300"}) == 300


def test_duration_from_ticks_invalid_bpm():
    assert duration_from_ticks(50_000_000, {"duration": "oops"}) == 5


def test_duration_from_ticks_missing():
    assert duration_from_ticks(0, {"duration": None}) == 0
