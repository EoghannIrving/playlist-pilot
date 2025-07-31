# Fixed Bugs

This file lists bugs that have been resolved since the code audit.
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
*Fixed.* The search now normalizes the input `artist` value before comparison.

Snippet:
```
    artists = [normalize_search_term(a) for a in artists_list]
    if (
        title_cleaned.lower() in name.lower()
        and any(artist_cleaned.lower() in a.lower() for a in artists)
    ):
        ...
```
【F:services/jellyfin.py†L279-L285】

## 5. `get_cached_playlists` ignores supplied user id
*Fixed.* `fetch_audio_playlists` now accepts a `user_id` argument and `get_cached_playlists` forwards the provided value so the correct user's playlists are fetched.

Code:
```
async def get_cached_playlists(user_id: str | None = None) -> dict:
    user_id = user_id or settings.jellyfin_user_id
    cache_key = f"playlists:{user_id}"
    playlists_data = playlist_cache.get(cache_key)
    if playlists_data is None:
        playlists_data = await fetch_audio_playlists(user_id)
        playlist_cache.set(cache_key, playlists_data, expire=CACHE_TTLS["playlists"])
    return playlists_data
```
【F:utils/helpers.py†L15-L23】

## 6. Title and artist swapped when exporting history playlists
*Fixed.* The function now assigns the variables in the correct order before calling `resolve_jellyfin_path`.
```
    for track in entry.get("suggestions", []):
        artist, title = parse_track_text(track["text"])
        ...
        path = await resolve_jellyfin_path(title, artist, jellyfin_url, jellyfin_api_key)
```
【F:core/m3u.py†L74-L88】

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
*Fixed.* This helper now consistently returns a string or ``None`` instead of mixing integer and string types.
```
    if bpm_year:
        final_year = bpm_year
    elif jellyfin_year:
        final_year = jellyfin_year  # <-- string assigned
```
【F:core/playlist.py†L241-L255】

## 9. Uniform Jellyfin play counts lead to zero popularity
*Fixed.* `normalize_popularity` now returns `100` when all counts are equal and non-zero, preserving the Jellyfin contribution.
```
    jellyfin_raw = [t["jellyfin_play_count"] for t in tracks if isinstance(t.get("jellyfin_play_count"), int)]
    min_jf, max_jf = min(jellyfin_raw, default=0), max(jellyfin_raw, default=0)
    ... normalize_popularity(raw_jf, min_jf, max_jf)
```
【F:core/analysis.py†L223-L255】

## 10. Windows paths not handled when naming imported playlists
*Fixed.* `import_m3u_as_history_entry` now derives the label using
`ntpath.basename(filepath)`, which recognizes both slash types.
```
    if imported_tracks:
        playlist_name = f"Imported - {ntpath.basename(filepath)}"
```
【F:core/m3u.py†L209-L213】

## 11. `import_m3u_as_history_entry` treats bool as track metadata
*Fixed.* The importer now uses `fetch_jellyfin_track_metadata` to retrieve a track's metadata and `Id`.
```
    tasks = [
        asyncio.create_task(
            fetch_jellyfin_track_metadata(meta["title"], meta["artist"])
        )
        for _, meta in metas
    ]
    ...
    if isinstance(metadata, dict) and "Id" in metadata:
        enriched["jellyfin_id"] = metadata["Id"]
```
【F:core/m3u.py†L164-L202】

## 12. `summarize_tracks` crashes on `None` popularity values
*Fixed.* `avg_listeners` now filters out ``None`` values and falls back to ``0`` when no valid data is present.
```
    base_summary = {
        ...
        "avg_listeners": mean([t.get("popularity", 0) for t in tracks]),
        "avg_popularity": sum(popularity_values) / len(tracks),
    }
```
【F:core/analysis.py†L69-L81】

## 13. Non-numeric tempo tags cause validation errors
*Fixed.* `normalize_track` now converts tempo tags to integers only when the value is numeric, avoiding ``ValidationError`` for strings like ``"tempo:fast"``.
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
*Fixed.* Percentages now distribute leftover points so the total is exactly 100.
```
    counts = Counter(values)
    raw = {k: v * 100 / total for k, v in counts.items()}
    floored = {k: int(math.floor(p)) for k, p in raw.items()}
    remainder = 100 - sum(floored.values())
    if remainder:
        fractions = sorted(
            raw.items(), key=lambda item: item[1] - math.floor(item[1]), reverse=True
        )
        for i in range(remainder):
            floored[fractions[i % len(fractions)][0]] += 1
    return {k: f"{v}%" for k, v in floored.items()}
```
【F:core/analysis.py†L21-L40】

## 15. Deleting history by label removes duplicates
*Fixed.* Deletions now use the entry's unique ``id`` instead of the label, so only the selected item is removed.
```
    form = await request.form()
    raw_id = form.get("entry_id")
    entry_id = raw_id if isinstance(raw_id, str) else ""
    delete_history_entry_by_id(settings.jellyfin_user_id, entry_id)
```
【F:api/routes.py†L308-L316】

## 16. Extra hyphen breaks date extraction
*Fixed.* `extract_date_from_label` now matches only the final timestamp segment.
```
    match = re.search(r"- (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$", label)
```
【F:core/history.py†L21-L32】

## 17. Jellyfin playlist comparison uses nonexistent artist field
*Fixed.* `compare_playlists_form` now pulls the artist from the `Artists` list and falls back to `AlbumArtist`.
```
    formatted = [
        f'{t["Name"]} - {(t.get("Artists") or [None])[0] or t.get("AlbumArtist", "")}'
        for t in tracks
    ]
```
【F:api/routes.py†L174-L183】

## 18. YouTube lookup crashes with missing duration
*Fixed.* `get_youtube_url_single` now falls back to ``0`` when duration is missing.
```
    filtered_entries = [
        e
        for e in entries
        if settings.youtube_min_duration
        <= (e.get("duration") or 0)
        <= settings.youtube_max_duration
    ]
```
【F:services/metube.py†L58-L64】

## 19. Invalid JSON in settings form causes crash
*Fixed.* JSON fields are parsed with `_safe_json` and invalid input triggers a 400 error.
```
    def _safe_json(value: str, default: dict, field_name: str) -> dict:
        if not value:
            return default
        try:
            return json.loads(value)
        except JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON for {field_name}: {exc.msg}",
            ) from exc

    return cls(
        ...
        cache_ttls=_safe_json(cache_ttls, AppSettings().cache_ttls, "cache_ttls"),
        getsongbpm_base_url=getsongbpm_base_url,
        getsongbpm_headers=_safe_json(
            getsongbpm_headers,
            AppSettings().getsongbpm_headers,
            "getsongbpm_headers",
        ),
```
【F:api/forms.py†L40-L68】

## 20. Unvalidated path components when generating proposed paths
*Fixed.* Path components are sanitized with `_sanitize_component` before joining.
```
    artist_dir = _sanitize_component(artist, "Unknown Artist")
    album_dir = _sanitize_component(album, "Unknown Album")
    title_file = _sanitize_component(title, "Unknown Title")
    return (
        Path(settings.music_library_root) / artist_dir / album_dir / f"{title_file}.mp3"
    ).as_posix()
```
【F:core/m3u.py†L37-L56】

## 21. Logging setup assumes existing `logs/` directory
*Fixed.* The application now creates the log folder before adding the file handler.
```
if not logger.handlers:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3
    )
```
【F:main.py†L36-L41】

## 22. Invalid settings persisted before validation
*Fixed.* `update_settings` now validates the form input before saving to `settings.json` so invalid data is not persisted.

Code:
```
    try:
        settings.validate_settings()
        save_settings(settings)
        validation_message = "Settings saved successfully."
        validation_error = False
    except ValueError as ve:
        validation_message = str(ve)
        validation_error = True
```
【F:api/routes.py†L392-L407】

## 23. Temporary M3U files written with unsupported newline argument
*Fixed.* `export_history_entry_as_m3u` no longer passes an unsupported `newline` parameter to `Path.write_text`.

Code:
```
    m3u_path = Path(tempfile.gettempdir()) / f"suggest_{uuid.uuid4().hex}.m3u"
    m3u_path.write_text("\n".join(lines), encoding="utf-8")
```
【F:core/m3u.py†L124-L125】

## 24. M3U import aborts on a single metadata failure
*Fixed.* `import_m3u_as_history_entry` now gathers metadata with `return_exceptions=True` and skips tracks whose fetch fails instead of aborting the entire import.

Code:
```python
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for (path, meta), metadata in zip(metas, results):
        title = meta["title"]
        artist = meta["artist"]
        if isinstance(metadata, Exception):
            logger.warning(
                "Metadata fetch failed for %s - %s: %s", title, artist, metadata
            )
            metadata = None
        if metadata:
            enriched_obj = await enrich_track({"title": title, "artist": artist})
```
【F:core/m3u.py†L196-L215】

## 42. ``normalize_popularity_log`` crashes with zero bounds
*Fixed.* The helper now verifies both bounds are positive and returns ``0`` when they are not.

Code snippet:
```python
    if min_val <= 0 or max_val <= 0:
        logger.warning(
            "normalize_popularity_log returning 0 due to non-positive bounds"
        )
        return 0
    if min_val == max_val:
        logger.warning(
            "normalize_popularity_log returning %s due to uniform bounds", 100
        )
        return 100
```
【F:core/analysis.py†L239-L255】

## 37. Logging fails when combined popularity is ``None``
*Fixed.* The logger now formats ``combined_popularity`` with ``%s`` so ``None`` values no longer raise ``TypeError``.

Code snippet:
```python
        combined = track.get("combined_popularity")
        logger.info(
            "%s - %s | Combined: %s | Last.fm: %s, Jellyfin: %s",
            track["title"],
            track["artist"],
            f"{combined:.1f}" if isinstance(combined, (int, float)) else combined,
            raw_lfm,
            raw_jf,
        )
```
【F:core/playlist.py†L688-L698】

## 36. OpenAI clients ignore updated API keys
*Fixed.* OpenAI clients are now created with the current API key each time they are used.
```python
def get_sync_openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)

def get_async_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)
```
【F:services/gpt.py†L22-L29】

## 23. Network failures cached as missing Jellyfin tracks
*Fixed.* The search function no longer caches failures, preventing transient
errors from marking tracks as permanently absent.
```python
    except Exception as exc:  # pylint: disable=broad-exception-caught
        record_failure("jellyfin")
        logger.warning("Jellyfin search failed for %s - %s: %s", title, artist, exc)
        # Avoid caching failures so transient issues don't mark the track as missing
        return False
```
【F:services/jellyfin.py†L91-L95】

## 30. Last.fm errors cached as track absence
*Fixed.* `get_lastfm_track_info` now returns ``None`` without caching when a request fails.
```python
    except Exception as exc:  # pylint: disable=broad-exception-caught
        record_failure("lastfm")
        logger.warning("Last.fm lookup failed for %s - %s: %s", title, artist, exc)
        # Avoid caching failures so transient issues don't mark the track as missing
        return None
```
【F:services/lastfm.py†L108-L112】

## 27. Playlist fetch failures cached permanently
*Fixed.* `get_cached_playlists` now only caches successful playlist fetches.
```python
    playlists_data = playlist_cache.get(cache_key)
    if playlists_data is None:
        try:
            playlists_data = await fetch_audio_playlists(user_id)
            playlist_cache.set(
                cache_key, playlists_data, expire=CACHE_TTLS["playlists"]
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Failed to fetch playlists: %s", exc)
            # Return the error response but avoid caching it so transient issues
            # do not persist until the TTL expires
            return {"playlists": [], "error": str(exc)}
```
【F:utils/helpers.py†L19-L35】

## 45. Last.fm tag failures repeatedly hit the API
*Fixed.* `get_lastfm_tags` now caches an empty list when a request fails so repeated errors don't hammer the API.
```python
    except Exception as exc:  # pylint: disable=broad-exception-caught
        record_failure("lastfm")
        logger.warning("Last.fm tag fetch failed for %s - %s: %s", title, artist, exc)
        lastfm_cache.set(cache_key, [], expire=CACHE_TTLS["lastfm"])
        return []
```
【F:services/lastfm.py†L60-L67】

## 41. Mood weight constants stay stale after updates
*Fixed.* `combine_mood_scores` now reads weighting values from `settings` each
time it runs, ensuring updates take effect immediately.

```python
    combined = {}
    tags_weight = settings.tags_weight
    bpm_weight = settings.bpm_weight
    lyrics_weight = settings.lyrics_weight

    for mood in MOOD_TAGS:
        score = (
            tags_weight * tag_scores.get(mood, 0)
            + bpm_weight * bpm_scores.get(mood, 0)
            + (lyrics_weight * lyrics_scores.get(mood, 0) if lyrics_scores else 0)
        )
        weighted = score * MOOD_WEIGHTS.get(mood, 1.0)
        combined[mood] = weighted
```
【F:core/analysis.py†L492-L503】

## 21. Popularity thresholds remain stale after settings updates
*Fixed.* Popularity calculations now read the Last.fm listener bounds from
`settings` whenever they run instead of using constants set at import time.

```python
def get_global_min_lfm() -> int:
    return settings.global_min_lfm

def get_global_max_lfm() -> int:
    return settings.global_max_lfm
```
【F:config.py†L195-L202】

```python
norm_lfm = normalize_popularity_log(
    raw_lfm, get_global_min_lfm(), get_global_max_lfm()
)
```
【F:core/analysis.py†L284-L289】

## 22. Cache TTL configuration not refreshed
*Fixed.* Updating settings now refreshes the shared cache TTL dictionary so new cache entries honor the changed values.

```python
    settings.cache_ttls = form_data.cache_ttls
    # Update shared cache TTLs in-place so other modules
    # that imported the dictionary see the new values
    from utils import cache_manager  # import here to avoid circular dependency

    cache_manager.CACHE_TTLS.clear()
    cache_manager.CACHE_TTLS.update(settings.cache_ttls)
```
【F:api/routes.py†L383-L389】

## 24. Imported M3U files must be UTF-8
*Fixed.* The importer now ignores decoding errors so playlists encoded differently can still be read.

```python
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = [
            line.strip() for line in f if line.strip() and not line.startswith("#")
        ]
```
【F:core/m3u.py†L186-L189】

## 32. Suggest request parsing fails for list payloads
*Fixed.* `parse_suggest_request` now handles list objects directly and only decodes JSON when the ``tracks`` value is a string.

```python
    tracks_raw = data.get("tracks", "[]")
    logger.info("tracks_raw: %s", str(tracks_raw)[:100])
    playlist_name = str(data.get("playlist_name", ""))
    text_summary = str(data.get("text_summary", ""))

    if isinstance(tracks_raw, str):
        tracks_raw_str = tracks_raw
        try:
            tracks = json.loads(tracks_raw_str)
        except json.JSONDecodeError:
            logger.warning("Failed to decode tracks JSON from form.")
            tracks = []
    elif isinstance(tracks_raw, (list, tuple)):
        tracks = list(tracks_raw)
    else:
        logger.warning("Unexpected tracks type: %s", type(tracks_raw))
        tracks = []
```
【F:utils/helpers.py†L49-L67】

## 33. Tag extraction is case-sensitive
*Fixed.* `extract_tag_value` now matches prefixes in a case-insensitive manner.
```python
    prefix_lower = prefix.lower()
    for tag in tags or []:
        if tag.lower().startswith(f"{prefix_lower}:"):
            return tag.split(":", 1)[1]
```
【F:core/playlist.py†L638-L642】

## 35. `normalize_genre` crashes on ``None`` input
*Fixed.* The helper now returns an empty string when passed ``None`` or another falsy value.

```python
def normalize_genre(raw: str | None) -> str:
    """Map genre synonyms to canonical names."""
    if not raw:
        return ""
    cleaned = str(raw).strip().lower()
    return GENRE_SYNONYMS.get(cleaned, cleaned)
```
【F:core/playlist.py†L413-L418】

## 43. Outlier detection flags every genre when dominant genre is unknown
*Fixed.* The function now ignores mismatches when the dominant genre is `'Unknown'`.

```python
        genre = t.get("genre")
        if (
            isinstance(genre, str)
            and isinstance(dominant_genre, str)
            and dominant_genre.lower() != "unknown"
            and genre.lower() != dominant_genre.lower()
        ):
            reasons.append("genre")
```
【F:core/analysis.py†L142-L150】

## 46. Album overwrite check triggers unnecessarily
*Fixed.* The exporter now overwrites the album automatically when Jellyfin has no existing album value, avoiding an unnecessary confirmation prompt.

`export_track_metadata` asked for confirmation even when the Jellyfin album field was blank.

```python
    album_to_use = existing_album
    if not skip_album and incoming_album:
        if not existing_album:
            album_to_use = incoming_album
        elif existing_album != incoming_album:
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
【F:api/routes.py†L937-L952】

## 47. `read_m3u` fails on non‑UTF‑8 files
*Fixed.* `read_m3u` now falls back to Latin‑1 when UTF‑8 decoding fails.

```python
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        logger.debug("UTF-8 decode failed for %s, trying Latin-1", file_path)
        lines = file_path.read_text(encoding="latin-1").splitlines()
```
【F:core/m3u.py†L148-L152】

## 44. Search misses tracks with smart quotes
*Fixed.* `search_jellyfin_for_track` now normalizes curly quotes before comparing titles and artists.

```python
    title_cleaned = normalize_search_term(title)
    artist_cleaned = normalize_search_term(artist)
    ...
            name = normalize_search_term(item.get("Name", ""))
            artists_list = item.get("Artists", [])
            artists = [normalize_search_term(a) for a in artists_list]
            if title_cleaned.lower() in name.lower() and any(
                artist_cleaned.lower() in a.lower() for a in artists
            ):
                ...
```
【F:services/jellyfin.py†L44-L79】

## 38. Template directory bound to current working directory
*Fixed.* `core.templates` now computes an absolute directory path so the app can
load HTML files correctly no matter the invocation location.

```python
TEMPLATES_DIR = (Path(__file__).resolve().parent.parent / "templates").resolve()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
```
【F:core/templates.py†L4-L10】

## 45. `lyrics_enabled` default disabled in settings form
*Fixed.* The settings form now initializes ``lyrics_enabled`` with ``True`` so the application's default is preserved when the checkbox is omitted.

```python
lyrics_enabled: bool = Form(True)
```
【F:api/forms.py†L30-L36】

## 39. Library scan records tracks with missing metadata
*Fixed.* ``get_full_audio_library`` now ignores items missing ``Name`` or ``AlbumArtist`` to avoid entries like ``"None - None"``.

```python
for item in chunk:
    if isinstance(item, dict):
        song = item.get("Name")
        artist = item.get("AlbumArtist")
        if song and artist:
            items.append(f"{song} - {artist}")
```
【F:core/playlist.py†L150-L158】

## 25. `duration_human` filter rejects numeric strings
*Fixed.* The template filter now accepts numeric strings and floats by casting them before formatting.

```python
def duration_human(seconds: int | float | str) -> str:
    """Return ``MM:SS`` style duration strings for template rendering."""
    try:
        seconds_int = int(float(seconds))
    except (TypeError, ValueError):
        return "?:??"
    return f"{seconds_int // 60}:{seconds_int % 60:02d}"
```
【F:core/templates.py†L13-L19】

## 31. `strip_lrc_timecodes` removes bracketed lyrics
*Fixed.* Timecodes are now matched with a specific regex so annotations like `[Chorus]` remain intact.

```python
    timecode_pattern = r"\[(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,2})?\]"
    return re.sub(timecode_pattern, "", lrc_text).strip()
```
【F:services/jellyfin.py†L488-L498】

## 34. OpenAI test route blocks the event loop
*Fixed.* `test_openai` now performs the model listing in a thread to avoid blocking.
```python
    def _list_models():
        client = openai.OpenAI(api_key=key)
        return client.models.list()

    models = await asyncio.to_thread(_list_models)
```
【F:api/routes.py†L500-L509】

## 51. GPT prompt cache ignores model choice
*Fixed.* The cache key now incorporates the selected model so prompts for different models don't collide.
```python
    key = prompt_fingerprint(
        f"{prompt}|temperature={temperature}|model={settings.model}"
    )
```
【F:services/gpt.py†L137-L151】

## 52. `get_playlist_id_by_name` fetches all playlists
*Fixed.* The helper now queries Jellyfin for the playlist name using ``SearchTerm`` instead of retrieving every playlist.
```python
    resp = await jf_get(
        f"/Users/{settings.jellyfin_user_id}/Items",
        IncludeItemTypes="Playlist",
        Recursive="true",
        SearchTerm=name,
        Limit=20,
    )
```
【F:core/playlist.py†L82-L101】

## 28. Debug route returns coroutine object
*Fixed.* The `/test-lastfm-tags` endpoint is now asynchronous and awaits ``get_lastfm_tags``.
```python
@router.get("/test-lastfm-tags")
async def debug_lastfm_tags(title: str, artist: str):
    """Return tags for a given track from Last.fm for debugging."""
    tags = await get_lastfm_tags(title, artist)
    return {"tags": tags}
```
【F:api/routes.py†L702-L706】

## 48. `parse_gpt_line` hides malformed suggestions
*Fixed.* The helper now raises ``ValueError`` when lines cannot be parsed so invalid suggestions are skipped.
```python
    parts = [p.strip() for p in line.split(" - ")]
    if len(parts) >= 2:
        ...
    by_split = re.split(r"\s+by\s+", line, maxsplit=1, flags=re.IGNORECASE)
    if len(by_split) == 2:
        return by_split[0].strip(), by_split[1].strip()
    raise ValueError(f"Could not parse suggestion line: {line}")
```
【F:services/gpt.py†L183-L211】
