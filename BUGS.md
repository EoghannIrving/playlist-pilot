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
