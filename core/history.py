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
    match = re.search(r'- (.+)$', label)
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

    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"History file for user {user_id} is empty or invalid. Resetting.")
            data = []
    else:
        data = []

    data.append({
        "label": label,
        "suggestions": suggestions
    })

    try:
        with open(history_file, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"History saved to {history_file}")
    except Exception as e:
        logger.error(f"Failed to write history for {user_id}: {e}")

def load_user_history(user_id: str) -> list[dict]:
    """
    Load all saved playlist history for a given user.

    Args:
        user_id (str): Jellyfin user ID

    Returns:
        list[dict]: All labeled suggestion entries
    """
    history_file = user_history_path(user_id)
    logger.debug(f"📂 Reading history from {history_file}")
    try:
        with open(history_file, "r") as f:
            data = json.load(f)
            logger.debug(f"✅ Loaded {len(data)} history entries")
            return data
    except Exception as e:
        logger.warning(f"⚠️ Could not load history: {e}")
        return []

def save_whole_user_history(user_id: str, history: list[dict]) -> None:
    """
    Overwrite a user's entire history file.

    Args:
        user_id (str): Jellyfin user ID
        history (list[dict]): The full history to save
    """
    history_file = user_history_path(user_id)
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)
    logger.debug(f"History saved to {history_file}")
    logger.debug(f"Saved {len(history)} history entries")
