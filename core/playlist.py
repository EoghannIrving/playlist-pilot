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
from typing import Any, Coroutine, cast

from config import settings, get_global_min_lfm, get_global_max_lfm
from core.analysis import (
    mood_scores_from_bpm_data,
    mood_scores_from_lastfm_tags,
    mood_scores_from_context,
    combine_mood_scores,
    normalize_popularity,
    combined_popularity_score,
    normalize_popularity_log,
    build_lyrics_scores,
    add_combined_popularity,
)
from core.models import Track, EnrichedTrack
from services.getsongbpm import get_cached_bpm
from services.gpt import analyze_mood_from_lyrics, analyze_mood_from_track_context
from services.jellyfin import jf_get, read_lrc_for_track, strip_lrc_timecodes
from services.media_factory import get_media_server
from services.metube import get_youtube_url_single
from services.lastfm import enrich_with_lastfm
from services.listenbrainz import get_recording_tags, get_release_group_tags
from services.musicbrainz import match_recording
from services.spotify import fetch_spotify_metadata
from services.applemusic import fetch_applemusic_metadata
from utils.cache_manager import library_cache, CACHE_TTLS
from utils.file_tags import read_track_tags
from utils.http_client import get_http_client
from utils.media_paths import resolve_library_audio_path

logger = logging.getLogger("playlist-pilot")


async def fetch_audio_playlists(user_id: str | None = None) -> dict:
    """Fetch all playlists that contain at least one audio track."""
    if (
        user_id
        and user_id != settings.media_user_id
        and user_id != settings.jellyfin_user_id
    ):
        logger.warning(
            (
                "fetch_audio_playlists received user_id override %s, "
                "but adapter selection currently uses configured backend "
                "context only"
            ),
            user_id,
        )
    playlists = await get_media_server().list_audio_playlists()
    return {
        "playlists": [
            {"name": playlist["name"], "id": playlist["id"]} for playlist in playlists
        ]
    }


async def get_playlist_id_by_name(name: str) -> str | None:
    """Return the ID of a Jellyfin playlist given its name."""
    try:
        resp = await jf_get(
            f"/Users/{settings.jellyfin_user_id}/Items",
            IncludeItemTypes="Playlist",
            Recursive="true",
            SearchTerm=name,
            Limit=20,
        )

        if "error" in resp:
            raise RuntimeError(resp["error"])

        for item in resp.get("Items", []):
            if item.get("Name") == name:
                return item.get("Id")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to get playlist ID for '%s': %s", name, exc)
    return None


async def get_playlist_tracks(playlist_id: str) -> list[str]:
    """Fetch and return track titles from a Jellyfin playlist by ID."""
    try:
        client = get_http_client()
        resp = await client.get(
            f"{settings.jellyfin_url.rstrip('/')}/Users/{settings.jellyfin_user_id}/Items",
            headers={"X-Emby-Token": settings.jellyfin_api_key},
            params={
                "ParentId": playlist_id,
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
            },
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
    # pylint: disable=duplicate-code
    cache_key = f"library:{settings.jellyfin_user_id or settings.media_user_id}"
    if not force_refresh:
        cached = library_cache.get(cache_key)
        if cached is not None:
            return cached

    items: list[str] = []
    start_index = 0
    limit = settings.library_scan_limit
    while True:
        response = await jf_get(
            f"/Users/{settings.jellyfin_user_id or settings.media_user_id}/Items",
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


async def fetch_jellyfin_track_metadata(title: str, artist: str) -> dict | None:
    """Compatibility wrapper for track metadata lookups."""
    return await get_media_server().get_track_metadata(title, artist)


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

    def _coerce_to_str(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            # Try to extract a name-like field
            for key in ("Name", "Artist"):
                candidate = value.get(key)
                if candidate:
                    normalized = _coerce_to_str(candidate)
                    if normalized:
                        return normalized
        if isinstance(value, (list, tuple)):
            for item in value:
                normalized = _coerce_to_str(item)
                if normalized:
                    return normalized
            return ""
        if value is None:
            return ""
        return str(value).strip()

    def _track_identifier(track_dict: dict) -> str:
        for key in ("Name", "PlaylistItemId", "Id"):
            candidate = _coerce_to_str(track_dict.get(key))
            if candidate:
                return candidate
        return "Unknown track"

    def _log_missing_metadata(track_dict: dict, field: str, fallback: str) -> None:
        identifier = _track_identifier(track_dict)
        logger.warning(
            "Track %s missing %s metadata; defaulting to %s",
            identifier,
            field,
            fallback,
        )

    def _resolve_title(track_dict: dict) -> str:
        for key in ("Name", "SortName"):
            candidate = _coerce_to_str(track_dict.get(key))
            if candidate:
                return candidate
        _log_missing_metadata(track_dict, "title", "Unknown Title")
        return "Unknown Title"

    def _resolve_artist(track_dict: dict) -> str:
        for key in (
            "AlbumArtist",
            "Artists",
            "Artist",
            "AlbumArtists",
            "People",
        ):
            candidate = _coerce_to_str(track_dict.get(key))
            if candidate:
                return candidate
        _log_missing_metadata(track_dict, "artist", "Unknown Artist")
        return "Unknown Artist"

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
        tempo_tag = extract_tag_value(raw.get("Tags") or [], "tempo")
        tempo_val = int(tempo_tag) if tempo_tag and tempo_tag.isdigit() else None
        lyrics = raw.get("lyrics")
        return Track(
            raw=raw.get("Name", ""),
            title=_resolve_title(raw),
            artist=_resolve_artist(raw),
            album=raw.get("Album", "").strip(),
            year=extract_year(raw),
            Genres=raw.get("Genres", []),
            lyrics=lyrics,
            tempo=tempo_val,
            RunTimeTicks=raw.get("RunTimeTicks", 0),
            Id=raw.get("Id"),
            PlaylistItemId=raw.get("PlaylistItemId"),
        )

    return Track(raw=str(raw), title="", artist="", album="", year="")


def _ensure_track(parsed: Track | dict) -> Track:
    """Validate and convert a raw track into a :class:`Track`."""
    if isinstance(parsed, dict):
        if "play_count" in parsed and "jellyfin_play_count" not in parsed:
            parsed["jellyfin_play_count"] = parsed["play_count"]
        if "jellyfin_play_count" in parsed and "play_count" not in parsed:
            parsed["play_count"] = parsed["jellyfin_play_count"]
        parsed = Track.model_validate(parsed)
    parsed.play_count = parsed.play_count or parsed.jellyfin_play_count
    parsed.jellyfin_play_count = parsed.jellyfin_play_count or parsed.play_count
    if not parsed.title or not parsed.artist:
        raise ValueError("Missing required track metadata (title/artist)")
    return parsed


async def _get_lastfm_data(title: str, artist: str) -> dict:
    """Retrieve tags, listeners and album information from Last.fm."""
    data = await enrich_with_lastfm(title, artist)
    return {
        "tags": data["tags"],
        "genre_tags": data.get("genre_tags", data["tags"]),
        "listeners": data["listeners"],
        "album": data["album"],
        "releasedate": data.get("releasedate", ""),
    }


def _select_genre(genres: list[str], tags: list[str]) -> str:
    """Choose a genre from Jellyfin metadata or Last.fm tags."""
    genre = filter_valid_genre(genres)
    if not genre or genre.lower() == "unknown":
        genre = filter_valid_genre(tags)
    return genre


async def _get_musicbrainz_data(title: str, artist: str, album: str, year: str) -> dict:
    """Resolve MusicBrainz identity and related genre/year metadata."""
    match = await match_recording(title, artist, album=album, year=year)
    if not match:
        return {
            "recording_id": "",
            "release_group_id": "",
            "original_year": "",
            "genre_tags": [],
            "score": 0.0,
        }
    return match


async def _get_listenbrainz_tags(recording_id: str, release_group_id: str) -> list[str]:
    """Return merged ListenBrainz tags for a matched MusicBrainz identity."""
    recording_task = (
        get_recording_tags(recording_id)
        if recording_id
        else asyncio.sleep(0, result=[])
    )
    release_group_task = (
        get_release_group_tags(release_group_id)
        if release_group_id
        else asyncio.sleep(0, result=[])
    )
    recording_tags, release_group_tags = await asyncio.gather(
        recording_task, release_group_task
    )
    return list(dict.fromkeys([*recording_tags, *release_group_tags]))


def _merge_genre_tags(
    backend_genres: list[str],
    lastfm_tags: list[str],
    musicbrainz_tags: list[str],
    listenbrainz_tags: list[str],
) -> tuple[str, str, list[str]]:
    """Merge genre evidence into a specific display genre and broad family context."""
    weighted_sources = [
        (listenbrainz_tags, 4),
        (musicbrainz_tags, 3),
        (lastfm_tags, 2),
        (backend_genres, 1),
    ]
    scores: dict[str, int] = {}
    merged_context: list[str] = []
    for tags, weight in weighted_sources:
        for tag in tags:
            if not tag:
                continue
            merged_context.append(tag)
            canonical = filter_valid_genre([tag])
            if not canonical:
                normalized = normalize_genre(tag)
                if normalized and normalized.lower() in KNOWN_GENRES:
                    canonical = normalized
            if canonical:
                scores[canonical] = scores.get(canonical, 0) + weight

    if scores:
        selected = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
    else:
        selected = _select_genre(backend_genres, lastfm_tags)
    family = genre_family(selected)
    context_genres = [
        genre
        for genre in dict.fromkeys([selected, family, *backend_genres, *merged_context])
        if genre and str(genre).lower() != "unknown"
    ]
    return selected or "Unknown", family or "Unknown", context_genres


async def _fetch_bpm_data(artist: str, title: str) -> dict:
    """Return cached BPM data from GetSongBPM if configured."""
    if artist and title and settings.getsongbpm_api_key:
        try:
            result = await asyncio.to_thread(
                get_cached_bpm,
                artist=artist,
                title=title,
                api_key=settings.getsongbpm_api_key,
            )
            return result or {}
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("GetSongBPM API failed for %s - %s: %s", artist, title, exc)
    return {}


async def _get_file_tag_year(parsed: Track) -> str:
    """Return the year from the resolved audio file tags when available."""
    file_path = getattr(parsed, "Path", None)
    if not file_path:
        try:
            file_path = await get_media_server().resolve_track_path(
                parsed.title, parsed.artist
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug(
                "Failed to resolve track path for file-tag year on %s - %s: %s",
                parsed.artist,
                parsed.title,
                exc,
            )
            return ""
    if not file_path:
        return ""

    resolved_path = resolve_library_audio_path(str(file_path))
    if not resolved_path:
        return ""

    try:
        tags = await asyncio.to_thread(read_track_tags, str(resolved_path))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.debug(
            "Failed to read file tags for %s - %s from %s: %s",
            parsed.artist,
            parsed.title,
            resolved_path,
            exc,
        )
        return ""

    return extract_year_from_string(str(tags.get("year", "")))


def _determine_year(
    backend_year: str,
    bpm_year: int | None,
    releasedate: str = "",
    file_tag_year: str = "",
    musicbrainz_year: str = "",
) -> tuple[str | None, str]:
    """Determine the final year and flag mismatches between sources."""
    year_flag = ""
    candidates: list[tuple[str, int]] = []
    if file_tag_year:
        try:
            candidates.append(("file_tags", int(file_tag_year)))
        except (ValueError, TypeError):
            logger.warning("Invalid file-tag year data: %s", file_tag_year)
    if musicbrainz_year:
        try:
            candidates.append(("musicbrainz", int(musicbrainz_year)))
        except (ValueError, TypeError):
            logger.warning("Invalid MusicBrainz year data: %s", musicbrainz_year)
    if backend_year:
        try:
            candidates.append(("backend", int(backend_year)))
        except (ValueError, TypeError):
            logger.warning("Invalid backend year data: %s", backend_year)
    if bpm_year:
        candidates.append(("getsongbpm", int(bpm_year)))
    release_year = extract_year_from_string(releasedate)
    if release_year:
        try:
            candidates.append(("lastfm", int(release_year)))
        except (ValueError, TypeError):
            logger.warning("Invalid Last.fm release year data: %s", release_year)
    year_map = dict(candidates)
    if settings.prefer_original_release_year and "musicbrainz" in year_map:
        final_year = str(year_map["musicbrainz"])
    elif "file_tags" in year_map:
        final_year = str(year_map["file_tags"])
    elif "lastfm" in year_map:
        final_year = str(year_map["lastfm"])
    elif "backend" in year_map:
        final_year = str(year_map["backend"])
    elif "getsongbpm" in year_map:
        final_year = str(year_map["getsongbpm"])
    else:
        final_year = None
    try:
        distinct_years = sorted({year for _, year in candidates})
        if len(distinct_years) > 1:
            year_flag = " / ".join(f"{source}: {year}" for source, year in candidates)
    except (ValueError, TypeError):
        logger.warning(
            "Invalid year data: backend=%s, BPM=%s, releasedate=%s",
            backend_year,
            bpm_year,
            releasedate,
        )
    return final_year, year_flag


def _duration_from_ticks(ticks: int, bpm_data: dict) -> int:
    """Convert Jellyfin run-time ticks to seconds, falling back to BPM data."""
    duration = int(ticks / 10_000_000) if ticks else 0
    bpm_duration = bpm_data.get("duration")
    if bpm_duration is not None:
        try:
            return int(bpm_duration)
        except (TypeError, ValueError):
            logger.warning("Invalid BPM duration: %s", bpm_duration)
    return duration


async def _classify_mood(
    parsed: Track,
    tags: list[str],
    bpm_data: dict,
    context_genres: list[str] | None = None,
    context_year: str | int | None = None,
) -> tuple[str, float]:
    """Return mood label and confidence score for a track."""
    logger.debug("Enriching track: %s", parsed.title)
    tag_scores = mood_scores_from_lastfm_tags(tags)
    bpm_scores = mood_scores_from_bpm_data(bpm_data or {})
    context_scores = mood_scores_from_context(
        context_genres,
        context_year,
        bpm_data.get("bpm"),
    )
    lyrics_scores = None
    lyrics = None
    if settings.lyrics_enabled:
        lyrics = await resolve_lyrics_for_enrich(parsed)
        lyrics_mood = (
            await asyncio.to_thread(analyze_mood_from_lyrics, lyrics)
            if lyrics
            else None
        )
        logger.debug(
            "Lyrics mood input for %s - %s: lyrics_present=%s raw_mood=%s",
            parsed.artist,
            parsed.title,
            bool(lyrics),
            lyrics_mood,
        )
        lyrics_scores = build_lyrics_scores(lyrics_mood) if lyrics_mood else None
    mood_result = combine_mood_scores(
        tag_scores, bpm_scores, lyrics_scores, context_scores
    )
    if mood_result[0] == "unknown" and (
        lyrics or any(value > 0 for value in context_scores.values())
    ):
        fallback_mood = await asyncio.to_thread(
            analyze_mood_from_track_context,
            parsed.title,
            parsed.artist,
            context_genres or [],
            context_year,
            lyrics,
        )
        fallback_scores = build_lyrics_scores(fallback_mood) if fallback_mood else None
        if fallback_scores:
            mood_result = combine_mood_scores(
                tag_scores,
                bpm_scores,
                fallback_scores,
                context_scores,
            )
            if mood_result[0] == "unknown":
                mapped = next(
                    (mood for mood, score in fallback_scores.items() if score > 0),
                    "unknown",
                )
                if mapped != "unknown":
                    mood_result = (mapped, 0.45 if lyrics else 0.35)
            logger.info(
                "Mood fallback for %s - %s: raw=%s final=%s confidence=%.2f",
                parsed.artist,
                parsed.title,
                fallback_mood,
                mood_result[0],
                mood_result[1],
            )
    logger.info(
        (
            "Mood diagnostics for %s - %s: "
            "tags=%s bpm=%s lyrics=%s context=%s final=%s confidence=%.2f"
        ),
        parsed.artist,
        parsed.title,
        {k: round(v, 2) for k, v in tag_scores.items() if v},
        {k: round(v, 2) for k, v in bpm_scores.items() if v},
        {k: round(v, 2) for k, v in (lyrics_scores or {}).items() if v},
        {k: round(v, 2) for k, v in context_scores.items() if v},
        mood_result[0],
        mood_result[1],
    )
    return mood_result


async def enrich_track(parsed: Track | dict) -> EnrichedTrack:
    """Enrich a track with Last.fm, BPM, mood and other metadata."""
    parsed = _ensure_track(parsed)

    need_meta = not parsed.album or not parsed.year or not parsed.RunTimeTicks
    tasks: list[Coroutine[Any, Any, dict[str, Any]]] = [
        _get_lastfm_data(parsed.title, parsed.artist),
        _fetch_bpm_data(parsed.artist, parsed.title),
    ]
    if need_meta and settings.spotify_client_id and settings.spotify_client_secret:
        tasks.append(
            cast(
                Coroutine[Any, Any, dict[str, Any]],
                fetch_spotify_metadata(parsed.title, parsed.artist),
            )
        )
    else:
        tasks.append(asyncio.sleep(0, result={}))
    if need_meta and settings.apple_client_id and settings.apple_client_secret:
        tasks.append(
            cast(
                Coroutine[Any, Any, dict[str, Any]],
                fetch_applemusic_metadata(parsed.title, parsed.artist),
            )
        )
    else:
        tasks.append(asyncio.sleep(0, result={}))

    file_tag_year_task = _get_file_tag_year(parsed)
    lastfm, bpm_data, spotify_meta, apple_meta, file_tag_year = await asyncio.gather(
        *tasks, file_tag_year_task
    )
    meta = {**(apple_meta or {}), **(spotify_meta or {})}

    if need_meta:
        if not parsed.album:
            parsed.album = meta.get("album", "")
        if not parsed.year:
            parsed.year = meta.get("year", "")
        if not parsed.RunTimeTicks and meta.get("duration_ms"):
            parsed.RunTimeTicks = int(meta["duration_ms"] * 10_000)

    musicbrainz_data = await _get_musicbrainz_data(
        parsed.title,
        parsed.artist,
        parsed.album,
        file_tag_year or parsed.year or "",
    )
    listenbrainz_tags = await _get_listenbrainz_tags(
        str(musicbrainz_data.get("recording_id") or ""),
        str(musicbrainz_data.get("release_group_id") or ""),
    )
    year_info = _determine_year(
        parsed.year or "",
        bpm_data.get("year"),
        lastfm.get("releasedate", ""),
        file_tag_year,
        str(musicbrainz_data.get("original_year") or ""),
    )
    selected_genre, selected_genre_family, context_genres = _merge_genre_tags(
        parsed.Genres or [],
        lastfm.get("genre_tags", lastfm["tags"]),
        list(musicbrainz_data.get("genre_tags") or []),
        listenbrainz_tags,
    )
    mood_data = await _classify_mood(
        parsed,
        lastfm["tags"],
        bpm_data,
        context_genres=context_genres,
        context_year=year_info[0] or parsed.year or bpm_data.get("year"),
    )
    duration_seconds = _duration_from_ticks(parsed.RunTimeTicks, bpm_data)
    tempo = bpm_data.get("bpm") or parsed.tempo
    if tempo is None and duration_seconds:
        tempo = estimate_tempo(duration_seconds, selected_genre)

    return EnrichedTrack(
        **parsed.model_dump(
            exclude={"tempo", "jellyfin_play_count", "play_count", "album"}
        ),
        genre=selected_genre,
        genre_family=selected_genre_family,
        mood=mood_data[0],
        mood_confidence=round(mood_data[1], 2),
        tempo=tempo,
        decade=infer_decade(year_info[0] or ""),
        duration=duration_seconds,
        popularity=lastfm["listeners"],
        play_count=parsed.play_count,
        jellyfin_play_count=parsed.jellyfin_play_count,
        year_flag=year_info[1],
        album=lastfm["album"] or parsed.album,
        FinalYear=year_info[0],
        mb_recording_id=str(musicbrainz_data.get("recording_id") or ""),
        mb_release_group_id=str(musicbrainz_data.get("release_group_id") or ""),
        genre_tags=context_genres,
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
        prod_year = track.get("ProductionYear")
        if prod_year:
            return str(prod_year)
        premiere = track.get("PremiereDate", "")
        return str(premiere)[:4] if premiere else ""
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
    "folk rock": "folk rock",
    "indie folk": "folk",
    "acoustic pop": "folk pop",
    "singer songwriter": "singer-songwriter",
    "singer-songwriter": "singer-songwriter",
    "contemporary folk": "folk",
    "folk pop": "folk pop",
    "folk-pop": "folk pop",
    "folk music": "folk",
    "traditional folk": "folk",
    "traditional scottish folk": "scottish folk",
    "celtic": "celtic folk",
    "celtic folk": "celtic folk",
    "celtic rock": "celtic rock",
    "celtic pop": "celtic pop",
    "scottish folk": "scottish folk",
    "scottish": "scottish folk",
    "gaelic": "celtic folk",
    "sea shanty": "sea shanty",
    "sea shanties": "sea shanty",
    "shanty": "sea shanty",
    "shanties": "sea shanty",
    "maritime": "folk",
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
    "synth-pop": "synthpop",
    "synth pop": "synthpop",
    "electropop": "synthpop",
    "new romantic": "new romantic",
    "sophisti-pop": "sophisti-pop",
    "ambient music": "ambient",
    "music": "",
}

GENRE_FAMILY_OVERRIDES = {
    "folk rock": "folk",
    "folk pop": "folk",
    "scottish folk": "folk",
    "celtic folk": "folk",
    "celtic rock": "folk",
    "celtic pop": "folk",
    "sea shanty": "folk",
    "singer-songwriter": "folk",
    "new romantic": "new wave",
    "sophisti-pop": "pop",
}


def normalize_genre(raw: str | None) -> str:
    """Map genre synonyms to canonical names."""
    if not raw:
        return ""
    cleaned = str(raw).strip().lower()
    return GENRE_SYNONYMS.get(cleaned, cleaned)


def genre_family(raw: str | None) -> str:
    """Map a specific genre to its broader family used for fallback context."""
    normalized = normalize_genre(raw)
    if not normalized:
        return ""
    return GENRE_FAMILY_OVERRIDES.get(normalized, normalized)


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
    "folk rock",
    "folk pop",
    "scottish folk",
    "celtic folk",
    "celtic rock",
    "celtic pop",
    "sea shanty",
    "singer-songwriter",
    "new romantic",
    "sophisti-pop",
}


def filter_valid_genre(tags: list[str]) -> str:
    """Return the first tag that matches a known genre."""
    for tag in tags:
        normalized = normalize_genre(tag).lower()
        if normalized in KNOWN_GENRES:
            return normalize_genre(tag)
        for genre in KNOWN_GENRES:
            if genre in normalized:
                return genre
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
    raw_tracks = await get_media_server().get_playlist_tracks(playlist_id)
    if isinstance(limit, int) and limit > 0:
        raw_tracks = raw_tracks[:limit]

    async def process(track: dict) -> dict | None:
        try:
            norm = normalize_track(track)
            norm.play_count = track.get("UserData", {}).get("PlayCount", 0)
            norm.jellyfin_play_count = norm.play_count
            enriched_data = await enrich_track(norm)
            logger.info(
                "✅ Enriched: %s | Last.fm: %s | Play Count: %s",
                norm.title or "Unknown",
                (
                    enriched_data.popularity
                    if hasattr(enriched_data, "popularity")
                    else "N/A"
                ),
                norm.play_count,
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
        t["play_count"] for t in enriched if isinstance(t.get("play_count"), int)
    ]

    logger.debug(
        "📊 Last.fm popularity range: min=%s, max=%s",
        min(lastfm_raw, default=0),
        max(lastfm_raw, default=0),
    )
    logger.debug(
        "📊 Play count range: min=%s, max=%s",
        min(jellyfin_raw, default=0),
        max(jellyfin_raw, default=0),
    )

    max_jf = max(jellyfin_raw, default=1)

    for t in enriched:
        raw_lfm = t.get("popularity")
        raw_jf = t.get("play_count")
        norm_lfm = normalize_popularity_log(
            raw_lfm, get_global_min_lfm(), get_global_max_lfm()
        )
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
def get_lyrics_for_enrich(track: dict) -> str | None:
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


async def resolve_lyrics_for_enrich(parsed: Track | dict) -> str | None:
    """Resolve lyrics for enrichment from metadata, local sidecars, or backend APIs."""
    parsed = _ensure_track(parsed)
    track = parsed.model_dump()

    lyrics = get_lyrics_for_enrich(track)
    if lyrics:
        logger.debug(
            "Lyrics source for %s - %s: inline metadata",
            parsed.artist,
            parsed.title,
        )
        return lyrics

    track_path = track.get("Path")
    if isinstance(track_path, str) and track_path.strip():
        lrc_contents = read_lrc_for_track(track_path.strip())
        if lrc_contents:
            logger.debug(
                "Lyrics source for %s - %s: local .lrc sidecar",
                parsed.artist,
                parsed.title,
            )
            return strip_lrc_timecodes(lrc_contents).strip()

    item_id = next(
        (
            str(value).strip()
            for value in (
                track.get("Id"),
                track.get("PlaylistItemId"),
                track.get("backend_item_id"),
            )
            if isinstance(value, str) and str(value).strip()
        ),
        "",
    )
    if not item_id:
        return None

    server = get_media_server()
    if not server.supports_lyrics():
        return None

    try:
        backend_lyrics = await server.get_lyrics(item_id)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to resolve backend lyrics for %s - %s (%s): %s",
            parsed.artist,
            parsed.title,
            item_id,
            exc,
        )
        return None

    if isinstance(backend_lyrics, str) and backend_lyrics.strip():
        logger.debug(
            "Lyrics source for %s - %s: backend adapter",
            parsed.artist,
            parsed.title,
        )
        return backend_lyrics.strip()
    logger.debug("Lyrics source for %s - %s: none", parsed.artist, parsed.title)
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
    prefix_lower = prefix.lower()
    for tag in tags or []:
        if tag.lower().startswith(f"{prefix_lower}:"):
            return tag.split(":", 1)[1]
    return None


async def enrich_suggestion(suggestion: dict) -> dict | None:
    """Return enriched data for a single GPT suggestion."""
    # pylint: disable=too-many-locals
    try:
        text, reason = parse_suggestion_line(suggestion["text"])
        title = suggestion["title"]
        artist = suggestion["artist"]
        jellyfin_data = await fetch_jellyfin_track_metadata(title, artist)
        in_library = jellyfin_data is not None
        play_count = 0
        genres = []
        duration_ticks = 0
        youtube_url = None
        if jellyfin_data:
            play_count = jellyfin_data.get("UserData", {}).get("PlayCount", 0)
            genres = jellyfin_data.get("Genres", [])
            duration_ticks = jellyfin_data.get("RunTimeTicks", 0)
        if not in_library:
            search_query = f"{suggestion['title']} {suggestion['artist']}"
            try:
                _, youtube_url = await get_youtube_url_single(search_query)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("YTDLP lookup failed for %s: %s", search_query, exc)
        parsed = {
            "title": suggestion["title"],
            "artist": suggestion["artist"],
            "year": str(suggestion.get("year") or ""),
            "play_count": play_count,
            "jellyfin_play_count": play_count,
            "Id": jellyfin_data.get("Id") if jellyfin_data else None,
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
            "in_library": in_library,
            "in_jellyfin": in_library,
            "server_track_id": (
                suggestion.get("server_track_id")
                or suggestion.get("backend_item_id")
                or (jellyfin_data.get("backend_item_id") if jellyfin_data else None)
                or (jellyfin_data.get("Id") if jellyfin_data else None)
            ),
            "server_backend": (
                suggestion.get("server_backend")
                or (jellyfin_data.get("backend") if jellyfin_data else None)
            ),
            "fit_score": suggestion.get("fit_score"),
            "fit_breakdown": suggestion.get("fit_breakdown"),
            **enriched.model_dump(),
        }

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Skipping suggestion: %s", exc)
        return None


async def enrich_and_score_suggestions(suggestions_raw: list[dict]) -> list[dict]:
    """Enrich suggestions with metadata and compute popularity score."""
    parsed_raw = await asyncio.gather(*[enrich_suggestion(s) for s in suggestions_raw])
    suggestions = [s for s in parsed_raw if s is not None]

    add_combined_popularity(suggestions, w_lfm=0.3, w_jf=0.7)
    suggestions.sort(
        key=lambda s: (
            not s.get("in_library", s.get("in_jellyfin")),
            -(s.get("fit_score") or 0),
            -(s.get("combined_popularity") or 0),
        )
    )
    for track in suggestions:
        raw_lfm = track.get("popularity")
        raw_jf = track.get("play_count", track.get("jellyfin_play_count"))
        combined = track.get("combined_popularity")
        logger.info(
            "%s - %s | Fit: %s | Combined: %s | Last.fm: %s, Play Count: %s",
            track["title"],
            track["artist"],
            (
                f"{track.get('fit_score'):.2f}"
                if isinstance(track.get("fit_score"), (int, float))
                else track.get("fit_score")
            ),
            f"{combined:.1f}" if isinstance(combined, (int, float)) else combined,
            raw_lfm,
            raw_jf,
        )

    return suggestions
