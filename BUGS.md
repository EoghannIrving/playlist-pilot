# Known Issues

This file documents outstanding bugs discovered during a code audit.
Fixed issues have been moved to [FIXED_BUGS.md](FIXED_BUGS.md).


## 21. Popularity thresholds remain stale after settings updates
When `global_min_lfm` or `global_max_lfm` are changed in the UI, the
module-level constants used by the analysis functions retain their original
values. This causes all popularity calculations to keep using outdated
thresholds.
```
settings: AppSettings = load_settings()
...
GLOBAL_MIN_LFM = settings.global_min_lfm
GLOBAL_MAX_LFM = settings.global_max_lfm
```
【F:config.py†L191-L195】

## 22. Cache TTL configuration not refreshed
`CACHE_TTLS` is set once at import time from `settings.cache_ttls`.
Updating TTLs through the settings page does not propagate to existing caches.
```
# TTL configuration (in seconds) for each named cache
CACHE_TTLS = settings.cache_ttls
```
【F:utils/cache_manager.py†L49-L50】

## 23. Network failures cached as missing Jellyfin tracks
If `search_jellyfin_for_track` encounters an HTTP error, it stores `False`
in the cache, permanently marking the track as absent.
```
except Exception as exc:  # pylint: disable=broad-exception-caught
    record_failure("jellyfin")
    logger.warning("Jellyfin search failed for %s - %s: %s", title, artist, exc)
    jellyfin_track_cache.set(key, False, expire=CACHE_TTLS["jellyfin_tracks"])
    return False
```
【F:services/jellyfin.py†L91-L95】

## 24. Imported M3U files must be UTF-8
`import_m3u_as_history_entry` opens playlists with a fixed UTF‑8 encoding.
Files encoded differently trigger `UnicodeDecodeError` and abort the import.
```
with open(filepath, "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
```
【F:core/m3u.py†L185-L188】

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

## 26. Temporary M3U files written with unsupported newline argument
`export_history_entry_as_m3u` calls `Path.write_text()` using a `newline` parameter, which does not exist and raises `TypeError` at runtime.
```
    m3u_path = Path(tempfile.gettempdir()) / f"suggest_{uuid.uuid4().hex}.m3u"
    m3u_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
```
【F:core/m3u.py†L124-L125】

## 27. Playlist fetch failures cached permanently
`get_cached_playlists` stores the error response in the cache, so a transient fetch failure leaves the error cached until the TTL expires.
```
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Failed to fetch playlists: %s", exc)
            playlists_data = {"playlists": [], "error": str(exc)}
        playlist_cache.set(cache_key, playlists_data, expire=CACHE_TTLS["playlists"])
```
【F:utils/helpers.py†L24-L31】

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

## 29. Logging setup assumes existing `logs/` directory
`RotatingFileHandler` is created for `logs/playlist_pilot.log` but the directory is never created, causing startup failures on a fresh install.
```
if not logger.handlers:
    handler = RotatingFileHandler(
        "logs/playlist_pilot.log", maxBytes=1_000_000, backupCount=3
    )
```
【F:main.py†L36-L38】

## 30. Last.fm errors cached as track absence
`get_lastfm_track_info` caches `False` when any exception occurs, so network issues mark the track as missing until the cache expires.
```
    except Exception as exc:  # pylint: disable=broad-exception-caught
        record_failure("lastfm")
        logger.warning("Last.fm lookup failed for %s - %s: %s", title, artist, exc)
        lastfm_cache.set(key, False, expire=CACHE_TTLS["lastfm"])
        return None
```
【F:services/lastfm.py†L108-L112】

## 31. `strip_lrc_timecodes` removes bracketed lyrics
The helper deletes all `[text]` sections, erasing annotations like `[Chorus]` rather than only timecodes.
```
return re.sub(r"\[.*?\]", "", lrc_text).strip()
```
【F:services/jellyfin.py†L484-L494】

## 32. Suggest request parsing fails for list payloads
`parse_suggest_request` converts the `tracks` field to a string before JSON parsing. If the form sends a list object, the resulting string uses single quotes and cannot be decoded.
```
    tracks_raw = data.get("tracks", "[]")
    tracks_raw_str = str(tracks_raw)
    ...
    tracks = json.loads(tracks_raw_str)
```
【F:utils/helpers.py†L44-L52】

## 33. Tag extraction is case-sensitive
`extract_tag_value` only matches lowercase prefixes and misses tags like `Tempo:120`.
```
for tag in tags or []:
    if tag.startswith(f"{prefix}:"):
        return tag.split(":", 1)[1]
```
【F:core/playlist.py†L626-L630】

## 34. OpenAI test route blocks the event loop
`test_openai` performs a synchronous API call inside an async route without `await` or `to_thread`.
```
    client = openai.OpenAI(api_key=key)
    models = client.models.list()
    valid = any(m.id.startswith("gpt") for m in models.data)
```
【F:api/routes.py†L491-L499】

## 35. `normalize_genre` crashes on ``None`` input
The helper assumes a string and calls `.strip()`, raising ``AttributeError`` when passed ``None``.
```
def normalize_genre(raw: str) -> str:
    cleaned = raw.strip().lower()
    return GENRE_SYNONYMS.get(cleaned, cleaned)
```
【F:core/playlist.py†L413-L416】
## 36. OpenAI clients ignore updated API keys
`sync_openai_client` and `async_openai_client` are created at import time using the initial `openai_api_key`. Updating the key through `/settings` leaves these clients unchanged.
```
sync_openai_client = OpenAI(api_key=settings.openai_api_key)
async_openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
```
【F:services/gpt.py†L20-L21】

## 37. Logging fails when combined popularity is ``None``
`enrich_and_score_suggestions` formats the score with ``%.1f`` even when `combined_popularity` is ``None`` which raises ``TypeError``.
```
for track in suggestions:
    logger.info(
        "%s - %s | Combined: %.1f | Last.fm: %s, Jellyfin: %s",
        track["title"],
        track["artist"],
        track["combined_popularity"],
        raw_lfm,
        raw_jf,
    )
```
【F:core/playlist.py†L686-L697】

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

## 40. Invalid settings persisted before validation
`update_settings` writes the new configuration to disk prior to calling `validate_settings`, so bad input still overwrites ``settings.json``.
```
save_settings(settings)
try:
    settings.validate_settings()
    validation_message = "Settings saved successfully."
```
【F:api/routes.py†L368-L402】

## 41. Mood weight constants stay stale after updates
`LYRICS_WEIGHT`, `BPM_WEIGHT`, and `TAGS_WEIGHT` are set once from ``settings`` and never refreshed when the values change.
```
LYRICS_WEIGHT = settings.lyrics_weight
BPM_WEIGHT = settings.bpm_weight
TAGS_WEIGHT = settings.tags_weight
```
【F:core/analysis.py†L419-L421】

## 42. ``normalize_popularity_log`` crashes with zero bounds
The function calls ``math.log10`` on ``min_val`` and ``max_val`` without checking they are positive.
```
log_min = math.log10(min_val)
log_max = math.log10(max_val)
log_val = math.log10(value)
```
【F:core/analysis.py†L248-L250】

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

## 44. M3U import aborts on a single metadata failure
`import_m3u_as_history_entry` awaits ``asyncio.gather`` without ``return_exceptions`` so one failing request stops the entire import.
```
metas = [(path, infer_track_metadata_from_path(path)) for path in lines]
tasks = [
    asyncio.create_task(
        fetch_jellyfin_track_metadata(meta["title"], meta["artist"])
    )
    for _, meta in metas
]
for (path, meta), metadata in zip(metas, await asyncio.gather(*tasks)):
```
【F:core/m3u.py†L190-L199】

## 45. Last.fm tag failures repeatedly hit the API
`get_lastfm_tags` returns an empty list on error but never caches the failure, causing repeated requests during outages.
```
except Exception as exc:  # pylint: disable=broad-exception-caught
    record_failure("lastfm")
    logger.warning("Last.fm tag fetch failed for %s - %s: %s", title, artist, exc)
    return []
```
【F:services/lastfm.py†L60-L68】
