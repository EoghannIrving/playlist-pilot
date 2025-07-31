"""Tests for Jellyfin and GPT helper functions using lightweight stubs."""

import sys
import types
import importlib
import asyncio
import pytest


# Stub httpx for jellyfin service
class DummyResp:
    """Simple stand-in for ``httpx.Response``."""

    def __init__(self, items):
        self._items = items
        self.status_code = 200

    def json(self):
        """Return the response JSON payload."""
        return {"Items": self._items}

    def raise_for_status(self):
        """Pretend to validate the response status."""
        return None


class DummyClient:
    """Async client stub used by ``make_httpx_stub``."""

    def __init__(self, items):
        self._items = items

    async def __aenter__(self):
        """Enter the asynchronous context."""
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Exit the asynchronous context without special handling."""
        return None

    async def get(self, *_args, **_kwargs):
        """Return a dummy response object."""
        return DummyResp(self._items)


def make_httpx_stub(items):
    """Create a minimal ``httpx`` stub returning ``items``."""
    module = types.ModuleType("httpx")
    module.AsyncClient = lambda *a, **kw: DummyClient(items)
    return module


# Stub diskcache Cache used by jellyfin module
class DummyCache(dict):
    """Minimal ``diskcache.Cache`` replacement used for tests."""

    def get(self, _key):
        """Return ``None`` for any missing key."""
        return None

    def set(self, _key, value, expire=None):
        """Store ``value`` ignoring the ``expire`` parameter."""
        _ = expire  # accept ``expire`` keyword for compatibility
        self[_key] = value


sys.modules["diskcache"] = types.ModuleType("diskcache")
sys.modules["diskcache"].Cache = DummyCache  # type: ignore[attr-defined]

# Stub utils.cache_manager used inside jellyfin
jellyfin_cache_stub = types.ModuleType("utils.cache_manager")
jellyfin_cache_stub.jellyfin_track_cache = DummyCache()  # type: ignore[attr-defined]
jellyfin_cache_stub.CACHE_TTLS = {"jellyfin_tracks": 1}  # type: ignore[attr-defined]
sys.modules["utils.cache_manager"] = jellyfin_cache_stub


def test_search_jellyfin_track_found(monkeypatch):
    """Return ``True`` when the Jellyfin API finds a matching item."""
    sys.modules["httpx"] = make_httpx_stub(
        [{"Name": "My Song", "Artists": ["My Artist"]}]
    )
    sys.modules.pop("services.jellyfin", None)
    jellyfin = importlib.import_module("services.jellyfin")  # import after stubbing
    monkeypatch.setattr(jellyfin, "jellyfin_track_cache", DummyCache())
    found = asyncio.get_event_loop().run_until_complete(
        jellyfin.search_jellyfin_for_track("My Song", "My Artist")
    )
    assert found is True


def test_search_jellyfin_track_not_found(monkeypatch):
    """Return ``False`` when the Jellyfin API returns no results."""
    sys.modules["httpx"] = make_httpx_stub([])
    sys.modules.pop("services.jellyfin", None)
    jellyfin = importlib.import_module("services.jellyfin")
    monkeypatch.setattr(jellyfin, "jellyfin_track_cache", DummyCache())
    found = asyncio.get_event_loop().run_until_complete(
        jellyfin.search_jellyfin_for_track("Other", "Artist")
    )
    assert found is False


def test_search_jellyfin_track_smart_quotes(monkeypatch):
    """Smart quotes should be normalized when matching tracks."""
    sys.modules["httpx"] = make_httpx_stub(
        [{"Name": "Don’t Stop", "Artists": ["My Artist"]}]
    )
    sys.modules.pop("services.jellyfin", None)
    jellyfin = importlib.import_module("services.jellyfin")
    monkeypatch.setattr(jellyfin, "jellyfin_track_cache", DummyCache())
    found = asyncio.get_event_loop().run_until_complete(
        jellyfin.search_jellyfin_for_track("Don't Stop", "My Artist")
    )
    assert found is True


def test_parse_gpt_line():
    """Validate GPT line parsing and popularity descriptions."""
    # Stub openai so importing services.gpt succeeds
    openai_stub = types.ModuleType("openai")

    class Dummy:  # pylint: disable=too-few-public-methods
        """Simple OpenAI client stub used for import."""

        def __init__(self, **_kwargs):
            """Ignore initialization parameters."""
            return

    openai_stub.OpenAI = Dummy
    openai_stub.AsyncOpenAI = Dummy
    openai_stub.OpenAIError = Exception
    sys.modules["openai"] = openai_stub
    # Stub utils.cache_manager for gpt
    gpt_cache_stub = types.ModuleType("utils.cache_manager")
    gpt_cache_stub.prompt_cache = DummyCache()
    gpt_cache_stub.lastfm_cache = DummyCache()
    gpt_cache_stub.CACHE_TTLS = {"prompt": 1}
    sys.modules["utils.cache_manager"] = gpt_cache_stub
    gpt_mod = importlib.import_module("services.gpt")
    parse_gpt_line = gpt_mod.parse_gpt_line
    describe_popularity = gpt_mod.describe_popularity

    title, artist = parse_gpt_line("Song - Artist - Album - 2020 - Reason")
    assert title == "Song"
    assert artist == "Artist"

    title, artist = parse_gpt_line("Another Song by Some Artist - Reason")
    assert title == "Another Song"
    assert artist == "Some Artist"

    with pytest.raises(ValueError):
        parse_gpt_line("Malformed line")

    assert describe_popularity(95) == "Global smash hit"
    assert describe_popularity(75) == "Mainstream favorite"
    assert describe_popularity(55) == "Moderately mainstream"
    assert describe_popularity(35) == "Niche appeal"
    assert describe_popularity(10) == "Obscure or local"


def test_strip_number_prefix():
    """strip_number_prefix should remove leading digits and punctuation."""
    openai_stub = types.ModuleType("openai")

    class Dummy:  # pylint: disable=too-few-public-methods
        """Simple OpenAI client stub used for import."""

        def __init__(self, **_kwargs):
            """Ignore initialization parameters."""
            return

    openai_stub.OpenAI = Dummy
    openai_stub.AsyncOpenAI = Dummy
    openai_stub.OpenAIError = Exception
    sys.modules["openai"] = openai_stub

    cache_stub = types.ModuleType("utils.cache_manager")
    cache_stub.prompt_cache = DummyCache()
    cache_stub.lastfm_cache = DummyCache()
    cache_stub.CACHE_TTLS = {"prompt": 1}
    sys.modules["utils.cache_manager"] = cache_stub

    gpt_mod = importlib.import_module("services.gpt")
    strip_prefix = gpt_mod.strip_number_prefix

    assert strip_prefix("1. Song - Artist") == "Song - Artist"
    assert strip_prefix("10) Track - Name") == "Track - Name"


def test_format_removal_suggestions():
    """Format removal suggestions and drop invalid trailing lines."""
    openai_stub = types.ModuleType("openai")

    class Dummy:  # pylint: disable=too-few-public-methods
        """Simple OpenAI client stub used for import."""

        def __init__(self, **_kwargs):
            return

    openai_stub.OpenAI = Dummy
    openai_stub.AsyncOpenAI = Dummy
    openai_stub.OpenAIError = Exception
    sys.modules["openai"] = openai_stub

    cache_stub = types.ModuleType("utils.cache_manager")
    cache_stub.prompt_cache = DummyCache()
    cache_stub.lastfm_cache = DummyCache()
    cache_stub.CACHE_TTLS = {"prompt": 1}
    sys.modules["utils.cache_manager"] = cache_stub

    gpt_mod = importlib.import_module("services.gpt")
    format_lines = gpt_mod.format_removal_suggestions

    raw = "1. Foo - Bar - Reason\n2. Baz - Qux - Another\nThanks!"
    tracks = [
        {"title": "Foo", "artist": "Bar", "PlaylistItemId": "1"},
        {"title": "Baz", "artist": "Qux", "PlaylistItemId": "2"},
    ]
    result = format_lines(raw, tracks)
    assert result == [
        {
            "html": "<strong>Foo</strong> - <strong>Bar</strong> - Reason",
            "item_id": "1",
        },
        {
            "html": "<strong>Baz</strong> - <strong>Qux</strong> - Another",
            "item_id": "2",
        },
    ]


def test_format_removal_suggestions_by_style():
    """Preserve explanation text when GPT uses 'by' formatting."""
    openai_stub = types.ModuleType("openai")

    class Dummy:  # pylint: disable=too-few-public-methods
        """Simple OpenAI client stub used for import."""

        def __init__(self, **_kwargs):
            return

    openai_stub.OpenAI = Dummy
    openai_stub.AsyncOpenAI = Dummy
    openai_stub.OpenAIError = Exception
    sys.modules["openai"] = openai_stub

    cache_stub = types.ModuleType("utils.cache_manager")
    cache_stub.prompt_cache = DummyCache()
    cache_stub.lastfm_cache = DummyCache()
    cache_stub.CACHE_TTLS = {"prompt": 1}
    sys.modules["utils.cache_manager"] = cache_stub

    gpt_mod = importlib.import_module("services.gpt")
    format_lines = gpt_mod.format_removal_suggestions

    raw = "1. Track One by Artist A - too fast"
    tracks = [{"title": "Track One", "artist": "Artist A", "PlaylistItemId": "x"}]
    result = format_lines(raw, tracks)
    assert result == [
        {
            "html": "<strong>Track One</strong> - <strong>Artist A</strong> - too fast",
            "item_id": "x",
        },
    ]
