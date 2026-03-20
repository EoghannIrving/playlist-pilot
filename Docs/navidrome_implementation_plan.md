# Navidrome Multi-Backend Implementation Plan

## Goal

Extend Playlist Pilot to support Navidrome without removing Jellyfin support.

The preferred architecture is a multi-backend design:

- keep the existing Jellyfin integration working
- introduce a backend abstraction for media-server operations
- add a Navidrome adapter behind the same interface

This reduces long-term maintenance cost compared with a Navidrome-only fork and keeps the door open for upstreaming the change later.

## Current State

Playlist Pilot is currently Jellyfin-centric in several layers:

- configuration fields are Jellyfin-specific
- the settings UI is Jellyfin-specific
- API connection tests are Jellyfin-specific
- core playlist logic imports Jellyfin helpers directly
- M3U export logic assumes Jellyfin path resolution
- multiple tests monkeypatch `services.jellyfin` directly

The main integration boundary is concentrated enough that this can be refactored safely if done in stages.

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
- `MediaServer` contract added
- `JellyfinAdapter` added
- `get_media_server()` factory added
- generic media settings added
- legacy Jellyfin settings migration added
- first core caller path migrated through the adapter factory
- targeted tests added for factory, config migration, adapter behavior, and playlist factory usage

### Remaining

- PR 2: migrate remaining `core/` and `api/routes/` code paths to the adapter
- PR 3: implement Navidrome adapter and backend-specific wiring
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

## File-By-File Execution Checklist

Work through these files in order. The goal is to land the abstraction first, then migrate callers, then add Navidrome.

### 1. New Adapter Layer

#### `services/media_server.py`

- define the `MediaServer` abstract base class or protocol
- define normalized typed shapes or helper models for track, playlist, and user data
- define adapter capability methods such as `requires_user_id()`, `supports_lyrics()`, and `supports_path_resolution()`
- define `get_media_server()` or keep the factory in a separate file if cleaner

#### `services/navidrome.py`

- create the `NavidromeAdapter`
- implement Subsonic or OpenSubsonic request helpers
- implement normalized playlist listing
- implement normalized track lookup and metadata lookup
- implement normalized lyrics lookup
- implement server-side playlist create or update flows
- return `None` for unsupported path resolution until proven reliable

#### Optional: `services/media_factory.py`

- add this file only if the factory feels too large for `services/media_server.py`
- centralize backend selection and adapter construction here

### 2. Existing Jellyfin Integration Refactor

#### `services/jellyfin.py`

- convert current top-level helper functions into methods consumable by `JellyfinAdapter`
- preserve current request behavior and response parsing
- normalize return values into the canonical shapes defined in the new adapter layer
- keep temporary compatibility wrappers if existing code still imports old helpers during transition

#### `services/__init__.py`

- export the new adapter-facing entry points if needed
- avoid re-exporting Jellyfin-specific helpers as the long-term public interface

### 3. Settings And Configuration

#### `config.py`

- add the new generic media-server fields:
  - `media_backend`
  - `media_url`
  - `media_username`
  - `media_password`
  - `media_api_key`
  - `media_user_id`
- implement migration from legacy Jellyfin keys during `load_settings()`
- update `validate_settings()` to branch on `media_backend`
- update cache invalidation helpers if cache key naming changes require it
- ensure `save_settings()` writes the canonical schema only

#### `env.example`

- replace or supplement Jellyfin-only examples with generic media-server settings
- document the Jellyfin and Navidrome variants clearly

#### `core/constants.py`

- replace hard-coded Jellyfin default-setting keys with generic media-setting keys
- keep temporary aliases only if still needed by older code paths

### 4. Forms, Schemas, And Route Wiring

#### `api/forms.py`

- replace Jellyfin-only form fields with generic media-server fields
- keep transitional aliases only if needed for backward compatibility
- ensure form parsing matches the new validation model

#### `api/schemas.py`

- add or rename request and response models for backend-neutral connection testing
- preserve backward compatibility only if existing frontend JavaScript still depends on current names during transition

#### `api/routes/settings_routes.py`

- replace direct imports from `services.jellyfin`
- load the active adapter from the factory
- route connection tests through the active backend
- make user-list loading conditional on backend capability
- update settings save logic to write generic media fields

#### Other files under `api/routes/`

- search for direct `services.jellyfin` imports
- switch playlist and metadata calls to the adapter factory
- rename route labels or tags that should become backend-neutral

### 5. Core Logic Migration

#### `core/playlist.py`

- remove direct imports of Jellyfin helpers
- call the active adapter for:
  - playlist listing
  - playlist track fetch
  - library scanning
  - track metadata lookup
- replace backend-native field usage such as `jellyfin_play_count` with normalized fields
- keep any temporary translation layer near the adapter boundary, not spread through the file

#### `core/m3u.py`

- remove direct imports of Jellyfin helpers
- route metadata lookup and path resolution through the adapter
- make server-side playlist creation the preferred export path where supported
- keep path-based M3U export as a capability-driven fallback

#### `core/analysis.py`

- replace direct references to Jellyfin-specific popularity fields
- use normalized `play_count`
- verify all ranking and normalization functions still behave correctly with missing play counts

#### `core/models.py`

- update model fields if they currently encode Jellyfin-specific names
- add normalized backend-neutral fields where needed
- keep compatibility fields only if removing them would cause excessive churn in one pass

#### `core/templates.py`

- update any template context helpers that assume Jellyfin naming
- expose backend name or capability flags to templates where needed

#### `core/history.py`

- inspect stored suggestion payloads for fields like `in_jellyfin`
- decide whether to migrate to `in_library` during write, read, or both

### 6. Templates And Frontend Text

#### `templates/settings.html`

- add a backend selector
- conditionally render backend-specific credential fields
- rename general labels from `Jellyfin` to `Media Server` where appropriate
- adjust the connection-test JavaScript to call the backend-neutral route or payload

#### `templates/analyze.html`

- rename `Jellyfin Playlist` labels to backend-neutral wording
- update any element IDs or JavaScript variables that encode Jellyfin-specific names if they are part of shared UX

#### `templates/compare.html`

- make playlist source wording backend-neutral
- update any serialized playlist variables or frontend labels that still imply Jellyfin-only behavior

#### `templates/history.html`

- rename export actions if they should target the active backend instead of Jellyfin specifically
- update any `in_jellyfin` display logic to use normalized `in_library`

#### `templates/results.html`

- update library-presence markers to use backend-neutral naming

#### Other templates

- search for visible `Jellyfin` wording
- leave backend-specific wording only where it is intentionally describing the selected backend

### 7. Utility Layer

#### `utils/cache_manager.py`

- update cache-key composition to include backend and user scope
- decide whether cache bucket names stay the same or become backend-neutral
- ensure no cache helpers assume Jellyfin-only fields

#### `utils/integration_watchdog.py`

- generalize integration names if failures are currently tracked under Jellyfin-only assumptions
- ensure Navidrome can be tracked independently in logs and warnings

#### `utils/helpers.py`

- inspect for any backend-specific formatting or messages

### 8. Tests

#### `tests/test_jellyfin.py`

- convert these into adapter-focused Jellyfin tests
- keep them validating parsing and capability behavior specific to Jellyfin

#### `tests/test_playlist.py`

- replace direct monkeypatching of `services.jellyfin` with monkeypatching of the adapter factory or adapter methods
- update assertions to use normalized fields

#### `tests/test_m3u.py`

- update export tests for capability-based path resolution
- add coverage for server-side export behavior if implemented here

#### `tests/test_api_routes.py`

- update route tests to reflect backend-neutral settings and connection-test flows
- add coverage for backend-specific required fields

#### `tests/test_config.py`

- add coverage for legacy Jellyfin settings migration
- add validation tests for Jellyfin and Navidrome backend modes

#### `tests/test_history.py`

- update stored field expectations if historical payload naming changes

#### `tests/conftest.py`

- add reusable adapter fixtures or backend-setting fixtures
- centralize factory monkeypatching here if it reduces repeated setup

#### Additional new tests

- add adapter contract tests
- add Navidrome-specific parsing tests
- add factory-selection tests

### 9. Documentation

#### `README.md`

- update feature descriptions from Jellyfin-first to multi-backend
- document supported backends and their required settings

#### `Docs/architecture.md`

- describe the adapter layer and backend selection flow

#### `Docs/configuration.md`

- document the new generic media-server settings
- include backend-specific examples for Jellyfin and Navidrome

#### `Docs/usage_guide.md`

- update user-facing setup and playlist flow descriptions where they mention Jellyfin specifically

#### `Docs/api_reference.md`

- rename or document any backend-neutral testing routes and settings payloads

#### `Docs/navidrome_implementation_plan.md`

- check off completed milestones as work progresses
- keep implementation notes here if design changes are needed

### 10. Final Verification Pass

#### Repository-wide search

- search for:
  - `jellyfin_`
  - `Jellyfin`
  - `in_jellyfin`
  - `jellyfin_play_count`
- classify each remaining occurrence as:
  - intentional backend-specific code
  - transitional compatibility code
  - cleanup still required

#### Verification commands

- run `black .`
- run `pylint core api services utils`
- run `pytest`

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

## PR 2 Detailed Execution Checklist

This is the second implementation slice. It should migrate the remaining Jellyfin-dependent application paths to the adapter layer while keeping Jellyfin as the only active backend.

### Goal

Make `core/` and `api/routes/` backend-agnostic enough that adding `NavidromeAdapter` becomes additive rather than invasive.

### Non-Goals

- no Navidrome implementation yet
- no backend selector UI yet
- no full terminology cleanup yet unless required by route or core migration
- no removal of legacy Jellyfin compatibility fields yet

### Primary Work Areas

#### `core/playlist.py`

- replace remaining direct Jellyfin helper usage where the adapter already has equivalent methods
- migrate:
  - playlist track fetch
  - full library scan calls
  - track metadata lookup calls
- keep temporary compatibility translation near the adapter boundary if legacy downstream code still expects Jellyfin-shaped fields
- leave backend-specific response shaping inside adapters, not in this file

#### `core/m3u.py`

- replace direct imports from `services.jellyfin`
- use `get_media_server()` for:
  - `get_track_metadata()`
  - `resolve_track_path()`
- keep current path-based export behavior for Jellyfin
- structure export flow so server-side playlist export can be added in PR 3 without another major rewrite

#### `api/routes/settings_routes.py`

- replace direct `services.jellyfin` imports with adapter-factory usage where practical
- route settings page user loading through `get_media_server().list_users()`
- route connection tests through `get_media_server().test_connection()` or a backend-neutral helper
- keep current Jellyfin route names if changing them would force premature frontend churn
- make route internals backend-aware even if the public endpoint names stay transitional

#### `api/forms.py`

- add generic media-server fields:
  - `media_backend`
  - `media_url`
  - `media_username`
  - `media_password`
  - `media_api_key`
  - `media_user_id`
- keep legacy Jellyfin fields accepted during transition if route wiring still reads them
- prefer generic fields in returned form objects

#### `api/schemas.py`

- add backend-neutral request or response models if needed for connection testing
- avoid broad schema churn unless required for `settings_routes.py`

#### `core/analysis.py`

- start replacing direct `jellyfin_play_count` assumptions where low-risk
- if a full rename is too large for PR 2, add a compatibility normalization step and defer the final rename to PR 4

### Secondary Work Areas

#### `core/models.py`

- inspect whether model fields need additive normalized aliases such as `play_count` or `in_library`
- avoid large incompatible model surgery in PR 2 unless it unblocks adapter usage

#### `core/history.py`

- keep writing existing history payload shape unless changing it is necessary for migrated core paths
- if needed, add read-time compatibility for both `in_jellyfin` and `in_library`

#### `services/jellyfin.py`

- add any missing adapter methods needed by migrated callers
- keep existing helper functions only where still referenced by transitional code
- do not start Navidrome code here

### Tests To Add Or Update

#### `tests/test_playlist.py`

- add coverage for additional adapter-based code paths migrated in `core/playlist.py`
- patch the factory or adapter methods instead of patching Jellyfin helpers directly where possible

#### `tests/test_m3u.py`

- replace direct `services.jellyfin` monkeypatching with adapter-based patching for migrated paths
- cover capability-based path resolution behavior

#### `tests/test_api_routes.py`

- update settings-route tests to reflect adapter-based user loading and connection testing
- add coverage for backend-neutral settings fields if they are introduced into route handling in this PR

#### `tests/test_forms.py`

- add tests for generic media-server form parsing
- keep transition coverage for legacy Jellyfin fields if still accepted

#### `tests/test_config.py`

- add any extra coverage required by the route and form migration

### Exact Search Targets For PR 2

Repository-wide searches to run before editing:

- `from services.jellyfin import`
- `services.jellyfin`
- `fetch_jellyfin_`
- `resolve_jellyfin_path`
- `jellyfin_play_count`
- `in_jellyfin`

Classify each occurrence as:

- migrate now to adapter usage
- keep temporarily as transitional compatibility
- defer to PR 4 cleanup

### Expected Deliverables

- `core/playlist.py` uses adapter methods for the remaining migrated paths
- `core/m3u.py` no longer imports Jellyfin helpers directly
- `api/routes/settings_routes.py` uses the adapter layer for user listing and connection testing
- `api/forms.py` accepts generic media-server settings
- route and core tests cover adapter-based flows

### Exit Criteria For PR 2

PR 2 is complete when all of the following are true:

- no new non-adapter code paths import Jellyfin helpers directly
- `core/m3u.py` and migrated `core/playlist.py` paths use `get_media_server()`
- settings routes use adapter-based connection and user-list logic
- generic media-server form fields are accepted and exercised by tests
- targeted tests for playlist, M3U, forms, config, and route flows pass
- `black .`, `pylint core api services utils`, and the updated targeted test set pass

### Verification Commands For PR 2

- `black .`
- `pylint core api services utils`
- `pytest tests/test_playlist.py tests/test_m3u.py tests/test_api_routes.py tests/test_forms.py tests/test_config.py`
