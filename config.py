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

GLOBAL_MIN_LFM = 10_000        # anything below this is "low popularity"
GLOBAL_MAX_LFM = 15_000_000     # extremely popular tracks
