"""Helper functions for cached playlist retrieval and history sorting."""
# pylint: disable=duplicate-code

import json
import logging
from fastapi import Request

from core.history import load_user_history, extract_date_from_label
from utils.cache_manager import playlist_cache, CACHE_TTLS
from config import settings
from core.playlist import fetch_audio_playlists

logger = logging.getLogger("playlist-pilot")

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


async def parse_suggest_request(request: Request) -> tuple[list[dict], str, str]:
    """Extract tracks and related fields from a suggestion form request."""
    data = await request.form()
    tracks_raw = data.get("tracks", "[]")
    logger.info("tracks_raw: %s", tracks_raw[:100])
    playlist_name = data.get("playlist_name", "")
    text_summary = data.get("text_summary", "")

    try:
        tracks = json.loads(tracks_raw)
    except json.JSONDecodeError:
        logger.warning("Failed to decode tracks JSON from form.")
        tracks = []

    return tracks, playlist_name, text_summary
