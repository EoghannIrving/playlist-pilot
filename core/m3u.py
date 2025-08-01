"""
m3u.py

Generates .m3u playlist files in a temporary directory using unique filenames.
"""

import logging
import os
import re
import tempfile
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
import ntpath

from config import settings
from services.jellyfin import (
    resolve_jellyfin_path,
    fetch_jellyfin_track_metadata,
)
from core.history import save_user_history
from core.playlist import enrich_track

logger = logging.getLogger("playlist-pilot")


def cleanup_temp_file(path: Path):
    """Delete a temporary file if it exists."""
    try:
        path.unlink(missing_ok=True)
        logger.debug("Deleted temporary file: %s", path)
    except OSError as exc:
        logger.warning("Failed to delete temp file %s: %s", path, exc)


INVALID_CHARS_RE = re.compile(r"[\\/:*?\"<>|]")


def _parse_title_artist(text: str) -> tuple[str, str]:
    """Return the title and artist from a suggestion line."""
    parts = [p.strip() for p in text.split(" - ")]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", ""


def _sanitize_component(value: str, fallback: str) -> str:
    """Return a filename-safe path component."""
    if not value:
        return fallback
    base = os.path.basename(value.strip())
    sanitized = INVALID_CHARS_RE.sub("_", base)
    return sanitized or fallback


def generate_proposed_path(artist: str, album: str, title: str) -> str:
    """Return a sanitized path suggestion for a track."""
    artist_dir = _sanitize_component(artist, "Unknown Artist")
    album_dir = _sanitize_component(album, "Unknown Album")
    title_file = _sanitize_component(title, "Unknown Title")
    return (
        Path(settings.music_library_root) / artist_dir / album_dir / f"{title_file}.mp3"
    ).as_posix()


def parse_track_text(text: str) -> tuple[str, str]:
    """Split a track label into artist and title parts."""
    parts = text.split(" - ", 1)
    if len(parts) >= 2:
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        artist, title = "Unknown", text.strip()
    return artist, title


def write_m3u(tracks: list[str]) -> Path:
    """
    Write a list of track labels to an .m3u playlist file.

    Args:
        tracks (list[str]): List of track strings to include in the file.

    Returns:
        Path: Path to the generated .m3u file
    """
    p = Path(tempfile.gettempdir()) / f"suggest_{uuid.uuid4().hex}.m3u"
    p.write_text("#EXTM3U\n" + "\n".join(tracks), encoding="utf-8")
    return p


def persist_history_and_m3u(suggestions: list[dict], playlist_name: str) -> Path:
    """Save generated playlist suggestions to history and disk."""
    playlist_clean = playlist_name.strip('"').strip("'")
    label = f"{playlist_clean} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    user_id = settings.jellyfin_user_id
    save_user_history(user_id, label, suggestions)
    return write_m3u([s["text"] for s in suggestions])


async def export_history_entry_as_m3u(entry, jellyfin_url, jellyfin_api_key):
    """Export a history entry's tracks into an M3U playlist."""
    lines = ["#EXTM3U"]

    for track in entry.get("suggestions", []):
        title = track.get("title")
        artist = track.get("artist")
        if not title or not artist:
            title, artist = _parse_title_artist(track.get("text", ""))
        album = track.get("album", "Unknown_Album")  # If `album` present in `track`
        if track.get("in_jellyfin"):
            path = await resolve_jellyfin_path(
                title, artist, jellyfin_url, jellyfin_api_key
            )
            if path:
                lines.append(path)
            else:
                proposed_path = generate_proposed_path(artist, album, title)
                lines.append(f"# Missing Jellyfin path: {proposed_path}")
        else:
            proposed_path = generate_proposed_path(artist, album, title)
            lines.append(f"# Suggested (not in library): {proposed_path}")

    m3u_path = Path(tempfile.gettempdir()) / f"suggest_{uuid.uuid4().hex}.m3u"
    m3u_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info(
        "Wrote hybrid M3U playlist with %d entries: %s",
        len(lines) - 1,
        m3u_path,
    )
    return m3u_path


def read_m3u(file_path: Path) -> list[dict]:
    """
    Parse an .m3u file into a list of track dicts with title and artist fields.

    Args:
        file_path (Path): Path to the .m3u file

    Returns:
        list[dict]: List of track dictionaries
    """
    logger.debug("Reading M3U file: %s", file_path)
    tracks = []

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        logger.debug("UTF-8 decode failed for %s, trying Latin-1", file_path)
        lines = file_path.read_text(encoding="latin-1").splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        artist, title = parse_track_text(line)
        tracks.append({"artist": artist, "title": title})

    logger.info("Parsed %d tracks from %s", len(tracks), file_path)
    return tracks


def infer_track_metadata_from_path(path: str) -> dict:
    """Infer basic metadata from a file path."""
    parts = path.replace("\\", "/").split("/")
    filename = parts[-1].rsplit(".", 1)[0]
    clean_title = re.sub(r"^\d+\s*[-_.]\s*", "", filename).strip()
    if " - " in clean_title:
        artist, title = parse_track_text(clean_title)
    else:
        title = clean_title
        artist = parts[-3] if len(parts) >= 3 else "Unknown Artist"
    return {"title": title, "artist": artist}


async def import_m3u_as_history_entry(filepath: str):
    """Import tracks from an M3U file into user history."""
    # pylint: disable=too-many-locals
    logger.info("📂 Importing M3U playlist: %s", filepath)
    user_id = settings.jellyfin_user_id
    imported_tracks = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = [
            line.strip() for line in f if line.strip() and not line.startswith("#")
        ]

    metas = [(path, infer_track_metadata_from_path(path)) for path in lines]
    tasks = [
        asyncio.create_task(
            fetch_jellyfin_track_metadata(meta["title"], meta["artist"])
        )
        for _, meta in metas
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for (path, meta), metadata in zip(metas, results):
        title = meta["title"]
        artist = meta["artist"]
        if isinstance(metadata, Exception):
            logger.warning(
                "Metadata fetch failed for %s - %s: %s", title, artist, metadata
            )
            metadata = None
        if metadata:
            enriched_obj = await enrich_track({"title": title, "artist": artist})
            enriched = (
                enriched_obj.dict()
                if enriched_obj
                else {"title": title, "artist": artist}
            )
            enriched.setdefault("text", f"{title} - {artist}")
            enriched.setdefault("reason", "Imported from M3U file.")
            enriched.setdefault(
                "youtube_url",
                f"https://www.youtube.com/results?search_query={title}+{artist}",
            )
            enriched.setdefault("in_jellyfin", True)
            enriched.setdefault("jellyfin_play_count", 0)
            enriched.setdefault("Genres", [])
            enriched.setdefault("RunTimeTicks", 0)
            enriched.setdefault("tags", [])
            enriched.setdefault("genre", "Unknown")
            enriched.setdefault("mood", "Unknown")
            enriched.setdefault("mood_confidence", 0.0)
            enriched.setdefault("tempo", 0)
            enriched.setdefault("decade", "Unknown")
            enriched.setdefault("duration", 0)
            enriched.setdefault("popularity", 0)
            enriched.setdefault("year_flag", "")
            enriched.setdefault("combined_popularity", 0)
            enriched["path"] = path
            if isinstance(metadata, dict) and "Id" in metadata:
                enriched["jellyfin_id"] = metadata["Id"]
                # Ensure 'text' field is present for History UI compatibility
            enriched["text"] = f"{title} - {artist}"
            imported_tracks.append(enriched)
        else:
            logger.warning(
                "Skipping track not found in Jellyfin: %s by %s",
                title,
                artist,
            )
    if imported_tracks:
        playlist_name = f"Imported - {ntpath.basename(filepath)}"
        save_user_history(user_id, label=playlist_name, suggestions=imported_tracks)
        logger.info(
            "✅ Imported playlist '%s' with %d tracks.",
            playlist_name,
            len(imported_tracks),
        )
    else:
        logger.warning("No valid tracks found to import.")
