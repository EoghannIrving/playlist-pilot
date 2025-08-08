"""Tests for Jellyfin lyric helpers."""

from services.jellyfin import strip_lrc_timecodes


def test_strip_timecodes_basic():
    """Timecodes preceding lyrics should be removed."""
    line = "[01:23.45]Lyrics"
    assert strip_lrc_timecodes(line) == "Lyrics"


def test_strip_timecodes_preserves_annotation():
    """Annotation brackets without timecodes remain unchanged."""
    line = "[Chorus]"
    assert strip_lrc_timecodes(line) == "[Chorus]"


def test_strip_timecodes_combined_with_annotation():
    """Only timecodes are stripped when combined with annotations."""
    line = "[02:03.45][Chorus]Lyrics"
    assert strip_lrc_timecodes(line) == "[Chorus]Lyrics"
