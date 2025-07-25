"""Tests for functions in ``core.analysis``."""

from core.analysis import (
    combined_popularity_score,
    add_combined_popularity,
    summarize_tracks,
    percent_distribution,
    normalize_popularity,
    normalize_popularity_log,
    normalized_entropy,
    detect_outliers,
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


def test_add_combined_popularity_uniform_counts():
    """Uniform Jellyfin counts should yield full popularity."""
    tracks = [
        {"jellyfin_play_count": 5, "popularity": 100},
        {"jellyfin_play_count": 5, "popularity": 200},
    ]
    result = add_combined_popularity(tracks, w_lfm=0.0, w_jf=1.0)
    assert all(t["combined_popularity"] == 100 for t in result)


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


def test_summarize_tracks_empty_list():
    """Summarizing an empty list should return zeros without error."""
    summary = summarize_tracks([])
    assert summary["avg_listeners"] == 0
    assert summary["avg_popularity"] == 0


def test_percent_distribution_rounding():
    """Percentages should sum to 100 even with fractional parts."""
    result = percent_distribution(["a", "a", "b"])
    assert result == {"a": "67%", "b": "33%"}
    assert sum(int(v.rstrip("%")) for v in result.values()) == 100


def test_normalize_popularity_edge_cases():
    """Handle uniform value ranges correctly."""
    assert normalize_popularity(0, 0, 0) == 0
    assert normalize_popularity(5, 5, 5) == 100


def test_normalized_entropy_identical():
    """Entropy of identical values should be zero."""
    assert normalized_entropy(["rock", "rock", "rock"]) == 0.0


def test_normalize_popularity_log_bounds():
    """Edge cases for ``normalize_popularity_log`` should not error."""
    assert normalize_popularity_log(10, 0, 0) == 0
    assert normalize_popularity_log(10, -5, 5) == 0
    assert normalize_popularity_log(10, 5, 5) == 100


def test_detect_outliers_basic():
    """Tracks deviating from summary should be flagged."""
    tracks = [
        {
            "title": "Slow Song",
            "tempo": 50,
            "genre": "rock",
            "mood": "happy",
            "mood_confidence": 0.5,
            "popularity": 100,
        },
        {
            "title": "Weird Genre",
            "tempo": 110,
            "genre": "pop",
            "mood": "",
            "mood_confidence": 0.2,
            "popularity": 2,
            "year_flag": True,
        },
        {
            "title": "OK",
            "tempo": 100,
            "genre": "rock",
            "mood": "happy",
            "mood_confidence": 0.9,
            "popularity": 110,
        },
    ]
    summary = {"tempo_avg": 100, "dominant_genre": "rock", "avg_listeners": 100}
    outliers = detect_outliers(tracks, summary)
    assert len(outliers) == 2
    assert outliers[0]["title"] == "Weird Genre"
    assert set(outliers[0]["reasons"]) == {"genre", "mood", "popularity", "year"}
    assert outliers[1]["reasons"] == ["tempo"]


def test_detect_outliers_unknown_genre():
    """When dominant genre is unknown, genre mismatches are ignored."""
    tracks = [
        {
            "title": "Song",
            "tempo": 150,
            "genre": "pop",
            "mood": None,
            "mood_confidence": 0.1,
            "popularity": 1,
        }
    ]
    summary = {"tempo_avg": 100, "dominant_genre": "Unknown", "avg_listeners": 100}
    outliers = detect_outliers(tracks, summary)
    assert outliers[0]["title"] == "Song"
    assert "genre" not in outliers[0]["reasons"]
    assert set(outliers[0]["reasons"]) == {"tempo", "mood", "popularity"}
