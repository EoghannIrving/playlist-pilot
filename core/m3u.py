"""
m3u.py

Generates .m3u playlist files in a temporary directory using unique filenames.
"""

import os
import re
import tempfile
import uuid
from pathlib import Path
import httpx
import logging

from core.constants import *
from services.jellyfin import resolve_jellyfin_path, search_jellyfin_for_track
from core.history import save_user_history, load_user_history
from config import *
from core.playlist import enrich_track

logger = logging.getLogger("playlist-pilot")

def generate_proposed_path(artist, album, title):
    # Simple sanitization for readable path
    artist_dir = artist.strip()
    album_dir = album.strip() if album else "Unknown Album"
    title_file = title.strip()
    return f"Movies/Music/{artist_dir}/{album_dir}/{title_file}.mp3"

def parse_track_text(text):
    parts = text.split(" - ")
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

async def export_history_entry_as_m3u(entry, jellyfin_url, jellyfin_api_key):
    lines = ["#EXTM3U"]

    for track in entry.get("suggestions", []):
        title, artist = parse_track_text(track["text"])
        album = track.get("album", "Unknown_Album")  # If `album` present in `track`
        if track.get("in_jellyfin"):
            path = await resolve_jellyfin_path(title, artist, jellyfin_url, jellyfin_api_key)
            if path:
                lines.append(path)
            else:
                proposed_path = generate_proposed_path(artist, album, title)
                lines.append(f"# Missing Jellyfin path: {proposed_path}")
        else:
            proposed_path = generate_proposed_path(artist, album, title)
            lines.append(f"# Suggested (not in library): {proposed_path}")

    m3u_path = Path(tempfile.gettempdir()) / f"suggest_{uuid.uuid4().hex}.m3u"
    m3u_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    logger.info(f"Wrote hybrid M3U playlist with {len(lines)-1} entries: {m3u_path}")
    return m3u_path

def read_m3u(file_path: Path) -> list[dict]:
    """
    Parse an .m3u file into a list of track dicts with title and artist fields.

    Args:
        file_path (Path): Path to the .m3u file

    Returns:
        list[dict]: List of track dictionaries
    """
    tracks = []
    
    lines = file_path.read_text(encoding='utf-8').splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        artist, title = parse_track_text(line)
        tracks.append({
            "artist": artist,
            "title": title
        })

    return tracks

def infer_track_metadata_from_path(path):
    parts = path.replace("\\", "/").split("/")
    filename = parts[-1].rsplit(".", 1)[0]
    clean_title = re.sub(r"^\d+\s*[-_.]\s*", "", filename).strip()
    if " - " in clean_title:
        segments = clean_title.split(" - ")
        if len(segments) >= 2:
            artist = segments[-2].strip()
            title = segments[-1].strip()
        else:
            title = segments[-1].strip()
            artist = parts[-3] if len(parts) >= 3 else "Unknown Artist"
    else:
        title = clean_title
        artist = parts[-3] if len(parts) >= 3 else "Unknown Artist"
    return {"title": title, "artist": artist}


def import_m3u_as_history_entry(filepath: str):
    logger.info(f"📂 Importing M3U playlist: {filepath}")
    user_id=settings.jellyfin_user_id
    imported_tracks = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    for path in lines:
        meta = infer_track_metadata_from_path(path)
        title = meta['title']
        artist = meta['artist']
        result = search_jellyfin_for_track(title, artist)
        if result:
            track_dict = {"title": title, "artist": artist}
            enriched = enrich_track(track_dict) or track_dict   # fallback to base if enrich returns None
            enriched.setdefault('text', f"{title} - {artist}")
            enriched.setdefault('reason', "Imported from M3U file.")
            enriched.setdefault('youtube_url', f"https://www.youtube.com/results?search_query={title}+{artist}")
            enriched.setdefault('in_jellyfin', True)
            enriched.setdefault('jellyfin_play_count', 0)
            enriched.setdefault('Genres', [])
            enriched.setdefault('RunTimeTicks', 0)
            enriched.setdefault('tags', [])
            enriched.setdefault('genre', "Unknown")
            enriched.setdefault('mood', "Unknown")
            enriched.setdefault('mood_confidence', 0.0)
            enriched.setdefault('tempo', 0)
            enriched.setdefault('decade', "Unknown")
            enriched.setdefault('duration', 0)
            enriched.setdefault('popularity', 0)
            enriched.setdefault('year_flag', "")
            enriched.setdefault('combined_popularity', 0)
            enriched['path'] = path
            if isinstance(result, dict) and 'Id' in result:
                enriched['jellyfin_id'] = result['Id']
                # Ensure 'text' field is present for History UI compatibility
            enriched['text'] = f"{title} - {artist}"
            imported_tracks.append(enriched)
        else:
            logger.warning(f"Skipping track not found in Jellyfin: {title} by {artist}")
    if imported_tracks:
        playlist_name = f"Imported - {filepath.split('/')[-1]}"
        save_user_history(user_id,label=playlist_name, suggestions=imported_tracks)
        logger.info(f"✅ Imported playlist '{playlist_name}' with {len(imported_tracks)} tracks.")
    else:
        logger.warning("No valid tracks found to import.")
