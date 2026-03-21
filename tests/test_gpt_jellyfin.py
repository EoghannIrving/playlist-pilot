"""Tests for Jellyfin and GPT helper functions using lightweight stubs."""

import sys
import types
import importlib
import asyncio
import logging
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

    title, artist = parse_gpt_line("Em Dash Song — Em Dash Artist - Reason")
    assert title == "Em Dash Song"
    assert artist == "Em Dash Artist"

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
            "title": "Foo",
            "artist": "Bar",
            "reason": "Reason",
            "item_id": "1",
        },
        {
            "title": "Baz",
            "artist": "Qux",
            "reason": "Another",
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
            "title": "Track One",
            "artist": "Artist A",
            "reason": "too fast",
            "item_id": "x",
        },
    ]


def test_format_removal_suggestions_multiline_justification():
    """Multiline removal suggestions should be collapsed into one entry."""
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

    raw = (
        "The Whole of the Moon (video version) - The Waterboys\n"
        "Justification: While it has a chill mood, the track's more expansive "
        "and expressive sound may disrupt the overall vibe.\n"
        "China in Your Hand - T'Pau"
    )
    tracks = [
        {
            "title": "The Whole of the Moon (video version)",
            "artist": "The Waterboys",
            "PlaylistItemId": "1",
        },
        {"title": "China in Your Hand", "artist": "T'Pau", "PlaylistItemId": "2"},
    ]
    result = format_lines(raw, tracks)
    assert result == [
        {
            "title": "The Whole of the Moon (video version)",
            "artist": "The Waterboys",
            "reason": "While it has a chill mood, the track's more expansive and expressive sound may disrupt the overall vibe.",
            "item_id": "1",
        },
        {
            "title": "China in Your Hand",
            "artist": "T'Pau",
            "reason": None,
            "item_id": "2",
        },
    ]


def test_extract_remaining_handles_dashes():
    """_extract_remaining should ignore dashes inside titles or artists."""
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
    extract = gpt_mod._extract_remaining  # pylint: disable=protected-access

    text = "Rock - Remix - Artist - extra - notes"
    assert extract(text, "Rock - Remix", "Artist") == "extra - notes"

    text = "Song - DJ - Mix - explanation"
    assert extract(text, "Song", "DJ - Mix") == "explanation"


def test_normalize_track_key_strips_version_suffixes():
    """Duplicate comparison should ignore common version suffixes."""
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

    assert gpt_mod.normalize_track_key(
        "The Whole of the Moon (video version)", "The Waterboys"
    ) == gpt_mod.normalize_track_key("The Whole of the Moon", "The Waterboys")


def test_gpt_suggest_validated_rejects_source_and_batch_duplicates(monkeypatch):
    """Suggestions should reject source-playlist and repeated normalized duplicates."""
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

    async def fake_completion(
        _prompt, temperature=0.7
    ):  # pylint: disable=unused-argument
        return (
            "The Whole of the Moon (video version) - The Waterboys - Reason\n"
            "The Whole of the Moon - The Waterboys - Another reason\n"
            "Only You - Yazoo - Keep\n"
            "Only You - Yazoo - Duplicate in batch"
        )

    async def fake_track_info(_title, _artist):
        return {"listeners": "100"}

    monkeypatch.setattr(gpt_mod, "cached_chat_completion", fake_completion)
    monkeypatch.setattr(gpt_mod, "get_lastfm_track_info", fake_track_info)

    result = asyncio.run(
        gpt_mod.gpt_suggest_validated(
            existing_tracks=["The Whole of the Moon - The Waterboys"],
            count=10,
            exclude_pairs={("The Whole of the Moon", "The Waterboys")},
        )
    )

    assert result == [
        {
            "title": "Only You",
            "artist": "Yazoo",
            "text": "Only You - Yazoo - Keep",
            "year": None,
            "popularity": 100,
            "tags": [],
            "decade": None,
            "fit_breakdown": {
                "decade_score": 0.5,
                "genre_score": 0.5,
                "mood_score": 0.5,
                "popularity_score": 0.5,
                "fit_score": 50.0,
            },
            "fit_score": 50.0,
        }
    ]


def test_detect_strict_decade_window():
    """Explicit decade playlist names should map to exact decade windows."""
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

    assert gpt_mod.detect_strict_decade_window("80s") == (1980, 1989)
    assert gpt_mod.detect_strict_decade_window("1980s essentials") == (1980, 1989)
    assert gpt_mod.detect_strict_decade_window("2000s mix") == (2000, 2009)
    assert gpt_mod.detect_strict_decade_window("Road Trip") is None


def test_build_prompt_context_strict_decade():
    """Prompt context should reflect strict decade mode and summary inputs."""
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

    context = gpt_mod.build_prompt_context(
        summary={
            "dominant_genre": "new wave",
            "mood_profile": {"romantic": "60%", "chill": "40%"},
            "tempo_avg": 102,
            "decades": {"1980s": "100%"},
        },
        profile_summary="An 80s synth-driven playlist.",
        playlist_name="80s",
    )
    prompt = gpt_mod._build_gpt_prompt(  # pylint: disable=protected-access
        ["Only You - Yazoo"],
        10,
        summary={
            "dominant_genre": "new wave",
            "mood_profile": {"romantic": "60%", "chill": "40%"},
            "tempo_avg": 102,
            "decades": {"1980s": "100%"},
            "avg_popularity": 55,
        },
        profile_summary="An 80s synth-driven playlist.",
        playlist_name="80s",
    )

    assert context["playlist_mode"] == "strict_decade"
    assert context["decade_window"] == (1980, 1989)
    assert context["dominant_genre"] == "new wave"
    assert context["moods"] == ["romantic", "chill"]
    assert "Suggestion mode: strict_decade" in prompt
    assert "Target decade window: 1980-1989" in prompt
    assert "Stay inside 1980-1989." in prompt
    assert "Mode-specific rules (strict_decade):" in prompt
    assert "Do not use later vibe-match substitutions" in prompt


def test_build_prompt_context_profile_match():
    """Prompt context should emit a different instruction block for profile mode."""
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

    context = gpt_mod.build_prompt_context(
        summary={
            "dominant_genre": "indie",
            "mood_profile": {"chill": "70%", "romantic": "30%"},
            "tempo_avg": 96,
            "decades": {"2000s": "60%", "2010s": "40%"},
        },
        profile_summary="A mellow indie mix.",
        playlist_name="Late Night Mix",
    )
    prompt = gpt_mod._build_gpt_prompt(  # pylint: disable=protected-access
        ["Chasing Cars - Snow Patrol"],
        10,
        summary={
            "dominant_genre": "indie",
            "mood_profile": {"chill": "70%", "romantic": "30%"},
            "tempo_avg": 96,
            "decades": {"2000s": "60%", "2010s": "40%"},
            "avg_popularity": 60,
        },
        profile_summary="A mellow indie mix.",
        playlist_name="Late Night Mix",
    )

    assert context["playlist_mode"] == "profile_match"
    assert context["decade_window"] is None
    assert "Suggestion mode: profile_match" in prompt
    assert "Mode-specific rules (profile_match):" in prompt
    assert "Avoid generic prestige picks or streaming-era melancholy tracks" in prompt
    assert "Suggest tracks released inside" not in prompt
    assert "Do not use later vibe-match substitutions" not in prompt


def test_gpt_suggest_validated_rejects_out_of_decade_candidates(monkeypatch):
    """Strict decade playlists should reject suggestions outside the detected decade."""
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

    async def fake_completion(
        _prompt, temperature=0.7
    ):  # pylint: disable=unused-argument
        return (
            "I Want to Break Free - Queen - The Works - 1984 - Keep\n"
            "Chasing Cars - Snow Patrol - Eyes Open - 2006 - Reject\n"
            "The Night We Met - Lord Huron - Strange Trails - 2015 - Reject"
        )

    async def fake_track_info(title, _artist):
        releasedates = {
            "I Want to Break Free": "28 Feb 1984",
            "Chasing Cars": "6 Jun 2006",
            "The Night We Met": "9 Apr 2015",
        }
        return {"listeners": "100", "releasedate": releasedates[title]}

    monkeypatch.setattr(gpt_mod, "cached_chat_completion", fake_completion)
    monkeypatch.setattr(gpt_mod, "get_lastfm_track_info", fake_track_info)

    result = asyncio.run(
        gpt_mod.gpt_suggest_validated(
            existing_tracks=["Only You - Yazoo"],
            count=10,
            playlist_name="80s",
        )
    )

    assert result == [
        {
            "title": "I Want to Break Free",
            "artist": "Queen",
            "text": "I Want to Break Free - Queen - The Works - 1984 - Keep",
            "year": 1984,
            "popularity": 100,
            "tags": [],
            "decade": "1980s",
            "fit_breakdown": {
                "decade_score": 1.0,
                "genre_score": 0.5,
                "mood_score": 0.5,
                "popularity_score": 0.5,
                "fit_score": 67.5,
            },
            "fit_score": 67.5,
        }
    ]


def test_gpt_suggest_validated_logs_prompt_context_and_fit_breakdown(
    monkeypatch, caplog
):
    """Suggestion runs should log prompt context, rejection counts, and fit breakdowns."""
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

    async def fake_completion(
        _prompt, temperature=0.7
    ):  # pylint: disable=unused-argument
        return (
            "Only You - Yazoo - Album - 1982 - Duplicate source\n"
            "I Want to Break Free - Queen - The Works - 1984 - Keep"
        )

    async def fake_track_info(title, _artist):
        payloads = {
            "Only You": {
                "listeners": "500",
                "releasedate": "1 Jan 1982",
                "toptags": {"tag": [{"name": "synthpop"}, {"name": "romantic"}]},
            },
            "I Want to Break Free": {
                "listeners": "1000",
                "releasedate": "1 Jan 1984",
                "toptags": {"tag": [{"name": "rock"}, {"name": "chill"}]},
            },
        }
        return payloads[title]

    monkeypatch.setattr(gpt_mod, "cached_chat_completion", fake_completion)
    monkeypatch.setattr(gpt_mod, "get_lastfm_track_info", fake_track_info)

    with caplog.at_level(logging.INFO, logger="playlist-pilot"):
        result = asyncio.run(
            gpt_mod.gpt_suggest_validated(
                existing_tracks=["Only You - Yazoo"],
                count=10,
                summary={
                    "dominant_genre": "rock",
                    "mood_profile": {"chill": "100%"},
                    "tempo_avg": 100,
                    "decades": {"1980s": "100%"},
                    "avg_listeners": 1000,
                },
                exclude_pairs={("Only You", "Yazoo")},
                playlist_name="80s",
            )
        )

    assert len(result) == 1
    assert "Suggestion prompt context:" in caplog.text
    assert "Suggestion pipeline summary:" in caplog.text
    assert "rejected_duplicate_source=1" in caplog.text
    assert "Accepted suggestion: I Want to Break Free - Queen" in caplog.text
    assert "decade_score" in caplog.text
    assert "genre_score" in caplog.text
    assert "mood_score" in caplog.text
    assert "popularity_score" in caplog.text


def test_gpt_suggest_validated_reranks_by_fit_score(monkeypatch):
    """Candidates should be ordered by deterministic playlist fit, not raw GPT order."""
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

    async def fake_completion(
        _prompt, temperature=0.7
    ):  # pylint: disable=unused-argument
        return (
            "Dance Tune - Pop Star - Album - 1986 - First from GPT\n"
            "Rock Anthem - Guitar Hero - Album - 1984 - Better fit"
        )

    async def fake_track_info(title, _artist):
        payloads = {
            "Dance Tune": {
                "listeners": "5000000",
                "releasedate": "1 Jan 1986",
                "toptags": {"tag": [{"name": "dance pop"}]},
            },
            "Rock Anthem": {
                "listeners": "1200",
                "releasedate": "1 Jan 1984",
                "toptags": {"tag": [{"name": "rock"}, {"name": "chill"}]},
            },
        }
        return payloads[title]

    monkeypatch.setattr(gpt_mod, "cached_chat_completion", fake_completion)
    monkeypatch.setattr(gpt_mod, "get_lastfm_track_info", fake_track_info)

    result = asyncio.run(
        gpt_mod.gpt_suggest_validated(
            existing_tracks=["Only You - Yazoo"],
            count=10,
            summary={
                "dominant_genre": "rock",
                "mood_profile": {"chill": "100%"},
                "decades": {"1980s": "100%"},
                "avg_listeners": 1000,
            },
        )
    )

    assert [track["title"] for track in result] == ["Rock Anthem", "Dance Tune"]
    assert result[0]["fit_score"] > result[1]["fit_score"]
    assert result[0]["decade"] == "1980s"
    assert result[1]["decade"] == "1980s"
    assert result[0]["popularity"] == 1200
    assert result[1]["popularity"] == 5000000


def test_score_candidate_fit_prefers_matching_genre_and_mood():
    """Fit scoring should reward candidates that match the source genre and mood."""
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

    summary = {
        "dominant_genre": "rock",
        "mood_profile": {"chill": "100%"},
        "decades": {"1980s": "100%"},
        "avg_listeners": 1000,
    }
    stronger = {
        "tags": ["rock", "chill"],
        "year": 1984,
        "decade": "1980s",
        "popularity": 900,
    }
    weaker = {
        "tags": ["dance pop"],
        "year": 1984,
        "decade": "1980s",
        "popularity": 900,
    }

    assert gpt_mod.score_candidate_fit(stronger, summary) > gpt_mod.score_candidate_fit(
        weaker, summary
    )
