# Known Issues

This file documents notable bugs discovered during a code audit.

## 1. Incorrect average popularity calculation
`core/analysis.py` computes `avg_popularity` by dividing the sum of known popularity scores by `len(tracks)`. If some tracks lack a `combined_popularity` value the denominator still includes them which underestimates the average.

Relevant code:
```
    base_summary = {
        ...
        "avg_listeners": mean([t.get("popularity", 0) for t in tracks]),
        "avg_popularity": sum(popularity_values) / len(tracks),
    }
```
【F:core/analysis.py†L69-L81】

## 2. History directory not created
`save_user_history` writes to `USER_DATA_DIR`, but the directory is never ensured to exist. Attempting to save history on a clean install fails with `FileNotFoundError`.

Code reference:
```
    history_file = user_history_path(user_id)
    ...
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
```
【F:core/history.py†L45-L67】

## 3. Crash when summarizing an empty track list
`summarize_tracks` calls `mean` on an empty sequence when no tracks are provided which raises `StatisticsError`.

Relevant line:
```
    "avg_listeners": mean([t.get("popularity", 0) for t in tracks]),
```
【F:core/analysis.py†L69-L80】

## 4. Artist names not normalized in Jellyfin metadata search
`fetch_jellyfin_track_metadata` cleans the item artist names but compares them to the raw `artist` parameter. Special quotes or punctuation can prevent matches.

Snippet:
```
    artists = [normalize_search_term(a) for a in artists_list]
    if (
        title_cleaned.lower() in name.lower()
        and any(artist.lower() in a.lower() for a in artists)
    ):
        ...
```
【F:services/jellyfin.py†L247-L253】

## 5. `get_cached_playlists` ignores supplied user id
`utils/helpers.py` accepts an optional `user_id` but always calls `fetch_audio_playlists()` which fetches playlists for the default user. Passing a different user id only changes the cache key, not the data fetched.

Code:
```
async def get_cached_playlists(user_id: str | None = None) -> dict:
    user_id = user_id or settings.jellyfin_user_id
    cache_key = f"playlists:{user_id}"
    playlists_data = playlist_cache.get(cache_key)
    if playlists_data is None:
        playlists_data = await fetch_audio_playlists()
        playlist_cache.set(cache_key, playlists_data, expire=CACHE_TTLS["playlists"])
    return playlists_data
```
【F:utils/helpers.py†L15-L23】

## 6. Title and artist swapped when exporting history playlists
`export_history_entry_as_m3u` assigns `title, artist = parse_track_text(...)` but `parse_track_text` returns `(artist, title)`. This reversal causes Jellyfin path lookups to use the wrong parameters.
```
    for track in entry.get("suggestions", []):
        title, artist = parse_track_text(track["text"])
        ...
        path = await resolve_jellyfin_path(title, artist, jellyfin_url, jellyfin_api_key)
```
【F:core/m3u.py†L74-L86】

## 7. `extract_year` can return the string "None"
`extract_year` converts the `ProductionYear` value to a string before using `or` to fall back to `PremiereDate`. When `ProductionYear` is `None`, the string "None" is returned instead of the premiere year.
```
    return str(track.get("ProductionYear")) or str(track.get("PremiereDate", "")[:4])
```
【F:core/playlist.py†L310-L315】

## 8. `_determine_year` returns mixed types
This helper claims to return `int | None` for the year, but actually returns a string when only the Jellyfin year is available.
```
    if bpm_year:
        final_year = bpm_year
    elif jellyfin_year:
        final_year = jellyfin_year  # <-- string assigned
```
【F:core/playlist.py†L241-L255】

## 9. Uniform Jellyfin play counts lead to zero popularity
When all tracks share the same Jellyfin play count, `min_jf` and `max_jf` are equal. `normalize_popularity` then returns `0` for every track, wiping out the Jellyfin contribution.
```
    jellyfin_raw = [t["jellyfin_play_count"] for t in tracks if isinstance(t.get("jellyfin_play_count"), int)]
    min_jf, max_jf = min(jellyfin_raw, default=0), max(jellyfin_raw, default=0)
    ... normalize_popularity(raw_jf, min_jf, max_jf)
```
【F:core/analysis.py†L223-L255】

## 10. Windows paths not handled when naming imported playlists
`import_m3u_as_history_entry` derives the playlist label using `filepath.split('/')[-1]`. This fails for Windows-style paths with backslashes.
```
    if imported_tracks:
        playlist_name = f"Imported - {filepath.split('/')[-1]}"
```
【F:core/m3u.py†L196-L204】

## 11. `import_m3u_as_history_entry` treats bool as track metadata
`search_jellyfin_for_track` returns a boolean, but the importer assumes it may return a dict with an `Id` field. As a result `jellyfin_id` is never set and the boolean value is misused.
```
    tasks = [
        asyncio.create_task(search_jellyfin_for_track(meta["title"], meta["artist"]))
        for _, meta in metas
    ]
    ...
    if isinstance(result, dict) and 'Id' in result:
        enriched['jellyfin_id'] = result['Id']
```
【F:core/m3u.py†L157-L192】

## 12. `summarize_tracks` crashes on `None` popularity values
`avg_listeners` passes possible `None` values directly to `mean`, which raises `TypeError` when any track lacks a numeric `popularity`.
```
    base_summary = {
        ...
        "avg_listeners": mean([t.get("popularity", 0) for t in tracks]),
        "avg_popularity": sum(popularity_values) / len(tracks),
    }
```
【F:core/analysis.py†L69-L81】

## 13. Non-numeric tempo tags cause validation errors
`normalize_track` forwards the raw `tempo` tag string to the `Track` model, which expects an integer. A tag like `"tempo:fast"` will trigger a `ValidationError`.
```
    tempo = extract_tag_value(raw.get("Tags"), "tempo")
    return Track(
        ...
        tempo=tempo,
        RunTimeTicks=raw.get("RunTimeTicks", 0),
    )
```
【F:core/playlist.py†L181-L194】

## 14. Percentage distribution may not sum to 100
`percent_distribution` uses floor division when calculating percentages, so the totals can be less than 100%.
```
    counts = Counter(values)
    return {k: f"{v * 100 // total}%" for k, v in counts.items()}
```
【F:core/analysis.py†L20-L26】

## 15. Deleting history by label removes duplicates
The delete route filters history entries by label string. If multiple entries share the same label, they will all be deleted.
```
    label = form.get("playlist_name")
    history = load_sorted_history(settings.jellyfin_user_id)
    updated_history = [item for item in history if item.get("label") != label]
```
【F:api/routes.py†L281-L291】
