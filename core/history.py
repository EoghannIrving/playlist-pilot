"""
history.py

Manages user playlist suggestion history (stored per user as JSON).
Each entry contains:
- label: A user-friendly string for identification
- suggestions: A list of track suggestion dictionaries
"""

import os
import json
import logging
from datetime import datetime
import re
from pathlib import Path
from core.constants import USER_DATA_DIR

logger = logging.getLogger("playlist-pilot")


def extract_date_from_label(label: str) -> datetime:
    """Extract a datetime object from a history label string."""
    match = re.search(r"- (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$", label)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
        except ValueError:
            return datetime.min
    return datetime.min


def user_history_path(user_id: str) -> Path:
    """Constructs the path to the user's history file."""
    return USER_DATA_DIR / f"{user_id}.json"


def save_user_history(user_id: str, label: str, suggestions: list[dict]) -> None:
    """
    Append a new labeled suggestion set to a user's history file.

    Args:
        user_id (str): Jellyfin user ID
        label (str): Label describing the playlist
        suggestions (list[dict]): Validated suggestions from GPT
    """
    history_file = user_history_path(user_id)
    # Ensure the user data directory exists before writing
    history_file.parent.mkdir(parents=True, exist_ok=True)

    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            logger.warning(
                "History file for user %s is empty or invalid. Resetting.", user_id
            )
            data = []
    else:
        data = []

    data.append({"label": label, "suggestions": suggestions})

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.debug("History saved to %s", history_file)
    except (OSError, TypeError) as exc:
        logger.error("Failed to write history for %s: %s", user_id, exc)


def load_user_history(user_id: str) -> list[dict]:
    """
    Load all saved playlist history for a given user.

    Args:
        user_id (str): Jellyfin user ID

    Returns:
        list[dict]: All labeled suggestion entries
    """
    history_file = user_history_path(user_id)
    logger.debug("📂 Reading history from %s", history_file)
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug("✅ Loaded %d history entries", len(data))
            return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("⚠️ Could not load history: %s", exc)
        return []


def save_whole_user_history(user_id: str, history: list[dict]) -> None:
    """
    Overwrite a user's entire history file.

    Args:
        user_id (str): Jellyfin user ID
        history (list[dict]): The full history to save
    """
    history_file = user_history_path(user_id)
    # Ensure the user data directory exists before writing
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    logger.debug("History saved to %s", history_file)
    logger.debug("Saved %d history entries", len(history))
