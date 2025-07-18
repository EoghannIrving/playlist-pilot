"""
playlist.py

Core logic for interacting with Jellyfin audio playlists and preparing data for GPT-assisted suggestions.

Functions included:
- Fetching user playlists from Jellyfin
- Fetching and labeling tracks
- Parsing GPT suggestion lines
- Searching and sampling the user's audio library
"""

import re
import random
import logging
import math
import cloudscraper
import asyncio
import httpx

from config import settings, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM
from core.constants import *
from services.jellyfin import jf_get, fetch_tracks_for_playlist_id
from services.lastfm import enrich_with_lastfm
from typing import Optional, Dict
from core.models import Track, EnrichedTrack
from urllib.parse import quote_plus
from utils.cache_manager import bpm_cache, library_cache, CACHE_TTLS
from services.getsongbpm import get_cached_bpm
from services.gpt import analyze_mood_from_lyrics
from core.analysis import (
    mood_scores_from_bpm_data,
    mood_scores_from_lastfm_tags,
    combine_mood_scores,
    normalize_popularity,
    combined_popularity_score,
    normalize_popularity_log,
    build_lyrics_scores,
)

logger = logging.getLogger("playlist-pilot")

async def fetch_audio_playlists() -> dict:
    """Fetch all playlists that contain at least one audio track."""
    playlists = (await jf_get(
        f"/Users/{settings.jellyfin_user_id}/Items",
        IncludeItemTypes="Playlist",
        Recursive="true"
    )).get("Items", [])

    audio_playlists = []
    for pl in playlists:
        pl_id = pl["Id"]
        contents = (await jf_get(
            f"/Users/{settings.jellyfin_user_id}/Items",
            ParentId=pl_id,
            IncludeItemTypes="Audio",
            Recursive="true",
            Limit=1,
        )).get("Items", [])
        if contents:
            audio_playlists.append({"name": pl["Name"], "id": pl["Id"]})

    audio_playlists.sort(key=lambda p: p["name"].lower())
    return {"playlists": audio_playlists}

async def get_playlist_id_by_name(name: str) -> str | None:
    """Return the ID of a Jellyfin playlist given its name."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.jellyfin_url.rstrip('/')}/Users/{settings.jellyfin_user_id}/Items",
                headers={"X-Emby-Token": settings.jellyfin_api_key},
                params={"IncludeItemTypes": "Playlist", "Recursive": "true"},
                timeout=10
            )
        resp.raise_for_status()
        for item in resp.json().get("Items", []):
            if item.get("Name") == name:
                return item.get("Id")
    except Exception as e:
        logger.error(f"Failed to get playlist ID for '{name}': {e}")
    return None

async def get_playlist_tracks(playlist_id: str) -> list[str]:
    """Fetch and return track titles from a Jellyfin playlist by ID."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.jellyfin_url.rstrip('/')}/Users/{settings.jellyfin_user_id}/Items",
                headers={"X-Emby-Token": settings.jellyfin_api_key},
                params={"ParentId": playlist_id, "IncludeItemTypes": "Audio", "Recursive": "true"},
                timeout=10
            )
        resp.raise_for_status()
        items = resp.json().get("Items", [])
        return [
            f"{track.get('Name')} - {track.get('AlbumArtist')}"
            for track in items if track.get("Name") and track.get("AlbumArtist")
        ]
    except Exception as e:
        logger.error(f"Failed to fetch playlist tracks for ID {playlist_id}: {e}")
        return []

async def get_full_audio_library(force_refresh: bool = False) -> list[str]:
    """Return the user's full audio library with caching."""
    cache_key = f"library:{settings.jellyfin_user_id}"
    if not force_refresh:
        cached = library_cache.get(cache_key)
        if cached is not None:
            return cached

    items: list[str] = []
    start_index = 0
    limit = 1000
    while True:
        response = await jf_get(
            f"/Users/{settings.jellyfin_user_id}/Items",
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
                items.append(f"{song} - {artist}")
        if len(chunk) < limit:
            break
        start_index += limit

    library_cache.set(cache_key, items, expire=CACHE_TTLS["full_library"])
    return items

def clean(text: str) -> str:
    """Normalize text by lowercasing and removing punctuation."""
    return re.sub(r"[^\w\s]", "", text.lower().strip())

def parse_suggestion_line(line: str) -> tuple[str, str]:
    """
    Parse a GPT suggestion line formatted as:
    "Track - Artist - Album - Year - Reason"

    Returns:
        (track_label, reason)
    """
    parts = [p.strip() for p in line.split(" - ", 4)]
    if len(parts) < 5:
        raise ValueError(f"Incomplete GPT suggestion line: '{line}'")
    text = " - ".join(parts[:4])
    reason = parts[4]
    return text, reason

def build_search_query(line: str) -> str:
    """Extract a basic search query from a track label."""
    parts = [part.strip() for part in line.split("-")]
    return f"{parts[0]} {parts[1]}" if len(parts) >= 2 else line.strip()

def normalize_track(raw: str | dict) -> Track:
    """
    Normalize a track from either a raw string (GPT) or a Jellyfin track dict.
    
    Returns a consistent track structure:
        {
            "raw": ...,
            "title": ...,
            "artist": ...,
            "album": ...,
            "year": ...
        }
    """
    if isinstance(raw, str):
        # GPT-style string
        parts = [p.strip() for p in raw.split(" - ")]
        return Track(
            raw=raw.strip(),
            title=parts[0] if len(parts) > 0 else "",
            artist=parts[1] if len(parts) > 1 else "",
            album=parts[2] if len(parts) > 2 else "",
            year=parts[3] if len(parts) > 3 else "",
        )

    elif isinstance(raw, dict):
        # Jellyfin track dict
        tempo = extract_tag_value(raw.get("Tags"), "tempo")
        return Track(
            raw=raw.get("Name", ""),
            title=raw.get("Name", "").strip(),
            artist=raw.get("AlbumArtist") or (raw.get("Artists") or [""])[0],
            album=raw.get("Album", "").strip(),
            year=extract_year(raw),
            Genres=raw.get("Genres", []),
            lyrics=raw.get("lyrics", []),
            tempo=tempo,
            RunTimeTicks=raw.get("RunTimeTicks", 0),
        )

    else:
        return Track(raw=str(raw), title="", artist="", album="", year="")

async def enrich_track(parsed: Track | dict) -> EnrichedTrack:
    # ✅ 0. Ensure essential fields
    if isinstance(parsed, dict):
        parsed = Track.parse_obj(parsed)

    if not parsed.title or not parsed.artist:
        raise ValueError("Missing required track metadata (title/artist)")

    title = parsed.title
    artist = parsed.artist

    # ✅ 1. Last.fm enrichment
    lastfm_data = await enrich_with_lastfm(title, artist)
    tags = lastfm_data["tags"]
    listeners = lastfm_data["listeners"]
    releasedate = lastfm_data["releasedate"]
    album = "Not in Last.fm"
    album = lastfm_data["album"]
    parsed.tags = tags  # used by mood scoring

    # ✅ 2. Genre selection via Jellyfin or Last.fm tags
    genres = parsed.Genres or []
    genre = filter_valid_genre(genres)
    if not genre or genre.lower() == "unknown":
        genre = filter_valid_genre(tags)

    # ✅ 3. Duration and tempo estimation
    ticks = parsed.RunTimeTicks
    duration_sec = int(ticks / 10_000_000) if ticks else 0
    tempo = estimate_tempo(duration_sec, genre)

    # ✅ 4. BPM + Year handling from GetSongBPM
    bpm_data = {}
    bpm = None
    bpmdatayear = 0
    year_flag = ""

    if artist and title and settings.getsongbpm_api_key:
        try:
            bpm_data = await asyncio.to_thread(
                get_cached_bpm,
                artist=artist,
                title=title,
                api_key=settings.getsongbpm_api_key,
            )
        except Exception as e:
            logger.warning(f"GetSongBPM API failed for {artist} - {title}: {e}")

    bpm = bpm_data.get("bpm") if bpm_data else None
    if not bpm:
        bpm = parsed.tempo
        logger.debug(f"BPM from Jellyfin metadata: {bpm}")
    
    bpmdatayear = bpm_data.get("year") if bpm_data else 0
    jellyfin_year = parsed.year or ""

    if bpmdatayear:
        final_year = bpmdatayear
    elif jellyfin_year:
        final_year = jellyfin_year
    else:
        final_year = None

    try:
        if jellyfin_year and bpmdatayear:
            if abs(int(jellyfin_year) - int(bpmdatayear)) > 1:
                year_flag = f"GetSongBPM Date: {bpmdatayear} or Jellyfin Date: {jellyfin_year}"
    except (ValueError, TypeError):
        logger.warning(f"Invalid year data: Jellyfin={jellyfin_year}, BPM={bpmdatayear}")

    bpm_duration=bpm_data.get("duration")
    if not duration_sec and bpm_data.get("duration"):
        duration_sec = bpm_data["duration"]

    # ✅ 5. Decade inference
    decade = infer_decade(final_year)

    # ✅ 6. Mood classification
    logger.debug(f"Enriching track: {parsed.title}")
    tag_scores = mood_scores_from_lastfm_tags(tags)
    bpm_scores = mood_scores_from_bpm_data(bpm_data or {})
    lyrics_scores = None
    lyrics = get_lyrics_for_enrich(parsed.dict())
    lyrics_mood = await asyncio.to_thread(analyze_mood_from_lyrics, lyrics)
    lyrics_scores = build_lyrics_scores(lyrics_mood) if lyrics_mood else None
    mood, confidence = combine_mood_scores(tag_scores, bpm_scores, lyrics_scores)

    # ✅ 7. Return enriched result
    return EnrichedTrack(
        **parsed.dict(),
        genre=genre or "Unknown",
        mood=mood,
        mood_confidence=round(confidence, 2),
        tempo=bpm,
        decade=decade,
        duration=duration_sec,
        popularity=listeners,
        jellyfin_play_count=parsed.jellyfin_play_count,
        year_flag=year_flag,
        album=album,
        FinalYear=final_year,
    )

def infer_decade(year_str: str) -> str:
    try:
        year = int(year_str)
        return f"{year // 10 * 10}s"
    except Exception:
        return "Unknown"

def extract_year(track: dict) -> str:
    try:
        return str(track.get("ProductionYear")) or str(track.get("PremiereDate", "")[:4])
    except:
        return ""

def clean_genre(genre: str) -> str:
    return genre.strip().lower().title()  # " hip hop " → "Hip Hop"

GENRE_SYNONYMS = {
    # Hip Hop & R&B
    "hip-hop": "hip hop",
    "rap": "hip hop",
    "trap": "hip hop",
    "rnb": "r&b",
    "rhythm and blues": "r&b",
    # Rock
    "alt rock": "alternative",
    "alternative rock": "alternative",
    "classic rock": "rock",
    "hard rock": "rock",
    "indie rock": "indie",
    "indie pop": "indie",
    "garage rock": "rock",
    "post-punk": "punk",
    # EDM/Electronic
    "electronica": "edm",
    "electronic": "edm",
    "dance": "edm",
    "house": "edm",
    "techno": "edm",
    "trance": "edm",
    "dnb": "drum and bass",
    "drum & bass": "drum and bass",
    "breakbeats": "breakbeat",
    "dub": "dubstep",
    # Moods and culture tags (ignored)
    "britpop": "pop",
    "lofi": "lo-fi",
    "lo-fi hip hop": "lo-fi",
    # Other
    "soundtrack": "ost",
    "original soundtrack": "ost",
    "musicals": "musical",
    "broadway": "musical",
    "latin pop": "latin",
    "salsa": "latin",
    "kpop": "k-pop",
    "jpop": "j-pop",
    "afrobeats": "afrobeat",
    "synth pop": "synthpop",
    "ambient music": "ambient"
}




def normalize_genre(raw: str) -> str:
    cleaned = raw.strip().lower()
    return GENRE_SYNONYMS.get(cleaned, cleaned)

def estimate_tempo(duration_sec: int, genre: str = "") -> int:
    genre = genre.lower()
    if "electronic" in genre or "edm" in genre:
        return 140 if duration_sec < 300 else 120
    elif "rock" in genre:
        return 120
    elif "hip hop" in genre:
        return 90
    elif "ambient" in genre:
        return 70
    else:
        return 100
KNOWN_GENRES = {
    "rock", "pop", "hip hop", "rap", "r&b", "jazz", "blues", "metal", "punk",
    "edm", "electronic", "folk", "classical", "indie", "alternative", "reggae",
    "country", "techno", "trance", "house", "ambient", "soul", "funk", "grunge",
    "ska", "emo", "drum and bass", "breakbeat", "dubstep", "trap",
    "lo-fi", "garage", "k-pop", "j-pop", "afrobeat", "new wave",
    "grime", "chillout", "chillwave", "synthpop", "industrial",
    "world", "latin", "reggaeton", "opera", "musical", "post-rock", "folk"
}

def filter_valid_genre(tags: list[str]) -> str:
    for tag in tags:
        normalized = normalize_genre(tag).lower()
        if normalized in KNOWN_GENRES:
            return normalize_genre(tag)
    return ""

def extract_year_from_string(releasedate: str) -> str:
    """
    Extract the 4-digit year from a Last.fm release date string.
    Returns a string or empty string if not found.
    """
    if not releasedate:
        return ""

    match = re.search(r"\b(19|20)\d{2}\b", releasedate)
    return match.group(0) if match else ""

async def enrich_jellyfin_playlist(playlist_id: str, limit: int = 10) -> list[dict]:
    """Fetch tracks for a playlist and enrich them concurrently."""
    raw_tracks = await fetch_tracks_for_playlist_id(playlist_id)
    async def process(track: dict) -> dict | None:
        try:
            norm = normalize_track(track)
            norm.jellyfin_play_count = track.get("UserData", {}).get("PlayCount", 0)
            enriched_data = await enrich_track(norm)
            logger.info(
                f"✅ Enriched: {norm.title or 'Unknown'} "
                f"| Last.fm: {enriched_data.popularity if hasattr(enriched_data, 'popularity') else 'N/A'} "
                f"| Jellyfin Plays: {norm.jellyfin_play_count}"
            )
            return enriched_data.dict()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Track enrichment failed for '%s': %s", track.get("Name"), exc)
            return None

    enriched_tasks = await asyncio.gather(*(process(t) for t in raw_tracks))
    enriched = [e for e in enriched_tasks if e is not None]

    # Collect raw popularity values
    lastfm_raw = [t["popularity"] for t in enriched if isinstance(t.get("popularity"), int)]
    jellyfin_raw = [t["jellyfin_play_count"] for t in enriched if isinstance(t.get("jellyfin_play_count"), int)]

    logger.info(f"📊 Last.fm popularity range: min={min(lastfm_raw, default=0)}, max={max(lastfm_raw, default=0)}")
    logger.info(f"📊 Jellyfin play count range: min={min(jellyfin_raw, default=0)}, max={max(jellyfin_raw, default=0)}")

    max_jf = max(jellyfin_raw, default=1)

    for t in enriched:
        raw_lfm = t.get("popularity")
        raw_jf = t.get("jellyfin_play_count")
        norm_lfm = normalize_popularity_log(raw_lfm, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM)
        norm_jf = normalize_popularity(raw_jf, 0, max_jf)
        logger.info(f"{t['title']}")
        combined = combined_popularity_score(norm_lfm, norm_jf)
        t["combined_popularity"] = combined

        logger.info(f"📈 {t['title']} → LFM: {raw_lfm} (→ {norm_lfm}), JF: {raw_jf} (→ {norm_jf}) → Combined: {combined}")

    return enriched


# Patch: Helper to get lyrics in enrich_track()
def get_lyrics_for_enrich(track: dict) -> str:
    """
    Unified helper for enrich_track() to retrieve lyrics from pre-fetched metadata.

    Args:
        track (dict): Enriched track dict with optional 'lyrics' key.

    Returns:
        str or None: Lyrics text if available.
    """
    lyrics = track.get("lyrics")
    if lyrics:
        logger.debug(f"Lyrics found in track metadata for {track.get('artist')} - {track.get('title')}")
        return lyrics.strip()

    logger.debug(f"No lyrics found for {track.get('artist')} - {track.get('title')}")
    return None

# Usage in enrich_track():
# lyrics = get_lyrics_for_enrich(track)
# lyrics_mood = analyze_mood_from_lyrics(lyrics) if lyrics else None
# lyrics_scores = build_lyrics_scores(lyrics_mood) if lyrics_mood else None

def extract_tag_value(tags: list[str], prefix: str) -> str | None:
    """
    Look for a tag that starts with '{prefix}:' and return its value (after colon).
    
    Args:
        tags (list[str]): List of tag strings like ['tempo:105', 'mood:uplifting']
        prefix (str): The prefix to search for (e.g., 'tempo')

    Returns:
        str or None: Value part if found, else None.
    """
    for tag in tags or []:
        if tag.startswith(f"{prefix}:"):
            return tag.split(":", 1)[1]
    return None
