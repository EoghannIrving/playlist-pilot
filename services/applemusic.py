"""Apple Music integration for metadata lookup."""

# pylint: disable=duplicate-code

from __future__ import annotations

import logging
import json
from typing import Any

import httpx

from config import settings
from utils.http_client import get_http_client
from utils.cache_manager import apple_music_cache, CACHE_TTLS

logger = logging.getLogger("playlist-pilot")

_access_token: str | None = None


async def _get_developer_token() -> str | None:
    """Return a cached Apple Music developer token."""
    global _access_token  # pylint: disable=global-statement
    if _access_token:
        return _access_token
    client_id = getattr(settings, "apple_client_id", "")
    client_secret = getattr(settings, "apple_client_secret", "")
    if not client_id or not client_secret:
        logger.info("[Apple Music] credentials not configured; skipping token request")
        return None
    try:
        client = get_http_client(short=True)
        resp = await client.post(
            "https://apple.music.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
        )
        resp.raise_for_status()
        _access_token = resp.json().get("access_token")
        return _access_token
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Apple Music token fetch failed: %s", exc)
        return None


async def fetch_applemusic_metadata(title: str, artist: str) -> dict[str, Any] | None:
    """Search Apple Music for basic metadata about a track."""
    cache_key = f"{title}|{artist}"
    cached = apple_music_cache.get(cache_key)
    if cached is not None:
        logger.info("Apple Music cache hit for %s - %s", title, artist)
        return cached
    token = await _get_developer_token()
    if not token:
        return None
    try:
        client = get_http_client(short=True)
        resp = await client.get(
            "https://api.music.apple.com/v1/catalog/us/search",
            params={"term": f"{title} {artist}", "types": "songs", "limit": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        items = resp.json().get("results", {}).get("songs", {}).get("data", [])
        if not items:
            return None
        track = items[0].get("attributes", {})
        result = {
            "album": track.get("albumName"),
            "year": track.get("releaseDate", "")[:4],
            "duration_ms": track.get("durationInMillis"),
        }
        apple_music_cache.set(cache_key, result, expire=CACHE_TTLS["apple_music"])
        return result
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Apple Music lookup failed for %s - %s: %s", title, artist, exc)
        return None
