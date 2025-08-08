"""Spotify integration for metadata lookup."""

from __future__ import annotations

import logging
import json
from typing import Any

import httpx

from config import settings
from utils.http_client import get_http_client
from utils.cache_manager import spotify_cache, CACHE_TTLS

logger = logging.getLogger("playlist-pilot")

_access_token: str | None = None


async def _get_access_token() -> str | None:
    """Return a cached Spotify access token."""
    global _access_token  # pylint: disable=global-statement
    if _access_token:
        return _access_token
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        logger.info("[Spotify] credentials not configured; skipping token request")
        return None
    try:
        client = get_http_client(short=True)
        resp = await client.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(settings.spotify_client_id, settings.spotify_client_secret),
        )
        resp.raise_for_status()
        _access_token = resp.json().get("access_token")
        return _access_token
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Spotify token fetch failed: %s", exc)
        return None


async def fetch_spotify_metadata(title: str, artist: str) -> dict[str, Any] | None:
    """Search Spotify for basic metadata about a track."""
    cache_key = f"{title}|{artist}"
    cached = spotify_cache.get(cache_key)
    if cached is not None:
        logger.info("Spotify cache hit for %s - %s", title, artist)
        return cached
    token = await _get_access_token()
    if not token:
        return None
    try:
        client = get_http_client(short=True)
        resp = await client.get(
            "https://api.spotify.com/v1/search",
            params={"q": f"track:{title} artist:{artist}", "type": "track", "limit": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        items = resp.json().get("tracks", {}).get("items", [])
        if not items:
            return None
        track = items[0]
        result = {
            "album": track.get("album", {}).get("name"),
            "year": track.get("album", {}).get("release_date", "")[:4],
            "duration_ms": track.get("duration_ms"),
        }
        spotify_cache.set(cache_key, result, expire=CACHE_TTLS["spotify"])
        return result
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Spotify lookup failed for %s - %s: %s", title, artist, exc)
        return None
