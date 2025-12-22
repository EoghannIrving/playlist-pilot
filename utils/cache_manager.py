"""cache_manager.py

Defines named persistent caches using diskcache for various subsystems:
- prompt_cache: stores GPT responses
- yt_search_cache: YouTube fallback search results
- lastfm_cache: Last.fm track existence flags
- playlist_cache: Jellyfin playlists per user
- LASTFM_POP_CACHE: listener count from Last.fm
- spotify_cache: Spotify track metadata
- apple_music_cache: Apple Music metadata

All caches are file-backed and located under the `cache/` directory.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from diskcache import Cache

from config import settings

LOGGER = logging.getLogger("playlist-pilot.cache_manager")

CACHE_NAMES = (
    "prompt",
    "youtube",
    "lastfm",
    "playlists",
    "lastfm_popularity",
    "jellyfin_tracks",
    "bpm",
    "full_library",
    "spotify",
    "apple_music",
)

FALLBACK_BASE = Path(tempfile.gettempdir()) / "playlist_pilot_cache"


def _determine_cache_base() -> Path:
    """Ensure the cache root is writable, otherwise use the fallback path."""
    base = Path("cache")
    base.mkdir(parents=True, exist_ok=True)

    for name in CACHE_NAMES:
        candidate = base / name
        if candidate.exists() and not os.access(candidate, os.W_OK):
            FALLBACK_BASE.mkdir(parents=True, exist_ok=True)
            LOGGER.warning(
                "Existing cache path %s is not writable; switching to %s",
                candidate,
                FALLBACK_BASE,
            )
            return FALLBACK_BASE

    return base


# Root directory for all cache files
CACHE_BASE = _determine_cache_base()

# Named caches for different functional areas

# Stores deduplicated GPT responses keyed by prompt hash
prompt_cache = Cache(CACHE_BASE / "prompt")

# Caches YouTube video URLs for search queries
yt_search_cache = Cache(CACHE_BASE / "youtube")

# Caches True/False values for Last.fm track existence checks
lastfm_cache = Cache(CACHE_BASE / "lastfm")

# Caches Jellyfin playlist metadata for users
playlist_cache = Cache(CACHE_BASE / "playlists")

# Stores Last.fm listener count (popularity data)
LASTFM_POP_CACHE = Cache(CACHE_BASE / "lastfm_popularity")

# Cache results of Jellyfin track search queries
jellyfin_track_cache = Cache(CACHE_BASE / "jellyfin_tracks")

# Caches track BPM, key, acousticness, danceability, etc. from GetSongBPM
bpm_cache = Cache(CACHE_BASE / "bpm")

# Caches results of a full Jellyfin library scan
library_cache = Cache(CACHE_BASE / "full_library")

# Cache Spotify metadata lookups
spotify_cache = Cache(CACHE_BASE / "spotify")

# Cache Apple Music metadata lookups
apple_music_cache = Cache(CACHE_BASE / "apple_music")


# TTL configuration (in seconds) for each named cache. This dict is shared with
# ``settings.cache_ttls`` so runtime updates propagate automatically.
CACHE_TTLS: dict[str, int] = settings.cache_ttls
