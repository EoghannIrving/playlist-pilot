"""Tests for minimal FastAPI route helpers."""

# pylint: disable=exec-used

import ast
from pathlib import Path
import asyncio
import types
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile


def _extract_health_check():
    """Load the ``health_check`` coroutine from ``api.routes`` without importing."""
    src = Path("api/routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"
    )
    func.decorator_list = []
    module = ast.Module(body=[func], type_ignores=[])
    ns = {}
    exec(
        compile(module, filename="<health>", mode="exec"), ns
    )  # pylint: disable=exec-used
    return ns["health_check"]


def test_health_check():
    """``health_check`` should return the expected status dictionary."""
    health_check = _extract_health_check()
    result = asyncio.get_event_loop().run_until_complete(health_check())
    assert result == {"status": "ok"}


def _extract_export_m3u():
    """Return the ``export_m3u`` coroutine without side effects."""
    src = Path("api/routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "export_m3u"
    )
    func.decorator_list = []
    module = ast.Module(body=[func], type_ignores=[])
    ns = {
        "HTTPException": HTTPException,
        "BackgroundTask": object,
        "FileResponse": object,
        "resolve_jellyfin_path": lambda *a, **k: None,
        "settings": object,
        "uuid": __import__("uuid"),
        "tempfile": __import__("tempfile"),
        "Path": Path,
        "Request": object,
    }
    exec(compile(module, filename="<export_m3u>", mode="exec"), ns)
    return ns["export_m3u"]


def _extract_import_m3u_file():
    """Return ``import_m3u_file`` coroutine without importing ``api.routes``."""
    src = Path("api/routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "import_m3u_file"
    )
    func.decorator_list = []
    func.args.defaults = []
    func.args.kw_defaults = []
    for arg in func.args.args[:2]:
        arg.annotation = None
    func.returns = None
    module = ast.Module(body=[func], type_ignores=[])
    ns = {
        "HTTPException": HTTPException,
        "import_m3u_as_history_entry": lambda _: None,
        "cleanup_temp_file": lambda _: None,
        "tempfile": __import__("tempfile"),
        "shutil": __import__("shutil"),
        "Path": Path,
        "RedirectResponse": type("Resp", (), {}),
    }
    exec(compile(module, filename="<import_m3u_file>", mode="exec"), ns)
    return ns["import_m3u_file"]


def test_export_m3u_no_tracks():
    """``export_m3u`` should reject empty track lists."""
    export_m3u = _extract_export_m3u()

    async def dummy_json():
        """Return an empty track list in request body."""
        return {"name": "x", "tracks": []}

    dummy_req = types.SimpleNamespace(json=dummy_json)

    with pytest.raises(HTTPException) as exc:
        asyncio.get_event_loop().run_until_complete(export_m3u(dummy_req))
    assert exc.value.status_code == 400


def test_import_m3u_file_invalid_extension(tmp_path):
    """Invalid file extensions should result in ``HTTPException``."""
    dummy_file = UploadFile(tmp_path / "test.txt", filename="test.txt")
    dummy_req = types.SimpleNamespace(headers={})
    dummy_payload = types.SimpleNamespace(m3u_file=dummy_file)
    import_m3u = _extract_import_m3u_file()

    with pytest.raises(HTTPException) as exc:
        asyncio.get_event_loop().run_until_complete(
            import_m3u(dummy_req, dummy_payload)
        )
    assert exc.value.status_code == 400
