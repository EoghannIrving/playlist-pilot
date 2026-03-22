"""Backend-agnostic media-server contracts and normalized data shapes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict


class NormalizedTrack(TypedDict):
    """Canonical track shape adapters should return."""

    id: str
    title: str
    artist: str
    artists: list[str]
    album: str | None
    year: int | None
    genres: list[str]
    duration_seconds: int | None
    play_count: int
    path: str | None
    lyrics: str | None
    backend: str
    backend_item_id: str


class NormalizedPlaylist(TypedDict):
    """Canonical playlist shape adapters should return."""

    id: str
    name: str
    track_count: int | None
    backend: str


class NormalizedUser(TypedDict):
    """Canonical user shape adapters should return."""

    id: str
    name: str


class MediaServer(ABC):
    """Abstract interface for media-server adapters."""

    @abstractmethod
    def backend_name(self) -> str:
        """Return the adapter backend name."""

    @abstractmethod
    def requires_user_id(self) -> bool:
        """Return whether the backend requires an explicit user ID."""

    @abstractmethod
    def supports_lyrics(self) -> bool:
        """Return whether the backend can provide lyrics."""

    @abstractmethod
    def supports_path_resolution(self) -> bool:
        """Return whether the backend can resolve filesystem paths."""

    @abstractmethod
    async def test_connection(self) -> dict:
        """Validate backend connectivity and credentials."""

    @abstractmethod
    async def list_users(self) -> list[NormalizedUser]:
        """Return available backend users."""

    @abstractmethod
    async def list_audio_playlists(self) -> list[NormalizedPlaylist]:
        """Return audio playlists visible to the current backend context."""

    @abstractmethod
    async def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        """Return detailed tracks for a playlist."""

    @abstractmethod
    async def search_track(self, title: str, artist: str) -> bool:
        """Return whether a track exists in the backend library."""

    @abstractmethod
    async def get_track_metadata(self, title: str, artist: str) -> dict | None:
        """Return backend metadata for a matching track."""

    @abstractmethod
    async def get_full_audio_library(self, force_refresh: bool = False) -> list[str]:
        """Return the user's full audio library."""

    @abstractmethod
    async def get_lyrics(self, item_id: str) -> str | None:
        """Return lyrics for an item if available."""

    @abstractmethod
    async def create_playlist(self, name: str, track_ids: list[str]) -> dict | None:
        """Create a playlist and return backend-specific metadata."""

    @abstractmethod
    async def update_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> dict | None:
        """Update a playlist and return backend-specific metadata."""

    @abstractmethod
    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist."""

    @abstractmethod
    async def add_track_to_playlist(self, playlist_id: str, track_id: str) -> dict:
        """Add a single track to a playlist and return status metadata."""

    @abstractmethod
    async def resolve_track_path(self, title: str, artist: str) -> str | None:
        """Return the filesystem path for a track when supported."""

    @abstractmethod
    async def trigger_library_scan(self) -> dict:
        """Trigger a backend library scan when supported."""
