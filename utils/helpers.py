"""Helper functions for cached playlist retrieval and history sorting."""

# pylint: disable=duplicate-code

import json
import logging
from fastapi import Request

from config import settings
from core.history import load_user_history, extract_date_from_label
from core.playlist import fetch_audio_playlists
from core.constants import LOG_FILE
from utils.cache_manager import playlist_cache, CACHE_TTLS


logger = logging.getLogger("playlist-pilot")


def current_user_scope() -> str:
    """Return the active user scope for playlists and history."""
    if settings.media_backend == "navidrome":
        return settings.media_username or settings.media_user_id
    return settings.jellyfin_user_id or settings.media_user_id


async def get_cached_playlists(
    user_id: str | None = None, force_refresh: bool = False
) -> dict:
    """Return audio playlists for a user using caching.

    Navidrome playlist lists are refreshed on each request because playlist
    creation commonly happens outside Playlist Pilot and stale server-side state
    is more confusing than the extra fetch.
    """
    user_id = user_id or current_user_scope()
    cache_key = f"playlists:{user_id}"
    should_bypass_cache = force_refresh or settings.media_backend == "navidrome"
    playlists_data = None if should_bypass_cache else playlist_cache.get(cache_key)
    if playlists_data is None:
        try:
            playlists_data = await fetch_audio_playlists(user_id)
            playlist_cache.set(
                cache_key, playlists_data, expire=CACHE_TTLS["playlists"]
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Failed to fetch playlists: %s", exc)
            # Return the error response but avoid caching it so transient issues
            # do not persist until the TTL expires
            return {"playlists": [], "error": str(exc)}
    return playlists_data


def invalidate_cached_playlists(user_id: str | None = None) -> None:
    """Invalidate cached playlists for the active or provided user scope."""
    user_id = user_id or current_user_scope()
    cache_key = f"playlists:{user_id}"
    try:
        if hasattr(playlist_cache, "delete"):
            playlist_cache.delete(cache_key)
        else:
            playlist_cache.pop(cache_key, None)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to invalidate playlist cache for %s: %s", user_id, exc)


def load_sorted_history(user_id: str | None = None) -> list:
    """Load user history sorted by most recent entries."""
    user_id = user_id or current_user_scope()
    history = load_user_history(user_id)
    history.sort(key=lambda e: extract_date_from_label(e["label"]), reverse=True)
    return history


async def parse_suggest_request(request: Request) -> tuple[list[dict], str, str]:
    """Extract tracks and related fields from a suggestion form request."""
    data = await request.form()
    tracks_raw = data.get("tracks", "[]")
    logger.info("tracks_raw: %s", str(tracks_raw)[:100])
    playlist_name = str(data.get("playlist_name", ""))
    text_summary = str(data.get("text_summary", ""))

    if isinstance(tracks_raw, str):
        tracks_raw_str = tracks_raw
        try:
            tracks = json.loads(tracks_raw_str)
        except json.JSONDecodeError:
            logger.warning("Failed to decode tracks JSON from form.")
            tracks = []
    elif isinstance(tracks_raw, (list, tuple)):
        tracks = list(tracks_raw)
    else:
        logger.warning("Unexpected tracks type: %s", type(tracks_raw))
        tracks = []

    return tracks, playlist_name, text_summary


def get_log_excerpt(lines: int = 20) -> list[str]:
    """Return the last ``lines`` lines from the application log file."""
    log_path = LOG_FILE
    if not log_path.exists():
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as file:
            data = file.readlines()[-lines:]
        return [ln.rstrip() for ln in data]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read log file: %s", exc)
        return [f"Error reading log file: {exc}"]
