import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Stub missing third-party modules
sys.modules.setdefault("httpx", types.ModuleType("httpx"))

# Remove playlist stub from other tests if present
sys.modules.pop("core.playlist", None)

# Minimal diskcache stub used by utils.cache_manager
cache_mod = types.ModuleType("diskcache")
class DummyCache(dict):
    def get(self, k, default=None):
        return super().get(k, default)
    def set(self, k, v, expire=None):
        self[k] = v
cache_mod.Cache = DummyCache
sys.modules.setdefault("diskcache", cache_mod)

# Stub out heavy service modules
getsongbpm_stub = types.ModuleType("services.getsongbpm")
getsongbpm_stub.get_cached_bpm = lambda *a, **k: {}
sys.modules["services.getsongbpm"] = getsongbpm_stub

gpt_stub = types.ModuleType("services.gpt")
gpt_stub.analyze_mood_from_lyrics = lambda *_a, **_kw: {}
sys.modules["services.gpt"] = gpt_stub

jellyfin_stub = types.ModuleType("services.jellyfin")
jellyfin_stub.jf_get = lambda *_a, **_kw: {}
jellyfin_stub.fetch_tracks_for_playlist_id = lambda *_a, **_kw: []
jellyfin_stub.fetch_jellyfin_track_metadata = lambda *_a, **_kw: {}
sys.modules["services.jellyfin"] = jellyfin_stub

metube_stub = types.ModuleType("services.metube")
metube_stub.get_youtube_url_single = lambda *_a, **_kw: (None, None)
sys.modules["services.metube"] = metube_stub

# Provide dummy cache manager used by playlist module
cache_manager_stub = types.ModuleType("utils.cache_manager")
cache_manager_stub.library_cache = DummyCache()
cache_manager_stub.CACHE_TTLS = {"full_library": 60}
sys.modules["utils.cache_manager"] = cache_manager_stub

# Stub analysis helpers
analysis_stub = types.ModuleType("core.analysis")
analysis_stub.mood_scores_from_bpm_data = lambda *_a, **_kw: {}
analysis_stub.mood_scores_from_lastfm_tags = lambda *_a, **_kw: {}
analysis_stub.combine_mood_scores = lambda *_a, **_kw: ("Neutral", 0.0)
analysis_stub.normalize_popularity = lambda v, *_a: v or 0
analysis_stub.combined_popularity_score = lambda *_a, **_kw: 0
analysis_stub.normalize_popularity_log = lambda v, *_a: v or 0
analysis_stub.build_lyrics_scores = lambda *_a, **_kw: {}
analysis_stub.add_combined_popularity = lambda *_a, **_kw: None
analysis_stub.summarize_tracks = lambda *_a, **_kw: {}
sys.modules.setdefault("core.analysis", analysis_stub)

# services.lastfm will be patched in tests
lfm_stub = types.ModuleType("services.lastfm")
async def _dummy_enrich(*_a, **_kw):
    return {"tags": [], "listeners": 0, "album": ""}
lfm_stub.enrich_with_lastfm = _dummy_enrich
sys.modules["services.lastfm"] = lfm_stub

from core.playlist import (
    parse_suggestion_line,
    extract_tag_value,
    infer_decade,
    enrich_track,
)
from core.models import Track

import pytest


def test_parse_suggestion_line():
    text, reason = parse_suggestion_line(
        "Song - Artist - Album - 1999 - Because it's great"
    )
    assert text == "Song - Artist - Album - 1999"
    assert reason == "Because it's great"


def test_extract_tag_value():
    tags = ["tempo:120", "mood:happy"]
    assert extract_tag_value(tags, "tempo") == "120"
    assert extract_tag_value(tags, "genre") is None


def test_infer_decade():
    assert infer_decade("1999") == "1990s"
    assert infer_decade("abc") == "Unknown"
