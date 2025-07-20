# Known Issues

This file documents notable bugs discovered during a code audit.

## 1. Incorrect average popularity calculation
*Fixed.* `avg_popularity` now divides by the number of popularity values present and returns ``0`` when none exist.

## 2. History directory not created
*Fixed.* The user history directory is now created automatically before writing files.

`save_user_history` writes to `USER_DATA_DIR`, but the directory was never ensured to exist. Attempting to save history on a clean install failed with `FileNotFoundError`.

Code reference:
```
    history_file = user_history_path(user_id)
    ...
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
```
【F:core/history.py†L45-L71】

## 3. Crash when summarizing an empty track list
*Fixed.* The function now falls back to ``0`` for ``avg_listeners`` and ``avg_popularity`` when no tracks are supplied.

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
*Fixed.* The function now checks the ``ProductionYear`` value before converting to a string and only falls back to ``PremiereDate`` when it's missing.
```
    prod_year = track.get("ProductionYear")
    if prod_year:
        return str(prod_year)
    premiere = track.get("PremiereDate", "")
    return str(premiere)[:4] if premiere else ""
```
【F:core/playlist.py†L342-L350】

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

## 16. Extra hyphen breaks date extraction
`extract_date_from_label` uses a greedy regex and fails when the playlist label contains another " - " before the timestamp.
```
    match = re.search(r"- (.+)$", label)
```
【F:core/history.py†L21-L30】

## 17. Jellyfin playlist comparison uses nonexistent artist field
`compare_playlists_form` looks for `Artist` on each Jellyfin track, but the API provides an `Artists` list. Artist names end up blank during comparison.
```
    formatted = [
        f'{t["Name"]} - {t.get("AlbumArtist") or t.get("Artist", "")}'
        for t in tracks
    ]
```
【F:api/routes.py†L174-L183】

## 18. YouTube lookup crashes with missing duration
`get_youtube_url_single` filters search results by duration using `e.get("duration", 0)`. If a result has `None` for duration the comparison raises `TypeError`.
```
    filtered_entries = [
        e
        for e in entries
        if settings.youtube_min_duration <= e.get("duration", 0) <= settings.youtube_max_duration
    ]
```
【F:services/metube.py†L58-L64】

## 19. Invalid JSON in settings form causes crash
`SettingsForm.as_form` passes user input directly to `json.loads`. Malformed JSON in `cache_ttls` or `getsongbpm_headers` raises `JSONDecodeError` and results in a 500 error.
```
    cache_ttls=(json.loads(cache_ttls) if cache_ttls else AppSettings().cache_ttls),
    getsongbpm_headers=(
        json.loads(getsongbpm_headers)
        if getsongbpm_headers
        else AppSettings().getsongbpm_headers
    ),
```
【F:api/forms.py†L46-L51】

## 20. Unvalidated path components when generating proposed paths
`generate_proposed_path` simply strips whitespace from inputs before joining them into a file path, allowing traversal sequences like `../`.
```
    artist_dir = artist.strip()
    album_dir = album.strip() if album else "Unknown Album"
    title_file = title.strip()
    return f"{settings.music_library_root}/{artist_dir}/{album_dir}/{title_file}.mp3"
```
【F:core/m3u.py†L31-L36】
