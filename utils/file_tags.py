"""Helpers for reading and writing audio file tags directly on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _require_mutagen() -> dict[str, Any]:
    """Import mutagen modules lazily so the app can still import without it."""
    # pylint: disable=import-outside-toplevel
    try:
        from mutagen import File  # type: ignore
        from mutagen.flac import FLAC  # type: ignore
        from mutagen.id3 import (  # type: ignore
            ID3,
            TALB,
            TBPM,
            TCON,
            TDRC,
            TIT2,
            TPE1,
            TPE2,
            TXXX,
        )
        from mutagen.mp4 import MP4  # type: ignore
        from mutagen.oggopus import OggOpus  # type: ignore
        from mutagen.oggvorbis import OggVorbis  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via route handling
        raise RuntimeError(
            "mutagen is required for direct file-tag export but is not installed."
        ) from exc

    return {
        "File": File,
        "FLAC": FLAC,
        "ID3": ID3,
        "TALB": TALB,
        "TBPM": TBPM,
        "TCON": TCON,
        "TDRC": TDRC,
        "TIT2": TIT2,
        "TPE1": TPE1,
        "TPE2": TPE2,
        "TXXX": TXXX,
        "MP4": MP4,
        "OggOpus": OggOpus,
        "OggVorbis": OggVorbis,
    }


def _coerce_tempo(value: Any) -> int | None:
    """Normalize a tempo value into an integer when possible."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _coerce_text(value: Any) -> str:
    """Return a normalized string for common tag payload shapes."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _coerce_text(item)
            if text:
                return text
        return ""
    text_attr = getattr(value, "text", None)
    if text_attr is not None:
        return _coerce_text(text_attr)
    return str(value).strip()


def read_track_tags(file_path: str) -> dict[str, Any]:
    """Read common editable tags from a local audio file."""
    # pylint: disable=too-many-locals,too-many-branches
    modules = _require_mutagen()
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Track file does not exist: {file_path}")

    File = modules["File"]
    FLAC = modules["FLAC"]
    ID3 = modules["ID3"]
    MP4 = modules["MP4"]
    OggOpus = modules["OggOpus"]
    OggVorbis = modules["OggVorbis"]

    audio = File(path)
    if audio is None:
        raise ValueError(f"Unsupported audio format for metadata export: {file_path}")

    result = {
        "title": "",
        "artist": "",
        "album": "",
        "album_artist": "",
        "genre": "",
        "year": "",
        "bpm": None,
        "mood": "",
        "path": str(path),
    }

    if isinstance(audio, MP4):
        result["title"] = _coerce_text(audio.get("\xa9nam"))
        result["artist"] = _coerce_text(audio.get("\xa9ART"))
        result["album"] = _coerce_text(audio.get("\xa9alb"))
        result["album_artist"] = _coerce_text(audio.get("aART"))
        result["genre"] = _coerce_text(audio.get("\xa9gen"))
        result["year"] = _coerce_text(audio.get("\xa9day"))
        result["bpm"] = _coerce_tempo(_coerce_text(audio.get("tmpo")))
        result["mood"] = _coerce_text(audio.get("----:com.apple.iTunes:MOOD"))
        return result

    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        result["title"] = _coerce_text(audio.get("title"))
        result["artist"] = _coerce_text(audio.get("artist"))
        result["album"] = _coerce_text(audio.get("album"))
        result["album_artist"] = _coerce_text(audio.get("albumartist"))
        result["genre"] = _coerce_text(audio.get("genre"))
        result["year"] = _coerce_text(audio.get("date")) or _coerce_text(
            audio.get("year")
        )
        result["bpm"] = _coerce_tempo(
            _coerce_text(audio.get("bpm")) or _coerce_text(audio.get("tempo"))
        )
        result["mood"] = _coerce_text(audio.get("mood"))
        return result

    tags = getattr(audio, "tags", None)
    if isinstance(tags, ID3):
        result["title"] = _coerce_text(tags.getall("TIT2"))
        result["artist"] = _coerce_text(tags.getall("TPE1"))
        result["album"] = _coerce_text(tags.getall("TALB"))
        result["album_artist"] = _coerce_text(tags.getall("TPE2"))
        result["genre"] = _coerce_text(tags.getall("TCON"))
        result["year"] = _coerce_text(tags.getall("TDRC"))
        result["bpm"] = _coerce_tempo(_coerce_text(tags.getall("TBPM")))
        result["mood"] = _coerce_text(tags.getall("TXXX:MOOD"))
        return result

    raise ValueError(f"Unsupported tag container for metadata export: {file_path}")


def write_track_tags(file_path: str, track: dict[str, Any]) -> None:
    """Write common editable tags to a local audio file."""
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements,invalid-name
    modules = _require_mutagen()
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Track file does not exist: {file_path}")

    File = modules["File"]
    FLAC = modules["FLAC"]
    ID3 = modules["ID3"]
    TALB = modules["TALB"]
    TBPM = modules["TBPM"]
    TCON = modules["TCON"]
    TDRC = modules["TDRC"]
    TIT2 = modules["TIT2"]
    TPE1 = modules["TPE1"]
    TPE2 = modules["TPE2"]
    TXXX = modules["TXXX"]
    MP4 = modules["MP4"]
    OggOpus = modules["OggOpus"]
    OggVorbis = modules["OggVorbis"]

    audio = File(path)
    if audio is None:
        raise ValueError(f"Unsupported audio format for metadata export: {file_path}")

    title = track.get("title")
    artist = track.get("artist")
    album = track.get("album")
    album_artist = track.get("album_artist")
    genre = track.get("genre")
    year = track.get("year")
    mood = track.get("mood")
    tempo = _coerce_tempo(track.get("tempo"))

    if isinstance(audio, MP4):
        if title:
            audio["\xa9nam"] = [str(title)]
        if artist:
            audio["\xa9ART"] = [str(artist)]
        if album:
            audio["\xa9alb"] = [str(album)]
        if album_artist:
            audio["aART"] = [str(album_artist)]
        if genre:
            audio["\xa9gen"] = [str(genre)]
        if year:
            audio["\xa9day"] = [str(year)]
        if tempo is not None:
            audio["tmpo"] = [tempo]
        if mood:
            audio["----:com.apple.iTunes:MOOD"] = [str(mood).encode("utf-8")]
        audio.save()
        return

    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        if title:
            audio["title"] = [str(title)]
        if artist:
            audio["artist"] = [str(artist)]
        if album:
            audio["album"] = [str(album)]
        if album_artist:
            audio["albumartist"] = [str(album_artist)]
        if genre:
            audio["genre"] = [str(genre)]
        if year:
            audio["date"] = [str(year)]
            audio["year"] = [str(year)]
        if tempo is not None:
            audio["bpm"] = [str(tempo)]
            audio["tempo"] = [str(tempo)]
        if mood:
            audio["mood"] = [str(mood)]
        audio.save()
        return

    tags = getattr(audio, "tags", None)
    if tags is None:
        try:
            audio.add_tags()
            tags = audio.tags
        except AttributeError as exc:
            raise ValueError(
                f"Unsupported tagged audio object for metadata export: {file_path}"
            ) from exc

    if isinstance(tags, ID3):
        if title:
            tags.setall("TIT2", [TIT2(encoding=3, text=[str(title)])])
        if artist:
            tags.setall("TPE1", [TPE1(encoding=3, text=[str(artist)])])
        if album:
            tags.setall("TALB", [TALB(encoding=3, text=[str(album)])])
        if album_artist:
            tags.setall("TPE2", [TPE2(encoding=3, text=[str(album_artist)])])
        if genre:
            tags.setall("TCON", [TCON(encoding=3, text=[str(genre)])])
        if year:
            tags.setall("TDRC", [TDRC(encoding=3, text=[str(year)])])
        if tempo is not None:
            tags.setall("TBPM", [TBPM(encoding=3, text=[str(tempo)])])
        if mood:
            tags.setall("TXXX:MOOD", [TXXX(encoding=3, desc="MOOD", text=[str(mood)])])
        audio.save()
        return

    raise ValueError(f"Unsupported tag container for metadata export: {file_path}")
