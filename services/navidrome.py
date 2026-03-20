"""Navidrome media-server adapter using the Subsonic-compatible API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from typing import Any

import httpx

from config import settings
from services.media_server import MediaServer, NormalizedPlaylist, NormalizedUser
from utils.http_client import get_http_client

logger = logging.getLogger("playlist-pilot")

_API_VERSION = "1.16.1"
_CLIENT_NAME = "playlist-pilot"


def _navidrome_url() -> str:
    """Return the active Navidrome base URL."""
    return settings.media_url.rstrip("/")


def _navidrome_username() -> str:
    """Return the active Navidrome username."""
    return settings.media_username


def _navidrome_password() -> str:
    """Return the active Navidrome password."""
    return settings.media_password


class NavidromeAdapter(MediaServer):
    """Media-server adapter for Navidrome."""

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._url = (url or _navidrome_url()).rstrip("/")
        self._username = username or _navidrome_username()
        self._password = password or _navidrome_password()

    def backend_name(self) -> str:
        return "navidrome"

    def requires_user_id(self) -> bool:
        return False

    def supports_lyrics(self) -> bool:
        return True

    def supports_path_resolution(self) -> bool:
        return True

    def _auth_params(self) -> dict[str, str]:
        salt = secrets.token_hex(3)
        token = hashlib.md5(
            f"{self._password}{salt}".encode("utf-8")
        ).hexdigest()  # nosec B324
        return {
            "u": self._username,
            "t": token,
            "s": salt,
            "v": _API_VERSION,
            "c": _CLIENT_NAME,
            "f": "json",
        }

    async def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        url = f"{self._url}/rest/{endpoint}.view"
        client = get_http_client(short=True)
        response = await client.get(url, params={**self._auth_params(), **params})
        response.raise_for_status()
        data = response.json()
        payload = data.get("subsonic-response", {})
        error = payload.get("error")
        if error:
            raise httpx.HTTPStatusError(
                error.get("message", "Navidrome API error"),
                request=response.request,
                response=response,
            )
        return payload

    @staticmethod
    def _duration_seconds(song: dict[str, Any]) -> int | None:
        duration = song.get("duration")
        if isinstance(duration, int):
            return duration
        return None

    @staticmethod
    def _year(song: dict[str, Any]) -> int | None:
        year = song.get("year")
        if isinstance(year, int):
            return year
        return None

    @staticmethod
    def _artists(song: dict[str, Any]) -> list[str]:
        artists = song.get("artists")
        if isinstance(artists, list):
            return [artist for artist in artists if isinstance(artist, str)]
        artist = song.get("artist")
        if isinstance(artist, str) and artist.strip():
            return [artist]
        return []

    def _normalize_song(self, song: dict[str, Any]) -> dict[str, Any]:
        """Return a Jellyfin-compatible track shape from a Navidrome song."""
        artists = self._artists(song)
        title = str(song.get("title", "")).strip()
        album = str(song.get("album", "")).strip()
        genre = str(song.get("genre", "")).strip()
        item_id = str(song.get("id", "")).strip()
        duration_seconds = self._duration_seconds(song) or 0
        play_count = song.get("playCount")

        return {
            "Id": item_id or None,
            "PlaylistItemId": item_id or None,
            "Name": title,
            "SortName": title,
            "AlbumArtist": (
                artists[0] if artists else str(song.get("artist", "")).strip()
            ),
            "Artists": artists,
            "Artist": str(song.get("artist", "")).strip(),
            "Album": album,
            "Genres": [genre] if genre else [],
            "ProductionYear": self._year(song),
            "PremiereDate": None,
            "RunTimeTicks": duration_seconds * 10_000_000,
            "Path": song.get("path"),
            "lyrics": song.get("lyrics"),
            "UserData": {"PlayCount": play_count if isinstance(play_count, int) else 0},
            "backend": self.backend_name(),
            "backend_item_id": item_id or None,
        }

    @staticmethod
    def _needs_song_hydration(song: dict[str, Any]) -> bool:
        """Return whether a playlist entry is missing useful metadata."""
        return not (
            song.get("genre")
            and song.get("duration")
            and song.get("year")
            and song.get("artist")
            and song.get("title")
        )

    async def _hydrate_song(self, song: dict[str, Any]) -> dict[str, Any]:
        """Fetch a full song record when a playlist entry is sparse."""
        if not self._needs_song_hydration(song):
            return song
        item_id = str(song.get("id", "")).strip()
        if not item_id:
            return song
        try:
            data = await self._get("getSong", id=item_id)
            full_song = data.get("song", {})
            if isinstance(full_song, dict) and full_song.get("id"):
                merged = dict(song)
                merged.update(full_song)
                return merged
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning("Failed to hydrate Navidrome song %s: %s", item_id, exc)
        return song

    async def test_connection(self) -> dict:
        """Verify Navidrome connectivity using current settings."""
        try:
            data = await self._get("ping")
            return {"success": data.get("status") == "ok", "status": 200, "data": data}
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.error("Navidrome connection test failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def list_users(self) -> list[NormalizedUser]:
        """Return users when available, otherwise fall back to the authenticated user."""
        try:
            data = await self._get("getUsers")
            users = data.get("users", {}).get("user", [])
            if isinstance(users, dict):
                users = [users]
            return [
                {"id": user.get("username", ""), "name": user.get("username", "")}
                for user in users
                if isinstance(user, dict) and user.get("username")
            ]
        except (httpx.HTTPError, json.JSONDecodeError):
            if self._username:
                return [{"id": self._username, "name": self._username}]
            return []

    async def list_audio_playlists(self) -> list[NormalizedPlaylist]:
        """Return all visible Navidrome playlists in normalized form."""
        try:
            data = await self._get("getPlaylists")
            playlists = data.get("playlists", {}).get("playlist", [])
            if isinstance(playlists, dict):
                playlists = [playlists]
            return [
                {
                    "id": playlist.get("id", ""),
                    "name": playlist.get("name", ""),
                    "track_count": playlist.get("songCount"),
                    "backend": self.backend_name(),
                }
                for playlist in playlists
                if isinstance(playlist, dict) and playlist.get("id")
            ]
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.error("Failed to list Navidrome playlists: %s", exc)
            return []

    async def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        """Return track entries for a playlist."""
        try:
            data = await self._get("getPlaylist", id=playlist_id)
            playlist = data.get("playlist", {})
            entries = playlist.get("entry", [])
            if isinstance(entries, dict):
                entries = [entries]
            hydrated_entries = await self._hydrate_playlist_entries(entries)
            return [
                self._normalize_song(entry)
                for entry in hydrated_entries
                if isinstance(entry, dict)
            ]
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.error("Failed to fetch Navidrome playlist %s: %s", playlist_id, exc)
            return []

    async def _hydrate_playlist_entries(
        self, entries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Hydrate sparse playlist entries using ``getSong``."""
        return await asyncio.gather(
            *[self._hydrate_song(entry) for entry in entries if isinstance(entry, dict)]
        )

    async def search_track(self, title: str, artist: str) -> bool:
        """Return whether a track exists in the library."""
        return await self.get_track_metadata(title, artist) is not None

    async def get_track_metadata(self, title: str, artist: str) -> dict | None:
        """Return metadata for the best matching track."""
        try:
            data = await self._get("search3", query=f"{title} {artist}", songCount=10)
            songs = data.get("searchResult3", {}).get("song", [])
            if isinstance(songs, dict):
                songs = [songs]
            title_lower = title.strip().lower()
            artist_lower = artist.strip().lower()
            for song in songs:
                if not isinstance(song, dict):
                    continue
                song_title = str(song.get("title", "")).lower()
                song_artist = str(song.get("artist", "")).lower()
                if title_lower in song_title and artist_lower in song_artist:
                    full_song = await self._hydrate_song(song)
                    return self._normalize_song(full_song)
            return None
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.error("Navidrome track metadata lookup failed: %s", exc)
            return None

    async def get_full_audio_library(self, force_refresh: bool = False) -> list[str]:
        """Return the user's full audio library using paged search results."""
        del force_refresh  # cache integration remains backend-agnostic for now
        items: list[str] = []
        offset = 0
        limit = settings.library_scan_limit
        while True:
            try:
                data = await self._get(
                    "search3",
                    query="",
                    songCount=limit,
                    songOffset=offset,
                )
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                logger.error("Navidrome full-library scan failed: %s", exc)
                return items
            songs = data.get("searchResult3", {}).get("song", [])
            if isinstance(songs, dict):
                songs = [songs]
            for song in songs:
                if isinstance(song, dict):
                    title = song.get("title")
                    artist = song.get("artist")
                    if isinstance(title, str) and isinstance(artist, str):
                        items.append(f"{title.strip()} - {artist.strip()}")
            if len(songs) < limit:
                break
            offset += limit
        return items

    async def get_lyrics(self, item_id: str) -> str | None:
        """Return lyrics for an item when available."""
        try:
            data = await self._get("getLyricsBySongId", id=item_id)
            lyrics = data.get("lyrics", {})
            value = lyrics.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning("Failed to fetch Navidrome lyrics for %s: %s", item_id, exc)
        return None

    async def create_playlist(self, name: str, track_ids: list[str]) -> dict | None:
        """Create a Navidrome playlist."""
        try:
            data = await self._get("createPlaylist", name=name, songId=track_ids)
            playlist = data.get("playlist", {})
            if isinstance(playlist, dict) and playlist.get("id"):
                return {"id": playlist["id"]}
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.error("Failed to create Navidrome playlist %s: %s", name, exc)
        return None

    async def update_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> dict | None:
        """Update is not implemented in the first Navidrome pass."""
        logger.warning(
            "Navidrome playlist update not implemented for playlist %s",
            playlist_id,
        )
        del track_ids
        return None

    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete is not implemented in the first Navidrome pass."""
        logger.warning(
            "Navidrome playlist delete not implemented for playlist %s",
            playlist_id,
        )
        return False

    async def resolve_track_path(self, title: str, artist: str) -> str | None:
        """Resolve a Navidrome track path via metadata lookup."""
        metadata = await self.get_track_metadata(title, artist)
        if isinstance(metadata, dict):
            path = metadata.get("Path")
            if isinstance(path, str) and path.strip():
                return path
        return None
