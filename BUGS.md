# Known Issues

This file documents outstanding bugs discovered during a code audit.
Fixed issues have been moved to [FIXED_BUGS.md](FIXED_BUGS.md).

## 35. `normalize_genre` crashes on ``None`` input
The helper assumes a string and calls `.strip()`, raising ``AttributeError`` when passed ``None``.
```
def normalize_genre(raw: str) -> str:
    cleaned = raw.strip().lower()
    return GENRE_SYNONYMS.get(cleaned, cleaned)
```
【F:core/playlist.py†L413-L416】

## 46. Album overwrite check triggers unnecessarily
`export_track_metadata` asks for confirmation even when the Jellyfin album field is blank.
```
album_to_use = existing_album
if not skip_album and incoming_album and existing_album != incoming_album:
    if force_album_overwrite:
        album_to_use = incoming_album
    else:
        return JSONResponse(
            {
                "action": "confirm_overwrite_album",
                "current_album": existing_album,
                "suggested_album": incoming_album,
            },
            status_code=409,
        )
```
【F:api/routes.py†L884-L897】

## 47. `read_m3u` fails on non‑UTF‑8 files
The loader decodes using UTF‑8 without fallback, raising ``UnicodeDecodeError`` for other encodings.


## 38. Template directory bound to current working directory
`Jinja2Templates` uses the relative path ``"templates"`` so running the app from another directory cannot locate the HTML files.

```
lines = file_path.read_text(encoding="utf-8").splitlines()
```
【F:core/m3u.py†L148-L148】

## 45. `lyrics_enabled` default disabled in settings form
`SettingsForm.as_form` uses ``Form(False)`` which overrides the true default in ``AppSettings`` when saving settings.
```
lyrics_enabled: bool = Form(False)
```
【F:api/forms.py†L14-L36】

## 44. Search misses tracks with smart quotes
`search_jellyfin_for_track` compares raw titles without normalizing quotes, so `'` vs `’` fails to match.
```
if title.lower() in name.lower() and any(
    artist.lower() in a.lower() for a in artists
):
```
【F:services/jellyfin.py†L60-L81】

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

## 38. Template directory bound to current working directory
`Jinja2Templates` uses the relative path ``"templates"`` so running the app from another directory cannot locate the HTML files.
```
templates = Jinja2Templates(directory="templates")
```
【F:core/templates.py†L3-L5】

## 31. `strip_lrc_timecodes` removes bracketed lyrics
The helper deletes all `[text]` sections, erasing annotations like `[Chorus]` rather than only timecodes.
```
return re.sub(r"\[.*?\]", "", lrc_text).strip()
```
【F:services/jellyfin.py†L484-L494】

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

## 34. OpenAI test route blocks the event loop
`test_openai` performs a synchronous API call inside an async route without ``await`` or ``to_thread``.
```
    client = openai.OpenAI(api_key=key)
    models = client.models.list()
    valid = any(m.id.startswith("gpt") for m in models.data)
```
【F:api/routes.py†L491-L499】

## 51. GPT prompt cache ignores model choice
`cached_chat_completion` builds its cache key from only the prompt and temperature, so switching models may return stale text.
```
key = prompt_fingerprint(f"{prompt}|temperature={temperature}")
content = prompt_cache.get(key)
```
【F:services/gpt.py†L139-L167】

## 52. `get_playlist_id_by_name` fetches all playlists
The helper retrieves the full playlist list and scans it every call, which is inefficient on large libraries.
```
async with httpx.AsyncClient() as client:
    resp = await client.get(
        f"{settings.jellyfin_url.rstrip('/')}/Users/{settings.jellyfin_user_id}/Items",
        headers={"X-Emby-Token": settings.jellyfin_api_key},
        params={"IncludeItemTypes": "Playlist", "Recursive": "true"},
        timeout=10,
    )
```
【F:core/playlist.py†L82-L98】

## 33. Tag extraction is case-sensitive
`extract_tag_value` only matches lowercase prefixes and misses tags like `Tempo:120`.
```
for tag in tags or []:
    if tag.startswith(f"{prefix}:"):
        return tag.split(":", 1)[1]
```
【F:core/playlist.py†L626-L630】

## 25. `duration_human` filter rejects numeric strings
The Jinja filter only accepts integers and returns `?:??` for float or string durations.
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

## 48. `parse_gpt_line` hides malformed suggestions
Invalid lines return empty strings instead of raising an error.
```
parts = [p.strip() for p in line.split(" - ")]
return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")
```
【F:services/gpt.py†L180-L191】

## 49. `build_search_query` splits on every dash
Hyphens inside artist or title confuse the query generator.
```
parts = [part.strip() for part in line.split("-")]
return f"{parts[0]} {parts[1]}" if len(parts) >= 2 else line.strip()
```
【F:utils/text_utils.py†L39-L42】

## 50. `parse_track_text` drops data after second dash
Extra segments beyond ``Artist - Title`` are ignored.
```
parts = text.split(" - ")
if len(parts) >= 2:
    artist, title = parts[0].strip(), parts[1].strip()
else:
    artist, title = "Unknown", text.strip()
```
【F:core/m3u.py†L68-L74】

## 53. Filename metadata inference misreads complex names
`infer_track_metadata_from_path` only keeps the last two dash-separated parts, so ``Artist - Title - Live.mp3`` records ``Title - Live`` as the title.
```
segments = clean_title.split(" - ")
if len(segments) >= 2:
    artist = segments[-2].strip()
    title = segments[-1].strip()
```
【F:core/m3u.py†L161-L177】
