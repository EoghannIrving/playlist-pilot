"""
lastfm.py

Provides Last.fm integration for:
- Validating track existence using the Last.fm API
- Optionally retrieving track popularity via listener counts
"""

import logging
import re
import unicodedata
import asyncio
import json
import httpx
from config import settings
from utils.http_client import get_http_client
from utils.cache_manager import lastfm_cache, CACHE_TTLS
from utils.integration_watchdog import record_failure, record_success


logger = logging.getLogger("playlist-pilot")

# Precompile regex patterns for efficiency and to avoid backtracking
# Avoid leading whitespace in the parenthetical pattern to prevent
# catastrophic backtracking on long inputs consisting of spaces or
# parentheses.
_paren_re = re.compile(r"\([^)]*\)")
_punct_re = re.compile(r"[^a-z0-9 ]")
_space_re = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Standardize text for caching and comparison."""
    # Normalize accents to their ASCII equivalents before lowercasing
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = _paren_re.sub("", text)  # Remove content in parentheses
    text = _punct_re.sub("", text)  # Remove punctuation
    text = _space_re.sub(" ", text)  # Collapse whitespace
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
        client = get_http_client(short=True)
        response = await client.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "track.getTopTags",
                "api_key": settings.lastfm_api_key,
                "artist": artist,
                "track": title,
                "format": "json",
            },
        )
        response.raise_for_status()
        record_success("lastfm")
        data = response.json()
        tags = [tag["name"] for tag in data.get("toptags", {}).get("tag", [])]
        logger.info("[Last.fm] Extracted tags for %s - %s: %s", title, artist, tags)
        lastfm_cache.set(cache_key, tags, expire=CACHE_TTLS["lastfm"])
        return tags
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("lastfm")
        logger.warning("Last.fm tag fetch failed for %s - %s: %s", title, artist, exc)
        lastfm_cache.set(cache_key, [], expire=CACHE_TTLS["lastfm"])
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
    if not settings.lastfm_api_key.strip():
        logger.info("[Last.fm] API key not configured; skipping track info fetch")
        # Cache the absence to avoid repeated lookups when the key is missing
        lastfm_cache.set(key, False, expire=CACHE_TTLS["lastfm"])
        return None
    try:
        client = get_http_client()
        response = await client.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "track.getInfo",
                "api_key": settings.lastfm_api_key,
                "artist": artist,
                "track": title,
                "format": "json",
            },
        )
        response.raise_for_status()
        record_success("lastfm")
        data = response.json()
        track = data.get("track")
        if track and track.get("name") and track.get("artist"):
            lastfm_cache.set(key, track, expire=CACHE_TTLS["lastfm"])
            return track
        lastfm_cache.set(key, False, expire=CACHE_TTLS["lastfm"])
        return None

    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("lastfm")
        logger.warning("Last.fm lookup failed for %s - %s: %s", title, artist, exc)
        # Avoid caching failures so transient issues don't mark the track as missing
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
        "releasedate": (
            track_data.get("album", {}).get("releasedate", "") if track_data else ""
        ),
        "album": track_data.get("album", {}).get("title"),
        "tags": tags,
    }
