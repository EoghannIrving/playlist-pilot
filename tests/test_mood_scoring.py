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
