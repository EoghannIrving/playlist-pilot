"""Tests for helpers in ``core.history``."""

from datetime import datetime

from core.history import extract_date_from_label


def test_extract_date_from_label_extra_hyphen():
    """Handle labels with an extra hyphen section."""
    label = "Favorites - Smooth - 2023-09-30 12:00"
    assert extract_date_from_label(label) == datetime(2023, 9, 30, 12, 0)


def test_extract_date_from_label_invalid():
    """Return ``datetime.min`` for labels without dates."""
    label = "No Date"
    assert extract_date_from_label(label) == datetime.min
