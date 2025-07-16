import cloudscraper
from urllib.parse import quote_plus
import logging
from typing import Optional, Dict
from utils.cache_manager import bpm_cache, CACHE_TTLS

logger = logging.getLogger("playlist-pilot")

def get_bpm_from_getsongbpm(artist: str, title: str, api_key: str) -> Optional[Dict[str, Optional[int]]]:
    """Query GetSongBPM for tempo and related metadata."""
    lookup = quote_plus(f"song:{title} artist:{artist}")
    search_url = f"https://api.getsongbpm.com/search/?api_key={api_key}&type=both&lookup={lookup}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://getsongbpm.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest"
    }

    scraper = cloudscraper.create_scraper(browser='chrome')

    try:
        resp = scraper.get(search_url, headers=headers, timeout=5)
        data = resp.json()
    except Exception as e:
        logger.info(f"GetSongBPM API error: {e}")
        return None

    songs = data.get("search", [])
    if not songs:
        logger.warning("No song found in GetSongBPM response!")
        return None

    song = songs[0]
    duration_str = song.get("duration")
    duration_sec = None
    if duration_str and isinstance(duration_str, str) and ":" in duration_str:
        try:
            minutes, seconds = map(int, duration_str.strip().split(":"))
            duration_sec = minutes * 60 + seconds
        except Exception as e:
            logger.warning(f"Could not parse duration '{duration_str}': {e}")

    return {
        "bpm": int(song["tempo"]) if song.get("tempo") else None,
        "key": song.get("key_of"),
        "danceability": int(song["danceability"]) if song.get("danceability") else None,
        "acousticness": int(song["acousticness"]) if song.get("acousticness") else None,
        "year": int(song["album"]["year"]) if song.get("album", {}).get("year") else None,
        "duration": duration_sec
    }

def get_cached_bpm(artist: str, title: str, api_key: str) -> Optional[Dict[str, Optional[int]]]:
    """Return BPM data using cache to minimize external requests."""
    key = f"{title.strip().lower()}::{artist.strip().lower()}"
    if key in bpm_cache:
        logger.info(f"Cache hit for {key}")
        return bpm_cache[key]

    logger.info(f"Cache miss for {key} — calling GetSongBPM API")
    bpm_data = get_bpm_from_getsongbpm(artist, title, api_key)
    if bpm_data:
        bpm_cache.set(key, bpm_data, expire=CACHE_TTLS["bpm"])

    return bpm_data
