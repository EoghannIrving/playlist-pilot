"""Helpers for writing audio file tags directly on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _require_mutagen() -> dict[str, Any]:
    """Import mutagen modules lazily so the app can still import without it."""
    # pylint: disable=import-outside-toplevel
    try:
        from mutagen import File  # type: ignore
        from mutagen.flac import FLAC  # type: ignore
        from mutagen.id3 import ID3, TALB, TBPM, TCON, TXXX  # type: ignore
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


def write_track_tags(file_path: str, track: dict[str, Any]) -> None:
    """Write album, genre, mood, and tempo tags to a local audio file."""
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
    TXXX = modules["TXXX"]
    MP4 = modules["MP4"]
    OggOpus = modules["OggOpus"]
    OggVorbis = modules["OggVorbis"]

    audio = File(path)
    if audio is None:
        raise ValueError(f"Unsupported audio format for metadata export: {file_path}")

    genre = track.get("genre")
    album = track.get("album")
    mood = track.get("mood")
    tempo = _coerce_tempo(track.get("tempo"))

    if isinstance(audio, MP4):
        if album:
            audio["\xa9alb"] = [str(album)]
        if genre:
            audio["\xa9gen"] = [str(genre)]
        if tempo is not None:
            audio["tmpo"] = [tempo]
        if mood:
            audio["----:com.apple.iTunes:MOOD"] = [str(mood).encode("utf-8")]
        audio.save()
        return

    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        if album:
            audio["album"] = [str(album)]
        if genre:
            audio["genre"] = [str(genre)]
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
        if album:
            tags.setall("TALB", [TALB(encoding=3, text=[str(album)])])
        if genre:
            tags.setall("TCON", [TCON(encoding=3, text=[str(genre)])])
        if tempo is not None:
            tags.setall("TBPM", [TBPM(encoding=3, text=[str(tempo)])])
        if mood:
            tags.setall("TXXX:MOOD", [TXXX(encoding=3, desc="MOOD", text=[str(mood)])])
        audio.save()
        return

    raise ValueError(f"Unsupported tag container for metadata export: {file_path}")
