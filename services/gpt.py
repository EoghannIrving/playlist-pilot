"""
gpt.py

Handles GPT prompt generation, caching, and result validation for playlist suggestions.
"""

import hashlib
import logging
import asyncio
import json

import openai
from openai import OpenAI, AsyncOpenAI
from config import settings
from utils.cache_manager import prompt_cache, CACHE_TTLS
from utils.text_utils import strip_markdown
from services.lastfm import get_lastfm_track_info

logger = logging.getLogger("playlist-pilot")


def get_sync_openai_client() -> OpenAI:
    """Return an OpenAI client using the current API key."""
    return OpenAI(api_key=settings.openai_api_key)


def get_async_openai_client() -> AsyncOpenAI:
    """Return an asynchronous OpenAI client using the current API key."""
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def fetch_openai_models(api_key: str) -> list[str]:
    """Return available GPT models for the provided API key."""
    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.models.list()
        return [m.id for m in resp.data if m.id.startswith("gpt")]
    except openai.AuthenticationError as exc:  # type: ignore[attr-defined]
        logger.error("Invalid OpenAI API key: %s", exc)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to fetch OpenAI models: %s", exc)
    return []


def describe_popularity(score: float) -> str:
    """Return a human-friendly label for a popularity score."""
    if score >= 90:
        return "Global smash hit"
    if score >= 70:
        return "Mainstream favorite"
    if score >= 50:
        return "Moderately mainstream"
    if score >= 30:
        return "Niche appeal"
    return "Obscure or local"


def _build_gpt_prompt(
    existing_tracks: list[str], count: int, summary: dict | str | None = None
) -> str:
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
        summary_block = ""

    intro = (
        "The user has provided a playlist which has the following "
        f"characteristics:\n{summary_block}\n\n"
        f"Reference Playlist:\n{base}\n\n"
        f"Suggest exactly {count} additional **real and relevant** songs "
        "that would strongly appeal to someone who enjoys this playlist."
        + (
            "\n\nStrict constraints:\n"
            "- Songs must be real, commercially released tracks.\n"
            "- All songs must be available on both YouTube and Spotify.\n"
            "- Do NOT include any songs already listed in the provided playlist.\n"
            "- Do NOT invent or fabricate song titles, artists, or albums.\n"
            "- Only include songs that are publicly verifiable and recognizable.\n"
            "- Avoid remixes, covers, live-only performances, or "
            "obscure/independent tracks unless they had commercial release.\n\n"
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

    logger.debug("GPT Prompt: %s", intro)
    return intro


def prompt_fingerprint(prompt: str) -> str:
    """Generate SHA256 fingerprint of the prompt."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def cached_chat_completion_sync(prompt: str, temperature: float = 0.7) -> str:
    """
    Get a GPT completion from cache or OpenAI, allowing temperature override.

    Args:
        prompt (str): The user/system prompt.
        temperature (float): Temperature for GPT completion (default 0.7).

    Returns:
        str: GPT's raw response content.
    """
    key = prompt_fingerprint(
        f"{prompt}|temperature={temperature}"
    )  # Ensure cache keys differentiate by temperature
    content = prompt_cache.get(key)
    if content is not None:
        logger.info("GPT cache hit: %s", key)
        return content

    logger.info("GPT cache miss: %s", key)
    response = get_sync_openai_client().chat.completions.create(
        model=settings.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    raw_content = response.choices[0].message.content or ""
    content = raw_content.strip()
    content = strip_markdown(content)
    prompt_cache.set(key, content, expire=CACHE_TTLS["prompt"])
    logger.debug("GPT API original text: %s", content)
    return content


async def cached_chat_completion(prompt: str, temperature: float = 0.7) -> str:
    """Asynchronous variant of cached_chat_completion."""
    key = prompt_fingerprint(f"{prompt}|temperature={temperature}")
    content = prompt_cache.get(key)
    if content is not None:
        logger.info("GPT cache hit: %s", key)
        return content

    logger.info("GPT cache miss: %s", key)
    response = await get_async_openai_client().chat.completions.create(
        model=settings.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    raw_content = response.choices[0].message.content or ""
    content = raw_content.strip()
    content = strip_markdown(content)
    prompt_cache.set(key, content, expire=CACHE_TTLS["prompt"])
    logger.debug("GPT API original text: %s", content)
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


async def gpt_suggest_validated(
    existing_tracks: list[str],
    count: int,
    summary: dict | str | None = None,
    exclude_pairs: set[tuple[str, str]] | None = None,
) -> list[dict]:
    """
    Main interface to request playlist suggestions from GPT.

    Args:
        existing_tracks (list[str]): Seed data from user.
        count (int): Number of suggestions to return.

    Returns:
        list[dict]: Validated GPT suggestions (title, artist, text, popularity)
    """
    prompt = _build_gpt_prompt(existing_tracks, count * 3, summary)
    logger.debug("Sending GPT prompt:\n%s...", prompt[:500])
    result = await cached_chat_completion(prompt)
    response_content = result.strip()

    raw_lines = response_content.splitlines()
    logger.info("📦 GPT returned %d lines before validation", len(raw_lines))

    suggestions_raw = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            title, artist = parse_gpt_line(line)
            suggestions_raw.append({"title": title, "artist": artist, "text": line})
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("⚠️ Failed to parse line: '%s' → %s", line, exc)

    async def validate_and_score(track: dict) -> dict | None:
        title = track["title"]
        artist = track["artist"]

        try:
            track_data = await get_lastfm_track_info(title, artist)
            if not track_data:
                return None

            track["popularity"] = int(track_data.get("listeners", 0))
            return track

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "⚠️ Last.fm lookup failed for %s - %s: %s", title, artist, exc
            )
            track["popularity"] = 0
            return track

    validated = await asyncio.gather(*[validate_and_score(t) for t in suggestions_raw])
    suggestions_raw = [track for track in validated if track]
    if exclude_pairs:
        suggestions_raw = [
            track
            for track in suggestions_raw
            if (track["title"], track["artist"]) not in exclude_pairs
        ]

    logger.info(
        "✅ %d valid suggestions after validation and filtering",
        len(suggestions_raw),
    )
    return suggestions_raw[:count]


async def fetch_gpt_suggestions(
    tracks: list[dict], text_summary: str, count: int
) -> list[dict]:
    """Wrapper to request suggestions from GPT based on seed tracks."""
    seed_lines = [f"{t['title']} - {t['artist']}" for t in tracks]
    exclude_pairs = {(t["title"], t["artist"]) for t in tracks}
    return await gpt_suggest_validated(
        seed_lines,
        count,
        text_summary,
        exclude_pairs=exclude_pairs,
    )


async def generate_playlist_analysis_summary(summary: dict, tracks: list):
    """
    Returns (gpt_summary, removal_suggestions) using cached GPT response if available.
    """

    # Create a cache key from summary + track metadata
    digest_input = json.dumps(
        {
            "summary": summary,
            "tracks": [
                {
                    "title": t["title"],
                    "artist": t["artist"],
                    "genre": t.get("genre"),
                    "mood": t.get("mood"),
                    "tempo": t.get("tempo"),
                    "decade": t.get("decade"),
                }
                for t in tracks
            ],
        },
        sort_keys=True,
    ).encode("utf-8")
    cache_key = hashlib.sha256(digest_input).hexdigest()

    # Return from cache if available
    if (cached := prompt_cache.get(cache_key)) is not None:
        logger.info("Prompt Cache Hit in generate_playlist_analysis_summary")
        return (
            cached.get("gpt_summary"),
            cached.get("removal_suggestions"),
        )

    logger.info("Prompt Cache Miss generate_playlist_analysis_summary")
    # Build prompt
    track_blob = "\n".join(
        [
            (
                f"{t['title']} by {t['artist']} – genre: {t.get('genre')}, "
                f"mood: {t.get('mood')}, tempo: {t.get('tempo')} BPM, "
                f"decade: {t.get('decade')}, listeners: {t.get('popularity', 0):,}"
            )
            for t in tracks
        ]
    )

    prompt = (
        "You are an expert music curator analyzing a playlist to guide future "
        "additions. In 1–2 sentences, describe what kinds of tracks would "
        "complement and extend this playlist, focusing on the overall mood, "
        "vibe, and listening experience rather than strictly on genres or "
        "decades, but factoring in geography. Do not suggest specific tracks "
        "by name.\n\n"
        "Then, suggest up to 4 tracks that feel out of place and could be "
        "removed to improve consistency under the heading Suggested Removals. "
        "Justify each suggestion briefly. You can suggest less than 4.\n\n"
        "Tracks:\n"
        f"{track_blob}"
    )

    response = await get_async_openai_client().chat.completions.create(
        model=settings.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = strip_markdown((response.choices[0].message.content or "").strip())

    # Split output if needed
    if "Suggested Removals" in content:
        summary_text, removal_raw = [
            p.strip() for p in content.split("Suggested Removals", 1)
        ]
        result = {
            "gpt_summary": summary_text,
            "removal_suggestions": removal_raw.lstrip(": \n").strip(),
        }

    elif "1." in content:
        split_idx = content.find("1.")
        result = {
            "gpt_summary": content[:split_idx].strip(),
            "removal_suggestions": content[split_idx:].strip(),
        }

    else:
        result = {"gpt_summary": content.strip(), "removal_suggestions": ""}
    # Store the analysis summary in the prompt cache with a TTL
    prompt_cache.set(cache_key, result, expire=CACHE_TTLS["prompt"])
    return result["gpt_summary"], result["removal_suggestions"]


def analyze_mood_from_lyrics(lyrics: str) -> str | None:
    """Classify the overall mood of a song based on its lyrics via GPT."""
    if not lyrics:
        return None

    prompt = (
        "You are an expert music analyst.\n\n"
        "Analyze the following song lyrics and classify the overall mood of the song "
        "in one word, such as 'happy', 'sad', 'chill', 'intense', 'romantic', "
        "'dark', 'uplifting', 'nostalgic', 'party'.\n\n"
        "Lyrics:\n"
        "Respond with only the mood label and nothing else.\n\n"
        f"""\n{lyrics}\n"""
    )
    try:
        # Lower temperature for consistency
        result = cached_chat_completion_sync(prompt, temperature=0.4)
        mood = result.strip().lower()
        logger.debug("Lyrics mood classification: %s", mood)
        logger.info("GPT lyrics mood analysis result: %s", mood)
        return mood
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Lyrics mood analysis failed: %s", exc)
        return None
