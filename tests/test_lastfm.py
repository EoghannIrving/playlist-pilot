"""Tests for the ``normalize`` helper in ``services.lastfm``."""

import sys
import types
import importlib


def _load_normalize(monkeypatch):
    """Import ``normalize`` with minimal stub modules."""

    monkeypatch.setitem(sys.modules, "httpx", types.ModuleType("httpx"))
    config_stub = types.ModuleType("config")
    config_stub.settings = types.SimpleNamespace(
        lastfm_api_key="", http_timeout_short=1, http_timeout_long=1
    )
    monkeypatch.setitem(sys.modules, "config", config_stub)
    cache_stub = types.ModuleType("utils.cache_manager")
    cache_stub.lastfm_cache = types.SimpleNamespace(
        get=lambda _k: None, set=lambda *_a, **_kw: None
    )
    cache_stub.CACHE_TTLS = {"lastfm": 1}
    monkeypatch.setitem(sys.modules, "utils.cache_manager", cache_stub)
    lastfm = importlib.import_module("services.lastfm")
    return lastfm.normalize


def test_normalize_basic(monkeypatch):
    """Parenthetical content and punctuation are removed."""
    normalize = _load_normalize(monkeypatch)
    assert normalize("Song Title (Live)") == "song title"


def test_normalize_multiple_parens(monkeypatch):
    """Repeated parentheses should be stripped without slowdown."""
    normalize = _load_normalize(monkeypatch)
    text = "(((Example)))"
    assert normalize(text) == ""


def test_normalize_long_spaces(monkeypatch):
    """Many spaces should not impact performance or output."""
    normalize = _load_normalize(monkeypatch)
    text = " " * 500 + "Example"
    assert normalize(text) == "example"


def test_normalize_long_open_parens(monkeypatch):
    """Strings starting with numerous '(' characters are handled."""
    normalize = _load_normalize(monkeypatch)
    text = "(" * 500 + "Example"
    assert normalize(text) == "example"
