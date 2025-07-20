import os
import sys
import ast
from pathlib import Path
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _extract_health_check():
    src = Path("api/routes.py").read_text()
    tree = ast.parse(src)
    func = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check")
    func.decorator_list = []
    module = ast.Module(body=[func], type_ignores=[])
    ns = {}
    exec(compile(module, filename="<health>", mode="exec"), ns)
    return ns["health_check"]


def test_health_check():
    health_check = _extract_health_check()
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(health_check())
    assert result == {"status": "ok"}
