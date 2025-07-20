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
