# Known Issues

This file documents outstanding bugs discovered during a code audit.
Fixed issues have been moved to [FIXED_BUGS.md](FIXED_BUGS.md).

## 31. `strip_lrc_timecodes` removes bracketed lyrics
The helper deletes all `[text]` sections, erasing annotations like `[Chorus]` rather than only timecodes.
```
return re.sub(r"\[.*?\]", "", lrc_text).strip()
```
【F:services/jellyfin.py†L484-L494】


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

## 54. Last.fm normalization strips accented characters
`normalize` removes all non-ASCII characters so artists like "Beyoncé" are cached without the accent, causing mismatches.
```
_punct_re = re.compile(r"[^a-z0-9 ]")
...
text = _punct_re.sub("", text)
```
【F:services/lastfm.py†L21-L31】

## 55. `get_lastfm_track_info` makes API calls even when the API key is blank
The function always queries Last.fm without validating `settings.lastfm_api_key`, leading to failing requests when no key is set.
```
async with httpx.AsyncClient() as client:
    response = await client.get(
        "https://ws.audioscrobbler.com/2.0/",
        params={"method": "track.getInfo", "api_key": settings.lastfm_api_key}
    )
```
【F:services/lastfm.py†L72-L98】

## 56. `_duration_from_ticks` may crash on non-numeric BPM data
The helper casts the BPM API's ``duration`` field directly to ``int`` without validating its type.
```
bpm_duration = bpm_data.get("duration")
return int(bpm_duration) if bpm_duration is not None else duration
```
【F:core/playlist.py†L287-L291】

## 57. `parse_gpt_line` ignores em dashes
Only en dashes are normalized, so lines using an em dash (`—`) fail to parse.
```
line = line.replace("\u2013", "-").strip()  # normalize en dash
```
【F:services/gpt.py†L181-L201】

## 58. `_extract_remaining` splits on every dash
When titles or artists contain dashes, the remaining text is truncated because the helper splits on ``" - "`` without limit.
```
parts = [p.strip() for p in normalized.split(" - ")]
return " - ".join(parts[2:]).strip()
```
【F:services/gpt.py†L304-L315】
