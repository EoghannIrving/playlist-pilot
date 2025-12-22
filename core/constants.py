"""Centralized constants for Playlist Pilot."""

import logging
import os
import tempfile
from pathlib import Path

LOGGER = logging.getLogger("playlist-pilot.constants")

BASE_DIR = Path(__file__).resolve().parent.parent
USER_DATA_DIR = BASE_DIR / "user_data"
# Match the location used in `config.py` so settings are read from the same file
SETTINGS_FILE = Path(
    os.getenv(
        "PLAYLIST_PILOT_SETTINGS_FILE",
        Path(__file__).resolve().parent.parent / "settings.json",
    )
)
CACHE_DIR = BASE_DIR / "cache"
LOG_FILE = BASE_DIR / "logs" / "playlist_pilot.log"

DEFAULT_SETTINGS = {
    "settings.jellyfin_url": "",
    "settings.jellyfin_api_key": "",
    "settings.jellyfin_user_id": "",
    "settings.openai_api_key": "",
    "settings.lastfm_api_key": "",
    "settings.model": "gpt-4o-mini",
}


FALLBACK_USER_DATA_DIR = Path(tempfile.gettempdir()) / "playlist_pilot_user_data"


def _ensure_user_data_dir(base: Path) -> Path:
    """
    Return ``base`` if it can be written to, otherwise switch to the fallback.
    """
    try:
        base.mkdir(parents=True, exist_ok=True)
        test_file = base / ".write_test"
        with test_file.open("w", encoding="utf-8") as handle:
            handle.write("ok")
        test_file.unlink(missing_ok=True)
        return base
    except OSError as exc:
        FALLBACK_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOGGER.warning(
            "User data directory %s not writable (%s); using fallback %s",
            base,
            exc,
            FALLBACK_USER_DATA_DIR,
        )
        return FALLBACK_USER_DATA_DIR


USER_DATA_DIR = _ensure_user_data_dir(USER_DATA_DIR)
