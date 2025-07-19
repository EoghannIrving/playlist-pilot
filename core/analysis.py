"""Utility functions for analyzing playlists and track metadata."""

from collections import Counter
from typing import Dict, List
from statistics import mean
import math
import logging
import re
from config import settings, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM

logger = logging.getLogger("playlist-pilot")


def most_common(values: List[str]) -> str:
    """Return the most common element in *values* or ``'Unknown'`` if empty."""
    if not values:
        return "Unknown"
    return Counter(values).most_common(1)[0][0]

def percent_distribution(values: List[str]) -> Dict[str, str]:
    """Return a mapping of value to percentage occurrence."""
    total = len(values)
    if total == 0:
        return {}
    counts = Counter(values)
    return {k: f"{v * 100 // total}%" for k, v in counts.items()}

def average_tempo(tracks: List[dict]) -> int:
    """Calculate the rounded average tempo for a list of tracks."""
    tempos = [
        t["tempo"]
        for t in tracks
        if isinstance(t.get("tempo"), (int, float))
    ]
    return round(sum(tempos) / len(tempos)) if tempos else 0

def normalized_entropy(values: list[str]) -> float:
    """Return the normalized Shannon entropy of *values*."""
    total = len(values)
    if total == 0:
        return 0.0
    counts = Counter(values)
    entropy = -sum((v / total) * math.log2(v / total) for v in counts.values())
    max_entropy = math.log2(len(counts))
    return round(entropy / max_entropy, 2) if max_entropy > 0 else 0.0

def average_duration(tracks: List[dict]) -> int:
    """Return the average duration in seconds for the given tracks."""
    durations = [
        t["duration"]
        for t in tracks
        if isinstance(t.get("duration"), (int, float))
    ]
    return round(sum(durations) / len(durations)) if durations else 0

def summarize_tracks(tracks: List[dict]) -> dict:
    """Return a summary dictionary for a list of track metadata."""
    genres = [t["genre"] for t in tracks if t.get("genre")]
    moods = [t["mood"] for t in tracks if t.get("mood")]
    decades = [t["decade"] for t in tracks if t.get("decade")]

    avg_tempo = average_tempo(tracks)
    popularity_values = [
        t["combined_popularity"]
        for t in tracks
        if t.get("combined_popularity") is not None
    ]

    base_summary = {
        "dominant_genre": most_common(genres),
        "mood_profile": percent_distribution(moods),
        "tempo_avg": avg_tempo,
        "decades": percent_distribution(decades),
        "genre_diversity_score": normalized_entropy(genres),
        "avg_duration": average_duration(tracks),
        "genre_distribution": percent_distribution(genres),
        "mood_distribution": percent_distribution(moods),
        "tempo_ranges": classify_tempo_ranges(tracks),
        "avg_listeners": mean([t.get("popularity", 0) for t in tracks]),
        "avg_popularity": sum(popularity_values) / len(tracks),
    }

    base_summary["outliers"] = detect_outliers(tracks, base_summary)
    return base_summary

def classify_tempo_ranges(tracks: list[dict]) -> dict:
    """Group track tempos into broad BPM ranges."""
    ranges = []
    for track in tracks:
        tempo = track.get("tempo")
        if isinstance(tempo, (int, float)):
            if tempo < 90:
                ranges.append("<90 BPM")
            elif 90 <= tempo <= 120:
                ranges.append("90–120 BPM")
            else:
                ranges.append(">120 BPM")
    return percent_distribution(ranges)


def detect_outliers(tracks: List[dict], summary: dict) -> List[str]:
    """Identify tracks that deviate strongly from the provided summary."""
    avg_tempo = summary.get("tempo_avg")
    dominant_genre = summary.get("dominant_genre")
    avg_listeners = summary.get("avg_listeners", 0)

    outliers = []

    for t in tracks:
        reasons = []

        # Tempo deviation > 40 BPM
        if isinstance(t.get("tempo"), (int, float)) and abs(t["tempo"] - avg_tempo) > 40:
            reasons.append("tempo")

        # Genre mismatch (excluding 'Unknown')
        if t.get("genre") and t["genre"].lower() != dominant_genre.lower():
            reasons.append("genre")

        # Mood unknown or missing confidence
        if not t.get("mood") or t.get("mood_confidence", 0) < 0.3:
            reasons.append("mood")

        # Listeners < 5% of average
        if t.get("popularity", 0) < avg_listeners * 0.05:
            reasons.append("popularity")

        # Year flagged as inconsistent
        if t.get("year_flag"):
            reasons.append("year")

        if reasons:
            outliers.append({
                "title": t["title"],
                "reasons": reasons
            })
    outliers.sort(key=lambda x: len(x["reasons"]), reverse=True)
    return outliers[:5]

def normalize_popularity(value, min_val, max_val):
    """Normalize a value to a 0-100 scale given its min and max bounds."""
    logger.info(
        "normalize_popularity called with value=%s, min_val=%s, max_val=%s",
        value,
        min_val,
        max_val,
    )
    if min_val == max_val:
        logger.warning("normalize_popularity returning 0 due to min_val == max_val")
        return 0
    result = round(100 * (value - min_val) / (max_val - min_val), 2)
    logger.info("normalize_popularity for jellyfin returning %s", result)
    return result

def combined_popularity_score(lastfm, jellyfin, w_lfm=0.4, w_jf=0.6):
    """Combine popularity metrics from Last.fm and Jellyfin."""
    logger.info(
        "combined_popularity_score called with lastfm=%s, jellyfin=%s, w_lfm=%s, w_jf=%s",
        lastfm,
        jellyfin,
        w_lfm,
        w_jf,
    )

    result = None

    if (jellyfin is None or jellyfin == 0) and lastfm is not None:
        result = round(lastfm, 2)
        logger.warning(
            "combined_popularity_score returning %s (fallback to lastfm)",
            result,
        )

    elif (lastfm is None or lastfm == 0) and jellyfin is not None:
        result = round(jellyfin, 2)
        logger.warning(
            "combined_popularity_score returning %s (fallback to jellyfin)",
            result,
        )

    elif lastfm is not None and jellyfin is not None:
        result = round((lastfm * w_lfm + jellyfin * w_jf) / (w_lfm + w_jf), 2)
        logger.debug(
            "combined_popularity_score returning %s (weighted average)",
            result,
        )

    else:
        logger.warning("combined_popularity_score returning None (no valid inputs)")
        return None

    if result == 0:
        logger.warning("⚠️ combined_popularity_score result is 0")

    return result

def normalize_popularity_log(value, min_val, max_val):
    """Normalize logarithmic popularity values to a 0-100 scale."""
    logger.info(
        "normalize_popularity_log called with value=%s, min_val=%s, max_val=%s",
        value,
        min_val,
        max_val,
    )
    if value is None or value <= 0:
        logger.warning(
            "normalize_popularity_log for lastfm returning 0 (value is None or <= 0)"
        )
        return 0
    log_min = math.log10(min_val)
    log_max = math.log10(max_val)
    log_val = math.log10(value)
    score = 100 * (log_val - log_min) / (log_max - log_min)
    result = round(max(0, min(score, 100)), 2)
    logger.debug(
        "normalize_popularity_log for lastfm returning %s (normalized log scale) raw value: %s",
        result,
        value,
    )
    return result


def add_combined_popularity(
    tracks: list[dict], w_lfm: float = 0.3, w_jf: float = 0.7
) -> list[dict]:
    """Calculate combined popularity for a list of track dictionaries."""

    jellyfin_raw = [
        t["jellyfin_play_count"]
        for t in tracks
        if isinstance(t.get("jellyfin_play_count"), int)
    ]
    min_jf, max_jf = min(jellyfin_raw, default=0), max(jellyfin_raw, default=0)

    for track in tracks:
        raw_lfm = track.get("popularity")
        raw_jf = track.get("jellyfin_play_count")
        norm_lfm = (
            normalize_popularity_log(raw_lfm, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM)
            if raw_lfm is not None
            else None
        )
        norm_jf = (
            normalize_popularity(raw_jf, min_jf, max_jf)
            if raw_jf is not None
            else None
        )
        track["combined_popularity"] = combined_popularity_score(
            norm_lfm,
            norm_jf,
            w_lfm=w_lfm,
            w_jf=w_jf,
        )

    return tracks


MOOD_TAGS = {
    "happy": {"happy", "fun", "cheerful", "feel good", "sunny"},
    "sad": {"sad", "melancholy", "emotional", "heartbreak", "blue"},
    "chill": {"chill", "relaxing", "calm", "downtempo", "smooth"},
    "intense": {"aggressive", "intense", "dark", "heavy", "angry", "epic"},
    "romantic": {"romantic", "love", "sensual"},
    "dark": {"dark", "gothic", "ominous"},
    "uplifting": {"uplifting", "inspiring", "empowering", "anthem"},
    "nostalgic": {"nostalgic", "retro", "vintage"},
    "party": {"party", "club", "dance"},
}


def mood_scores_from_bpm_data(data: dict) -> dict:
    """Infer mood scores from BPM-related audio features."""
    # pylint: disable=too-many-branches, too-many-statements
    bpm = data.get("bpm")
    key = (data.get("key") or "").lower()
    dance = data.get("danceability", 0)
    acoustic = data.get("acousticness", 0)
    year = data.get("year")

    scores = {mood: 0.0 for mood in MOOD_TAGS}
    logger.debug(
        "   BPM: %s, Key: %s, Danceability: %s, Acousticness: %s, Year: %s",
        bpm,
        key,
        dance,
        acoustic,
        year,
    )

    # --- Primary rules (high-confidence) ---
    if bpm and 110 <= bpm <= 140 and dance > 65 and acoustic < 40:
        scores["party"] += 1.0
        logger.debug(
            "  +1.0 party (strong match: bpm 110–140, high danceability, low acousticness)"
        )

    if bpm and bpm < 95 and acoustic > 50 and dance < 55:
        scores["chill"] += 1.0
        logger.debug("  +1.0 chill (strong match: slow, acoustic, low danceability)")

    if bpm and bpm > 125 and acoustic < 30 and dance > 55:
        scores["intense"] += 1.0
        logger.debug("  +1.0 intense (strong match: fast, synthetic, danceable)")

    if bpm and bpm < 95 and acoustic > 55 and "m" not in key:
        scores["romantic"] += 1.0
        logger.debug("  +1.0 romantic (strong match: slow, acoustic, major key)")

    if bpm and bpm > 95 and "m" not in key and acoustic < 50 and dance > 55:
        scores["uplifting"] += 1.0
        logger.debug("  +1.0 uplifting (strong match: upbeat, major key, synthetic, danceable)")

    if year and year < 2005 and acoustic > 45 and bpm and bpm < 105:
        scores["nostalgic"] += 1.0
        logger.debug("  +1.0 nostalgic (strong match: pre-2005, mellow, acoustic)")

    if bpm and bpm < 115 and "m" in key and acoustic < 40:
        scores["dark"] += 1.0
        logger.debug("  +1.0 dark (strong match: slow, minor key, synthetic)")

    if bpm and bpm > 105 and "m" not in key and dance > 55:
        scores["happy"] += 1.0
        logger.debug("  +1.0 happy (strong match: fast, major key, danceable)")

    if bpm and bpm < 90 and "m" in key and dance < 55:
        scores["sad"] += 1.0
        logger.debug("  +1.0 sad (strong match: slow, minor key, low danceability)")

    # --- Fallback rules (low-confidence signals, +0.5) ---

    if bpm:
        if bpm > 130:
            scores["intense"] += 0.5
            logger.debug("  +0.5 intense (fallback: bpm > 130)")
        if bpm > 110:
            scores["happy"] += 0.5
            logger.debug("  +0.5 happy (fallback: bpm > 110)")
        if 90 <= bpm <= 110:
            scores["uplifting"] += 0.5
            logger.debug("  +0.5 uplifting (fallback: mid-tempo)")
        if bpm < 90:
            scores["chill"] += 0.5
            logger.debug("  +0.5 chill (fallback: bpm < 90)")
        if bpm < 80:
            scores["sad"] += 0.5
            logger.debug("  +0.5 sad (fallback: bpm < 80)")

    if acoustic > 60:
        scores["chill"] += 0.5
        scores["romantic"] += 0.5
        logger.debug("  +0.5 chill, +0.5 romantic (fallback: acousticness > 60)")
    elif acoustic < 20:
        scores["intense"] += 0.5
        logger.debug("  +0.5 intense (fallback: acousticness < 20)")

    if dance > 70:
        scores["party"] += 0.5
        scores["happy"] += 0.5
        logger.debug("  +0.5 party, +0.5 happy (fallback: danceability > 70)")
    elif dance < 30:
        scores["sad"] += 0.5
        scores["chill"] += 0.5
        logger.debug("  +0.5 sad, +0.5 chill (fallback: danceability < 30)")
    return scores

# Apply mood-specific weightings
MOOD_WEIGHTS = {
    "happy": 0.9,
    "sad": 1.0,
    "chill": 1.0,
    "intense": 1.0,
    "romantic": 1.2,
    "dark": 1.2,
    "uplifting": 1.3,
    "nostalgic": 1.3,
    "party": 1.3,
}


LYRICS_WEIGHT = settings.lyrics_weight
BPM_WEIGHT = settings.bpm_weight
TAGS_WEIGHT = settings.tags_weight
DEFAULT_LYRICS_CONFIDENCE = 1  # Confidence assigned to GPT-derived mood

MOOD_MAPPING = {
    "happy": "happy",
    "sad": "sad",
    "melancholy": "sad",
    "chill": "chill",
    "relaxing": "chill",
    "calm": "chill",
    "angry": "intense",
    "aggressive": "intense",
    "romantic": "romantic",
    "dark": "dark",
    "uplifting": "uplifting",
    "nostalgic": "nostalgic",
    "party": "party",
    "hopeful": "uplifting"
}

def map_lyrics_mood_to_internal_mood(lyrics_mood: str) -> str:
    """Convert a raw lyrics mood string to an internal mood label."""
    mood = lyrics_mood.strip().lower()
    return MOOD_MAPPING.get(mood)

def build_lyrics_scores(lyrics_mood: str) -> dict:
    """Return a mood score dictionary derived from lyrics analysis."""
    scores = {mood: 0.0 for mood in MOOD_TAGS}
    mapped_mood = map_lyrics_mood_to_internal_mood(lyrics_mood)
    if mapped_mood:
        scores[mapped_mood] = DEFAULT_LYRICS_CONFIDENCE
    return scores

# Updated combine_mood_scores()
def combine_mood_scores(
    tag_scores: dict,
    bpm_scores: dict,
    lyrics_scores: dict | None = None,
) -> tuple[str, float]:
    """Merge mood scores from tags, BPM analysis and optional lyrics."""
    # pylint: disable=too-many-locals
    logger.info("\n→ Combining mood scores from Last.fm tags, BPM data, and Lyrics mood:")
    logger.info("  Raw Tag Scores: %s", tag_scores)
    logger.info("  Raw BPM Scores: %s", bpm_scores)
    logger.info("  Raw Lyrics Scores: %s", lyrics_scores)



    tag_sum = sum(tag_scores.values())
    bpm_sum = sum(bpm_scores.values())
    lyrics_sum = sum(lyrics_scores.values()) if lyrics_scores else 0

    # Boost single-source if no other contributors
    if tag_sum > 0 and bpm_sum == 0 and lyrics_sum == 0:
        tag_scores = {m: s * 1.5 for m, s in tag_scores.items()}
    if bpm_sum > 0 and tag_sum == 0 and lyrics_sum == 0:
        bpm_scores = {m: s * 1.5 for m, s in bpm_scores.items()}
    if lyrics_sum > 0 and tag_sum == 0 and bpm_sum == 0:
        lyrics_scores = {m: s * 1.5 for m, s in lyrics_scores.items()}

    # Combine with weighting:
    combined = {}
    for mood in MOOD_TAGS:
        score = (
            TAGS_WEIGHT * tag_scores.get(mood, 0) +
            BPM_WEIGHT * bpm_scores.get(mood, 0) +
            (LYRICS_WEIGHT * lyrics_scores.get(mood, 0) if lyrics_scores else 0)
        )
        weighted = score * MOOD_WEIGHTS.get(mood, 1.0)
        combined[mood] = weighted

    # Filter top 3 moods
    sorted_moods = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    filtered = dict(sorted_moods[:3])
    logger.debug("Filtered mood scores: %s", filtered)
    if not filtered or max(filtered.values()) < 0.3:
        logger.warning("← Final Mood: unknown (no strong scores)\n")
        return "unknown", 0.0

    # Softmax confidence
    exp_scores = {m: math.exp(s) for m, s in filtered.items()}
    total_exp = sum(exp_scores.values())
    top_mood = max(exp_scores, key=exp_scores.get)
    confidence = exp_scores[top_mood] / total_exp

    # Optional confidence bump if dominant
    top_two = sorted(filtered.values(), reverse=True)[:2]
    if len(top_two) == 2 and top_two[0] >= 1.5 * top_two[1] and confidence < 0.6:
        confidence = max(confidence, 0.6)

    # Tie-breaking with preferred order
    preferred_order = [
        "romantic", "chill", "uplifting", "party",
        "happy", "nostalgic", "sad", "dark", "intense"
    ]
    top_score = max(filtered.values())
    top_moods = [m for m, s in filtered.items() if s == top_score]
    best_mood = next((m for m in preferred_order if m in top_moods), top_mood)

    logger.info(
        "← Final Mood: %s (softmax confidence: %.2f)\n",
        best_mood,
        confidence,
    )
    return best_mood, round(confidence, 2)

def mood_scores_from_lastfm_tags(tags: list[str]) -> dict:
    """Calculate mood scores from a list of Last.fm tags."""
    if not isinstance(tags, list) or not tags:
        return {mood: 0.0 for mood in MOOD_TAGS}

    scores = {mood: 0.0 for mood in MOOD_TAGS}

    for tag in tags:
        tag_lower = tag.lower().strip()
        tag_lower = re.sub(r"[^a-z0-9\s\-]", "", tag_lower)
        matched = False

        for mood, keywords in MOOD_TAGS.items():
            for keyword in keywords:
                if mood == "party":
                    if tag_lower == keyword:
                        scores[mood] += 1.0
                        matched = True
                        break
                else:
                    if keyword in tag_lower:
                        scores[mood] += 1.0
                        matched = True
                        break
            if matched:
                break

    return scores
