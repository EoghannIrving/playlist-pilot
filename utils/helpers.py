from core.playlist import fetch_audio_playlists
from core.history import load_user_history, extract_date_from_label
from utils.cache_manager import playlist_cache, CACHE_TTLS
from config import settings


async def get_cached_playlists(user_id: str | None = None) -> dict:
    """Return audio playlists for a user using caching."""
    user_id = user_id or settings.jellyfin_user_id
    cache_key = f"playlists:{user_id}"
    playlists_data = playlist_cache.get(cache_key)
    if playlists_data is None:
        playlists_data = await fetch_audio_playlists()
        playlist_cache.set(cache_key, playlists_data, expire=CACHE_TTLS["playlists"])
    return playlists_data


def load_sorted_history(user_id: str | None = None) -> list:
    """Load user history sorted by most recent entries."""
    user_id = user_id or settings.jellyfin_user_id
    history = load_user_history(user_id)
    history.sort(key=lambda e: extract_date_from_label(e["label"]), reverse=True)
    return history
