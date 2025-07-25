# TODO

This file outlines upcoming tasks based on the current roadmap and list of outstanding bugs.

## Bug Fixes
- [ ] **46. Album overwrite check triggers unnecessarily** – skip confirmation when no existing album is set.
- [ ] **47. `read_m3u` fails on non‑UTF‑8 files** – add encoding fallback when parsing playlists.
- [ ] **38. Template directory bound to current working directory** – use an absolute templates path.
- [ ] **45. `lyrics_enabled` default disabled in settings form** – align the form default with `AppSettings`.
- [ ] **44. Search misses tracks with smart quotes** – normalize quotes in search comparisons.
- [ ] **39. Library scan records tracks with missing metadata** – skip items lacking name or artist.
- [ ] **31. `strip_lrc_timecodes` removes bracketed lyrics** – preserve `[Chorus]` style annotations.
- [ ] **34. OpenAI test route blocks the event loop** – make the request asynchronous.
- [ ] **51. GPT prompt cache ignores model choice** – include the model name in the cache key.
- [ ] **52. `get_playlist_id_by_name` fetches all playlists** – query Jellyfin for a single playlist instead.
- [ ] **33. Tag extraction is case-sensitive** – support capitalized prefixes.
- [ ] **25. `duration_human` filter rejects numeric strings** – accept numeric strings or floats.
- [ ] **28. Debug route returns coroutine object** – await `get_lastfm_tags` in the debug route.
- [ ] **48. `parse_gpt_line` hides malformed suggestions** – raise an error or log invalid lines.
- [ ] **49. `build_search_query` splits on every dash** – only split the first dash between artist and title.
- [ ] **50. `parse_track_text` drops data after second dash** – keep additional segments when present.
- [ ] **53. Filename metadata inference misreads complex names** – improve parsing of dashed file names.

## Roadmap
### Phase 2 – Advanced Analysis & Playlist Management
- [X] Surface mood/confidence scores and highlight outliers.
- [ ] Add playlist management tools for renaming, reordering and deduplication.
- [X] Refine history views and settings editing in the UI.

### Phase 3 – Cross-Service Integration & Scaling
- [ ] Experiment with metadata/play link lookups from Spotify or Apple Music.
- [ ] Optimize caching and async calls; enhance containerization.
- [ ] Evaluate if/when real downloading support should be added.

### Phase 4 – API Expansion & Future Explorations
- [ ] Expand FastAPI endpoints into a fully documented API.
- [ ] Explore advanced ML models for mood analysis and similarity.
- [ ] Prototype a mobile app or PWA and gather user feedback.

