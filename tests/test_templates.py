from core.templates import duration_human


def test_duration_human_int():
    """Integer seconds should format as MM:SS."""
    assert duration_human(125) == "2:05"


def test_duration_human_numeric_string():
    """Numeric strings should be accepted."""
    assert duration_human("125") == "2:05"


def test_duration_human_float():
    """Float seconds should be cast to int."""
    assert duration_human(125.7) == "2:05"


def test_duration_human_invalid():
    """Non-numeric input should return placeholder."""
    assert duration_human("foo") == "?:??"
