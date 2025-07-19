"""
lastfm.py

Provides Last.fm integration for:
- Validating track existence using the Last.fm API
- Optionally retrieving track popularity via listener counts
"""

import logging
import re
import asyncio
import httpx

from config import settings
from utils.cache_manager import lastfm_cache, CACHE_TTLS

logger = logging.getLogger("playlist-pilot")

def normalize(text: str) -> str:
    """Standardize text for caching and comparison."""
    text = text.lower()
    text = re.sub(r"\s*\(.*?\)", "", text)  # Remove content in parentheses
    text = re.sub(r"[^a-z0-9 ]", "", text)     # Remove punctuation
    return text.strip()

async def get_lastfm_tags(title: str, artist: str) -> list[str]:

    """
    Retrieve top genre-like tags for a given track from Last.fm.
    Falls back to empty list on error.
    """
    cache_key = f"tags:{normalize(artist)}:{normalize(title)}"
    cached = lastfm_cache.get(cache_key)
    if cached is not None:
        logger.info("[Last.fm] Cache hit for %s - %s", title, artist)
        return cached

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "track.getTopTags",
                    "api_key": settings.lastfm_api_key,
                    "artist": artist,
                    "track": title,
                    "format": "json",
                },
                timeout=settings.http_timeout_short,
            )
        response.raise_for_status()
        data = response.json()
        tags = [tag["name"] for tag in data.get("toptags", {}).get("tag", [])]
        logger.info("[Last.fm] Extracted tags for %s - %s: %s", title, artist, tags)
        lastfm_cache.set(cache_key, tags, expire=CACHE_TTLS["lastfm"])
        return tags
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Last.fm tag fetch failed for %s - %s: %s", title, artist, exc)
        return []

async def get_lastfm_track_info(title: str, artist: str) -> dict | None:
    """
    Retrieve and cache Last.fm track.getInfo data.

    Returns:
        dict | None: Full Last.fm track object if available, else None
    """
    key = f"lastfm:{normalize(artist)}:{normalize(title)}"
    cached = lastfm_cache.get(key)
    if cached:
        logger.info("Last.fm cache hit for %s - %s", title, artist)
        return cached if isinstance(cached, dict) else None

    logger.info("Last.fm cache miss for %s - %s", title, artist)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "track.getInfo",
                    "api_key": settings.lastfm_api_key,
                    "artist": artist,
                    "track": title,
                    "format": "json",
                },
                timeout=settings.http_timeout_long,
            )
        response.raise_for_status()
        data = response.json()
        track = data.get("track")
        if track and track.get("name") and track.get("artist"):
            lastfm_cache.set(key, track, expire=CACHE_TTLS["lastfm"])
            return track
        lastfm_cache.set(key, False, expire=CACHE_TTLS["lastfm"])
        return None

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Last.fm lookup failed for %s - %s: %s", title, artist, exc)
        lastfm_cache.set(key, False, expire=CACHE_TTLS["lastfm"])
        return None

async def enrich_with_lastfm(title: str, artist: str) -> dict:
    """
    Returns a dict with Last.fm metadata for a track.
    Includes: existence, listeners, release date, tags
    """
    track_task = asyncio.create_task(get_lastfm_track_info(title, artist))
    tags_task = asyncio.create_task(get_lastfm_tags(title, artist))
    track_data, tags = await asyncio.gather(track_task, tags_task)

    return {
        "exists": track_data is not None,
        "listeners": int(track_data.get("listeners", 0)) if track_data else 0,
        "releasedate": track_data.get("album", {}).get("releasedate", "") if track_data else "",
        "album": track_data.get("album", {}).get("title"),
        "tags": tags,
    }
