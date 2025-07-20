"""Utility functions for simple text normalization and query building."""

# pylint: disable=cyclic-import

import re


def strip_markdown(text: str) -> str:
    """Remove common Markdown formatting from ``text``."""

    # Code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Images
    text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", "", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Inline code
    text = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", text)
    # Bold/italic/strikethrough
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    # Headings
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Lists
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    return text.strip()


def clean(text: str) -> str:
    """Normalize text by lowercasing and removing punctuation."""
    return re.sub(r"[^\w\s]", "", text.lower().strip())


def build_search_query(line: str) -> str:
    """Extract a basic search query from a track label."""
    parts = [part.strip() for part in line.split("-")]
    return f"{parts[0]} {parts[1]}" if len(parts) >= 2 else line.strip()
