"""Data models for playlist-pilot."""

from typing import List, Optional
from pydantic import BaseModel, Field

class Track(BaseModel):
    """Normalized track metadata."""

    raw: str = ""
    title: str
    artist: str
    album: str = ""
    year: str = ""
    Genres: List[str] = Field(default_factory=list)
    lyrics: Optional[str] = None
    tempo: Optional[int] = None
    RunTimeTicks: int = 0
    jellyfin_play_count: int = 0

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ``Track`` model."""
        extra = "allow"

class EnrichedTrack(Track):
    """Track metadata after enrichment."""

    tags: List[str] = Field(default_factory=list)
    genre: str = "Unknown"
    mood: str = "Unknown"
    mood_confidence: float = 0.0
    decade: str = "Unknown"
    duration: int = 0
    popularity: int = 0
    year_flag: str = ""
    combined_popularity: Optional[float] = None
    FinalYear: Optional[str] = None

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ``EnrichedTrack`` model."""
        extra = "allow"
