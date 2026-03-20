"""Factory for selecting the active media-server adapter."""

from __future__ import annotations

from config import settings
from services.jellyfin import JellyfinAdapter
from services.media_server import MediaServer


def get_media_server() -> MediaServer:
    """Return the configured media-server adapter."""
    backend = (settings.media_backend or "jellyfin").strip().lower()
    if backend == "jellyfin":
        return JellyfinAdapter()
    raise ValueError(f"Unsupported media backend: {backend}")
