"""Tests for Jellyfin lyric helpers."""

import pytest

from services.jellyfin import strip_lrc_timecodes


def test_strip_timecodes_basic():
    """Timecodes preceding lyrics should be removed."""
    line = "[01:23.45]Hello there"
    assert strip_lrc_timecodes(line) == "Hello there"


def test_strip_timecodes_preserves_annotation():
    """Annotation brackets without timecodes remain unchanged."""
    line = "[Chorus]"
    assert strip_lrc_timecodes(line) == "[Chorus]"


def test_strip_timecodes_combined_with_annotation():
    """Only timecodes are stripped when combined with annotations."""
    line = "[02:03.45][Chorus]Sing along"
    assert strip_lrc_timecodes(line) == "[Chorus]Sing along"
