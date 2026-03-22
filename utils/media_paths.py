"""Helpers for resolving media-library file paths safely."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from config import settings


def configured_library_root() -> Path:
    """Return the most plausible configured music library root for this runtime."""
    configured = Path(settings.music_library_root).expanduser()
    if configured.is_absolute():
        return configured.resolve()

    direct_root = Path("/") / configured
    if direct_root.exists():
        return direct_root.resolve()
    return configured.resolve()


def normalize_path_component(value: str) -> str:
    """Return a comparison-safe representation for filesystem path components."""
    normalized = unicodedata.normalize("NFKC", value)
    replacements = {
        "…": "...",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        ":": " ",
        "(": " ",
        ")": " ",
        "[": " ",
        "]": " ",
        "_": " ",
    }
    for src, dst in replacements.items():
        normalized = normalized.replace(src, dst)
    return " ".join(normalized.casefold().split())


def component_tokens(value: str) -> set[str]:
    """Return significant tokens for fuzzy component matching."""
    normalized = normalize_path_component(value)
    normalized = normalized.replace("-", " ")
    normalized = normalized.replace(".", " ")
    tokens = {
        token
        for token in normalized.split()
        if token and len(token) > 1
    }
    stop_words = {
        "the",
        "and",
        "of",
        "edition",
        "deluxe",
        "expanded",
        "remastered",
        "version",
        "disc",
        "cd",
    }
    return {token for token in tokens if token not in stop_words}


def normalize_filename_stem(value: str) -> str:
    """Return a comparison-safe representation for track filenames."""
    normalized = normalize_path_component(value)
    normalized = normalized.rsplit(".", 1)[0]
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace(" - ", " ")
    normalized = normalized.replace("-", " ")
    normalized = normalized.replace("(", " ").replace(")", " ")
    normalized = normalized.replace("[", " ").replace("]", " ")
    normalized = " ".join(normalized.split())
    normalized = normalized.replace(" the lightning seeds ", " ")
    normalized = normalized.strip()
    normalized = normalized.lstrip("0123456789. -")
    normalized = " ".join(normalized.split())
    return normalized


def filename_tokens(value: str) -> set[str]:
    """Return significant filename tokens for fuzzy matching within an album directory."""
    normalized = normalize_filename_stem(value)
    tokens = {
        token
        for token in normalized.split()
        if token and not token.isdigit() and len(token) > 1
    }
    stop_words = {
        "the",
        "and",
        "of",
        "are",
        "made",
        "this",
        "feat",
        "featuring",
        "remaster",
        "remastered",
        "version",
        "edit",
        "mix",
        "album",
        "collection",
    }
    return {token for token in tokens if token not in stop_words}


def resolve_filename_variant(candidate: Path) -> Path:
    """Return a unique audio-file match from the parent directory when possible."""
    parent = candidate.parent
    if not parent.exists() or not parent.is_dir():
        return candidate

    audio_extensions = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac"}
    target_stem = normalize_filename_stem(candidate.name)
    matches = [
        entry
        for entry in parent.iterdir()
        if entry.is_file()
        and entry.suffix.lower() in audio_extensions
        and normalize_filename_stem(entry.name) == target_stem
    ]
    if len(matches) == 1:
        return matches[0]

    target_tokens = filename_tokens(candidate.name)
    if not target_tokens:
        return candidate

    scored_matches: list[tuple[int, Path]] = []
    for entry in parent.iterdir():
        if not entry.is_file() or entry.suffix.lower() not in audio_extensions:
            continue
        entry_tokens = filename_tokens(entry.name)
        if not entry_tokens:
            continue
        overlap = len(target_tokens & entry_tokens)
        if overlap:
            scored_matches.append((overlap, entry))

    if scored_matches:
        scored_matches.sort(key=lambda item: item[0], reverse=True)
        best_score = scored_matches[0][0]
        best_matches = [entry for score, entry in scored_matches if score == best_score]
        if len(best_matches) == 1 and best_score >= max(1, len(target_tokens) - 1):
            return best_matches[0]
    return candidate


def resolve_path_component_variants(candidate: Path, library_root: Path) -> Path:
    """Resolve a path by matching each component against real directory entries."""
    parts = candidate.parts
    root_parts = library_root.parts
    if parts[: len(root_parts)] != root_parts:
        return candidate

    current = Path(*root_parts)
    for component in parts[len(root_parts) :]:
        next_path = current / component
        if next_path.exists():
            current = next_path
            continue
        if not current.exists() or not current.is_dir():
            return candidate

        normalized_component = normalize_path_component(component)
        matches = [
            entry
            for entry in current.iterdir()
            if normalize_path_component(entry.name) == normalized_component
        ]
        if len(matches) == 1:
            current = matches[0]
            continue

        target_tokens = component_tokens(component)
        if not target_tokens:
            return candidate

        scored_matches: list[tuple[int, Path]] = []
        for entry in current.iterdir():
            entry_tokens = component_tokens(entry.name)
            if not entry_tokens:
                continue
            overlap = len(target_tokens & entry_tokens)
            if overlap:
                scored_matches.append((overlap, entry))

        if not scored_matches:
            return candidate

        scored_matches.sort(key=lambda item: item[0], reverse=True)
        best_score = scored_matches[0][0]
        best_matches = [entry for score, entry in scored_matches if score == best_score]
        if len(best_matches) != 1 or best_score < max(1, len(target_tokens) - 1):
            return candidate
        current = best_matches[0]

    return current


def resolve_library_audio_path(file_path: str) -> Path | None:
    """Resolve a backend path to a real audio file within the configured library root."""
    library_root = configured_library_root()
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = library_root / candidate
    path = resolve_path_component_variants(candidate, library_root)
    if not path.exists():
        path = resolve_filename_variant(path)
    try:
        path = path.resolve()
    except FileNotFoundError:
        return None

    if library_root not in path.parents and path != library_root:
        return None
    if not path.is_file():
        return None
    return path
