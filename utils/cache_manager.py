"""
cache_manager.py

Defines named persistent caches using diskcache for various subsystems:
- prompt_cache: stores GPT responses
- yt_search_cache: YouTube fallback search results
- lastfm_cache: Last.fm track existence flags
- playlist_cache: Jellyfin playlists per user
- LASTFM_POP_CACHE: listener count from Last.fm

All caches are file-backed and located in the `cache/` directory.
"""

from diskcache import Cache
from pathlib import Path

# Root directory for all cache files
BASE_CACHE = Path("cache")
BASE_CACHE.mkdir(parents=True, exist_ok=True)

# Named caches for different functional areas

# Stores deduplicated GPT responses keyed by prompt hash
prompt_cache = Cache(BASE_CACHE / "prompt")

# Caches YouTube video URLs for search queries
yt_search_cache = Cache(BASE_CACHE / "youtube")

# Caches True/False values for Last.fm track existence checks
lastfm_cache = Cache(BASE_CACHE / "lastfm")

# Caches Jellyfin playlist metadata for users
playlist_cache = Cache(BASE_CACHE / "playlists")

# Stores Last.fm listener count (popularity data)
LASTFM_POP_CACHE = Cache(BASE_CACHE / "lastfm_popularity")

# Cache results of Jellyfin track search queries
jellyfin_track_cache = Cache(BASE_CACHE / "jellyfin_tracks")

# Caches track BPM, key, acousticness, danceability, etc. from GetSongBPM
bpm_cache = Cache(BASE_CACHE / "bpm")

# Caches results of a full Jellyfin library scan
library_cache = Cache(BASE_CACHE / "full_library")


# TTL configuration (in seconds) for each named cache
CACHE_TTLS = {
    "prompt": 60 * 60 * 24,            # 24 hours
    "youtube": 60 * 60 * 6,            # 6 hours
    "lastfm": 60 * 60 * 24 * 7,        # 7 days
    "lastfm_popularity": 60 * 60 * 24 * 7,
    "playlists": 60 * 30,              # 30 minutes
    "bpm": 60 * 60 * 24 * 30,          # 30-day TTL
    "jellyfin_tracks": 60 * 60 * 24,   # 24 hours
    "full_library": 60 * 60 * 24       # 24 hours
}
