"""
cache_manager.py

Defines named persistent caches using diskcache for various subsystems:
- prompt_cache: stores GPT responses
- yt_search_cache: YouTube fallback search results
- lastfm_cache: Last.fm track existence flags
- playlist_cache: Jellyfin playlists per user
- LASTFM_POP_CACHE: listener count from Last.fm
- spotify_cache: Spotify track metadata
- apple_music_cache: Apple Music track metadata

All caches are file-backed and located in the `cache/` directory.
"""

from pathlib import Path
from diskcache import Cache
from config import settings

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

# Cache Spotify metadata lookups
spotify_cache = Cache(BASE_CACHE / "spotify")

# Cache Apple Music metadata lookups
apple_music_cache = Cache(BASE_CACHE / "apple_music")


# TTL configuration (in seconds) for each named cache. This dict is shared with
# ``settings.cache_ttls`` so runtime updates propagate automatically.
CACHE_TTLS: dict[str, int] = settings.cache_ttls
