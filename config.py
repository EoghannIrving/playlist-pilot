"""
config.py

Configuration module for Playlist Pilot.

This file manages:
- Loading and saving app settings from a JSON file
- Validating that critical settings are provided
- Exposing a global `settings` object to be used throughout the app
"""

import json
import logging
from pathlib import Path
from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────
# Constants

#SETTINGS_FILE = Path(__file__).parent / "settings.json"
SETTINGS_FILE = Path("/app/settings.json")
"""
Path to the local JSON file where application settings are stored.
"""

# ─────────────────────────────────────────────────────────────
# Settings Schema

class AppSettings(BaseModel):
    """
    Defines required configuration settings for the application.
    
    Attributes:
        jellyfin_url (str): Base URL of your Jellyfin server.
        jellyfin_api_key (str): API key used to authenticate with Jellyfin.
        jellyfin_user_id (str): User ID to fetch personalized data.
        openai_api_key (str): API key for OpenAI.
        lastfm_api_key (str): Optional key for Last.fm integration.
        model (str): GPT model to use (default is 'gpt-4o-mini').
    """
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""
    jellyfin_user_id: str = ""
    openai_api_key: str = ""
    lastfm_api_key: str = ""
    model: str = "gpt-4o-mini"
    getsongbpm_api_key: str = ""
    global_min_lfm: int = 10_000
    global_max_lfm: int = 15_000_000
    cache_ttls: dict[str, int] = {
        "prompt": 60 * 60 * 24,
        "youtube": 60 * 60 * 6,
        "lastfm": 60 * 60 * 24 * 7,
        "lastfm_popularity": 60 * 60 * 24 * 7,
        "playlists": 60 * 30,
        "bpm": 60 * 60 * 24 * 30,
        "jellyfin_tracks": 60 * 60 * 24,
        "full_library": 60 * 60 * 24,
    }
    getsongbpm_base_url: str = "https://api.getsongbpm.com/search/"
    getsongbpm_headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://getsongbpm.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    }
    http_timeout_short: int = 5
    http_timeout_long: int = 10
    youtube_min_duration: int = 120
    youtube_max_duration: int = 360
    library_scan_limit: int = 1000
    music_library_root: str = "Movies/Music"
    lyrics_weight: float = 1.5
    bpm_weight: float = 1.0
    tags_weight: float = 0.7

    def validate_settings(self) -> None:
        """
        Validates that all required configuration fields are filled.

        Raises:
            ValueError: If any required field is missing or empty.
        """
        missing = []
        if not self.jellyfin_url.strip():
            missing.append("Jellyfin URL")
        if not self.jellyfin_api_key.strip():
            missing.append("Jellyfin API Key")
        if not self.jellyfin_user_id.strip():
            missing.append("Jellyfin User ID")
        if not self.openai_api_key.strip():
            missing.append("OpenAI API Key")
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")

# ─────────────────────────────────────────────────────────────
# Settings Management Functions

def load_settings() -> AppSettings:
    """
    Loads app settings from the `settings.json` file.

    Returns:
        AppSettings: The loaded settings object.
    """
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Normalize keys to lowercase for compatibility
        normalized = {k.lower(): v for k, v in data.items()}
        return AppSettings(**normalized)
    return AppSettings()

def save_settings(s: AppSettings) -> None:
    """
    Saves the provided settings object to the `settings.json` file.

    Args:
        s (AppSettings): The settings object to save.
    """
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s.dict(), f, indent=2)

# ─────────────────────────────────────────────────────────────
# Global Config Instance

settings: AppSettings = load_settings()
logging.getLogger("playlist-pilot").debug("settings loaded: %s", settings.dict())

GLOBAL_MIN_LFM = settings.global_min_lfm
GLOBAL_MAX_LFM = settings.global_max_lfm
