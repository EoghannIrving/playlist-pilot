"""
playlist.py

Core logic for interacting with Jellyfin audio playlists and preparing data for GPT suggestions.

Functions included:
- Fetching user playlists from Jellyfin
- Fetching and labeling tracks
- Parsing GPT suggestion lines
- Searching and sampling the user's audio library
"""

import asyncio
import logging
import re

import httpx

from config import settings, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM
from core.analysis import (
    mood_scores_from_bpm_data,
    mood_scores_from_lastfm_tags,
    combine_mood_scores,
    normalize_popularity,
    combined_popularity_score,
    normalize_popularity_log,
    build_lyrics_scores,
    add_combined_popularity,
)
from core.models import Track, EnrichedTrack
from services.getsongbpm import get_cached_bpm
from services.gpt import analyze_mood_from_lyrics
from services.jellyfin import (
    jf_get,
    fetch_tracks_for_playlist_id,
    fetch_jellyfin_track_metadata,
)
from services.metube import get_youtube_url_single
from services.lastfm import enrich_with_lastfm
from utils.cache_manager import library_cache, CACHE_TTLS

logger = logging.getLogger("playlist-pilot")


async def fetch_audio_playlists() -> dict:
    """Fetch all playlists that contain at least one audio track."""
    resp = await jf_get(
        f"/Users/{settings.jellyfin_user_id}/Items",
        IncludeItemTypes="Playlist",
        Recursive="true",
    )
    if "error" in resp:
        return {"playlists": [], "error": resp["error"]}
    playlists = resp.get("Items", [])

    audio_playlists = []
    for pl in playlists:
        pl_id = pl["Id"]
        contents_resp = await jf_get(
            f"/Users/{settings.jellyfin_user_id}/Items",
            ParentId=pl_id,
            IncludeItemTypes="Audio",
            Recursive="true",
            Limit=1,
        )
        if "error" in contents_resp:
            logger.error(
                "Failed to check playlist %s contents: %s",
                pl_id,
                contents_resp["error"],
            )
            continue
        contents = contents_resp.get("Items", [])
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
                timeout=10,
            )
        resp.raise_for_status()
        for item in resp.json().get("Items", []):
            if item.get("Name") == name:
                return item.get("Id")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to get playlist ID for '%s': %s", name, exc)
    return None


async def get_playlist_tracks(playlist_id: str) -> list[str]:
    """Fetch and return track titles from a Jellyfin playlist by ID."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.jellyfin_url.rstrip('/')}/Users/{settings.jellyfin_user_id}/Items",
                headers={"X-Emby-Token": settings.jellyfin_api_key},
                params={
                    "ParentId": playlist_id,
                    "IncludeItemTypes": "Audio",
                    "Recursive": "true",
                },
                timeout=10,
            )
        resp.raise_for_status()
        items = resp.json().get("Items", [])
        return [
            f"{track.get('Name')} - {track.get('AlbumArtist')}"
            for track in items
            if track.get("Name") and track.get("AlbumArtist")
        ]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error(
            "Failed to fetch playlist tracks for ID %s: %s",
            playlist_id,
            exc,
        )
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
    limit = settings.library_scan_limit
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

    if isinstance(raw, dict):
        # Jellyfin track dict
        tempo = extract_tag_value(raw.get("Tags"), "tempo")
        lyrics = raw.get("lyrics")
        return Track(
            raw=raw.get("Name", ""),
            title=raw.get("Name", "").strip(),
            artist=raw.get("AlbumArtist") or (raw.get("Artists") or [""])[0],
            album=raw.get("Album", "").strip(),
            year=extract_year(raw),
            Genres=raw.get("Genres", []),
            lyrics=lyrics,
            tempo=tempo,
            RunTimeTicks=raw.get("RunTimeTicks", 0),
        )

    return Track(raw=str(raw), title="", artist="", album="", year="")


def _ensure_track(parsed: Track | dict) -> Track:
    """Validate and convert a raw track into a :class:`Track`."""
    if isinstance(parsed, dict):
        parsed = Track.parse_obj(parsed)
    if not parsed.title or not parsed.artist:
        raise ValueError("Missing required track metadata (title/artist)")
    return parsed


async def _get_lastfm_data(title: str, artist: str) -> dict:
    """Retrieve tags, listeners and album information from Last.fm."""
    data = await enrich_with_lastfm(title, artist)
    return {
        "tags": data["tags"],
        "listeners": data["listeners"],
        "album": data["album"],
    }


def _select_genre(genres: list[str], tags: list[str]) -> str:
    """Choose a genre from Jellyfin metadata or Last.fm tags."""
    genre = filter_valid_genre(genres)
    if not genre or genre.lower() == "unknown":
        genre = filter_valid_genre(tags)
    return genre


async def _fetch_bpm_data(artist: str, title: str) -> dict:
    """Return cached BPM data from GetSongBPM if configured."""
    if artist and title and settings.getsongbpm_api_key:
        try:
            return await asyncio.to_thread(
                get_cached_bpm,
                artist=artist,
                title=title,
                api_key=settings.getsongbpm_api_key,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("GetSongBPM API failed for %s - %s: %s", artist, title, exc)
    return {}


def _determine_year(jellyfin_year: str, bpm_year: int | None) -> tuple[int | None, str]:
    """Determine the final year and flag mismatches between sources."""
    year_flag = ""
    if bpm_year:
        final_year = bpm_year
    elif jellyfin_year:
        final_year = jellyfin_year
    else:
        final_year = None
    try:
        if jellyfin_year and bpm_year and abs(int(jellyfin_year) - int(bpm_year)) > 1:
            year_flag = f"GetSongBPM Date: {bpm_year} or Jellyfin Date: {jellyfin_year}"
    except (ValueError, TypeError):
        logger.warning(
            "Invalid year data: Jellyfin=%s, BPM=%s", jellyfin_year, bpm_year
        )
    return final_year, year_flag


def _duration_from_ticks(ticks: int, bpm_data: dict) -> int:
    """Convert Jellyfin run-time ticks to seconds, falling back to BPM data."""
    duration = int(ticks / 10_000_000) if ticks else 0
    return bpm_data.get("duration", duration)


async def _classify_mood(
    parsed: Track, tags: list[str], bpm_data: dict
) -> tuple[str, float]:
    """Return mood label and confidence score for a track."""
    logger.debug("Enriching track: %s", parsed.title)
    tag_scores = mood_scores_from_lastfm_tags(tags)
    bpm_scores = mood_scores_from_bpm_data(bpm_data or {})
    lyrics = get_lyrics_for_enrich(parsed.dict())
    lyrics_mood = await asyncio.to_thread(analyze_mood_from_lyrics, lyrics)
    lyrics_scores = build_lyrics_scores(lyrics_mood) if lyrics_mood else None
    return combine_mood_scores(tag_scores, bpm_scores, lyrics_scores)


async def enrich_track(parsed: Track | dict) -> EnrichedTrack:
    """Enrich a track with Last.fm, BPM, mood and other metadata."""
    parsed = _ensure_track(parsed)
    lastfm = await _get_lastfm_data(parsed.title, parsed.artist)
    parsed.tags = lastfm["tags"]  # used by mood scoring
    genre = _select_genre(parsed.Genres or [], lastfm["tags"])
    bpm_data = await _fetch_bpm_data(parsed.artist, parsed.title)
    bpm = bpm_data.get("bpm") or parsed.tempo
    duration_sec = _duration_from_ticks(parsed.RunTimeTicks, bpm_data)
    final_year, year_flag = _determine_year(parsed.year or "", bpm_data.get("year"))
    decade = infer_decade(final_year)
    mood, confidence = await _classify_mood(parsed, lastfm["tags"], bpm_data)

    base_data = parsed.dict(exclude={"tempo", "jellyfin_play_count", "album"})

    return EnrichedTrack(
        **base_data,
        genre=genre or "Unknown",
        mood=mood,
        mood_confidence=round(confidence, 2),
        tempo=bpm,
        decade=decade,
        duration=duration_sec,
        popularity=lastfm["listeners"],
        jellyfin_play_count=parsed.jellyfin_play_count,
        year_flag=year_flag,
        album=lastfm["album"],
        FinalYear=final_year,
    )


def infer_decade(year_str: str) -> str:
    """Return the decade string (e.g. ``1990s``) for a given year string."""
    try:
        year = int(year_str)
        return f"{year // 10 * 10}s"
    except (ValueError, TypeError):
        return "Unknown"


def extract_year(track: dict) -> str:
    """Extract the production year from a Jellyfin track dict."""
    try:
        return str(track.get("ProductionYear")) or str(
            track.get("PremiereDate", "")[:4]
        )
    except (AttributeError, TypeError):
        return ""


def clean_genre(genre: str) -> str:
    """Normalize capitalization and whitespace of a genre string."""
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
    "ambient music": "ambient",
}


def normalize_genre(raw: str) -> str:
    """Map genre synonyms to canonical names."""
    cleaned = raw.strip().lower()
    return GENRE_SYNONYMS.get(cleaned, cleaned)


def estimate_tempo(duration_sec: int, genre: str = "") -> int:
    """Return a rough BPM estimate based on duration and genre heuristics."""
    genre = genre.lower()
    if "electronic" in genre or "edm" in genre:
        return 140 if duration_sec < 300 else 120
    if "rock" in genre:
        return 120
    if "hip hop" in genre:
        return 90
    if "ambient" in genre:
        return 70
    return 100


KNOWN_GENRES = {
    "rock",
    "pop",
    "hip hop",
    "rap",
    "r&b",
    "jazz",
    "blues",
    "metal",
    "punk",
    "edm",
    "electronic",
    "folk",
    "classical",
    "indie",
    "alternative",
    "reggae",
    "country",
    "techno",
    "trance",
    "house",
    "ambient",
    "soul",
    "funk",
    "grunge",
    "ska",
    "emo",
    "drum and bass",
    "breakbeat",
    "dubstep",
    "trap",
    "lo-fi",
    "garage",
    "k-pop",
    "j-pop",
    "afrobeat",
    "new wave",
    "grime",
    "chillout",
    "chillwave",
    "synthpop",
    "industrial",
    "world",
    "latin",
    "reggaeton",
    "opera",
    "musical",
    "post-rock",
}


def filter_valid_genre(tags: list[str]) -> str:
    """Return the first tag that matches a known genre."""
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


async def enrich_jellyfin_playlist(
    playlist_id: str, limit: int | None = None
) -> list[dict]:
    """Fetch tracks for a playlist and enrich them concurrently."""
    raw_tracks = await fetch_tracks_for_playlist_id(playlist_id, limit)
    if isinstance(limit, int) and limit > 0:
        raw_tracks = raw_tracks[:limit]

    async def process(track: dict) -> dict | None:
        try:
            norm = normalize_track(track)
            norm.jellyfin_play_count = track.get("UserData", {}).get("PlayCount", 0)
            enriched_data = await enrich_track(norm)
            logger.info(
                "✅ Enriched: %s | Last.fm: %s | Jellyfin Plays: %s",
                norm.title or "Unknown",
                (
                    enriched_data.popularity
                    if hasattr(enriched_data, "popularity")
                    else "N/A"
                ),
                norm.jellyfin_play_count,
            )
            return enriched_data.dict()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Track enrichment failed for '%s': %s", track.get("Name"), exc
            )
            return None

    enriched_tasks = await asyncio.gather(*(process(t) for t in raw_tracks))
    enriched = [e for e in enriched_tasks if e is not None]

    # Collect raw popularity values
    lastfm_raw = [
        t["popularity"] for t in enriched if isinstance(t.get("popularity"), int)
    ]
    jellyfin_raw = [
        t["jellyfin_play_count"]
        for t in enriched
        if isinstance(t.get("jellyfin_play_count"), int)
    ]

    logger.debug(
        "📊 Last.fm popularity range: min=%s, max=%s",
        min(lastfm_raw, default=0),
        max(lastfm_raw, default=0),
    )
    logger.debug(
        "📊 Jellyfin play count range: min=%s, max=%s",
        min(jellyfin_raw, default=0),
        max(jellyfin_raw, default=0),
    )

    max_jf = max(jellyfin_raw, default=1)

    for t in enriched:
        raw_lfm = t.get("popularity")
        raw_jf = t.get("jellyfin_play_count")
        norm_lfm = normalize_popularity_log(raw_lfm, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM)
        norm_jf = normalize_popularity(raw_jf, 0, max_jf)
        logger.debug("%s", t["title"])
        combined = combined_popularity_score(norm_lfm, norm_jf)
        t["combined_popularity"] = combined

        logger.debug(
            "📈 %s → LFM: %s (→ %s), JF: %s (→ %s) → Combined: %s",
            t["title"],
            raw_lfm,
            norm_lfm,
            raw_jf,
            norm_jf,
            combined,
        )

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
        logger.debug(
            "Lyrics found in track metadata for %s - %s",
            track.get("artist"),
            track.get("title"),
        )
        return lyrics.strip()

    logger.debug(
        "No lyrics found for %s - %s",
        track.get("artist"),
        track.get("title"),
    )
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


async def enrich_suggestion(suggestion: dict) -> dict | None:
    """Return enriched data for a single GPT suggestion."""
    try:
        text, reason = parse_suggestion_line(suggestion["text"])
        title = suggestion["title"]
        artist = suggestion["artist"]
        jellyfin_data = await fetch_jellyfin_track_metadata(title, artist)
        in_jellyfin = bool(jellyfin_data)
        play_count = 0
        genres = []
        duration_ticks = 0
        youtube_url = None
        if in_jellyfin:
            play_count = jellyfin_data.get("UserData", {}).get("PlayCount", 0)
            genres = jellyfin_data.get("Genres", [])
            duration_ticks = jellyfin_data.get("RunTimeTicks", 0)
        if not in_jellyfin:
            search_query = f"{suggestion['title']} {suggestion['artist']}"
            try:
                _, youtube_url = await get_youtube_url_single(search_query)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("YTDLP lookup failed for %s: %s", search_query, exc)
        parsed = {
            "title": suggestion["title"],
            "artist": suggestion["artist"],
            "jellyfin_play_count": play_count,
            "Genres": genres,
            "RunTimeTicks": duration_ticks,
        }
        enriched = await enrich_track(parsed)
        return {
            "text": text,
            "reason": reason,
            "title": suggestion["title"],
            "artist": suggestion["artist"],
            "youtube_url": youtube_url,
            "in_jellyfin": in_jellyfin,
            **enriched.dict(),
        }

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Skipping suggestion: %s", exc)
        return None


async def enrich_and_score_suggestions(suggestions_raw: list[dict]) -> list[dict]:
    """Enrich suggestions with metadata and compute popularity score."""
    parsed_raw = await asyncio.gather(*[enrich_suggestion(s) for s in suggestions_raw])
    suggestions = [s for s in parsed_raw if s is not None]

    suggestions.sort(key=lambda s: not s["in_jellyfin"])

    add_combined_popularity(suggestions, w_lfm=0.3, w_jf=0.7)
    for track in suggestions:
        raw_lfm = track.get("popularity")
        raw_jf = track.get("jellyfin_play_count")
        logger.info(
            "%s - %s | Combined: %.1f | Last.fm: %s, Jellyfin: %s",
            track["title"],
            track["artist"],
            track["combined_popularity"],
            raw_lfm,
            raw_jf,
        )

    return suggestions
