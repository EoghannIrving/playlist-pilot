"""Tests for minimal FastAPI route helpers."""

# pylint: disable=exec-used

import ast
from pathlib import Path
import asyncio
import types
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile
from api.schemas import AnalysisExportRequest
from api.forms import SettingsForm
from api.routes import settings_routes, analysis_routes
from api.schemas import VerifyEntryRequest


def _extract_health_check():
    """Load the ``health_check`` coroutine from ``api.routes`` without importing."""
    src = Path("api/routes/monitoring_routes.py").read_text(encoding="utf-8")
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
    result = asyncio.run(health_check())
    assert result == {"status": "ok"}


def _extract_export_m3u():
    """Return the ``export_m3u`` coroutine without side effects."""
    src = Path("api/routes/analysis_routes.py").read_text(encoding="utf-8")
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
        "AnalysisExportRequest": AnalysisExportRequest,
    }
    exec(compile(module, filename="<export_m3u>", mode="exec"), ns)
    return ns["export_m3u"]


def _extract_import_m3u_file():
    """Return ``import_m3u_file`` coroutine without importing ``api.routes``."""
    src = Path("api/routes/analysis_routes.py").read_text(encoding="utf-8")
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
        asyncio.run(export_m3u(dummy_req))
    assert exc.value.status_code == 400


def test_import_m3u_file_invalid_extension(tmp_path):
    """Invalid file extensions should result in ``HTTPException``."""
    dummy_file = UploadFile(tmp_path / "test.txt", filename="test.txt")
    dummy_req = types.SimpleNamespace(headers={})
    dummy_payload = types.SimpleNamespace(m3u_file=dummy_file)
    import_m3u = _extract_import_m3u_file()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(import_m3u(dummy_req, dummy_payload))
    assert exc.value.status_code == 400


def test_verify_playlist_entry_uses_media_server(monkeypatch):
    """Verify-entry should resolve tracks through the adapter."""

    class DummyServer:
        async def get_playlist_tracks(self, _playlist_id):
            return [{"PlaylistItemId": "entry-1", "Name": "Song"}]

    monkeypatch.setattr(settings_routes, "get_media_server", lambda: DummyServer())

    result = asyncio.run(
        settings_routes.verify_playlist_entry(
            VerifyEntryRequest(playlist_id="playlist", entry_id="entry-1")
        )
    )

    assert result.success is True
    assert result.track["Name"] == "Song"


def test_update_settings_prefers_generic_media_fields(monkeypatch):
    """Settings updates should persist generic media fields and use adapter users."""

    class DummyServer:
        async def list_users(self):
            return [{"id": "u1", "name": "User One"}]

    captured = {}

    def fake_template_response(_template, context):
        captured.update(context)
        return context

    async def fake_models(_key):
        return ["gpt-4o-mini"]

    monkeypatch.setattr(settings_routes, "get_media_server", lambda: DummyServer())
    monkeypatch.setattr(
        settings_routes.templates, "TemplateResponse", fake_template_response
    )
    monkeypatch.setattr(settings_routes, "fetch_openai_models", fake_models)
    monkeypatch.setattr(settings_routes, "get_log_excerpt", lambda: "logs")
    monkeypatch.setattr(settings_routes, "save_settings", lambda _settings: None)

    form_data = SettingsForm(
        media_backend="jellyfin",
        media_url="http://media",
        media_api_key="media-key",
        media_user_id="media-user",
        jellyfin_url="http://legacy",
        jellyfin_api_key="legacy-key",
        jellyfin_user_id="legacy-user",
        openai_api_key="openai",
        cache_ttls={},
        getsongbpm_headers={},
    )

    result = asyncio.run(
        settings_routes.update_settings(
            request=types.SimpleNamespace(),
            form_data=form_data,
        )
    )

    assert result["media_server_users"] == {"User One": "u1"}
    assert settings_routes.settings.media_url == "http://media"
    assert settings_routes.settings.media_api_key == "media-key"
    assert settings_routes.settings.media_user_id == "media-user"


def test_test_jellyfin_route_supports_navidrome_backend(monkeypatch):
    """The transitional test route should support Navidrome credentials."""

    class DummyAdapter:
        async def test_connection(self):
            return {"success": True, "status": 200, "data": {"status": "ok"}}

    monkeypatch.setattr(
        settings_routes,
        "NavidromeAdapter",
        lambda **_kwargs: DummyAdapter(),
    )

    result = asyncio.run(
        settings_routes.test_jellyfin(
            settings_routes.JellyfinTestRequest(
                backend="navidrome",
                url="http://nav",
                username="user",
                password="pass",
            )
        )
    )

    assert result.success is True
    assert result.status == 200


def test_test_media_server_route_supports_navidrome_backend(monkeypatch):
    """The backend-neutral test route should support Navidrome credentials."""

    class DummyAdapter:
        async def test_connection(self):
            return {"success": True, "status": 200, "data": {"status": "ok"}}

    monkeypatch.setattr(
        settings_routes,
        "NavidromeAdapter",
        lambda **_kwargs: DummyAdapter(),
    )

    result = asyncio.run(
        settings_routes.test_media_server(
            settings_routes.JellyfinTestRequest(
                backend="navidrome",
                url="http://nav",
                username="user",
                password="pass",
            )
        )
    )

    assert result.success is True
    assert result.status == 200


def test_index_passes_refresh_to_playlist_cache(monkeypatch):
    """Index should forward the refresh flag to the playlist cache helper."""

    captured = {}

    async def fake_get_cached_playlists(user_id, force_refresh=False):
        captured["user_id"] = user_id
        captured["force_refresh"] = force_refresh
        return {"playlists": [], "error": None}

    def fake_template_response(_template, context):
        return context

    monkeypatch.setattr(
        analysis_routes, "get_cached_playlists", fake_get_cached_playlists
    )
    monkeypatch.setattr(analysis_routes, "current_user_scope", lambda: "user-1")
    monkeypatch.setattr(
        analysis_routes, "load_sorted_history", lambda _user_id=None: []
    )
    monkeypatch.setattr(
        analysis_routes.templates, "TemplateResponse", fake_template_response
    )
    monkeypatch.setattr(
        analysis_routes.settings.__class__,
        "validate_settings",
        lambda _self: None,
        raising=False,
    )

    result = asyncio.run(
        analysis_routes.index(
            types.SimpleNamespace(url=types.SimpleNamespace(path="/")), refresh=True
        )
    )

    assert captured == {"user_id": "user-1", "force_refresh": True}
    assert result["refresh_requested"] is True


def test_show_analysis_page_passes_refresh_to_playlist_cache(monkeypatch):
    """Analyze page should support forcing a fresh server playlist fetch."""

    captured = {}

    async def fake_get_cached_playlists(user_id, force_refresh=False):
        captured["user_id"] = user_id
        captured["force_refresh"] = force_refresh
        return {"playlists": [], "error": None}

    def fake_template_response(_template, context):
        return context

    monkeypatch.setattr(
        analysis_routes, "get_cached_playlists", fake_get_cached_playlists
    )
    monkeypatch.setattr(analysis_routes, "current_user_scope", lambda: "user-1")
    monkeypatch.setattr(
        analysis_routes, "load_sorted_history", lambda _user_id=None: []
    )
    monkeypatch.setattr(
        analysis_routes.templates, "TemplateResponse", fake_template_response
    )

    result = asyncio.run(
        analysis_routes.show_analysis_page(
            types.SimpleNamespace(url=types.SimpleNamespace(path="/analyze")),
            refresh=True,
        )
    )

    assert captured == {"user_id": "user-1", "force_refresh": True}
    assert result["refresh_requested"] is True
