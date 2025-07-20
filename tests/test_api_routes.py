"""Tests for minimal FastAPI route helpers."""

# pylint: disable=exec-used

import ast
from pathlib import Path
import asyncio


def _extract_health_check():
    """Load the ``health_check`` coroutine from ``api.routes`` without importing."""
    src = Path("api/routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check")
    func.decorator_list = []
    module = ast.Module(body=[func], type_ignores=[])
    ns = {}
    exec(compile(module, filename="<health>", mode="exec"), ns)  # pylint: disable=exec-used
    return ns["health_check"]


def test_health_check():
    """``health_check`` should return the expected status dictionary."""
    health_check = _extract_health_check()
    result = asyncio.get_event_loop().run_until_complete(health_check())
    assert result == {"status": "ok"}
