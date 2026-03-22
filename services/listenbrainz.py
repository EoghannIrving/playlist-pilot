"""ListenBrainz integration for recording and release-group tags."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings
from utils.cache_manager import listenbrainz_cache, CACHE_TTLS
from utils.http_client import get_http_client

logger = logging.getLogger("playlist-pilot")


def _extract_tag_names(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    tags = payload.get("tags", []) or []
    names: list[str] = []
    for tag in tags:
        if isinstance(tag, dict):
            name = str(tag.get("tag") or tag.get("name") or "").strip()
        else:
            name = str(tag).strip()
        if name:
            names.append(name)
    return list(dict.fromkeys(names))


async def _get_metadata(entity_name: str, mbid: str) -> dict[str, Any] | None:
    if not settings.listenbrainz_enabled or not mbid:
        return None
    cache_key = f"{entity_name}:{mbid}"
    cached = listenbrainz_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        client = get_http_client(short=True)
        response = await client.get(
            f"https://api.listenbrainz.org/1/metadata/{entity_name}/{mbid}",
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        listenbrainz_cache.set(cache_key, data, expire=CACHE_TTLS["listenbrainz"])
        return data
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "ListenBrainz %s lookup failed for %s: %s", entity_name, mbid, exc
        )
        return None


async def get_recording_tags(mb_recording_id: str) -> list[str]:
    """Return recording-level tags for a MusicBrainz recording ID."""
    data = await _get_metadata("recording", mb_recording_id)
    if not data:
        return []
    payload = data.get("payload") or {}
    return _extract_tag_names(payload.get("recording"))


async def get_release_group_tags(mb_release_group_id: str) -> list[str]:
    """Return release-group-level tags for a MusicBrainz release-group ID."""
    data = await _get_metadata("release-group", mb_release_group_id)
    if not data:
        return []
    payload = data.get("payload") or {}
    return _extract_tag_names(payload.get("release_group"))
