# Known Issues

This file documents outstanding bugs discovered during a code audit.
Fixed issues have been moved to [FIXED_BUGS.md](FIXED_BUGS.md).



## 24. Imported M3U files must be UTF-8
`import_m3u_as_history_entry` opens playlists with a fixed UTF‑8 encoding.
Files encoded differently trigger `UnicodeDecodeError` and abort the import.
```
with open(filepath, "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
```
【F:core/m3u.py†L185-L188】

## 32. Suggest request parsing fails for list payloads
`parse_suggest_request` converts the `tracks` field to a string before JSON parsing. If the form sends a list object, the resulting string uses single quotes and cannot be decoded.
```
    tracks_raw = data.get("tracks", "[]")
    tracks_raw_str = str(tracks_raw)
    ...
    tracks = json.loads(tracks_raw_str)
```
【F:utils/helpers.py†L44-L52】

## 35. `normalize_genre` crashes on ``None`` input
The helper assumes a string and calls `.strip()`, raising ``AttributeError`` when passed ``None``.
```
def normalize_genre(raw: str) -> str:
    cleaned = raw.strip().lower()
    return GENRE_SYNONYMS.get(cleaned, cleaned)
```
【F:core/playlist.py†L413-L416】
## 38. Template directory bound to current working directory
`Jinja2Templates` uses the relative path ``"templates"`` so running the app from another directory cannot locate the HTML files.
```
templates = Jinja2Templates(directory="templates")
```
【F:core/templates.py†L3-L5】

## 39. Library scan records tracks with missing metadata
`get_full_audio_library` appends song strings even when ``Name`` or ``AlbumArtist`` are ``None`` resulting in entries like ``"None - None"``.
```
for item in chunk:
    if isinstance(item, dict):
        song = item.get("Name")
        artist = item.get("AlbumArtist")
        items.append(f"{song} - {artist}")
```
【F:core/playlist.py†L150-L155】

## 31. `strip_lrc_timecodes` removes bracketed lyrics
The helper deletes all `[text]` sections, erasing annotations like `[Chorus]` rather than only timecodes.
```
return re.sub(r"\[.*?\]", "", lrc_text).strip()
```
【F:services/jellyfin.py†L484-L494】

## 34. OpenAI test route blocks the event loop
`test_openai` performs a synchronous API call inside an async route without `await` or `to_thread`.
```
    client = openai.OpenAI(api_key=key)
    models = client.models.list()
    valid = any(m.id.startswith("gpt") for m in models.data)
```
【F:api/routes.py†L491-L499】

## 33. Tag extraction is case-sensitive
`extract_tag_value` only matches lowercase prefixes and misses tags like `Tempo:120`.
```
for tag in tags or []:
    if tag.startswith(f"{prefix}:"):
        return tag.split(":", 1)[1]
```
【F:core/playlist.py†L626-L630】

## 25. `duration_human` filter rejects numeric strings
The Jinja filter only accepts integers and returns `?:??` for float or
string durations.
```
def duration_human(seconds: int) -> str:
    if not isinstance(seconds, int):
        return "?:??"
    return f"{seconds // 60}:{seconds % 60:02d}"
```
【F:core/templates.py†L8-L12】

## 28. Debug route returns coroutine object
The `/test-lastfm-tags` route calls the async `get_lastfm_tags` without awaiting it, returning a coroutine instead of tags.
```
@router.get("/test-lastfm-tags")
def debug_lastfm_tags(title: str, artist: str):
    """Return tags for a given track from Last.fm for debugging."""
    tags = get_lastfm_tags(title, artist)
    return {"tags": tags}
```
【F:api/routes.py†L659-L663】

## 43. Outlier detection flags every genre when dominant genre is unknown
`detect_outliers` intends to skip genre mismatches when the playlist's dominant genre is ``'Unknown'`` but no such check exists.
```
if (
    isinstance(genre, str)
    and isinstance(dominant_genre, str)
    and genre.lower() != dominant_genre.lower()
):
    reasons.append("genre")
```
【F:core/analysis.py†L142-L149】

