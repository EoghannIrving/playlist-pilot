"""
gpt.py

Handles GPT prompt generation, caching, and result validation for playlist suggestions.
"""

import hashlib
import logging
import openai
import requests
import asyncio
from config import settings
from utils.cache_manager import prompt_cache, CACHE_TTLS
from services.lastfm import get_lastfm_track_info
from openai import OpenAI
from typing import Tuple
import os
import json

logger = logging.getLogger("playlist-pilot")
openai_client = openai.OpenAI(api_key=settings.openai_api_key)

def describe_popularity(score: float) -> str:
    if score >= 90:
        return "Global smash hit"
    elif score >= 70:
        return "Mainstream favorite"
    elif score >= 50:
        return "Moderately mainstream"
    elif score >= 30:
        return "Niche appeal"
    else:
        return "Obscure or local"


def _build_gpt_prompt(existing_tracks: list[str], count: int, summary: dict | None = None) -> str:
    """
    Constructs a tailored GPT prompt based a user selected playlist.

    Args:
        existing_tracks (list[str]): Source tracks (playlist or library).
        count (int): Number of suggestions requested.

    Returns:
        str: The GPT prompt text.
    """
    base = "\n".join(existing_tracks)
    if summary:
        if isinstance(summary, str):
            summary_block = summary
        else:
            pop_score = summary.get("avg_popularity", 0)
            pop_desc = describe_popularity(pop_score)

            summary_block = f"""The following is a summary of the playlist:
            - Dominant Genre: {summary['dominant_genre']}
            - Moods: {", ".join(summary['mood_profile'].keys())}
            - Avg BPM: {int(summary['tempo_avg'])}
            - Popularity: ~{pop_desc} (score: {int(pop_score)})
            - Decades: {", ".join(summary['decades'].keys())}
            """
    else:
        summary_block=""

    intro = (
        f"The user has provided a playlist which has the following characteristics:\n{summary_block}\n\n"
        f"Reference Playlist:\n{base}\n\n"
        f"Suggest exactly {count} additional **real and relevant** songs that would strongly appeal to someone who enjoys this playlist."
        + ( "\n\nStrict constraints:\n"
            "- Songs must be real, commercially released tracks.\n"
            "- All songs must be available on both YouTube and Spotify.\n"
            "- Do NOT include any songs already listed in the provided playlist.\n"
            "- Do NOT invent or fabricate song titles, artists, or albums.\n"
            "- Only include songs that are publicly verifiable and recognizable.\n"
            "- Avoid remixes, covers, live-only performances, or obscure/independent tracks unless they had commercial release.\n\n"
            "Formatting rules:\n"
            "- Return each song on a single line.\n"
            "- Use the **exact** format:\n"
            "  Song - Artist - Album - Year - Reason\n"
            "- Do NOT include:\n"
            "  • Numbering\n"
            "  • Bullet points\n"
            "  • Extra commentary\n"
            "  • Fake, unreleased, or AI-generated music\n"
        )
    )

    logger.debug(f"GPT Prompt: {intro}")
    return intro

def prompt_fingerprint(prompt: str) -> str:
    """Generate SHA256 fingerprint of the prompt."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

def cached_chat_completion(prompt: str, temperature: float = settings.gpt_temperature) -> str:
    """
    Get a GPT completion from cache or OpenAI, allowing temperature override.

    Args:
        prompt (str): The user/system prompt.
        temperature (float): Temperature for GPT completion (default from settings).

    Returns:
        str: GPT's raw response content.
    """
    key = prompt_fingerprint(f"{prompt}|temperature={temperature}")  # Ensure cache keys differentiate by temperature
    content = prompt_cache.get(key)
    if content is not None:
        logger.info(f"GPT cache hit: {key}")
        return content

    logger.info(f"GPT cache miss: {key}")
    response = openai_client.chat.completions.create(
        model=settings.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    content = response.choices[0].message.content.strip()
    prompt_cache.set(key, content, expire=CACHE_TTLS["prompt"])
    logger.debug(f"GPT API original text: {content}")
    return content


def parse_gpt_line(line: str) -> tuple[str, str]:
    """
    Parse a GPT suggestion line into (title, artist).

    Args:
        line (str): Formatted as "Song - Artist - Album - Year - Reason".

    Returns:
        tuple[str, str]: title, artist
    """
    parts = [p.strip() for p in line.split(" - ")]
    return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")

async def gpt_suggest_validated(existing_tracks: list[str], count: int, summary: dict | None = None, exclude_pairs: set[tuple[str, str]] = None) -> list[dict]:

    """
    Main interface to request playlist suggestions from GPT.

    Args:
        existing_tracks (list[str]): Seed data from user.
        count (int): Number of suggestions to return.

    Returns:
        list[dict]: Validated GPT suggestions (title, artist, text, popularity)
    """
    prompt = _build_gpt_prompt(existing_tracks, count * 3, summary)
    logger.debug(f"Sending GPT prompt:\n{prompt[:500]}...")
    result = cached_chat_completion(prompt)
    response_content = result.strip()

    raw_lines = response_content.splitlines()
    logger.info(f"📦 GPT returned {len(raw_lines)} lines before validation")

    suggestions_raw = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            title, artist = parse_gpt_line(line)
            suggestions_raw.append({
                "title": title,
                "artist": artist,
                "text": line
            })
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse line: '{line}' → {e}")

    async def validate_and_score(track: dict) -> dict | None:
        title = track["title"]
        artist = track["artist"]

        try:
            track_data = get_lastfm_track_info(title, artist)
            if not track_data:
                return None

            track["popularity"] = int(track_data.get("listeners", 0))
            return track

        except Exception as e:
            logger.warning(f"⚠️ Last.fm lookup failed for {title} - {artist}: {e}")
            track["popularity"] = 0
            return track

    validated = await asyncio.gather(*[validate_and_score(t) for t in suggestions_raw])
    suggestions_raw = [track for track in validated if track]
    if exclude_pairs:
        suggestions_raw = [
            track for track in suggestions_raw
            if (track["title"], track["artist"]) not in exclude_pairs
        ]

    logger.info(f"✅ {len(suggestions_raw)} valid suggestions after validation and filtering")
    return suggestions_raw[:count]


def generate_playlist_analysis_summary(summary: dict, tracks: list):
    """
    Returns (gpt_summary, removal_suggestions) using cached GPT response if available.
    """

    # Create a cache key from summary + track metadata
    digest_input = json.dumps({
        "summary": summary,
        "tracks": [
            {
                "title": t["title"],
                "artist": t["artist"],
                "genre": t.get("genre"),
                "mood": t.get("mood"),
                "tempo": t.get("tempo"),
                "decade": t.get("decade")
            } for t in tracks
        ]
    }, sort_keys=True).encode("utf-8")
    cache_key = hashlib.sha256(digest_input).hexdigest()

    # Return from cache if available
    if cache_key in prompt_cache:
        logger.info(f"Prompt Cache Hit in generate_playlist_analysis_summary")
        return prompt_cache[cache_key]["gpt_summary"], prompt_cache[cache_key]["removal_suggestions"]
    else:
        print(f"Prompt Cache Miss generate_playlist_analysis_summary")
    # Build prompt
    track_blob = "\n".join([
        f"{t['title']} by {t['artist']} – genre: {t.get('genre')}, mood: {t.get('mood')}, "
        f"tempo: {t.get('tempo')} BPM, decade: {t.get('decade')}, listeners: {t.get('popularity', 0):,}"
        for t in tracks
    ])

    prompt = f"""
You are an expert music curator analyzing a playlist to guide future additions. In 1–2 sentences, describe what kinds of tracks would complement and extend this playlist, focusing on the overall mood, vibe, and listening experience rather than strictly on genres or decades, but factoring in geoography. Do not suggest specific tracks by name.

Then, suggest up to 4 tracks that feel out of place and could be removed to improve consistency under the heading Suggested Removals. Justify each suggestion briefly. You can suggest less than 4.

Tracks:
{track_blob}
"""

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=settings.gpt_temperature,
    )

    content = response.choices[0].message.content.strip()

    # Split output if needed
    if "Suggested Removals" in content:
        parts = content.split("Suggested Removals", 1)
        gpt_summary = parts[0].strip()
        removal_raw = parts[1].lstrip(": \n")  # Remove colon, spaces, newlines
        result = {
            "gpt_summary": gpt_summary,
            "removal_suggestions": removal_raw.strip()
        }

    elif "1." in content:
        split_idx = content.find("1.")
        gpt_summary = content[:split_idx].strip()
        removal_suggestions = content[split_idx:].strip()
        result = {
            "gpt_summary": gpt_summary,
            "removal_suggestions": removal_suggestions
        }

    else:
        result = {
            "gpt_summary": content.strip(),
            "removal_suggestions": ""
        }
    prompt_cache.set(cache_key, result)
    return result["gpt_summary"], result["removal_suggestions"]

def analyze_mood_from_lyrics(lyrics: str) -> str:
    if not lyrics:
        return None

    prompt = (
        "You are an expert music analyst.\n\n"
        "Analyze the following song lyrics and classify the overall mood of the song in one word, "
        "such as 'happy', 'sad', 'chill', 'intense', 'romantic', 'dark', 'uplifting', 'nostalgic', 'party'.\n\n"
        "Lyrics:\n"
         "Respond with only the mood label and nothing else.\n\n"
        f"""\n{lyrics}\n"""
    )
    try:
        result = cached_chat_completion(prompt, temperature=settings.lyrics_temperature)  # Lower temperature for consistency
        mood = result.strip().lower()
        print(f"mood: {mood}")
        logger.info(f"GPT lyrics mood analysis result: {mood}")
        return mood
    except Exception as e:
        logger.warning(f"Lyrics mood analysis failed: {e}")
        return None
