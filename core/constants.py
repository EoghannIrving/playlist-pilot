"""
Centralized constants for Playlist Pilot
"""
import os
from pathlib import Path


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
    "settings.model": "gpt-4o-mini"
}
