"""MusicBrainz integration for identity matching and original release dates."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from config import settings
from utils.cache_manager import musicbrainz_cache, CACHE_TTLS
from utils.http_client import get_http_client

logger = logging.getLogger("playlist-pilot")

_NON_ORIGINAL_MARKERS = {
    "live",
    "karaoke",
    "tribute",
    "instrumental",
    "demo",
    "acoustic",
    "remaster",
    "remastered",
    "radio edit",
    "single version",
    "video version",
}
_COMPILATION_MARKERS = {
    "greatest hits",
    "best of",
    "ultimate collection",
    "anthology",
    "essentials",
    "singles collection",
    "gold",
}
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _normalize_basic(text: str | None) -> str:
    if not text:
        return ""
    text = text.casefold()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^]]*\]", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"\b(feat|featuring|with)\b.*$", " ", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return " ".join(text.split())


def _normalized_title(text: str | None) -> str:
    normalized = _normalize_basic(text)
    for marker in sorted(_NON_ORIGINAL_MARKERS, key=len, reverse=True):
        normalized = normalized.replace(marker, " ")
    return " ".join(normalized.split())


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = _YEAR_RE.search(str(value))
    if not match:
        return None
    return int(match.group(0))


def _looks_like_compilation(album: str | None) -> bool:
    normalized = _normalize_basic(album)
    return any(marker in normalized for marker in _COMPILATION_MARKERS)


def _variant_penalty(text: str | None) -> float:
    normalized = _normalize_basic(text)
    penalty = 0.0
    for marker in _NON_ORIGINAL_MARKERS:
        if marker in normalized:
            penalty += 1.5
    return penalty


def _artist_names(recording: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for credit in recording.get("artist-credit", []):
        if isinstance(credit, dict):
            name = str(credit.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _score_candidate(
    recording: dict[str, Any],
    title: str,
    artist: str,
    album: str = "",
    year: str = "",
) -> float:
    score = 0.0
    target_title = _normalized_title(title)
    target_artist = _normalize_basic(artist)
    recording_title = _normalized_title(str(recording.get("title", "")))
    recording_artist_names = [
        _normalize_basic(name) for name in _artist_names(recording)
    ]

    if recording_title == target_title:
        score += 8.0
    elif target_title and target_title in recording_title:
        score += 5.5
    elif recording_title and recording_title in target_title:
        score += 4.5

    if any(name == target_artist for name in recording_artist_names):
        score += 7.0
    elif any(
        target_artist in name or name in target_artist
        for name in recording_artist_names
    ):
        score += 4.0

    release_group = recording.get("release-group") or {}
    primary_type = _normalize_basic(str(release_group.get("primary-type", "")))
    if primary_type == "album":
        score += 1.0
    elif primary_type == "single":
        score += 0.8
    elif primary_type == "compilation":
        score -= 2.0

    first_release_year = _extract_year(
        str(
            recording.get("first-release-date")
            or release_group.get("first-release-date")
            or ""
        )
    )
    target_year = _extract_year(year)
    if first_release_year and target_year:
        diff = abs(first_release_year - target_year)
        if diff == 0:
            score += 1.5
        elif diff <= 2:
            score += 1.0
        elif diff <= 5:
            score += 0.3
        else:
            score -= 0.8

    if album:
        normalized_album = _normalize_basic(album)
        for release in recording.get("releases", []) or []:
            release_title = _normalize_basic(str(release.get("title", "")))
            if release_title == normalized_album:
                score += 1.0 if not _looks_like_compilation(album) else -0.5
                break

    score -= _variant_penalty(str(recording.get("title", "")))
    for release in recording.get("releases", []) or []:
        score -= min(_variant_penalty(str(release.get("title", ""))), 1.0)
    return score


def _collect_genre_tags(match: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for genre in match.get("genres", []) or []:
        name = str(genre.get("name", "")).strip()
        if name:
            tags.append(name)
    for tag in match.get("tags", []) or []:
        name = str(tag.get("name", "")).strip()
        if name:
            tags.append(name)
    return list(dict.fromkeys(tags))


async def search_recording_candidates(
    title: str, artist: str, limit: int = 8
) -> list[dict[str, Any]]:
    """Search MusicBrainz for recording candidates."""
    if not settings.musicbrainz_enabled:
        return []

    cache_key = f"search:{title}|{artist}|{limit}"
    cached = musicbrainz_cache.get(cache_key)
    if cached is not None:
        return cached

    query = f'recording:"{title}" AND artist:"{artist}"'
    try:
        client = get_http_client(short=True)
        response = await client.get(
            "https://musicbrainz.org/ws/2/recording",
            params={"query": query, "fmt": "json", "limit": limit},
            headers={"User-Agent": "PlaylistPilot/1.0 (metadata-enrichment)"},
        )
        response.raise_for_status()
        results = response.json().get("recordings", []) or []
        musicbrainz_cache.set(cache_key, results, expire=CACHE_TTLS["musicbrainz"])
        return results
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("MusicBrainz search failed for %s - %s: %s", title, artist, exc)
        return []


async def _lookup_recording_details(recording_id: str) -> dict[str, Any] | None:
    cache_key = f"recording:{recording_id}"
    cached = musicbrainz_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        client = get_http_client(short=True)
        response = await client.get(
            f"https://musicbrainz.org/ws/2/recording/{recording_id}",
            params={
                "inc": "genres+tags+releases+release-groups+artist-credits",
                "fmt": "json",
            },
            headers={"User-Agent": "PlaylistPilot/1.0 (metadata-enrichment)"},
        )
        response.raise_for_status()
        data = response.json()
        musicbrainz_cache.set(cache_key, data, expire=CACHE_TTLS["musicbrainz"])
        return data
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "MusicBrainz recording lookup failed for %s: %s", recording_id, exc
        )
        return None


async def match_recording(
    title: str, artist: str, album: str = "", year: str = ""
) -> dict[str, Any] | None:
    """Return the best MusicBrainz recording match for a track."""
    candidates = await search_recording_candidates(title, artist)
    if not candidates:
        return None

    scored = sorted(
        (
            (_score_candidate(candidate, title, artist, album, year), candidate)
            for candidate in candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score, best = scored[0]
    if best_score < 9.0:
        return None

    details = await _lookup_recording_details(str(best.get("id", "")).strip())
    match = details or best
    release_group = match.get("release-group") or {}
    original_year = _extract_year(
        str(
            match.get("first-release-date")
            or release_group.get("first-release-date")
            or ""
        )
    )
    return {
        "recording_id": match.get("id"),
        "release_group_id": release_group.get("id"),
        "matched_title": match.get("title"),
        "matched_artist": _artist_names(match)[0] if _artist_names(match) else artist,
        "original_year": str(original_year) if original_year else "",
        "genre_tags": _collect_genre_tags(match),
        "score": round(best_score, 2),
    }


async def get_earliest_release_year(match: dict[str, Any] | None) -> str:
    """Return the earliest credible release year for a matched MusicBrainz recording."""
    if not match:
        return ""
    return str(match.get("original_year") or "").strip()
