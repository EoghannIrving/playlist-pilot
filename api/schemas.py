"""Pydantic request and response models for API routes."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Schema for health check responses."""

    status: str


class LastfmTestRequest(BaseModel):
    """Request model for Last.fm API key validation."""

    key: str


class LastfmTestResponse(BaseModel):
    """Response model for Last.fm API key validation."""

    success: bool
    status: Optional[int] = None
    body: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class JellyfinTestRequest(BaseModel):
    """Request model for Jellyfin API validation."""

    url: str
    key: str


class JellyfinTestResponse(BaseModel):
    """Response model for Jellyfin API validation."""

    success: bool
    status: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class OpenAITestRequest(BaseModel):
    """Request model for OpenAI API key validation."""

    key: str


class OpenAITestResponse(BaseModel):
    """Response model for OpenAI API key validation."""

    success: bool
    error: Optional[str] = None


class GetSongBPMTestRequest(BaseModel):
    """Request model for GetSongBPM API key validation."""

    key: str


class GetSongBPMTestResponse(BaseModel):
    """Response model for GetSongBPM API key validation."""

    success: bool
    status: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class VerifyEntryRequest(BaseModel):
    """Request model for verifying playlist entries in Jellyfin."""

    playlist_id: str
    entry_id: str


class VerifyEntryResponse(BaseModel):
    """Response model for verifying playlist entries in Jellyfin."""

    success: bool
    track: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TagsResponse(BaseModel):
    """Response model for Last.fm tag debugging."""

    tags: List[str]


class TrackRef(BaseModel):
    """Reference to a track by title and artist."""

    artist: str
    title: str


class OrderSuggestionResponse(BaseModel):
    """Response model for GPT ordering suggestions."""

    ordered_tracks: List[TrackRef]


class ExportPlaylistResponse(BaseModel):
    """Response model for Jellyfin playlist exports."""

    status: str
    playlist_id: str


class AnalysisExportRequest(BaseModel):
    """Request model for exporting analysis results to M3U."""

    name: str
    tracks: List[TrackRef]


class TrackMetadata(BaseModel):
    """Partial metadata for a track."""

    title: str
    artist: str
    album: Optional[str] = None
    genre: Optional[str] = None
    mood: Optional[str] = None
    tempo: Optional[int] = None


class ExportTrackMetadataRequest(BaseModel):
    """Request model for exporting track metadata to Jellyfin."""

    track: TrackMetadata
    force_album_overwrite: bool = False
    skip_album: bool = False


class ExportTrackMetadataResponse(BaseModel):
    """Response model for exporting track metadata to Jellyfin."""

    message: Optional[str] = None
    error: Optional[str] = None
    action: Optional[str] = None
    current_album: Optional[str] = None
    suggested_album: Optional[str] = None
