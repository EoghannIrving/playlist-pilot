"""Tests for helpers in ``utils.text_utils``."""

import utils.text_utils as tu


def test_strip_markdown_basic():
    """Remove common markdown characters from text."""
    text = "# Title\n- item1\n1. item2\n**bold** _italic_ [link](http://x.com)"
    cleaned = tu.strip_markdown(text)
    assert "#" not in cleaned
    assert "*" not in cleaned
    assert "_" not in cleaned
    assert "[" not in cleaned
    assert "Title" in cleaned
    assert "item1" in cleaned
    assert "item2" in cleaned
    assert "bold" in cleaned
    assert "italic" in cleaned
    assert "link" in cleaned


def test_clean_and_build_query():
    """Verify text normalization and search query extraction."""
    assert tu.clean(" Hello!!! ") == "hello"
    assert tu.clean("MiXeD Case") == "mixed case"

    assert tu.build_search_query("Song - Artist - Extra") == "Song Artist - Extra"
    assert tu.build_search_query("Solo") == "Solo"
