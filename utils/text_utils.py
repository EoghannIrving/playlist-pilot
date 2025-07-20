"""Utility functions for simple text normalization and query building."""

# pylint: disable=cyclic-import

import re


def clean(text: str) -> str:
    """Normalize text by lowercasing and removing punctuation."""
    return re.sub(r"[^\w\s]", "", text.lower().strip())


def build_search_query(line: str) -> str:
    """Extract a basic search query from a track label."""
    parts = [part.strip() for part in line.split("-")]
    return f"{parts[0]} {parts[1]}" if len(parts) >= 2 else line.strip()
