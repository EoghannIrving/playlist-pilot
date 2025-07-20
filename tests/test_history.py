from datetime import datetime

from core.history import extract_date_from_label


def test_extract_date_from_label_extra_hyphen():
    label = "Favorites - Smooth - 2023-09-30 12:00"
    assert extract_date_from_label(label) == datetime(2023, 9, 30, 12, 0)


def test_extract_date_from_label_invalid():
    label = "No Date"
    assert extract_date_from_label(label) == datetime.min
