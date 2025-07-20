import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Stub heavy dependencies to allow importing main app
jinja2_stub = types.ModuleType("jinja2")
sys.modules["jinja2"] = jinja2_stub
sys.modules["openai"] = types.ModuleType("openai")
sys.modules.pop("core.playlist", None)
multipart_pkg = types.ModuleType("multipart")
multipart_sub = types.ModuleType("multipart.multipart")
multipart_sub.parse_options_header = lambda *_a, **_kw: ("", {})
multipart_pkg.__version__ = "0"
sys.modules["multipart"] = multipart_pkg
sys.modules["multipart.multipart"] = multipart_sub
os.makedirs("logs", exist_ok=True)

cache_mod = types.ModuleType("diskcache")
class DummyCache(dict):
    def get(self, k, default=None):
        return super().get(k, default)
    def set(self, k, v, expire=None):
        self[k] = v
cache_mod.Cache = DummyCache
sys.modules.setdefault("diskcache", cache_mod)

# services stubs used during import
for name in [
    "services.jellyfin",
    "services.gpt",
    "services.getsongbpm",
    "services.metube",
]:
    mod = types.ModuleType(name)
    if name == "services.getsongbpm":
        mod.get_cached_bpm = lambda *a, **kw: {}
    if name == "services.jellyfin":
        mod.jf_get = lambda *_a, **_kw: {}
        mod.fetch_tracks_for_playlist_id = lambda *_a, **_kw: []
        mod.fetch_jellyfin_track_metadata = lambda *_a, **_kw: {}
        mod.create_jellyfin_playlist = lambda *_a, **_kw: {}
        mod.fetch_jellyfin_users = lambda *_a, **_kw: []
        mod.resolve_jellyfin_path = lambda *_a, **_kw: ""
    if name == "services.gpt":
        mod.analyze_mood_from_lyrics = lambda *_a, **_kw: {}
        mod.generate_playlist_analysis_summary = lambda *_a, **_kw: ("", [])
        mod.fetch_gpt_suggestions = lambda *_a, **_kw: []
        mod.fetch_openai_models = lambda *_a, **_kw: []
    if name == "services.metube":
        mod.get_youtube_url_single = lambda *_a, **_kw: (None, None)
    sys.modules[name] = mod

cache_mgr_stub = types.ModuleType("utils.cache_manager")
cache_mgr_stub.lastfm_cache = DummyCache()
cache_mgr_stub.CACHE_TTLS = {"lastfm": 60}
cache_mgr_stub.library_cache = DummyCache()
cache_mgr_stub.playlist_cache = DummyCache()
sys.modules["utils.cache_manager"] = cache_mgr_stub

# Minimal templates stub
templates_mod = types.ModuleType("core.templates")
class DummyTemplates:
    def TemplateResponse(self, *_a, **_kw):
        return ""
templates_mod.templates = DummyTemplates()
sys.modules["core.templates"] = templates_mod

# Stub services.lastfm for import; real functions will be patched later
lfm_mod = types.ModuleType("services.lastfm")
async def dummy_get_tags(*_a, **_kw):
    return []
lfm_mod.get_lastfm_tags = dummy_get_tags
async def dummy_enrich(*_a, **_kw):
    return {}
lfm_mod.enrich_with_lastfm = dummy_enrich
sys.modules["services.lastfm"] = lfm_mod

import asyncio
from api import routes
import pytest


def test_health():
    assert asyncio.run(routes.health_check()) == {"status": "ok"}


def test_lastfm_route(monkeypatch):

    async def fake_get(url, params=None, **_kw):
        class Resp:
            status_code = 200
            def json(self):
                return {"results": {}}
        return Resp()

    httpx_mod = types.ModuleType("httpx")
    class DummyClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, *a, **kw):
            return await fake_get(*a, **kw)
    httpx_mod.AsyncClient = DummyClient
    httpx_mod.HTTPError = Exception
    monkeypatch.setitem(sys.modules, "httpx", httpx_mod)
    monkeypatch.setattr(routes, "httpx", httpx_mod)

    class DummyRequest:
        async def json(self):
            return {"key": "abc"}

    request = DummyRequest()
    response = asyncio.run(routes.test_lastfm(request))
    assert response.status_code == 200
    import json
    assert json.loads(response.body)["success"] is True
