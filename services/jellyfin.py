"""Helpers for interacting with Jellyfin's API and local media files."""

import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from config import settings
from services.media_server import MediaServer, NormalizedPlaylist, NormalizedUser
from utils.cache_manager import jellyfin_track_cache, library_cache, CACHE_TTLS
from utils.http_client import get_http_client
from utils.integration_watchdog import record_failure, record_success

logger = logging.getLogger("playlist-pilot")


def _jellyfin_url() -> str:
    """Return the active Jellyfin base URL."""
    return settings.media_url or settings.jellyfin_url


def _jellyfin_api_key() -> str:
    """Return the active Jellyfin API key."""
    return settings.media_api_key or settings.jellyfin_api_key


def _jellyfin_user_id() -> str:
    """Return the active Jellyfin user ID."""
    return settings.media_user_id or settings.jellyfin_user_id


def normalize_search_term(term):
    """Normalize search term by replacing smart quotes and variants."""
    return term.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


class JellyfinAdapter(MediaServer):
    """Media-server adapter for Jellyfin."""

    def backend_name(self) -> str:
        return "jellyfin"

    def requires_user_id(self) -> bool:
        return True

    def supports_lyrics(self) -> bool:
        return True

    def supports_path_resolution(self) -> bool:
        return True

    async def test_connection(self) -> dict:
        """Verify Jellyfin connectivity using current settings."""
        url = _jellyfin_url().rstrip("/")
        key = _jellyfin_api_key()
        headers = {
            "X-Emby-Token": key,
            "Accept": "application/json",
            "User-Agent": "PlaylistPilotTest/1.0",
        }
        try:
            client = get_http_client(short=True)
            response = await client.get(f"{url}/System/Info", headers=headers)
            response.raise_for_status()
            data = response.json()
            return {
                "success": any(k.lower() == "version" for k in data),
                "status": response.status_code,
                "data": data,
            }
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.error("Jellyfin connection test failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def list_users(self) -> list[NormalizedUser]:
        """Return Jellyfin users in normalized form."""
        users = await fetch_jellyfin_users()
        return [{"id": user_id, "name": name} for name, user_id in users.items()]

    async def list_audio_playlists(self) -> list[NormalizedPlaylist]:
        """Return all Jellyfin audio playlists in normalized form."""
        user_id = _jellyfin_user_id()
        resp = await jf_get(
            f"/Users/{user_id}/Items",
            IncludeItemTypes="Playlist",
            Recursive="true",
        )
        if "error" in resp:
            return []
        playlists = resp.get("Items", [])
        audio_playlists: list[NormalizedPlaylist] = []
        for playlist in playlists:
            playlist_id = playlist["Id"]
            contents_resp = await jf_get(
                f"/Users/{user_id}/Items",
                ParentId=playlist_id,
                IncludeItemTypes="Audio",
                Recursive="true",
                Limit=1,
            )
            if "error" in contents_resp:
                logger.error(
                    "Failed to check playlist %s contents: %s",
                    playlist_id,
                    contents_resp["error"],
                )
                continue
            if contents_resp.get("Items", []):
                audio_playlists.append(
                    {
                        "id": playlist_id,
                        "name": playlist["Name"],
                        "track_count": None,
                        "backend": self.backend_name(),
                    }
                )
        audio_playlists.sort(key=lambda playlist: playlist["name"].lower())
        return audio_playlists

    async def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        return await fetch_tracks_for_playlist_id(playlist_id)

    async def search_track(self, title: str, artist: str) -> bool:
        return await search_jellyfin_for_track(title, artist)

    async def get_track_metadata(self, title: str, artist: str) -> dict | None:
        return await fetch_jellyfin_track_metadata(title, artist)

    async def get_full_audio_library(self, force_refresh: bool = False) -> list[str]:
        return await fetch_full_audio_library(force_refresh=force_refresh)

    async def get_lyrics(self, item_id: str) -> str | None:
        return await fetch_lyrics_for_item(item_id)

    async def create_playlist(self, name: str, track_ids: list[str]) -> dict | None:
        playlist_id = await create_jellyfin_playlist(name, track_ids)
        if not playlist_id:
            return None
        return {"id": playlist_id}

    async def update_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> dict | None:
        logger.warning(
            "Jellyfin playlist update not implemented for playlist %s",
            playlist_id,
        )
        return None

    async def delete_playlist(self, playlist_id: str) -> bool:
        logger.warning(
            "Jellyfin playlist delete not implemented for playlist %s",
            playlist_id,
        )
        return False

    async def resolve_track_path(self, title: str, artist: str) -> str | None:
        return await resolve_jellyfin_path(
            title, artist, _jellyfin_url(), _jellyfin_api_key()
        )


async def fetch_jellyfin_users():
    """Return a mapping of Jellyfin user names to IDs."""
    try:
        url = f"{_jellyfin_url().rstrip('/')}/Users"
        headers = {"X-Emby-Token": _jellyfin_api_key()}
        client = get_http_client()
        resp = await client.get(
            url,
            headers=headers,
        )
        resp.raise_for_status()
        record_success("jellyfin")
        return {u["Name"]: u["Id"] for u in resp.json()}
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.error("Failed to fetch Jellyfin users: %s", exc)
        return {}


async def search_jellyfin_for_track(title: str, artist: str) -> bool:
    """Return True if the track exists in Jellyfin."""
    logger.debug("🔍 search_jellyfin_for_track() called with: %s - %s", title, artist)

    title_cleaned = normalize_search_term(title)
    artist_cleaned = normalize_search_term(artist)
    key = f"{title_cleaned.strip().lower()}::{artist_cleaned.strip().lower()}"
    cached = jellyfin_track_cache.get(key)
    if cached is not None:
        logger.info("Jellyfin cache hit for %s - %s", title, artist)
        return bool(cached)

    try:
        client = get_http_client()
        response = await client.get(
            f"{_jellyfin_url()}/Items",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "SearchTerm": title_cleaned,
                "api_key": _jellyfin_api_key(),
                "userId": _jellyfin_user_id(),
            },
        )
        response.raise_for_status()
        record_success("jellyfin")
        data = response.json()

        items = data.get("Items", [])
        logger.debug("Found %d items", len(items))

        for item in items:
            name = normalize_search_term(item.get("Name", ""))
            artists_list = item.get("Artists", [])
            artists = [normalize_search_term(a) for a in artists_list]
            logger.debug("→ Track: %s, Artists: %s", name, artists)

            if title_cleaned.lower() in name.lower() and any(
                artist_cleaned.lower() in a.lower() for a in artists
            ):
                logger.debug("✅ Match found!")
                jellyfin_track_cache.set(
                    key, True, expire=CACHE_TTLS["jellyfin_tracks"]
                )
                return True

        logger.debug("❌ No matching track found")
        jellyfin_track_cache.set(key, False, expire=CACHE_TTLS["jellyfin_tracks"])
        return False

    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.warning("Jellyfin search failed for %s - %s: %s", title, artist, exc)
        # Avoid caching failures so transient issues don't mark the track as missing
        return False


async def jf_get(path, **params):
    """Helper to perform a GET request against the Jellyfin API."""
    url = f"{_jellyfin_url().rstrip('/')}{path}?api_key={_jellyfin_api_key()}"
    if params:
        query = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        url += f"&{query}"
    try:
        client = get_http_client()
        resp = await client.get(url)
        resp.raise_for_status()
        record_success("jellyfin")
        return resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.error("Jellyfin GET %s failed: %s", path, exc)
        return {"error": str(exc)}


async def fetch_tracks_for_playlist_id(
    playlist_id: str, limit: int | None = None
) -> list[dict]:
    """
    Fetch detailed track list for a given Jellyfin playlist ID.
    Includes expanded fields useful for enrichment and analysis.
    Reads .lrc files directly from disk if present,
    otherwise attempts Jellyfin Lyrics API fetch if HasLyrics is true.
    """
    url = f"{_jellyfin_url()}/Playlists/{playlist_id}/Items"
    params: dict[str, Any] = {
        "UserId": _jellyfin_user_id(),
        "Fields": (
            "Name,AlbumArtist,Artists,Album,ProductionYear,PremiereDate,"
            "Genres,RunTimeTicks,Genres,UserData,HasLyrics,Path,Tags,PlaylistItemId"
        ),
        "api_key": _jellyfin_api_key(),
    }
    if isinstance(limit, int) and limit > 0:
        params["Limit"] = limit

    try:
        client = get_http_client()
        response = await client.get(
            url,
            params=params,
        )
        response.raise_for_status()
        record_success("jellyfin")
        data = response.json()
        items = data.get("Items", [])
        logger.debug("Fetched %d tracks for playlist %s", len(items), playlist_id)

        for item in items:
            await _attach_lyrics(item)

        return items
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.error("Failed to fetch tracks for playlist %s: %s", playlist_id, exc)
        return []


async def fetch_full_audio_library(force_refresh: bool = False) -> list[str]:
    """Return the active Jellyfin user's full audio library."""
    cache_key = f"library:{_jellyfin_user_id()}"
    if not force_refresh:
        cached = library_cache.get(cache_key)
        if cached is not None:
            return cached

    items: list[str] = []
    start_index = 0
    limit = settings.library_scan_limit
    while True:
        response = await jf_get(
            f"/Users/{_jellyfin_user_id()}/Items",
            Recursive="true",
            IncludeItemTypes="Audio",
            StartIndex=start_index,
            Limit=limit,
        )
        chunk = response.get("Items", [])
        for item in chunk:
            if isinstance(item, dict):
                song = item.get("Name")
                artist = item.get("AlbumArtist")
                if isinstance(song, str) and isinstance(artist, str):
                    song = song.strip()
                    artist = artist.strip()
                    if song and artist:
                        items.append(f"{song} - {artist}")
        if len(chunk) < limit:
            break
        start_index += limit

    library_cache.set(cache_key, items, expire=CACHE_TTLS["full_library"])
    return items


async def fetch_lyrics_for_item(item_id: str) -> str | None:
    """
    Fetch raw lyrics JSON for a given Jellyfin audio item ID.

    Args:
        item_id (str): Jellyfin item ID.

    Returns:
        str or None: JSON text if available.
    """
    url = f"{_jellyfin_url()}/Items/{item_id}/Lyrics"
    params = {"api_key": _jellyfin_api_key()}
    try:
        client = get_http_client(short=True)
        response = await client.get(
            url,
            params=params,
        )
        if response.status_code == 200 and response.text.strip():
            record_success("jellyfin")
            logger.info("Fetched raw lyrics JSON from Jellyfin for item %s", item_id)
            return response.text.strip()
        record_success("jellyfin")
        logger.info("No lyrics available for item %s", item_id)
    except httpx.HTTPError as exc:
        record_failure("jellyfin")
        logger.warning("Failed to fetch lyrics for item %s: %s", item_id, exc)
    return None


async def _attach_lyrics(item: dict) -> None:
    """Attach lyrics to a track dictionary if available."""
    if not settings.lyrics_enabled:
        return
    track_path = item.get("Path")
    if track_path:
        lrc_contents = read_lrc_for_track(track_path)
        if lrc_contents:
            item["lyrics"] = strip_lrc_timecodes(lrc_contents)
            logger.info(
                "Attached lyrics from .lrc for item %s (%s)",
                item.get("Id"),
                item.get("Name"),
            )
            return

    if item.get("HasLyrics"):
        item_id = item.get("Id")
        logger.debug(
            "HasLyrics true but no .lrc found, checking Jellyfin API for item %s",
            item_id,
        )
        if isinstance(item_id, str):
            lyrics_json = await fetch_lyrics_for_item(item_id)
        else:
            lyrics_json = None
        if lyrics_json:
            try:
                parsed = json.loads(lyrics_json)
                text_lines = [
                    entry.get("Text")
                    for entry in parsed.get("Lyrics", [])
                    if entry.get("Text")
                ]
                if text_lines:
                    item["lyrics"] = "\n".join(text_lines)
                    logger.info(
                        "Extracted %d lines of Jellyfin API lyrics for item %s",
                        len(text_lines),
                        item_id,
                    )
                    logger.debug(
                        "Lyrics for item %s (%s):\n%s",
                        item_id,
                        item.get("Name"),
                        item["lyrics"],
                    )
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Failed to parse structured lyrics for item %s: %s",
                    item_id,
                    exc,
                )


async def fetch_jellyfin_track_metadata(title: str, artist: str) -> dict | None:
    """
    Search Jellyfin for a track by title and artist and return the full metadata dict if found.
    Returns None if no match is found.
    """
    title_cleaned = normalize_search_term(title)
    artist_cleaned = normalize_search_term(artist)
    try:
        client = get_http_client()
        response = await client.get(
            f"{_jellyfin_url()}/Items",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "SearchTerm": title_cleaned,
                "api_key": _jellyfin_api_key(),
                "userId": _jellyfin_user_id(),
            },
        )
        response.raise_for_status()
        record_success("jellyfin")
        data = response.json()

        items = data.get("Items", [])
        logger.debug(
            "🎧 Jellyfin metadata search: Found %d items for %s - %s",
            len(items),
            title_cleaned,
            artist,
        )
        for item in items:
            name = normalize_search_term(item.get("Name", ""))
            artists_list = item.get("Artists", [])
            artists = [normalize_search_term(a) for a in artists_list]
            if title_cleaned.lower() in name.lower() and any(
                artist_cleaned.lower() in a.lower() for a in artists
            ):
                logger.debug("✅ Match found: %s by %s", name, artists)
                return item

        logger.debug(
            "❌ No matching track metadata found for %s - %s", title_cleaned, artist
        )
        return None

    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.warning(
            "Jellyfin metadata fetch failed for %s - %s: %s", title, artist, exc
        )
        return None


async def resolve_jellyfin_path(
    title: str, artist: str, jellyfin_url: str, jellyfin_api_key: str
):
    """Return the filesystem path for a track if Jellyfin knows it."""
    url = f"{jellyfin_url}/Items"
    headers = {"X-Emby-Token": jellyfin_api_key, "Accept": "application/json"}
    params = {
        "Recursive": "true",
        "IncludeItemTypes": "Audio",
        "Filters": "IsNotFolder",
        "Artists": artist,
        "Name": title,
        "Fields": "Path",
    }

    logger.debug(
        "[resolve_jellyfin_path] Querying Jellyfin: Artist='%s' Title='%s'",
        artist,
        title,
    )
    logger.debug("[resolve_jellyfin_path] API URL: %s", url)
    logger.debug("[resolve_jellyfin_path] Params: %s", params)

    client = get_http_client()
    try:
        resp = await client.get(
            url,
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        record_success("jellyfin")

        data = resp.json()
        logger.debug("[resolve_jellyfin_path] Response JSON: %s", data)

        if "Items" in data and len(data["Items"]) > 0:
            path = data["Items"][0].get("Path")
            logger.debug("[resolve_jellyfin_path] Resolved path: %s", path)
            return path

        logger.debug(
            "[resolve_jellyfin_path] No items found for Artist='%s', Title='%s'",
            artist,
            title,
        )

    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.warning(
            "[resolve_jellyfin_path] Error during API call for '%s - %s': %s",
            artist,
            title,
            exc,
        )

    return None


async def create_jellyfin_playlist(
    name: str,
    track_item_ids: list[str],
    user_id: str | None = None,
) -> str | None:
    """
    Create a native Jellyfin playlist with the given name and list of track ItemIds.

    Args:
        name (str): Playlist name.
        track_item_ids (list[str]): List of Jellyfin ItemIds.
        user_id (str, optional): Jellyfin UserId. Defaults to settings.jellyfin_user_id.

    Returns:
        str | None: PlaylistId if created successfully, else None.
    """
    user_id = user_id or _jellyfin_user_id()

    url = f"{_jellyfin_url()}/Playlists"
    headers = {"X-Emby-Token": _jellyfin_api_key()}

    payload = {"Name": name, "UserId": user_id, "Ids": track_item_ids}

    logger.info(
        "🎵 Creating Jellyfin playlist '%s' for user %s with %d tracks",
        name,
        user_id,
        len(track_item_ids),
    )

    try:
        client = get_http_client()
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        record_success("jellyfin")
        playlist_id = response.json().get("Id")
        logger.info("✅ Jellyfin playlist created with Id: %s", playlist_id)
        return playlist_id

    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.error("❌ Failed to create Jellyfin playlist '%s': %s", name, exc)
        return None


async def get_full_item(item_id: str) -> dict | None:
    """Fetch the full Jellyfin item JSON for the given ID."""
    url = f"{_jellyfin_url().rstrip('/')}/Users/{_jellyfin_user_id()}/Items/{item_id}"
    headers = {"X-Emby-Token": _jellyfin_api_key()}
    try:
        client = get_http_client()
        resp = await client.get(
            url,
            headers=headers,
        )
        resp.raise_for_status()
        record_success("jellyfin")
        return resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        record_failure("jellyfin")
        logger.error("❌ Failed to fetch full Jellyfin item %s: %s", item_id, exc)
        return None


async def update_item_metadata(item_id: str, full_item: dict) -> bool:
    """Update a Jellyfin item with the provided metadata."""
    url = f"{_jellyfin_url().rstrip('/')}/Items/{item_id}"
    headers = {"X-Emby-Token": _jellyfin_api_key()}
    logger.info("Updating Item Metadata - Url:%s", url)
    try:
        client = get_http_client()
        resp = await client.post(
            url,
            headers=headers,
            json=full_item,
        )
        resp.raise_for_status()
        record_success("jellyfin")
        logger.info("✅ Successfully updated Jellyfin item %s", item_id)
        return True
    except httpx.HTTPError as exc:
        record_failure("jellyfin")
        logger.error("❌ Failed to update Jellyfin item %s: %s", item_id, exc)
        return False


def read_lrc_for_track(track_path: str) -> str | None:
    """
    Attempt to read an adjacent .lrc file for the given track path.

    Args:
        track_path (str): Filesystem path to the audio file.

    Returns:
        str or None: LRC file contents as plain text if found.
    """
    base, _ = os.path.splitext(track_path)
    lrc_path = base + ".lrc"
    if os.path.isfile(lrc_path):
        try:
            with open(lrc_path, "r", encoding="utf-8") as f:
                contents = f.read()
                logger.info(
                    "Loaded .lrc file: %s (%d lines)",
                    lrc_path,
                    len(contents.splitlines()),
                )
                return contents
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Error reading .lrc file %s: %s", lrc_path, exc)
    else:
        logger.debug("No .lrc file found for %s", track_path)
    return None


def strip_lrc_timecodes(lrc_text: str) -> str:
    """Remove `[mm:ss.xx]` style timecodes from LRC file contents.

    Args:
        lrc_text (str): Raw LRC contents.

    Returns:
        str: Plain lyrics text without timecodes.
    """
    timecode_pattern = r"\[(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,2})?\]"
    return re.sub(timecode_pattern, "", lrc_text).strip()
