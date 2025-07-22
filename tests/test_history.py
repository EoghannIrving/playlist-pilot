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


def test_delete_history_entry_by_id(monkeypatch, tmp_path):
    """Deleting by ID should remove only the matching entry."""
    from core import constants
    from core.history import save_whole_user_history, load_user_history

    monkeypatch.setattr(constants, "USER_DATA_DIR", tmp_path)
    user_id = "user"

    entry1 = {"id": "a", "label": "Mix", "suggestions": []}
    entry2 = {"id": "b", "label": "Mix", "suggestions": []}
    save_whole_user_history(user_id, [entry1, entry2])

    history = load_user_history(user_id)
    updated = [item for item in history if item.get("id") != "a"]
    save_whole_user_history(user_id, updated)

    final = load_user_history(user_id)
    assert len(final) == 1
    assert final[0]["id"] == "b"
