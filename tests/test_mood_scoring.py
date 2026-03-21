"""Tests for mood scoring helpers in ``core.analysis``."""

from core.analysis import (
    mood_scores_from_lastfm_tags,
    mood_scores_from_bpm_data,
    combine_mood_scores,
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
