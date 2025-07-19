"""Utility helpers for querying the GetSongBPM API."""

import logging
from urllib.parse import quote_plus
from typing import Optional, Dict

import cloudscraper

from utils.cache_manager import bpm_cache, CACHE_TTLS
from config import settings

logger = logging.getLogger("playlist-pilot")

def get_bpm_from_getsongbpm(
    artist: str, title: str, api_key: str
) -> Optional[Dict[str, Optional[int]]]:
    """Query GetSongBPM for tempo and related metadata."""
    lookup = quote_plus(f"song:{title} artist:{artist}")
    search_url = (
        f"{settings.getsongbpm_base_url}?api_key={api_key}&type=both&lookup={lookup}"
    )

    headers = settings.getsongbpm_headers

    try:
        data = (
            cloudscraper.create_scraper(browser="chrome")
            .get(
                search_url,
                headers=headers,
                timeout=settings.http_timeout_short,
            )
            .json()
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.info("GetSongBPM API error: %s", exc)
        return None

    songs = data.get("search", [])
    if not songs:
        logger.warning("No song found in GetSongBPM response!")
        return None

    song = songs[0]
    duration_str = song.get("duration")
    duration_sec = None
    if duration_str and isinstance(duration_str, str) and ":" in duration_str:
        try:
            minutes, seconds = (int(part) for part in duration_str.strip().split(":"))
            duration_sec = minutes * 60 + seconds
        except ValueError as exc:
            logger.warning("Could not parse duration '%s': %s", duration_str, exc)

    return {
        "bpm": int(song["tempo"]) if song.get("tempo") else None,
        "key": song.get("key_of"),
        "danceability": int(song["danceability"]) if song.get("danceability") else None,
        "acousticness": int(song["acousticness"]) if song.get("acousticness") else None,
        "year": int(song["album"]["year"]) if song.get("album", {}).get("year") else None,
        "duration": duration_sec
    }

def get_cached_bpm(artist: str, title: str, api_key: str) -> Optional[Dict[str, Optional[int]]]:
    """Return BPM data using cache to minimize external requests."""
    key = f"{title.strip().lower()}::{artist.strip().lower()}"
    if key in bpm_cache:
        logger.info("Cache hit for %s", key)
        return bpm_cache[key]

    logger.info("Cache miss for %s — calling GetSongBPM API", key)
    bpm_data = get_bpm_from_getsongbpm(artist, title, api_key)
    if bpm_data:
        bpm_cache.set(key, bpm_data, expire=CACHE_TTLS["bpm"])

    return bpm_data
