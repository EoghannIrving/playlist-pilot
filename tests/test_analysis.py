"""Tests for functions in ``core.analysis``."""

from core.analysis import (
    combined_popularity_score,
    add_combined_popularity,
    summarize_tracks,
)


def test_combined_popularity_score_basic():
    """Ensure combined score averages properly and handles ``None``."""
    assert combined_popularity_score(50, 50) == 50
    assert combined_popularity_score(None, 80) == 80
    assert combined_popularity_score(40, None) == 40
    assert combined_popularity_score(None, None) is None


def test_add_combined_popularity():
    """Verify ``combined_popularity`` field is added to all tracks."""
    tracks = [
        {"jellyfin_play_count": 10, "popularity": 5000},
        {"jellyfin_play_count": 20, "popularity": 10000},
    ]
    result = add_combined_popularity(tracks, w_lfm=0.5, w_jf=0.5)
    assert all("combined_popularity" in t for t in result)


def test_summarize_tracks_basic():
    """Summarize a small list of tracks and validate statistics."""
    tracks = [
        {
            "genre": "rock",
            "mood": "happy",
            "tempo": 120,
            "decade": "2000s",
            "combined_popularity": 60,
            "popularity": 100,
            "title": "A",
        },
        {
            "genre": "rock",
            "mood": "happy",
            "tempo": 126,
            "decade": "2000s",
            "combined_popularity": 70,
            "popularity": 120,
            "title": "B",
        },
    ]
    summary = summarize_tracks(tracks)
    assert summary["dominant_genre"] == "rock"
    assert summary["tempo_avg"] == 123
    assert summary["avg_popularity"] == 65
