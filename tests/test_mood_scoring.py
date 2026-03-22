"""Tests for mood scoring helpers in ``core.analysis``."""

from core.analysis import (
    combine_mood_scores,
    build_lyrics_scores,
    map_lyrics_mood_to_internal_mood,
    mood_scores_from_bpm_data,
    mood_scores_from_context,
    mood_scores_from_lastfm_tags,
)


def test_mood_scores_from_lastfm_tags_basic():
    """Tags should increment expected mood buckets."""
    tags = ["Happy", "Dance", "Party", "Dark vibe"]
    scores = mood_scores_from_lastfm_tags(tags)
    assert scores["happy"] == 1.0
    assert scores["party"] == 2.0
    assert scores["intense"] == 1.0
    zero_moods = [m for m in scores if m not in {"happy", "party", "intense"}]
    assert all(scores[m] == 0.0 for m in zero_moods)


def test_mood_scores_from_bpm_data_party_happy():
    """BPM and related features should infer party and happy moods."""
    data = {"bpm": 120, "key": "C", "danceability": 80, "acousticness": 20}
    scores = mood_scores_from_bpm_data(data)
    assert scores["party"] == 1.5
    assert scores["happy"] == 2.0
    assert scores["uplifting"] == 1.0


def test_combine_mood_scores_returns_dominant_mood():
    """Combining tag and BPM scores should yield the dominant mood."""
    tags = mood_scores_from_lastfm_tags(["Happy", "Dance", "Party", "Dark vibe"])
    bpm = mood_scores_from_bpm_data(
        {"bpm": 120, "key": "C", "danceability": 80, "acousticness": 20}
    )
    mood, confidence = combine_mood_scores(tags, bpm)
    assert mood == "party"
    assert 0.7 < confidence < 0.8


def test_combine_mood_scores_no_signal():
    """No mood signals should return 'unknown'."""
    empty = {m: 0.0 for m in mood_scores_from_lastfm_tags([])}
    mood, confidence = combine_mood_scores(empty, empty)
    assert mood == "unknown"
    assert confidence == 0.0


def test_combine_mood_scores_single_weak_signal_returns_unknown():
    """A single weak mood cue should not force a confident classification."""
    tags = mood_scores_from_lastfm_tags(["smooth"])
    empty = {m: 0.0 for m in mood_scores_from_lastfm_tags([])}
    mood, confidence = combine_mood_scores(tags, empty)
    assert mood == "unknown"
    assert confidence == 0.0


def test_mood_scores_from_bpm_data_missing_audio_features_do_not_fabricate_chill():
    """Missing danceability/acousticness should not create fallback chill scores."""
    scores = mood_scores_from_bpm_data({"bpm": 100, "year": 1984})
    assert scores["chill"] == 0.0
    assert scores["sad"] == 0.0
    assert scores["uplifting"] == 0.5


def test_mood_scores_from_lastfm_tags_support_romantic_and_nostalgic_language():
    """Broader descriptive tags should feed specific moods instead of generic chill."""
    tags = ["dreamy", "tender", "wistful", "reflective"]
    scores = mood_scores_from_lastfm_tags(tags)
    assert scores["romantic"] >= 2.0
    assert scores["nostalgic"] >= 2.0
    assert scores["chill"] == 0.0


def test_combine_mood_scores_prefers_romantic_over_generic_chill():
    """Specific romantic evidence should beat weak chill-style fallback cues."""
    tag_scores = mood_scores_from_lastfm_tags(["dreamy", "tender"])
    bpm_scores = mood_scores_from_bpm_data({"bpm": 100, "year": 1984})
    mood, confidence = combine_mood_scores(tag_scores, bpm_scores)
    assert mood == "romantic"
    assert confidence > 0.5


def test_mood_scores_from_context_support_80s_new_wave_ballads():
    """Genre and era context should provide a useful prior for sparse-tag 80s tracks."""
    scores = mood_scores_from_context(["new wave", "pop"], 1982, 100)
    assert scores["romantic"] >= 1.2
    assert scores["nostalgic"] >= 0.5
    assert scores["chill"] == 0.0


def test_combine_mood_scores_uses_context_when_tags_and_lyrics_are_sparse():
    """Context should prevent good 80s fits from collapsing to unknown."""
    empty = {m: 0.0 for m in mood_scores_from_lastfm_tags([])}
    context = mood_scores_from_context(["new wave", "pop"], 1982, 100)
    mood, confidence = combine_mood_scores(empty, empty, None, context)
    assert mood in {"romantic", "nostalgic"}
    assert confidence > 0.5


def test_combine_mood_scores_context_can_resolve_80s_rock_tracks():
    """Rock-era context should surface a useful mood without reverting to chill."""
    empty = {m: 0.0 for m in mood_scores_from_lastfm_tags([])}
    context = mood_scores_from_context(["rock"], 1985, 120)
    mood, confidence = combine_mood_scores(empty, empty, None, context)
    assert mood == "uplifting"
    assert confidence > 0.4


def test_mood_scores_from_context_support_energetic_new_wave_tracks():
    """Fast 80s new-wave tracks should lean party/uplifting more than nostalgic."""
    scores = mood_scores_from_context(["new wave", "synthpop"], 1985, 128)
    assert scores["party"] >= 0.9
    assert scores["uplifting"] >= 0.4
    assert scores["nostalgic"] <= 0.6


def test_combine_mood_scores_context_can_resolve_party_like_80s_new_wave():
    """High-energy synth/new-wave context should not collapse to nostalgic by default."""
    empty = {m: 0.0 for m in mood_scores_from_lastfm_tags([])}
    context = mood_scores_from_context(["new wave", "synthpop"], 1985, 128)
    mood, confidence = combine_mood_scores(empty, empty, None, context)
    assert mood in {"party", "uplifting"}
    assert confidence > 0.35


def test_mood_scores_from_context_support_modern_folk_tracks():
    """Modern folk and celtic tracks should not collapse to zero context."""
    scores = mood_scores_from_context(["folk", "celtic"], 2024, 100)
    assert scores["nostalgic"] >= 1.3
    assert scores["uplifting"] >= 1.2
    assert scores["romantic"] >= 0.4


def test_combine_mood_scores_context_can_resolve_modern_folk_tracks():
    """Strong folk/celtic context should produce a usable mood for sparse metadata tracks."""
    empty = {m: 0.0 for m in mood_scores_from_lastfm_tags([])}
    context = mood_scores_from_context(["folk", "celtic"], 2024, 100)
    mood, confidence = combine_mood_scores(empty, empty, None, context)
    assert mood in {"nostalgic", "uplifting"}
    assert confidence > 0.4


def test_map_lyrics_mood_to_internal_mood_supports_broader_labels():
    """Broader GPT lyric labels should map to internal moods cleanly."""
    assert map_lyrics_mood_to_internal_mood("wistful") == "nostalgic"
    assert map_lyrics_mood_to_internal_mood("reflective") == "nostalgic"
    assert map_lyrics_mood_to_internal_mood("yearning") == "romantic"
    assert map_lyrics_mood_to_internal_mood("dramatic") == "intense"
    assert map_lyrics_mood_to_internal_mood("melancholic") == "sad"


def test_build_lyrics_scores_uses_mapped_label():
    """Mapped lyric moods should contribute to the correct bucket."""
    scores = build_lyrics_scores("reflective")
    assert scores["nostalgic"] == 1
    assert scores["romantic"] == 0
