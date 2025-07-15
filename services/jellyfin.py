from config import settings
from core.constants import *
import urllib.parse
from urllib.parse import quote_plus
import requests
import logging
import httpx

logger = logging.getLogger("playlist-pilot")

def normalize_search_term(term):
    # Replace smart quotes and other common variants
    return term.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')

def fetch_jellyfin_users():
    try:
        url = f"{settings.jellyfin_url.rstrip('/')}/Users"
        headers = {"X-Emby-Token": settings.jellyfin_api_key}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return {u["Name"]: u["Id"] for u in resp.json()}
    except Exception as e:
        logger.error(f"Failed to fetch Jellyfin users: {e}")
        return {}

def search_jellyfin_for_track(title: str, artist: str) -> bool:
    logger.debug(f"🔍 search_jellyfin_for_track() called with: {title} - {artist}")
    try:
        response = requests.get(
            f"{settings.jellyfin_url}/Items",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "SearchTerm": title,
                "api_key": settings.jellyfin_api_key,
                "userId": settings.jellyfin_user_id,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        items = data.get("Items", [])
        logger.debug(f"Found {len(items)} items")

        for item in items:
            name = item.get("Name", "")
            artists = item.get("Artists", [])
            logger.debug(f"→ Track: {name}, Artists: {artists}")

            if title.lower() in name.lower() and any(artist.lower() in a.lower() for a in artists):
                logger.debug("✅ Match found!")
                return True

        logger.debug("❌ No matching track found")
        return False

    except Exception as e:
        logger.warning(f"Jellyfin search failed for {title} - {artist}: {e}")
        return False


def jf_get(path, **params):
    url = f"{settings.jellyfin_url.rstrip('/')}{path}?api_key={settings.jellyfin_api_key}"
    if params:
        query = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        url += f"&{query}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()



def fetch_tracks_for_playlist_id(playlist_id: str) -> list[dict]:
    """
    Fetch detailed track list for a given Jellyfin playlist ID.
    Includes expanded fields useful for enrichment and analysis.
    Reads .lrc files directly from disk if present,
    otherwise attempts Jellyfin Lyrics API fetch if HasLyrics is true.
    """
    url = f"{settings.jellyfin_url}/Users/{settings.jellyfin_user_id}/Items"
    params = {
        "ParentId": playlist_id,
        "IncludeItemTypes": "Audio",
        "Fields": "Name,AlbumArtist,Artists,Album,ProductionYear,PremiereDate,Genres,RunTimeTicks,Genres,UserData,HasLyrics,Path,Tags",
        "Recursive": True,
        "api_key": settings.jellyfin_api_key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        items = data.get("Items", [])
        logger.debug(f"Fetched {len(items)} tracks for playlist {playlist_id}")

        for item in items:
            track_path = item.get("Path")
            lyrics_attached = False
            track_tags = item.get("Tags")
            if track_path:
                lrc_contents = read_lrc_for_track(track_path)
                if lrc_contents:
                    plain_lyrics = strip_lrc_timecodes(lrc_contents)
                    item["lyrics"] = plain_lyrics
                    logger.info(f"Attached lyrics from .lrc for item {item.get('Id')} ({item.get('Name')})")
                    lyrics_attached = True
            if not lyrics_attached and item.get("HasLyrics"):
                item_id = item.get("Id")
                logger.debug(f"HasLyrics true but no .lrc found, checking Jellyfin API for item {item_id}")
                lyrics_json = fetch_lyrics_for_item(item_id)
                if lyrics_json:
                    try:
                        parsed = json.loads(lyrics_json)
                        text_lines = [entry.get("Text") for entry in parsed.get("Lyrics", []) if entry.get("Text")]
                        if text_lines:
                            item["lyrics"] = "\n".join(text_lines)
                            logger.info(f"Extracted {len(text_lines)} lines of Jellyfin API lyrics for item {item_id}")
                            logger.debug(f"Lyrics for item {item_id} ({item.get('Name')}):\n{item['lyrics']}")
                    except Exception as e:
                        logger.warning(f"Failed to parse structured lyrics for item {item_id}: {e}")

        return items
    except Exception as e:
        logger.error(f"Failed to fetch tracks for playlist {playlist_id}: {e}")
        return []


def fetch_lyrics_for_item(item_id: str) -> str:
    """
    Fetch raw lyrics JSON for a given Jellyfin audio item ID.

    Args:
        item_id (str): Jellyfin item ID.

    Returns:
        str or None: JSON text if available.
    """
    url = f"{settings.jellyfin_url}/Items/{item_id}/Lyrics"
    params = {"api_key": settings.jellyfin_api_key}
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200 and response.text.strip():
            logger.info(f"Fetched raw lyrics JSON from Jellyfin for item {item_id}")
            return response.text.strip()
        else:
            logger.info(f"No lyrics available for item {item_id}")
    except Exception as e:
        logger.warning(f"Failed to fetch lyrics for item {item_id}: {e}")
    return None




def fetch_jellyfin_track_metadata(title: str, artist: str) -> dict | None:
    """
    Search Jellyfin for a track by title and artist and return the full metadata dict if found.
    Returns None if no match is found.
    """
    title_cleaned = normalize_search_term(title)
    url=f"{settings.jellyfin_url}/Items"
    params={ "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "SearchTerm": title_cleaned,
                "api_key": settings.jellyfin_api_key,
                "userId": settings.jellyfin_user_id,
            }
    try:
        response = requests.get(
            f"{settings.jellyfin_url}/Items",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "SearchTerm": title_cleaned,
                "api_key": settings.jellyfin_api_key,
                "userId": settings.jellyfin_user_id,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        items = data.get("Items", [])
        logger.debug(f"🎧 Jellyfin metadata search: Found {len(items)} items for {title_cleaned} - {artist}")
        for item in items:
            name = normalize_search_term(item.get("Name", ""))
            artists_list = item.get("Artists", [])
            artists = [normalize_search_term(a) for a in artists_list]
            if title_cleaned.lower() in name.lower() and any(artist.lower() in a.lower() for a in artists):
                logger.debug(f"✅ Match found: {name} by {artists}")
                return item

        logger.debug(f"❌ No matching track metadata found for {title_cleaned} - {artist}")
        return None

    except Exception as e:
        logger.warning(f"Jellyfin metadata fetch failed for {title} - {artist}: {e}")
        return None


async def resolve_jellyfin_path(title, artist, jellyfin_url, jellyfin_api_key):
    url = f"{jellyfin_url}/Items"
    headers = {
        "X-Emby-Token": jellyfin_api_key,
        "Accept": "application/json"
    }
    params = {
        "Recursive": "true",
        "IncludeItemTypes": "Audio",
        "Filters": "IsNotFolder",
        "Artists": artist,
        "Name": title,
        "Fields": "Path"
    }

    logger.debug(f"[resolve_jellyfin_path] Querying Jellyfin: Artist='{artist}' Title='{title}'")
    logger.debug(f"[resolve_jellyfin_path] API URL: {url}")
    logger.debug(f"[resolve_jellyfin_path] Params: {params}")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()

            data = resp.json()
            logger.debug(f"[resolve_jellyfin_path] Response JSON: {data}")

            if "Items" in data and len(data["Items"]) > 0:
                path = data["Items"][0].get("Path")
                logger.debug(f"[resolve_jellyfin_path] Resolved path: {path}")
                return path
            else:
                logger.debug(f"[resolve_jellyfin_path] No items found for Artist='{artist}', Title='{title}'")

        except Exception as e:
            logger.warning(f"[resolve_jellyfin_path] Error during API call for '{artist} - {title}': {e}")

    return None

def create_jellyfin_playlist(name: str, track_item_ids: list[str], user_id: str = None) -> str | None:
    """
    Create a native Jellyfin playlist with the given name and list of track ItemIds.

    Args:
        name (str): Playlist name.
        track_item_ids (list[str]): List of Jellyfin ItemIds.
        user_id (str, optional): Jellyfin UserId. Defaults to settings.jellyfin_user_id.

    Returns:
        str | None: PlaylistId if created successfully, else None.
    """
    user_id = user_id or settings.jellyfin_user_id

    url = f"{settings.jellyfin_url}/Playlists"
    headers = {"X-Emby-Token": settings.jellyfin_api_key}

    payload = {
        "Name": name,
        "UserId": user_id,
        "Ids": track_item_ids
    }

    logger.info(f"🎵 Creating Jellyfin playlist '{name}' for user {user_id} with {len(track_item_ids)} tracks")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        playlist_id = response.json().get("Id")
        logger.info(f"✅ Jellyfin playlist created with Id: {playlist_id}")
        return playlist_id

    except Exception as e:
        logger.error(f"❌ Failed to create Jellyfin playlist '{name}': {e}")
        return None

def get_full_item(item_id: str) -> dict | None:
    url = f"{settings.jellyfin_url.rstrip('/')}/Users/{settings.jellyfin_user_id}/Items/{item_id}"
    headers = {"X-Emby-Token": settings.jellyfin_api_key}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"❌ Failed to fetch full Jellyfin item {item_id}: {e}")
        return None

def update_item_metadata(item_id: str, full_item: dict) -> bool:
    url = f"{settings.jellyfin_url.rstrip('/')}/Items/{item_id}"
    headers = {"X-Emby-Token": settings.jellyfin_api_key}
    logger.info(f"Updating Item Metadata - Url:{url}")
    try:
        resp = requests.post(url, headers=headers, json=full_item, timeout=10)
        resp.raise_for_status()
        logger.info(f"✅ Successfully updated Jellyfin item {item_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update Jellyfin item {item_id}: {e}")
        return False

import os

def read_lrc_for_track(track_path: str) -> str:
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
            with open(lrc_path, 'r', encoding='utf-8') as f:
                contents = f.read()
                logger.info(f"Loaded .lrc file: {lrc_path} ({len(contents.splitlines())} lines)")
                return contents
        except Exception as e:
            print(f"Error reading .lrc file {lrc_path}: {e}")

            logger.warning(f"Error reading .lrc file {lrc_path}: {e}")
    else:
        logger.debug(f"No .lrc file found for {track_path}")
    return None


import re

def strip_lrc_timecodes(lrc_text: str) -> str:
    """
    Remove [mm:ss.xx] style timecodes from LRC file contents.

    Args:
        lrc_text (str): Raw LRC contents.

    Returns:
        str: Plain lyrics text without timecodes.
    """
    return re.sub(r'\[.*?\]', '', lrc_text).strip()
