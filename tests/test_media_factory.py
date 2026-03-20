"""Tests for media-server adapter selection."""

from services.jellyfin import JellyfinAdapter
from services.media_factory import get_media_server
from config import settings


def test_get_media_server_defaults_to_jellyfin(monkeypatch):
    """Default backend selection should return the Jellyfin adapter."""
    monkeypatch.setattr(settings, "media_backend", "jellyfin", raising=False)
    adapter = get_media_server()
    assert isinstance(adapter, JellyfinAdapter)


def test_get_media_server_rejects_unsupported_backend(monkeypatch):
    """Unknown backends should raise a clear error."""
    monkeypatch.setattr(settings, "media_backend", "unsupported", raising=False)
    try:
        get_media_server()
    except ValueError as exc:
        assert "Unsupported media backend" in str(exc)
    else:
        raise AssertionError("Expected unsupported backend to raise ValueError")


def test_get_media_server_uses_default_when_backend_empty(monkeypatch):
    """Empty backend values should fall back to Jellyfin."""
    monkeypatch.setattr(settings, "media_backend", "", raising=False)
    adapter = get_media_server()
    assert isinstance(adapter, JellyfinAdapter)
