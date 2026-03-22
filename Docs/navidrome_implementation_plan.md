# Navidrome Multi-Backend Implementation Plan

## Goal

Extend Playlist Pilot to support Navidrome without removing Jellyfin support.

The preferred architecture is a multi-backend design:

- keep the existing Jellyfin integration working
- introduce a backend abstraction for media-server operations
- add a Navidrome adapter behind the same interface

This reduces long-term maintenance cost compared with a Navidrome-only fork and keeps the door open for upstreaming the change later.

## Current State

The adapter foundation is in place and the first backend-agnostic core and route migrations are complete. The remaining work is centered on adding the Navidrome implementation, wiring backend selection through the UI and settings flow, and cleaning up transitional Jellyfin-specific naming.

## Implementation Strategy

Do this in two major steps:

1. Refactor the application to use a generic media-server interface while keeping Jellyfin behavior unchanged.
2. Add a Navidrome adapter that implements the same interface.

Do not start with a large-scale text replacement of `Jellyfin` to `Navidrome`. That would create churn across config, UI, tests, and documentation without reducing coupling.

## Phase 1: Introduce A Media-Server Abstraction

### Objectives

- isolate backend-specific logic behind a contract
- preserve current Jellyfin behavior
- minimize behavior changes during the refactor

### Deliverables

- new `services/media_server.py` contract or protocol
- new `get_media_server()` factory
- existing Jellyfin logic wrapped as a `JellyfinAdapter`

### Suggested Interface

The first version of the media-server interface should cover only the operations already required by the application:

- `test_connection()`
- `list_users()`
- `list_audio_playlists()`
- `get_playlist_tracks()`
- `search_track()`
- `get_track_metadata()`
- `get_full_audio_library()`
- `get_lyrics()`
- `create_playlist()`
- `update_playlist()`
- `delete_playlist()`
- `resolve_track_path()`

### Notes

- Keep the interface narrow. Add methods only when a current feature requires them.
- Normalize backend responses inside adapters so `core/` logic does not contain backend branching.

## Phase 2: Wrap Jellyfin In The New Interface

### Objectives

- keep Jellyfin as the reference implementation
- avoid behavior regressions before Navidrome work begins

### Tasks

1. Create a `JellyfinAdapter` that delegates to the existing logic in `services/jellyfin.py`.
2. Move any directly reused helper logic into adapter methods or thin internal helper functions.
3. Introduce a factory such as `get_media_server()` that returns the active adapter based on settings.
4. Keep backward compatibility with existing settings during this phase.

### Success Criteria

- the app still works with Jellyfin
- existing routes still render and behave as before
- existing tests pass with minimal fixture changes

## Phase 3: Refactor Core Logic To Use The Interface

### Objectives

- remove direct `services.jellyfin` imports from non-adapter code
- make backend selection a runtime concern instead of a code-structure concern

### Tasks

1. Refactor `core/playlist.py` to call the media-server adapter instead of Jellyfin helpers directly.
2. Refactor `core/m3u.py` to use the adapter for metadata lookup and path resolution.
3. Refactor settings and test routes to use the active adapter for connection checks and user listing.
4. Update form handling and schemas to support backend-agnostic configuration.

### Success Criteria

- `core/` modules no longer know which server implementation is active
- route handlers do not import backend-specific modules directly

## Phase 4: Add Navidrome Support

### Objectives

- add a second backend without disturbing the application core
- normalize Navidrome responses into the internal track model

### Tasks

1. Create `services/navidrome.py`.
2. Implement the media-server interface using Navidrome's Subsonic or OpenSubsonic-compatible API.
3. Add authentication handling for Navidrome credentials.
4. Normalize Navidrome playlist, track, lyrics, and user data to the application's expected shape.

### Expected Navidrome API Areas

- connectivity check: `ping`
- user identity: `getUser` or `getUsers`
- search: `search3`
- playlists: `getPlaylists`, `getPlaylist`, `createPlaylist`, `updatePlaylist`, `deletePlaylist`
- track metadata: `getSong`
- lyrics: `getLyrics`

### Success Criteria

- Navidrome can connect successfully
- Navidrome playlists can be listed and analyzed
- Navidrome track metadata can be enriched through the existing core flows

## Phase 5: Update Configuration And UI

### Objectives

- make backend choice explicit in settings
- avoid exposing Jellyfin-only terminology in the general UI

### Tasks

1. Add a backend selector to configuration:
   - `media_backend`
   - `media_url`
   - `media_username`
   - `media_password`
   - `media_api_key`
   - `media_user_id`
2. Preserve compatibility with existing Jellyfin settings during migration.
3. Update the settings page to render backend-specific fields.
4. Replace generic user-facing labels such as `Jellyfin Playlist` with backend-neutral wording where appropriate.

### Success Criteria

- users can choose a backend from the UI
- validation rules match the selected backend
- the app no longer assumes Jellyfin in its general UX

## Phase 6: Handle Export And Feature Parity

### Objectives

- identify where Navidrome behavior differs from Jellyfin
- prevent hidden feature regressions

### Tasks

1. Rework M3U export so it does not assume Jellyfin filesystem path access.
2. Prefer server-side playlist creation where possible.
3. Make lyrics support backend-aware and optional.
4. Normalize play counts and popularity inputs before they reach analysis code.

### Success Criteria

- export behavior is clearly defined per backend
- unsupported features degrade gracefully instead of failing implicitly

## Phase 6A: Metadata Enrichment Roadmap

### Objectives

- improve original release-date accuracy for decade and era analysis
- improve genre/tag quality without depending on Last.fm alone
- keep file tags as the highest-trust local source when available

### Scope

This phase is about metadata quality only.

It should improve:

- original year and decade resolution
- genre and tag quality
- source provenance and debuggability

It should not change:

- backend abstraction
- playlist CRUD behavior
- suggestion-pipeline structure beyond better metadata inputs

### Problem Statement

The current enrichment flow is still too dependent on whichever upstream source answers first or most completely.

That creates recurring failures:

- compilation and best-of releases push tracks into newer decades
- remasters and reissues override the song's original era
- genre quality depends too heavily on Last.fm coverage
- obscure tracks often end up with weak or noisy tag data
- source disagreements are hard to inspect and reason about

This phase should make metadata selection intentional rather than opportunistic.

### Source Strategy

Use a layered metadata strategy instead of treating one external provider as authoritative.

#### Original Release Date Priority

1. local file tags when a real audio file can be resolved
2. MusicBrainz earliest credible release date
3. Last.fm release date
4. backend metadata year
5. GetSongBPM year as a weak fallback only

#### Genre And Tag Priority

1. ListenBrainz tags when a reliable MusicBrainz identity exists
2. MusicBrainz genres and tags
3. Last.fm track tags
4. backend genre metadata

### Metadata Domains

Different sources should be trusted for different metadata domains.

#### Original Release Date

Best source:

- MusicBrainz earliest credible release date

Supporting sources:

- file tags
- Last.fm
- backend metadata
- GetSongBPM

#### Canonical Identity

Best source:

- MusicBrainz recording and release-group identity

Supporting sources:

- file tags
- backend metadata

#### Genre And Tags

Best source mix:

- ListenBrainz
- MusicBrainz
- Last.fm

Supporting source:

- backend genre field

### Why MusicBrainz

MusicBrainz is the right free source for original release-date resolution, but only if it is used carefully.

- do not treat it as a naive first-hit track search
- use it to identify the underlying song or work
- then choose the earliest credible release date across matched candidates

This is specifically intended to avoid compilation and reissue drift such as:

- backend says `2003` because the file sits on a compilation
- the actual song first released in `1989`

### Why ListenBrainz

ListenBrainz is a better free complement for tags than relying on Last.fm alone, especially once a MusicBrainz identity has been resolved.

- use it as a tag enrichment layer
- do not require it to be the sole source of truth
- merge it into existing genre normalization rather than exposing raw tag noise directly

### Proposed Internal Contract

Add a normalized metadata-resolution result so core logic stops caring which source produced the answer.

Suggested internal shape:

```python
{
    "mb_recording_id": str | None,
    "mb_release_group_id": str | None,
    "matched_title": str | None,
    "matched_artist": str | None,
    "original_year": str | None,
    "year_source": str | None,
    "year_candidates": list[dict],
    "genre_tags": list[str],
    "raw_tags": list[str],
    "tag_sources": list[str],
}
```

Suggested year-candidate entry:

```python
{
    "source": "file_tags" | "musicbrainz" | "lastfm" | "backend" | "getsongbpm",
    "year": 1984,
    "confidence": float,
    "notes": str | None,
}
```

This should preserve source attribution for both debugging and `year_flag`.

### Matching Rules

The metadata pipeline should match the song identity, not the current compilation package.

#### Title Normalization

Strip or heavily penalize version markers such as:

- `remaster`
- `remastered`
- `radio edit`
- `single version`
- `video version`
- `live`
- `karaoke`
- `instrumental`
- `demo`
- `acoustic`

#### Match Priorities

1. artist match
2. normalized title match
3. explicit variant penalties
4. file-tag year proximity when available
5. album match as a weak supporting signal only
6. duration as a weak tie-breaker only

Duration should not be a primary key because too many legitimate variations exist.

### Match Scoring Rules

Use scoring, not first-hit selection.

#### Positive Signals

- exact normalized artist match
- exact normalized title match
- title contained within a longer version string where the extra text is low-risk
- year close to trusted file-tag year when present
- album match when the album itself does not look like a compilation

#### Negative Signals

- title contains `live`
- title contains `karaoke`
- title contains `instrumental`
- title contains `tribute`
- title contains `cover`
- title contains `demo`
- title contains `acoustic`
- title contains `remaster` without evidence it is still the original recording
- clear artist mismatch beyond simple featured-artist noise

#### Compilation Heuristics

Album match should be de-emphasized or penalized when the album looks like:

- `greatest hits`
- `best of`
- `ultimate collection`
- `anthology`
- `essentials`
- `singles collection`
- `gold`

#### Featured-Artist Handling

Normalize artist strings so these do not create false mismatches:

- `feat.`
- `featuring`
- `&`
- `and`
- `with`

### Original Release-Date Selection Policy

For a matched MusicBrainz candidate:

1. collect associated release dates
2. discard obvious non-original variants:
   - live
   - karaoke
   - tribute
   - instrumental-only variants
   - remaster-only variants
   - re-recordings when detectable
3. prefer the earliest remaining credible date
4. preserve the provenance in `year_flag` so disagreements remain visible

### Original-Year Resolution Rules

The winning year should not simply be the minimum of all candidates anymore.

Suggested policy:

1. If a trusted file-tag year exists, keep it as a strong candidate but not an unconditional override.
2. Resolve MusicBrainz identity and compute earliest credible release year.
3. If MusicBrainz agrees with file tags within a small tolerance, use that year.
4. If MusicBrainz is earlier than backend or Last.fm and the match quality is high, prefer MusicBrainz.
5. If file tags disagree with MusicBrainz by a large margin, keep both in `year_flag` and prefer:
   - file tags when the path is local and tags are trusted
   - MusicBrainz when the file clearly represents a compilation or reissue package
6. Use Last.fm only when MusicBrainz resolution fails or confidence is low.
7. Use backend year only as a late fallback.
8. Keep GetSongBPM year as a weak fallback only.

Recommended default:

- if file tags exist, use them first for immediate local accuracy
- if MusicBrainz finds an earlier credible original release date with high confidence, let it override for `FinalYear`
- preserve both values in `year_flag`

### Genre Resolution Rules

Genre should move from single-source selection to merged evidence.

Suggested flow:

1. collect backend genres
2. collect Last.fm track tags
3. collect MusicBrainz genres and tags
4. collect ListenBrainz tags when MBID exists
5. normalize all tags into canonical internal genre families
6. score those families
7. choose the best canonical genre

#### Tag Weighting

Recommended weighting:

- ListenBrainz tags: high
- MusicBrainz genres: high
- MusicBrainz freeform tags: medium
- Last.fm track tags: medium
- backend genres: low-to-medium
- artist-level fallback tags: low

#### Canonicalization

Expand the existing normalization so these merge correctly:

- `synth-pop` -> `synthpop`
- `folk rock` -> `folk`
- `scottish folk` -> `folk`
- `new romantic` -> `new wave`
- `sophisti-pop` -> `pop`
- `alt rock` -> `rock`
- `indie folk` -> `folk`
- `dance-pop` -> `pop`

The UI should still show canonical internal genres, not raw provider tag strings.

### Conflict Handling

When sources disagree:

- keep the winning value user-facing
- keep disagreement details machine-visible
- expose disagreement in `year_flag`
- consider a future `genre_flag` if debugging remains difficult

Examples:

- file tags say `1989`, MusicBrainz says `1989`, backend says `2003`
  - use `1989`
  - `year_flag = "file_tags: 1989 / musicbrainz: 1989 / backend: 2003"`

- file tags say `2003`, MusicBrainz says `1989`, album is clearly a compilation
  - use `1989`
  - keep both values in `year_flag`

- ListenBrainz says `new wave`, Last.fm says `pop`, backend says `rock`
  - normalize and select based on weighted canonical-family scoring

### Proposed Service Additions

- `services/musicbrainz.py`
- `services/listenbrainz.py`

#### `services/musicbrainz.py`

Suggested responsibilities:

- search candidate recordings and releases
- normalize and score candidates
- return the best matched identity
- compute earliest credible release year

Suggested entry points:

- `search_recording_candidates(title, artist) -> list[dict]`
- `match_recording(title, artist, album=None, year=None) -> dict | None`
- `get_earliest_release_year(match: dict) -> str | None`

#### `services/listenbrainz.py`

Suggested responsibilities:

- retrieve tags for a resolved MusicBrainz identity
- return normalized tag lists without UI formatting

Suggested entry points:

- `get_recording_tags(mb_recording_id: str) -> list[str]`
- `get_release_group_tags(mb_release_group_id: str) -> list[str]`

### Proposed Core Changes

#### `core/playlist.py`

- replace the current simple year-source merge with a layered resolver
- add a dedicated original-release lookup step
- keep file-tag year as highest priority when a real file is available
- record which source supplied the winning year

Suggested helpers:

- `_resolve_metadata_identity(parsed: Track) -> dict`
- `_resolve_original_year(parsed: Track, identity: dict, lastfm: dict, bpm_data: dict) -> tuple[str | None, str]`
- `_resolve_genre_tags(parsed: Track, identity: dict, lastfm: dict) -> dict`

#### Genre Resolution

- merge ListenBrainz and MusicBrainz tags into the existing normalized genre flow
- keep Last.fm as a fallback rather than the primary genre authority
- continue to normalize subgenres into the existing internal genre families

#### Caching

Add dedicated caches for:

- MusicBrainz candidate search
- MusicBrainz matched recording
- MusicBrainz earliest release year
- ListenBrainz tags

Cache keys should include normalized:

- title
- artist
- album when present

### Settings And Flags

Add optional settings for staged rollout:

- `musicbrainz_enabled`
- `listenbrainz_enabled`
- `prefer_original_release_year`

Recommended defaults:

- `musicbrainz_enabled = true`
- `listenbrainz_enabled = true`
- `prefer_original_release_year = true`

### Suggested Delivery Order

1. add `services/musicbrainz.py` for earliest-release lookup only
2. add a safe matching and scoring layer for artist plus normalized-title matching
3. use MusicBrainz earliest credible release date in year resolution
4. add `services/listenbrainz.py` for tag enrichment keyed by MusicBrainz identity
5. blend ListenBrainz, MusicBrainz, and Last.fm tags into genre normalization
6. add tests for compilation, remaster, and live-version edge cases

### PR Breakdown

#### PR 1: MusicBrainz Original-Year Foundation

- add `services/musicbrainz.py`
- add candidate scoring and earliest-release resolution
- thread MusicBrainz year into `core/playlist.py`
- add tests for compilation and remaster drift

#### PR 2: ListenBrainz Tag Enrichment

- add `services/listenbrainz.py`
- merge ListenBrainz and MusicBrainz tags into genre resolution
- add tag-normalization regressions

#### PR 3: Flags, Caching, And Debugging

- add config flags
- add cache keys and invalidation rules
- improve `year_flag` detail
- add debug logging for source disagreements

### Test Plan

Add focused tests for:

- compilation album returns original song year
- remaster does not force newer decade
- live version is rejected when original studio version exists
- title normalization strips version markers correctly
- ListenBrainz tags improve genre selection when Last.fm is sparse
- MusicBrainz unavailable path falls back cleanly
- ListenBrainz unavailable path falls back cleanly
- `year_flag` preserves all disagreement details

### Risks

- MusicBrainz match scoring could still pick the wrong song where titles are generic
- ListenBrainz tag coverage may be uneven on obscure tracks
- over-aggressive original-year preference could conflict with deliberately retagged local files

### Mitigations

- keep file tags and MusicBrainz both visible in `year_flag`
- use score thresholds and fail closed when identity confidence is low
- keep rollout behind settings flags
- preserve current fallback sources when the new pipeline cannot resolve confidently

### Acceptance Criteria

- tracks on compilations resolve to the original song era when a credible earlier release exists
- remasters do not force newer decades unless the track is actually a distinct later recording
- genre quality no longer depends solely on Last.fm coverage
- `year_flag` clearly shows when file tags, MusicBrainz, Last.fm, and backend data disagree
- the system still behaves safely when MusicBrainz or ListenBrainz is unavailable

## Phase 7: Tests And Verification

### Objectives

- keep the refactor safe
- make both adapters testable in isolation

### Tasks

1. Add adapter-level tests for Jellyfin and Navidrome.
2. Add service-factory tests.
3. Update tests that patch `services.jellyfin` directly.
4. Add backend-agnostic tests for core playlist flows.

### Verification Commands

Per repository instructions:

```bash
pip install -r requirements.txt
pip install pylint black pytest
black .
pylint core api services utils
pytest
```

## Delivery Milestones

### Milestone 1

Media-server abstraction exists and Jellyfin still works through it.

### Milestone 2

Core logic and routes are backend-agnostic.

### Milestone 3

Navidrome can connect, list playlists, and analyze playlists.

### Milestone 4

Navidrome playlist creation and export flows are defined and working.

### Milestone 5

Documentation and tests fully cover multi-backend support.

## Current Progress

### Completed

- PR 1: Adapter foundation
- PR 2: core and settings-route migration
- PR 3: Navidrome adapter and backend-aware settings flow
- `MediaServer` contract added
- `JellyfinAdapter` added
- `NavidromeAdapter` added
- `get_media_server()` factory added
- generic media settings added
- legacy Jellyfin settings migration added
- adapter-based playlist, M3U, and settings-route paths added
- backend-aware settings template added
- targeted tests added for factory, config migration, adapter behavior, forms, routes, playlist, M3U, and Navidrome flows

### Remaining

- PR 4: cleanup, terminology normalization, docs completion, and full test pass

## Resolved Design Decisions

This section converts the earlier gaps into implementation defaults. These should be treated as the baseline design unless a concrete backend limitation forces a change.

### 1. Authentication Model

Use backend-specific credentials in settings, but expose them through one generic settings shape.

Defaults:

- Jellyfin uses `media_url`, `media_api_key`, and `media_user_id`
- Navidrome uses `media_url`, `media_username`, and `media_password`
- `media_api_key` is optional for Navidrome and should not be required
- secrets remain stored in `settings.json`, matching the current app model
- connection tests validate only the fields relevant to the selected backend

Implementation rule:

- validation must branch on `media_backend`

### 2. User Identity Model

Treat explicit user selection as backend-capability based, not universally required.

Defaults:

- Jellyfin requires `media_user_id`
- Navidrome uses the authenticated user context by default
- the UI should only render user selection when the active backend supports or requires it
- the adapter interface should expose `requires_user_id: bool`

Implementation rule:

- core logic must not assume a user ID exists

### 3. Canonical Internal Models

Normalize all backend data into backend-neutral internal models before it reaches `core/`.

#### Normalized Track Shape

```python
{
    "id": str,
    "title": str,
    "artist": str,
    "artists": list[str],
    "album": str | None,
    "year": int | None,
    "genres": list[str],
    "duration_seconds": int | None,
    "play_count": int,
    "path": str | None,
    "lyrics": str | None,
    "backend": str,
    "backend_item_id": str,
}
```

#### Normalized Playlist Shape

```python
{
    "id": str,
    "name": str,
    "track_count": int | None,
    "backend": str,
}
```

#### Normalized User Shape

```python
{
    "id": str,
    "name": str,
}
```

Implementation rules:

- adapters may consume backend-native field names internally
- `core/` modules should consume normalized shapes only
- compatibility shims may temporarily translate normalized fields back into legacy field names where needed during migration

### 4. MediaServer Contract

Define the first contract as an abstract base class or protocol with explicit return types.

Required methods:

- `backend_name() -> str`
- `requires_user_id() -> bool`
- `supports_path_resolution() -> bool`
- `supports_lyrics() -> bool`
- `test_connection() -> dict`
- `list_users() -> list[dict]`
- `list_audio_playlists() -> list[dict]`
- `get_playlist_tracks(playlist_id: str) -> list[dict]`
- `search_track(title: str, artist: str) -> bool`
- `get_track_metadata(title: str, artist: str) -> dict | None`
- `get_full_audio_library(force_refresh: bool = False) -> list[str]`
- `get_lyrics(item_id: str) -> str | None`
- `create_playlist(name: str, track_ids: list[str]) -> dict | None`
- `update_playlist(playlist_id: str, track_ids: list[str]) -> dict | None`
- `delete_playlist(playlist_id: str) -> bool`
- `resolve_track_path(title: str, artist: str) -> str | None`

Error-handling rule:

- adapters should catch transport and decode failures and return empty or null-safe results
- adapter methods should log backend-specific errors internally
- `core/` code should not handle backend-specific exceptions

### 5. Export Strategy

Make server-side playlist creation the primary export path for all backends. Treat filesystem M3U export as secondary.

Defaults:

- Jellyfin continues to support path-based M3U export where possible
- Navidrome primary export is server-side playlist creation
- Navidrome path-based M3U export is optional and only enabled if reliable path data is available in practice
- when path resolution is unsupported, the UI should not present it as a normal success path

Implementation rule:

- `resolve_track_path()` is an optional-capability method; unsupported backends return `None`

### 6. Lyrics Strategy

Treat lyrics as optional enrichment, not a hard dependency.

Defaults:

- lyrics analysis remains globally configurable through `lyrics_enabled`
- adapters advertise support through `supports_lyrics()`
- if backend lyrics are unavailable, the app should continue without lyrics-based mood scoring
- local `.lrc` file lookup should remain a generic fallback when a track path is available

Implementation rule:

- missing lyrics must never fail playlist analysis

### 7. Popularity And Play Counts

Use a normalized `play_count` field for all backends.

Defaults:

- Jellyfin `UserData.PlayCount` maps to `play_count`
- Navidrome play statistics map to `play_count` if available
- if a backend does not provide play counts, default to `0`
- popularity calculations should operate on normalized `play_count`, not backend-native field names

Implementation rule:

- refactor analysis code to stop referencing `jellyfin_play_count` directly

### 8. Cache Strategy

Make all backend-sensitive cache keys include backend name and effective user identity.

Defaults:

- cache keys should use a prefix like `{backend}:{user_scope}:...`
- `user_scope` should be `media_user_id` for Jellyfin and authenticated username for Navidrome
- old Jellyfin cache contents do not need migration
- stale cache invalidation is acceptable during the transition

Implementation rule:

- preserve cache bucket names initially if needed, but change cache keys first

### 9. Terminology Strategy

Move user-facing text to backend-neutral wording except where a backend name is required for clarity.

Defaults:

- use `Media Server` in generic settings labels
- use `Server Playlist` instead of `Jellyfin Playlist` in shared UI flows
- use backend names explicitly in backend-specific connection tests and settings help text
- rename historical booleans such as `in_jellyfin` to `in_library`

Implementation rule:

- internal compatibility aliases are acceptable temporarily, but new code should not introduce more Jellyfin-specific names

### 10. Migration And Backward Compatibility

Support a soft migration path for existing installs.

Defaults:

- if legacy Jellyfin settings exist and `media_backend` is missing, auto-set `media_backend = "jellyfin"`
- map legacy fields into new generic fields at load time
- continue writing new generic fields after migration
- preserve legacy-field read support for one transition period only

Implementation rule:

- `load_settings()` should perform the migration normalization
- `save_settings()` should write the canonical schema only

## Feature Parity Matrix

This is the baseline target behavior.

| Capability | Jellyfin | Navidrome | Target Behavior |
| --- | --- | --- | --- |
| Connection test | Yes | Yes | Required |
| User selection | Yes | Usually no | Conditional by backend |
| Playlist listing | Yes | Yes | Required |
| Playlist track fetch | Yes | Yes | Required |
| Track metadata lookup | Yes | Yes | Required |
| Library scan | Yes | Yes | Required |
| Lyrics from API | Yes | Partial or backend-dependent | Optional |
| Local `.lrc` fallback | Yes | If path available | Optional |
| Server-side playlist creation | Yes | Yes | Preferred export path |
| Path-based M3U export | Yes | Maybe | Optional capability |
| Play count enrichment | Yes | Maybe | Normalize when available |

## Concrete Schema Changes

### New AppSettings Fields

Add:

- `media_backend: str = "jellyfin"`
- `media_url: str = ""`
- `media_username: str = ""`
- `media_password: str = ""`
- `media_api_key: str = ""`
- `media_user_id: str = ""`

Transitional handling:

- keep reading `jellyfin_url`, `jellyfin_api_key`, and `jellyfin_user_id`
- map them into generic media fields during load

### Validation Rules

For `media_backend == "jellyfin"` require:

- `media_url`
- `media_api_key`
- `media_user_id`
- `openai_api_key`

For `media_backend == "navidrome"` require:

- `media_url`
- `media_username`
- `media_password`
- `openai_api_key`

## Test Strategy Defaults

Use a three-layer test strategy.

### Contract Tests

Each adapter should satisfy the same test suite for:

- connection checks
- playlist listing
- track metadata lookup
- optional capability behavior

### Core Tests

Core tests should patch the media-server factory, not concrete backend modules.

### Backend-Specific Tests

Keep a small number of backend-specific tests only for:

- auth specifics
- response parsing
- backend capability differences

## Recommended PR Breakdown

### PR 1: Adapter Foundation

- add `MediaServer` contract
- add factory
- wrap Jellyfin in adapter form
- no functional changes intended

### PR 2: Core Migration

- migrate `core/` and `api/routes/` to adapter usage
- keep Jellyfin as the only active backend until tests are stable

### PR 3: Navidrome Support

- add `NavidromeAdapter`
- add backend-specific validation and UI handling

### PR 4: Cleanup And Terminology

- rename legacy field usage
- clean up compatibility shims
- finish docs and test updates

## PR 3 Detailed Execution Checklist

This is the third implementation slice. It should add a working `NavidromeAdapter`, extend backend selection beyond Jellyfin, and wire backend-aware validation and settings behavior without attempting the full terminology cleanup yet.

### Goal

Make Navidrome a real second backend with working connection, user-context handling, playlist listing, playlist track fetch, metadata lookup, and basic export-compatible behavior.

### Non-Goals

- no broad naming cleanup yet
- no full conversion from legacy history fields like `in_jellyfin`
- no comprehensive UI polish beyond what is required to choose and validate the backend
- no full cache-key redesign unless required for correctness

### Primary Work Areas

#### `services/navidrome.py`

- add `NavidromeAdapter(MediaServer)`
- implement authenticated request helper(s) for the Subsonic or OpenSubsonic API
- implement:
  - `backend_name() -> "navidrome"`
  - `requires_user_id() -> False`
  - `supports_lyrics()`
  - `supports_path_resolution() -> False` initially unless a reliable path flow is verified
  - `test_connection()`
  - `list_users()`
  - `list_audio_playlists()`
  - `get_playlist_tracks()`
  - `search_track()`
  - `get_track_metadata()`
  - `get_full_audio_library()`
  - `get_lyrics()`
  - `create_playlist()`
- implement safe default stubs for:
  - `update_playlist()`
  - `delete_playlist()`
  - `resolve_track_path()`

#### `services/media_factory.py`

- extend `get_media_server()` to return `NavidromeAdapter` when `settings.media_backend == "navidrome"`
- preserve clear error messages for unsupported backends

#### `config.py`

- ensure `validate_settings()` enforces:
  - Jellyfin: `media_url`, `media_api_key`, `media_user_id`
  - Navidrome: `media_url`, `media_username`, `media_password`
- keep legacy Jellyfin fallback logic for transition
- do not add Navidrome-specific legacy compatibility fields

#### `api/routes/settings_routes.py`

- make settings-page user loading conditional on backend capability
- for Navidrome, allow empty user list or authenticated-user-only behavior
- route connection testing through backend-aware logic
- keep the current `/test/jellyfin` endpoint only if the frontend still depends on it
- if needed, make the endpoint backend-aware internally while leaving the route name transitional

#### `api/forms.py`

- confirm generic media fields are sufficient for Navidrome
- ensure `media_username` and `media_password` are preserved into `SettingsForm`

### Secondary Work Areas

#### `templates/settings.html`

- add a backend selector if the current page still assumes Jellyfin-only configuration
- conditionally show:
  - API key and user ID for Jellyfin
  - username and password for Navidrome
- keep existing layout changes minimal in PR 3

#### `api/schemas.py`

- add backend-neutral connection-test models only if required by route wiring
- otherwise preserve current schema churn for PR 4

#### `core/playlist.py`

- verify existing adapter-based paths work with Navidrome return shapes
- add compatibility translation only where a migrated flow still assumes Jellyfin-shaped data

#### `core/m3u.py`

- keep path-based export as capability-driven
- ensure Navidrome gracefully falls back when `resolve_track_path()` returns `None`

### Navidrome Capability Targets

PR 3 should support:

- connection validation
- authenticated user context
- playlist listing
- playlist track retrieval
- track metadata lookup
- library search or scan
- server-side playlist creation if practical

PR 3 may defer:

- reliable path-based M3U export
- rich lyrics support if the API surface is inconsistent
- full playlist update or delete support

### Tests To Add Or Update

#### New tests

- `tests/test_navidrome.py`
  - adapter capability flags
  - connection-test parsing
  - playlist-list parsing
  - track metadata parsing
  - library lookup behavior

- adapter-factory coverage
  - extend `tests/test_media_factory.py` for Navidrome selection

#### Existing tests to extend

- `tests/test_config.py`
  - Navidrome validation success
  - Navidrome missing-field validation errors

- `tests/test_forms.py`
  - Navidrome form parsing for username and password

- `tests/test_api_routes.py`
  - settings routes with Navidrome active
  - route behavior when `list_users()` returns an empty list

- `tests/test_playlist.py`
  - at least one adapter-driven flow using a Navidrome-like server stub

### Exact Search Targets For PR 3

Repository-wide searches to run before editing:

- `media_backend`
- `test_jellyfin`
- `jellyfin_users`
- `settings.jellyfin_`
- `supports_path_resolution`
- `requires_user_id`

Classify each occurrence as:

- backend logic that now needs Navidrome support
- transitional Jellyfin naming that can remain until PR 4
- cleanup that should still wait

### Expected Deliverables

- `services/navidrome.py` exists and implements the adapter contract
- `get_media_server()` supports both Jellyfin and Navidrome
- config validation supports Navidrome credentials
- settings routes and forms can operate with `media_backend = "navidrome"`
- targeted Navidrome adapter and backend-selection tests pass

### Exit Criteria For PR 3

PR 3 is complete when all of the following are true:

- Navidrome can be selected through configuration
- the factory returns `NavidromeAdapter`
- Navidrome connection validation works
- Navidrome playlists and track metadata can be loaded through adapter-based flows
- settings and form tests cover both backend modes
- `black .`, `pylint core api services utils`, and the PR 3 targeted tests pass

### Verification Commands For PR 3

- `black .`
- `pylint core api services utils`
- `pytest tests/test_navidrome.py tests/test_media_factory.py tests/test_config.py tests/test_forms.py tests/test_api_routes.py tests/test_playlist.py`
