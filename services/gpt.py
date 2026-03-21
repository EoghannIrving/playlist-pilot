"""
gpt.py

Handles GPT prompt generation, caching, and result validation for playlist suggestions.
"""

# pylint: disable=too-many-lines

import hashlib
import logging
import asyncio
import json
import re
import unicodedata
import math

import openai
from openai import OpenAI, AsyncOpenAI
from config import settings
from utils.cache_manager import prompt_cache, CACHE_TTLS
from utils.text_utils import strip_markdown
from services.lastfm import get_lastfm_track_info

logger = logging.getLogger("playlist-pilot")

GENRE_FAMILIES = {
    "rock": {
        "rock",
        "classic rock",
        "hard rock",
        "soft rock",
        "pop rock",
        "alternative rock",
        "indie rock",
    },
    "pop": {"pop", "synthpop", "dance pop", "electropop", "sophisti-pop", "art pop"},
    "new wave": {"new wave", "synthpop", "post-punk", "new romantic"},
    "indie": {"indie", "indie rock", "indie pop", "alternative"},
    "hip hop": {"hip hop", "rap", "rnb", "trap"},
    "folk": {"folk", "folk rock", "singer-songwriter", "acoustic"},
    "ambient": {"ambient", "downtempo", "dream pop", "chillout"},
    "country": {"country", "country pop", "americana"},
    "jazz": {"jazz", "smooth jazz", "vocal jazz", "swing"},
    "classical": {"classical", "orchestral", "instrumental"},
}

MOOD_TAG_ALIASES = {
    "chill": {"chill", "calm", "soft", "dreamy", "mellow", "downtempo", "ambient"},
    "romantic": {"romantic", "love", "tender", "warm", "intimate"},
    "party": {"party", "dance", "club", "anthemic", "celebratory"},
    "happy": {"happy", "uplifting", "joyful", "bright", "feel good"},
    "sad": {"sad", "melancholy", "melancholic", "heartbreak", "sorrowful"},
    "energetic": {"energetic", "driving", "upbeat", "powerful", "anthemic"},
    "nostalgic": {"nostalgic", "wistful", "retro", "throwback"},
}


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
    except openai.OpenAIError as exc:  # type: ignore[attr-defined]
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


def detect_playlist_mode(playlist_name: str | None) -> str:
    """Return the suggestion mode implied by the playlist name."""
    return (
        "strict_decade"
        if detect_strict_decade_window(playlist_name or "")
        else "profile_match"
    )


def build_prompt_context(
    summary: dict | str | None = None,
    profile_summary: str | None = None,
    playlist_name: str | None = None,
) -> dict:
    """Build structured context for prompt generation and suggestion logging."""
    decade_window = detect_strict_decade_window(playlist_name or "")
    playlist_mode = detect_playlist_mode(playlist_name)
    dominant_genre = "Unknown"
    moods: list[str] = []
    avg_bpm = 0
    decades: list[str] = []

    if isinstance(summary, dict):
        dominant_genre = str(summary.get("dominant_genre") or "Unknown")
        moods = list(summary.get("mood_profile", {}).keys())
        avg_bpm = int(summary.get("tempo_avg") or 0)
        decades = list(summary.get("decades", {}).keys())
        if dominant_genre == "Unknown" or not moods or avg_bpm == 0 or not decades:
            logger.warning(
                "Weak suggestion summary input: dominant_genre=%s moods=%s tempo_avg=%s decades=%s",
                dominant_genre,
                moods,
                avg_bpm,
                decades,
            )

    avoid_rules = [
        "Do not include tracks already on the source playlist.",
        "Prefer strongest fit over broad popularity.",
    ]
    if playlist_mode == "strict_decade" and decade_window:
        start_year, end_year = decade_window
        avoid_rules.extend(
            [
                f"Stay inside {start_year}-{end_year}.",
                "Avoid post-decade vibe substitutions.",
            ]
        )
    else:
        avoid_rules.append(
            "Avoid generic prestige or streaming-era melancholy picks unless clearly supported."
        )

    return {
        "playlist_name": (playlist_name or "").strip(),
        "playlist_mode": playlist_mode,
        "decade_window": decade_window,
        "dominant_genre": dominant_genre,
        "moods": moods,
        "avg_bpm": avg_bpm,
        "decades": decades,
        "profile_summary": (profile_summary or "").strip(),
        "summary": summary,
        "avoid_rules": avoid_rules,
    }


def build_mode_instruction_block(context: dict) -> str:
    """Return the mode-specific instruction block for GPT suggestions."""
    if context["playlist_mode"] == "strict_decade" and context["decade_window"]:
        start_year, end_year = context["decade_window"]
        return (
            "Mode-specific rules (strict_decade):\n"
            f"- This playlist is explicitly decade-scoped to {start_year}-{end_year}.\n"
            f"- Suggest tracks released inside {start_year}-{end_year} only.\n"
            "- Prefer era, scene, instrumentation, and production adjacency "
            "over mood-only similarity.\n"
            "- Do not use later vibe-match substitutions, modern indie "
            "stand-ins, or nostalgic lookbacks from other decades.\n"
            "- Favor tracks that sound plausibly at home beside the source "
            "playlist, not just thematically similar.\n"
            "- Rank strongest same-decade fit first, even if a more famous "
            "out-of-era track feels broadly compatible.\n"
        )

    return (
        "Mode-specific rules (profile_match):\n"
        "- Prioritize genre, mood, scene, production style, and "
        "listening-flow fit over broad popularity.\n"
        "- Use the source playlist's strongest clusters as the primary anchor.\n"
        "- Prefer artists, scenes, and sonic palettes plausibly adjacent "
        "to the reference playlist.\n"
        "- Avoid generic prestige picks or streaming-era melancholy tracks "
        "unless the source clearly supports them.\n"
        "- A cross-era suggestion is acceptable only when it still feels "
        "like a natural extension of the playlist's identity.\n"
        "- Rank strongest profile fit first, not broad recognition.\n"
    )


def _build_gpt_prompt(
    existing_tracks: list[str],
    count: int,
    summary: dict | str | None = None,
    profile_summary: str | None = None,
    playlist_name: str | None = None,
) -> str:
    """
    Constructs a tailored GPT prompt based a user selected playlist.

    Args:
        existing_tracks (list[str]): Source tracks (playlist or library).
        count (int): Number of suggestions requested.

    Returns:
        str: The GPT prompt text.
    """
    # pylint: disable=too-many-locals,too-many-branches
    base = "\n".join(existing_tracks)
    context = build_prompt_context(summary, profile_summary, playlist_name)
    if summary:
        if isinstance(summary, str):
            summary_block = summary
        else:
            pop_score = summary.get("avg_popularity", 0)
            pop_desc = describe_popularity(pop_score)
            summary_lines = ["The following is a summary of the playlist:"]
            if summary.get("dominant_genre") and summary["dominant_genre"] != "Unknown":
                summary_lines.append(f"- Dominant Genre: {summary['dominant_genre']}")
            moods = list(summary.get("mood_profile", {}).keys())
            if moods:
                summary_lines.append(f"- Moods: {', '.join(moods)}")
            if summary.get("tempo_avg"):
                summary_lines.append(f"- Avg BPM: {int(summary['tempo_avg'])}")
            summary_lines.append(f"- Popularity: ~{pop_desc} (score: {int(pop_score)})")
            decades = list(summary.get("decades", {}).keys())
            if decades:
                summary_lines.append(f"- Decades: {', '.join(decades)}")
            summary_block = "\n".join(summary_lines)
    else:
        summary_block = ""

    if context["profile_summary"]:
        profile_block = f"\nPlaylist profile summary:\n{context['profile_summary']}\n"
    else:
        profile_block = ""

    decade_window = context["decade_window"]
    playlist_block = (
        f'Playlist name: "{playlist_name.strip()}"\n\n' if playlist_name else ""
    )
    prompt_context_lines = [
        "Prompt context:",
        f"- Suggestion mode: {context['playlist_mode']}",
        f"- Dominant genre: {context['dominant_genre']}",
    ]
    if context["moods"]:
        prompt_context_lines.append(f"- Top moods: {', '.join(context['moods'])}")
    if context["avg_bpm"]:
        prompt_context_lines.append(f"- Avg BPM: {context['avg_bpm']}")
    if context["decades"]:
        prompt_context_lines.append(
            f"- Source decades: {', '.join(context['decades'])}"
        )
    if decade_window:
        prompt_context_lines.append(
            f"- Target decade window: {decade_window[0]}-{decade_window[1]}"
        )
    prompt_context_lines.append(f"- Avoid rules: {'; '.join(context['avoid_rules'])}")
    prompt_context_block = "\n".join(prompt_context_lines)

    decade_constraint_block = ""
    if decade_window:
        start_year, end_year = decade_window
        decade_constraint_block = (
            "Decade constraint:\n"
            f"- This playlist is explicitly scoped to {start_year}-{end_year}.\n"
            f"- Prefer tracks released between {start_year} and {end_year}.\n"
            f"- Do not suggest tracks released outside {start_year}-{end_year}.\n\n"
        )
    mode_instruction_block = build_mode_instruction_block(context)

    intro = (
        "The user has provided a playlist which has the following "
        f"characteristics:\n{summary_block}\n\n"
        f"{playlist_block}"
        f"{prompt_context_block}\n\n"
        f"{profile_block}"
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
            f"{mode_instruction_block}\n"
            "Formatting rules:\n"
            "- Return each song on a single line.\n"
            "- Use the **exact** format:\n"
            "  Song - Artist - Album - Year - Reason\n"
            "- Do NOT include:\n"
            "  • Numbering\n"
            "  • Bullet points\n"
            "  • Extra commentary\n"
            "  • Fake, unreleased, or AI-generated music\n"
            f"\n{decade_constraint_block}"
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
        f"{prompt}|temperature={temperature}|model={settings.model}"
    )  # Ensure cache keys differentiate by model and temperature
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
    key = prompt_fingerprint(
        f"{prompt}|temperature={temperature}|model={settings.model}"
    )
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
    """Parse a GPT suggestion line into ``(title, artist)``.

    GPT generally returns lines in the format ``"Song - Artist - Reason"`` but
    occasionally uses ``"Song by Artist - Reason"``. This helper extracts the
    title and artist from either style. If the line cannot be parsed, a
    ``ValueError`` is raised.
    """

    line = re.sub(r"[\u2013\u2014]", "-", line).strip()  # normalize en/em dashes

    # Attempt to parse the common "Song - Artist" style first
    parts = [p.strip() for p in line.split(" - ")]
    if len(parts) >= 2:
        title_part, artist_part = parts[0], parts[1]
        if " by " in title_part.lower():
            title_split = re.split(
                r"\s+by\s+", title_part, maxsplit=1, flags=re.IGNORECASE
            )
            if len(title_split) == 2:
                title_part, artist_part = title_split[0].strip(), title_split[1].strip()
        return title_part, artist_part

    # Fallback to "Song by Artist" when no dash is present
    by_split = re.split(r"\s+by\s+", line, maxsplit=1, flags=re.IGNORECASE)
    if len(by_split) == 2:
        return by_split[0].strip(), by_split[1].strip()

    raise ValueError(f"Could not parse suggestion line: {line}")


async def gpt_suggest_validated(
    existing_tracks: list[str],
    count: int,
    summary: dict | str | None = None,
    profile_summary: str | None = None,
    exclude_pairs: set[tuple[str, str]] | None = None,
    playlist_name: str | None = None,
) -> list[dict]:
    """
    Main interface to request playlist suggestions from GPT.

    Args:
        existing_tracks (list[str]): Seed data from user.
        count (int): Number of suggestions to return.

    Returns:
        list[dict]: Validated GPT suggestions (title, artist, text, popularity)
    """
    # pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments,too-many-statements
    prompt_context = build_prompt_context(summary, profile_summary, playlist_name)
    prompt = _build_gpt_prompt(
        existing_tracks,
        count * 3,
        summary,
        profile_summary,
        playlist_name=playlist_name,
    )
    logger.info(
        (
            "Suggestion prompt context: playlist=%s mode=%s decade_window=%s "
            "source_tracks=%d dominant_genre=%s moods=%s avg_bpm=%s"
        ),
        prompt_context["playlist_name"],
        prompt_context["playlist_mode"],
        prompt_context["decade_window"],
        len(existing_tracks),
        prompt_context["dominant_genre"],
        prompt_context["moods"],
        prompt_context["avg_bpm"],
    )
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
            suggestions_raw.append(
                {
                    "title": title,
                    "artist": artist,
                    "text": line,
                    "year": extract_year_from_suggestion_line(line),
                }
            )
        except ValueError as exc:
            logger.warning("⚠️ Failed to parse line: '%s' → %s", line, exc)

    async def validate_and_score(track: dict) -> dict | None:
        title = track["title"]
        artist = track["artist"]

        track_data = await get_lastfm_track_info(title, artist)
        if not track_data:
            return None

        track["popularity"] = int(track_data.get("listeners", 0))
        track["tags"] = extract_tag_names(track_data.get("toptags"))
        if not track.get("year"):
            track["year"] = extract_year_from_releasedate(
                track_data.get("releasedate", "")
            )
        track["decade"] = year_to_decade(track.get("year"))
        fit_breakdown = score_candidate_fit_breakdown(track, summary, decade_window)
        track["fit_breakdown"] = fit_breakdown
        track["fit_score"] = fit_breakdown["fit_score"]
        return track

    decade_window = prompt_context["decade_window"]
    validated = await asyncio.gather(*[validate_and_score(t) for t in suggestions_raw])
    suggestions_raw = [track for track in validated if track]
    normalized_exclude_pairs = (
        {normalize_track_key(title, artist) for title, artist in exclude_pairs}
        if exclude_pairs
        else set()
    )
    accepted_keys: set[tuple[str, str]] = set()
    filtered_suggestions: list[dict] = []
    rejected_duplicate_source = 0
    rejected_duplicate_batch = 0
    rejected_decade = 0

    for track in suggestions_raw:
        key = normalize_track_key(track["title"], track["artist"])
        if key in normalized_exclude_pairs:
            rejected_duplicate_source += 1
            continue
        if key in accepted_keys:
            rejected_duplicate_batch += 1
            continue
        if decade_window and not year_in_window(track.get("year"), decade_window):
            rejected_decade += 1
            continue
        accepted_keys.add(key)
        filtered_suggestions.append(track)

    filtered_suggestions.sort(
        key=lambda track: (
            track.get("fit_score", 0.0),
            track.get("popularity", 0),
        ),
        reverse=True,
    )

    logger.info(
        (
            "Suggestion pipeline summary: playlist=%s mode=%s decade_window=%s "
            "raw_candidates=%d validated=%d accepted=%d "
            "rejected_duplicate_source=%d rejected_duplicate_batch=%d "
            "rejected_decade=%d"
        ),
        prompt_context["playlist_name"],
        prompt_context["playlist_mode"],
        decade_window,
        len(raw_lines),
        len(suggestions_raw),
        len(filtered_suggestions),
        rejected_duplicate_source,
        rejected_duplicate_batch,
        rejected_decade,
    )
    for track in filtered_suggestions[:count]:
        logger.info(
            "Accepted suggestion: %s - %s | fit=%s | breakdown=%s",
            track["title"],
            track["artist"],
            track.get("fit_score"),
            track.get("fit_breakdown"),
        )
    return filtered_suggestions[:count]


async def fetch_gpt_suggestions(
    tracks: list[dict],
    summary: dict | str | None,
    count: int,
    profile_summary: str = "",
    playlist_name: str = "",
) -> list[dict]:
    """Wrapper to request suggestions from GPT based on seed tracks."""
    seed_lines = [
        f"{t['title']} - {t['artist']}"
        f" - genre: {t.get('genre', 'unknown')}"
        f" - mood: {t.get('mood', 'unknown')}"
        f" - decade: {t.get('decade', 'unknown')}"
        f" - tempo: {t.get('tempo', '??')} BPM"
        for t in tracks
    ]
    exclude_pairs = {(t["title"], t["artist"]) for t in tracks}
    return await gpt_suggest_validated(
        seed_lines,
        count,
        summary,
        profile_summary=profile_summary,
        exclude_pairs=exclude_pairs,
        playlist_name=playlist_name,
    )


def detect_strict_decade_window(playlist_name: str) -> tuple[int, int] | None:
    """Return an exact decade window for explicit decade playlist names."""
    normalized = (playlist_name or "").strip().lower()
    match = re.search(r"\b((?:19|20)?\d{2})s\b", normalized)
    if not match:
        return None

    token = match.group(1)
    if len(token) == 2:
        decade_start = 1900 + int(token)
    else:
        decade_start = int(token)

    if decade_start < 1900 or decade_start > 2090 or decade_start % 10 != 0:
        return None
    return (decade_start, decade_start + 9)


def extract_year_from_suggestion_line(line: str) -> int | None:
    """Extract the explicit year segment from a GPT suggestion line if present."""
    parts = [part.strip() for part in re.sub(r"[\u2013\u2014]", "-", line).split(" - ")]
    if len(parts) < 4:
        return None
    return parse_year(parts[3])


def extract_year_from_releasedate(releasedate: str) -> int | None:
    """Extract a 4-digit year from a Last.fm release-date string."""
    match = re.search(r"\b(19\d{2}|20\d{2})\b", releasedate or "")
    if not match:
        return None
    return int(match.group(1))


def parse_year(value: str | int | None) -> int | None:
    """Parse a 4-digit year when available."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1900 <= value <= 2099 else None
    match = re.fullmatch(r"(19\d{2}|20\d{2})", str(value).strip())
    if not match:
        return None
    return int(match.group(1))


def year_in_window(year: int | None, window: tuple[int, int]) -> bool:
    """Return whether a parsed year falls inside the inclusive window."""
    if year is None:
        return False
    start_year, end_year = window
    return start_year <= year <= end_year


def extract_tag_names(raw_tags: dict | list | None) -> list[str]:
    """Extract normalized tag names from a Last.fm tag payload."""
    if not raw_tags:
        return []
    if isinstance(raw_tags, dict):
        raw_tags = raw_tags.get("tag", [])
    if isinstance(raw_tags, dict):
        raw_tags = [raw_tags]
    names = []
    for tag in raw_tags:
        if isinstance(tag, dict) and tag.get("name"):
            names.append(str(tag["name"]).strip().lower())
    return list(dict.fromkeys(names))


def year_to_decade(year: int | None) -> str | None:
    """Convert a year to a display decade like ``1980s``."""
    if year is None:
        return None
    return f"{year - (year % 10)}s"


def _score_genre_fit(candidate_tags: set[str], summary: dict | str | None) -> float:
    """Score genre fit against the source playlist summary."""
    if not isinstance(summary, dict):
        return 0.5
    dominant = str(summary.get("dominant_genre") or "").strip().lower()
    top_genres = {
        str(name).strip().lower()
        for name in (summary.get("genre_distribution") or {}).keys()
        if str(name).strip() and str(name).strip().lower() != "unknown"
    }
    if not dominant and not top_genres:
        return 0.5
    if dominant and dominant in candidate_tags:
        return 1.0
    if top_genres & candidate_tags:
        return 0.85

    candidate_family_matches = set()
    for genre, family in GENRE_FAMILIES.items():
        if genre in top_genres or genre == dominant:
            candidate_family_matches |= family & candidate_tags
    return 0.7 if candidate_family_matches else 0.2


def _score_mood_fit(candidate_tags: set[str], summary: dict | str | None) -> float:
    """Score mood fit against the source playlist summary."""
    if not isinstance(summary, dict):
        return 0.5
    moods = {
        str(name).strip().lower()
        for name in (summary.get("mood_profile") or {}).keys()
        if str(name).strip() and str(name).strip().lower() != "unknown"
    }
    if not moods:
        return 0.5
    for mood in moods:
        aliases = MOOD_TAG_ALIASES.get(mood, {mood})
        if aliases & candidate_tags:
            return 1.0
    return 0.3


def _score_popularity_fit(track: dict, summary: dict | str | None) -> float:
    """Score popularity fit using Last.fm listeners on a log scale."""
    if not isinstance(summary, dict):
        return 0.5
    avg_listeners = summary.get("avg_listeners") or 0
    listeners = track.get("popularity") or 0
    if not avg_listeners or not listeners:
        return 0.5
    delta = abs(math.log10(listeners + 1) - math.log10(avg_listeners + 1))
    return max(0.0, 1.0 - min(delta / 2.0, 1.0))


def _score_decade_fit(track: dict, summary: dict | str | None, decade_window) -> float:
    """Score decade fit from explicit window first, then source summary decades."""
    if decade_window:
        return 1.0 if year_in_window(track.get("year"), decade_window) else 0.0
    if not isinstance(summary, dict):
        return 0.5
    candidate_decade = track.get("decade")
    source_decades = {
        str(name).strip()
        for name in (summary.get("decades") or {}).keys()
        if str(name).strip()
    }
    if not source_decades or not candidate_decade:
        return 0.5
    return 1.0 if candidate_decade in source_decades else 0.3


def score_candidate_fit(
    track: dict,
    summary: dict | str | None = None,
    decade_window: tuple[int, int] | None = None,
) -> float:
    """Compute a deterministic fit score for a candidate suggestion."""
    return score_candidate_fit_breakdown(track, summary, decade_window)["fit_score"]


def score_candidate_fit_breakdown(
    track: dict,
    summary: dict | str | None = None,
    decade_window: tuple[int, int] | None = None,
) -> dict:
    """Return weighted fit-score components for a candidate suggestion."""
    candidate_tags = set(track.get("tags") or [])
    decade_score = _score_decade_fit(track, summary, decade_window)
    genre_score = _score_genre_fit(candidate_tags, summary)
    mood_score = _score_mood_fit(candidate_tags, summary)
    popularity_score = _score_popularity_fit(track, summary)
    fit_score = round(
        (
            0.35 * decade_score
            + 0.25 * genre_score
            + 0.20 * mood_score
            + 0.20 * popularity_score
        )
        * 100,
        2,
    )
    return {
        "decade_score": round(decade_score, 3),
        "genre_score": round(genre_score, 3),
        "mood_score": round(mood_score, 3),
        "popularity_score": round(popularity_score, 3),
        "fit_score": fit_score,
    }


def strip_number_prefix(line: str) -> str:
    """Remove any leading numbering from a playlist line."""
    return re.sub(r"^\d+[).\-\s]*", "", line).strip()


_TITLE_SUFFIX_RE = re.compile(
    r"\s*[\(\[]?(?:\d{4}\s+)?"
    r"(?:remaster(?:ed)?|radio edit|single version|video version|live|"
    r"mono version|stereo version|edit)"
    r"[\)\]]?\s*$",
    flags=re.IGNORECASE,
)


def _normalize_track_component(value: str) -> str:
    """Normalize a title or artist component for duplicate comparison."""
    normalized = (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    normalized = normalized.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _normalize_track_title(title: str) -> str:
    """Normalize a title and strip common version suffixes."""
    cleaned = _TITLE_SUFFIX_RE.sub("", title or "")
    return _normalize_track_component(cleaned)


def normalize_track_key(title: str, artist: str) -> tuple[str, str]:
    """Return a canonical `(title, artist)` key for duplicate detection."""
    return _normalize_track_title(title), _normalize_track_component(artist)


def _extract_remaining(text: str, title: str, artist: str) -> str:
    """Return the explanatory text after the title/artist pair."""
    normalized = text.replace("\u2013", "-")
    dash_pattern = f"{title} - {artist}"
    by_pattern = f"{title} by {artist}"
    lower_norm = normalized.lower()
    if lower_norm.startswith(dash_pattern.lower()):
        return normalized[len(dash_pattern) :].lstrip(" -")
    if lower_norm.startswith(by_pattern.lower()):
        return normalized[len(by_pattern) :].lstrip(" -")
    parts = [p.strip() for p in normalized.split(" - ", 2)]
    return parts[2].strip() if len(parts) > 2 else ""


def _normalize_removal_blocks(raw: str) -> list[str]:
    """Collapse multiline GPT removal suggestions into one line each."""
    blocks: list[str] = []
    current: str | None = None
    ignored_patterns = (
        r"^thanks[!. ]*$",
        r"^thank you[!. ]*$",
        r"^hope this helps[!. ]*$",
    )

    for line in raw.splitlines():
        text = strip_number_prefix(line).strip()
        if not text:
            continue
        if text.lower().startswith("suggested removals"):
            continue
        if any(
            re.match(pattern, text, flags=re.IGNORECASE) for pattern in ignored_patterns
        ):
            continue

        if text.lower().startswith("justification:"):
            reason = text.split(":", 1)[1].strip()
            if current and reason:
                current = f"{current} - {reason}"
            continue

        try:
            parse_gpt_line(text)
        except ValueError:
            if current:
                current = f"{current} {text}".strip()
            continue

        if current:
            blocks.append(current)
        current = text

    if current:
        blocks.append(current)

    return blocks


def format_removal_suggestions(
    raw: str, tracks: list[dict] | None = None
) -> list[dict]:
    """Return structured removal suggestions and matching item IDs.

    Each suggestion dict has ``title``, ``artist``, optional ``reason``, and
    ``item_id`` if a matching track is found in ``tracks`` based on title and
    artist.
    """

    track_index = {}
    if tracks:
        track_index = {
            (t.get("title", "").lower(), t.get("artist", "").lower()): t for t in tracks
        }

    suggestions: list[dict] = []
    for text in _normalize_removal_blocks(raw):
        try:
            title, artist = parse_gpt_line(text)
        except ValueError:
            continue

        remaining = _extract_remaining(text, title, artist)

        item_id = None
        match = track_index.get((title.lower(), artist.lower()))
        if match is not None:
            item_id = match.get("PlaylistItemId") or match.get("Id")

        suggestions.append(
            {
                "title": title,
                "artist": artist,
                "reason": remaining or None,
                "item_id": item_id,
            }
        )

    return suggestions


async def fetch_order_suggestions(
    tracks: list[dict], summary: str | None = None
) -> list[dict]:
    """Ask GPT to reorder the given tracks and return the new order."""
    seed_lines = [
        f"{t['title']} - {t['artist']}"
        f" - {t.get('tempo', '??')} BPM - mood: {t.get('mood', 'unknown')}"
        for t in tracks
    ]
    prompt = (
        "You are an expert DJ known for creating perfectly flowing playlists.\n"
        f"Reorder the following {len(seed_lines)} tracks to maximize musical flow "
        "and emotional progression.\n"
        "Consider transitions in tempo, energy, mood, genre, and style. "
        "Create a journey with natural rises and falls.\n"
        "Start strong, build gradually, avoid abrupt changes, and end with a "
        "satisfying resolution.\n"
        "Return the new order using the exact format:\n\n"
        "1. Song - Artist\n2. Song - Artist\n...\n\n"
        "Do not add, remove, or comment on any tracks.\n\nTracks:\n"
        + "\n".join(seed_lines)
    )

    if summary:
        prompt += f"\n\nPlaylist summary:\n{summary}"

    result = await cached_chat_completion(prompt)
    ordered = []
    for line in result.splitlines():
        line = strip_number_prefix(line)
        if not line:
            continue
        try:
            title, artist = parse_gpt_line(line)
        except ValueError:
            continue
        ordered.append({"title": title, "artist": artist, "text": line})
    return ordered


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
        "You are an expert music curator analyzing a playlist.\n\n"
        "First, write a true profile summary of the playlist in 2-3 sentences. "
        "Describe what the playlist currently is: its overall identity, mood, "
        "energy, genre mix, era balance, and any geographic or stylistic character. "
        "This must summarize the existing playlist, not recommend additions yet.\n\n"
        "Then, in 1 sentence, describe what kinds of tracks would complement and "
        "extend it while preserving its character. Focus on mood, vibe, listening "
        "experience, and geography rather than listing genres mechanically. "
        "Do not suggest specific tracks by name.\n\n"
        "Then output a section exactly titled:\n"
        "Suggested Removals\n\n"
        "In that section, list up to 4 tracks that feel out of place and could "
        "be removed to improve consistency. You can suggest fewer than 4.\n\n"
        "Formatting rules for Suggested Removals:\n"
        "- Each removal must be on exactly one line.\n"
        "- Use exactly this format:\n"
        "  Title - Artist - Short reason\n"
        "- Do not use bullets, numbering, markdown, labels, or extra commentary.\n"
        "- Do not use a separate 'Justification:' line.\n"
        "- Keep each reason under 18 words.\n"
        "- Only use tracks from the provided playlist.\n"
        "- If no removals are warranted, output exactly:\n"
        "  None\n\n"
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
        "Analyze the following song lyrics and classify the overall mood of the song.\n"
        "Respond with exactly one label from this list only:\n"
        "happy, sad, chill, intense, romantic, dark, uplifting, nostalgic, party\n\n"
        "Choose the closest label from that list even if another word like "
        "'wistful', 'reflective', 'dreamy', 'melancholic', or 'dramatic' might fit.\n\n"
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
    except openai.OpenAIError as exc:  # type: ignore[attr-defined]
        logger.warning("Lyrics mood analysis failed: %s", exc)
        return None


def analyze_mood_from_track_context(
    title: str,
    artist: str,
    genres: list[str] | None = None,
    year: str | int | None = None,
    lyrics: str | None = None,
) -> str | None:
    """Use GPT as a final constrained fallback for unresolved track moods."""
    genre_text = ", ".join(genre for genre in (genres or []) if genre) or "unknown"
    year_text = str(year).strip() if year else "unknown"
    lyrics_excerpt = ""
    if lyrics:
        compact = " ".join(lyrics.split())
        lyrics_excerpt = compact[:700]

    prompt = (
        "You are an expert music analyst.\n\n"
        "Classify the overall mood of this song.\n"
        "Respond with exactly one label from this list only:\n"
        "happy, sad, chill, intense, romantic, dark, uplifting, nostalgic, party\n\n"
        "Use the available metadata and lyrics excerpt. Prefer the closest label from "
        "the allowed list, even if the more natural description would be something "
        "like wistful, reflective, dramatic, or yearning.\n\n"
        f"Title: {title}\n"
        f"Artist: {artist}\n"
        f"Genres: {genre_text}\n"
        f"Year: {year_text}\n"
    )
    if lyrics_excerpt:
        prompt += f"Lyrics excerpt:\n{lyrics_excerpt}\n"

    try:
        result = cached_chat_completion_sync(prompt, temperature=0.2)
        mood = result.strip().lower()
        logger.debug(
            "Context fallback mood classification for %s - %s: %s",
            artist,
            title,
            mood,
        )
        return mood
    except openai.OpenAIError as exc:  # type: ignore[attr-defined]
        logger.warning(
            "Context fallback mood analysis failed for %s - %s: %s",
            artist,
            title,
            exc,
        )
        return None
