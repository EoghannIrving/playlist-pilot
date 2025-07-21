"""
metube.py

Handles YouTube fallback logic using yt-dlp for audio tracks not found in Jellyfin.
Includes duration filtering and VEVO prioritization.
"""

import asyncio
import logging
from urllib.parse import quote_plus

import yt_dlp
from utils.text_utils import build_search_query, clean
from utils.cache_manager import yt_search_cache, CACHE_TTLS
from config import settings

logger = logging.getLogger("playlist-pilot")


def _yt_search_sync(search_term: str) -> dict:
    """Perform a synchronous YouTube search using yt-dlp."""
    with yt_dlp.YoutubeDL(
        {
            "quiet": True,
            "noplaylist": True,
            "extract_flat": False,
            "no_warnings": True,
        }
    ) as ydl:
        return ydl.extract_info(f"ytsearch2:{search_term}", download=False)


async def get_youtube_url_single(search_line: str) -> tuple[str, str | None]:
    """
    Given a search line, return a YouTube URL matching the query (or fallback search URL).

    Args:
        search_line (str): Track info to be searched

    Returns:
        tuple: (original search line, YouTube URL or None)
    """
    search_term = build_search_query(search_line)
    cached_url = yt_search_cache.get(search_term)

    if cached_url is not None:
        logger.info("YTDLP cache hit for: %s", search_term)
        return search_line, cached_url

    logger.info("YTDLP cache miss for: %s", search_term)

    try:
        result = await asyncio.to_thread(_yt_search_sync, search_term)
        entries = result.get("entries", [])

        if not entries:
            url = f"https://www.youtube.com/results?search_query={quote_plus(search_term)}"
            yt_search_cache.set(search_term, url, expire=CACHE_TTLS["youtube"])
            return search_line, url

        ref = clean(search_term)
        filtered_entries = [
            e
            for e in entries
            if settings.youtube_min_duration
            <= e.get("duration", 0)
            <= settings.youtube_max_duration
        ]

        best_match = None
        for entry in filtered_entries:
            title = clean(entry.get("title", ""))
            uploader = clean(entry.get("uploader", ""))
            if ref in title or all(word in title for word in ref.split()):
                if "vevo" in uploader or any(w in uploader for w in ref.split()):
                    yt_search_cache.set(
                        search_term,
                        entry["webpage_url"],
                        expire=CACHE_TTLS["youtube"],
                    )
                    logger.debug("Returning match URL: %s", entry["webpage_url"])
                    return search_line, entry["webpage_url"]
                if not best_match:
                    best_match = entry

        if best_match:
            yt_search_cache.set(
                search_term,
                best_match["webpage_url"],
                expire=CACHE_TTLS["youtube"],
            )
            logger.debug("Returning best match URL: %s", best_match["webpage_url"])
            return search_line, best_match["webpage_url"]

        url = f"https://www.youtube.com/results?search_query={quote_plus(search_term)}"
        yt_search_cache.set(search_term, url, expire=CACHE_TTLS["youtube"])
        logger.debug("Returning fallback search URL: %s", url)
        return search_line, url

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Error getting YouTube URL for %s: %s", search_line, exc)
        return search_line, None
