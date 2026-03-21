# Suggestion Pipeline Reliability Spec

## Goals

- Preserve full analyzed-track metadata into the suggestion flow.
- Prevent suggestions that already exist on the source playlist.
- Enforce decade scope for decade-labeled playlists.
- Improve suggestion ranking using deterministic fit signals.
- Keep GPT as a candidate generator, not the final authority.

## Non-Goals

- No embeddings or audio-similarity implementation.
- No major UI redesign.
- No M3U/history format changes unless required for the suggestion request payload.

## Problem Statement

Current failures:

- analyzed playlist summary collapses to `Unknown`/`0` values in the suggestion step
- duplicate tracks can be suggested if they already exist on the source playlist
- decade-named playlists do not enforce decade fit
- GPT drifts toward generic reflective/chill recommendations when metadata is weak

## Root Causes To Address

- Suggestion request likely discards enriched track metadata and keeps only title/artist.
- No deterministic duplicate rejection against the source playlist.
- No deterministic decade filter for playlists named by decade.
- No reranking or rejection layer after GPT generation.

## Functional Requirements

1. Suggestion requests must preserve enriched track metadata.

The `/suggest-playlist` input must carry, per track:

- `title`
- `artist`
- `album`
- `genre`
- `mood`
- `tempo`
- `decade`
- `popularity`
- `combined_popularity`
- `FinalYear`
- `in_library`

2. The suggestion summary must be recomputed from enriched tracks, not title/artist stubs.

Expected outputs:

- dominant genre
- non-empty mood distribution when source tracks have moods
- average BPM when tempos exist
- decade distribution when years/decades exist

3. Source-playlist duplicate suggestions must be rejected.

A suggested track must not be returned if it matches any track already on the analyzed playlist after normalization.

4. GPT-output duplicates must be rejected.

If GPT returns the same track twice, keep one.

5. Decade-labeled playlists must enforce decade fit.

If playlist name indicates a decade, suggestions must be filtered by that decade policy.

6. Suggestion generation must over-generate and backfill.

If candidates are rejected, the system must continue until it has enough valid suggestions or exhausts candidates.

## Data Contract

Add a dedicated request model for suggestion input, distinct from `TrackRef`.

Suggested schema:

```python
class SuggestedSeedTrack(BaseModel):
    title: str
    artist: str
    album: str | None = None
    genre: str | None = None
    mood: str | None = None
    tempo: int | None = None
    decade: str | None = None
    popularity: int | None = None
    combined_popularity: float | None = None
    FinalYear: str | None = None
    in_library: bool | None = None
```

Then:

```python
class SuggestFromAnalyzedRequest(BaseModel):
    tracks: list[SuggestedSeedTrack]
    playlist_name: str
    text_summary: str | None = None
```

## Normalization Rules

Use a canonical `(title, artist)` comparison key for duplicate detection.

Normalization steps:

- lowercase
- Unicode normalize
- strip accents
- collapse whitespace
- remove punctuation except meaningful alphanumerics
- normalize apostrophes, quotes, and dashes
- strip common suffixes from title:
  - `remaster`
  - `remastered`
  - `radio edit`
  - `single version`
  - `video version`
  - `live`
  - `mono version`
  - `stereo version`
  - `edit`
- strip surrounding parentheses or brackets around those suffixes

Output:

```python
normalized_key = (normalized_title, normalized_artist)
```

## Playlist Type Detection

Infer playlist mode from playlist name.

Detection examples:

- `80s`, `1980s` -> `strict_decade`, target `1980-1989`
- `90s`, `1990s` -> `strict_decade`, target `1990-1999`
- `2000s`, `00s` -> `strict_decade`, target `2000-2009`

If no explicit decade marker is found:

- default to `profile_match`

Optional future modes:

- `strict_artist_family`
- `seasonal`
- `genre_core`

## Decade Policy

For `strict_decade`:

- hard accept window: exact decade
- optional soft window for fallback only: `decade +/- 1 year` or configurable adjacent range
- default behavior: reject out-of-decade tracks

Example:

- playlist `80s`
- accept: `1980-1989`
- reject: `1979`, `1990`, `2006`, `2015`

If metadata year is missing:

- candidate is lower-confidence
- either reject or penalize heavily

## Suggestion Pipeline

1. Receive enriched source tracks.
2. Compute structured playlist summary.
3. Infer playlist mode from playlist name.
4. Build normalized source-track key set.
5. Ask GPT for `count * 3` candidates minimum.
6. Normalize candidate keys.
7. Reject candidates that:
   - already exist on source playlist
   - duplicate another accepted candidate
   - violate decade policy
   - lack enough metadata for evaluation, if strict mode is active
8. Enrich remaining candidates.
9. Score remaining candidates.
10. Sort by score.
11. Return top `count`.

If fewer than `count` remain:

- optionally run another GPT round
- or return fewer with a warning or log note

## Candidate Rejection Rules

Reject immediately if:

- normalized candidate key is in the source playlist key set
- normalized candidate key already accepted in this batch
- playlist is `strict_decade` and candidate year is outside the allowed range
- candidate fails validation lookup
- candidate metadata is too incomplete for strict-mode evaluation

## Candidate Scoring

Each accepted candidate gets a fit score.

Suggested weighted components:

- decade fit: `0.35`
- genre fit: `0.20`
- mood fit: `0.15`
- popularity-band fit: `0.10`
- tempo fit: `0.10`
- artist or scenic adjacency: `0.10`

Notes:

- In `strict_decade`, decade fit should dominate.
- In general playlists, genre and mood can weigh more.

## Genre Fit

Compare candidate genre against:

- dominant genre
- top 3 genres in source playlist
- genre diversity profile

Rules:

- exact or top-genre match: high score
- adjacent genre family: medium score
- unrelated genre: low score

## Mood Fit

Compare candidate mood against:

- dominant moods
- mood distribution

Rules:

- mood in top mood bucket: positive
- generic `unknown`: neutral or slight penalty
- contradictory mood: negative

## Popularity Fit

Avoid suggesting only ultra-obscure or only globally dominant tracks if the source playlist sits elsewhere.

Compare candidate popularity against:

- source median or average popularity band

## Tempo Fit

If source playlist has good tempo coverage:

- reward candidates whose tempo falls near the main cluster
- mildly penalize large deviations unless playlist is intentionally broad

## Prompt Requirements

Prompt should explicitly state:

- playlist mode if detected
- dominant decade window
- top genre and mood cluster
- avoid duplicates from source playlist
- rank fit over popularity
- prefer scene and era adjacency

For decade playlists:

- `This playlist is explicitly scoped to 1980s tracks.`
- `Prefer 1980s releases.`
- `Do not suggest post-1989 tracks.`

Prompt remains advisory; deterministic filters remain authoritative.

## Observability

Add debug logging for each suggestion run:

- source track count
- playlist mode
- computed summary
- candidate count returned by GPT
- `rejected_duplicate_source` count
- `rejected_duplicate_batch` count
- `rejected_decade` count
- `rejected_missing_metadata` count
- `accepted` count

This is necessary for tuning.

## UI Expectations

Suggestion results page should continue to show:

- dominant genre
- moods
- avg BPM
- decades

If those are missing:

- that is a bug condition for enriched source tracks
- optionally log a warning when summary fields collapse unexpectedly

## Acceptance Criteria

For a playlist named `80s`:

- no suggested track already on the playlist
- majority or all suggestions are from the 1980s according to strict mode
- no 2000s or 2010s drift unless explicitly allowed
- summary block shows non-empty genre, mood, tempo, and decade fields when source analysis had them
- GPT outputs are filtered and reranked before display

## Test Cases

Add tests for:

- enriched suggestion request preserves genre, mood, tempo, and decade
- duplicate detection catches exact match
- duplicate detection catches remaster or video-version variants
- `80s` playlist rejects 2000s candidate
- `80s` playlist accepts 1984 candidate
- summary recomputation from suggestion payload returns non-empty fields
- reranking prefers decade-fit candidate over popularity-only candidate

## Suggested Delivery Order

1. Fix request schema so enriched track metadata survives.
2. Add source-playlist duplicate normalization and rejection.
3. Add decade-mode detection and strict decade filter.
4. Add candidate reranking.
5. Tighten prompt with explicit decade and profile constraints.
6. Add logs and tests.

## Implementation Checklist

### Phase 1: Preserve Enriched Track Payload

Goal: ensure `/suggest-playlist` receives the same enriched track data shown on the analysis page.

Tasks:

- Add a dedicated enriched suggestion seed schema in `api/schemas.py`.
- Replace `TrackRef` usage in `SuggestFromAnalyzedRequest` with the richer schema.
- Verify `analysis_result.html` posts full track payloads unchanged.
- Verify `suggest_from_analyzed()` does not discard metadata when rebuilding `tracks`.
- Add tests that confirm `genre`, `mood`, `tempo`, `decade`, and `FinalYear` survive the request boundary.

Exit criteria:

- `summarize_tracks()` inside `/suggest-playlist` returns non-empty values for analyzed playlists that already had enriched metadata.
- The results page no longer shows `Dominant Genre: Unknown`, `Avg. BPM: 0`, and empty decades for a metadata-rich playlist.

### Phase 2: Normalize Track Identity And Reject Duplicates

Goal: prevent suggestions that already exist on the source playlist and prevent duplicate suggestions in a single run.

Tasks:

- Add a reusable normalization helper for `(title, artist)` comparison keys.
- Normalize punctuation, accents, version suffixes, and whitespace.
- Build a normalized source-playlist key set before suggestion acceptance.
- Reject GPT candidates already present in the source playlist.
- Reject GPT candidates already accepted earlier in the same batch.
- Add rejection logging for duplicate-source and duplicate-batch cases.
- Add tests for exact-match and remaster/video-version duplicate rejection.

Exit criteria:

- Tracks already on the playlist are never returned as suggestions.
- Versioned title variants of source tracks are also rejected.

### Phase 3: Detect Decade Playlists And Enforce Decade Fit

Goal: make explicit decade playlists behave deterministically.

Tasks:

- Add playlist-name parsing for `80s`, `1980s`, `90s`, `1990s`, `2000s`, `00s`, etc.
- Introduce playlist suggestion modes, starting with `strict_decade` and `profile_match`.
- For `strict_decade`, compute an allowed year window.
- Reject candidates outside the allowed decade window.
- Decide policy for missing-year candidates: reject or heavily penalize.
- Add logging for decade-mode activation and decade-based rejections.
- Add tests for acceptance of in-decade candidates and rejection of out-of-decade candidates.

Exit criteria:

- A playlist named `80s` does not return 1960s, 1990s, 2000s, or 2010s suggestions.
- Decade enforcement is deterministic and not prompt-dependent.

### Phase 4: Add Candidate Scoring And Reranking

Goal: make accepted suggestions better ordered and more faithful to the source playlist.

Tasks:

- Add a candidate fit scorer with weighted components:
  - decade fit
  - genre fit
  - mood fit
  - popularity-band fit
  - tempo fit
  - artist/scenic adjacency
- Score only candidates that survive hard rejections.
- Sort surviving candidates by score before trimming to `count`.
- Add tests that verify better-fit same-decade candidates outrank generic high-popularity ones.

Exit criteria:

- Suggestions are ranked by playlist fit, not just by GPT ordering.
- Same-era, same-scene candidates beat generic modern “vibe” picks.

### Phase 5: Tighten Prompting

Goal: improve candidate generation quality before deterministic filtering.

Tasks:

- Update the suggestion prompt with explicit fit rules around era, scene, production style, and adjacency.
- Pass structured playlist summary plus prose profile summary into the prompt.
- Add decade-specific instruction blocks for `strict_decade` playlists.
- Ensure prompt wording reinforces duplicate avoidance and fit-over-popularity behavior.

Exit criteria:

- GPT output quality improves before post-filtering.
- The system still relies on deterministic filtering as the final authority.

### Phase 6: Add Observability And Regression Coverage

Goal: make the pipeline debuggable and safe to tune.

Tasks:

- Log source track count, playlist mode, and computed summary.
- Log GPT candidate count and all rejection counts.
- Log accepted count and final shortlist.
- Add end-to-end tests around decade playlists and duplicate rejection.
- Add fixture-based tests for low-metadata and high-metadata playlists.

Exit criteria:

- Suggestion failures can be explained from logs.
- The new pipeline is covered by focused regression tests.

## Recommended First Implementation Slice

Start with Phases 1 through 3 only:

1. preserve enriched track metadata into `/suggest-playlist`
2. normalize and reject source-playlist duplicates
3. enforce strict decade filtering for decade-named playlists

Why:

- these three changes address the biggest correctness failures directly
- they are deterministic
- they do not depend on subjective scoring weights
- they should materially improve `80s` playlist results before reranking work starts

## Definition Of Done For First Slice

- analyzed playlists retain their enriched summary fields during suggestion generation
- suggestions never include tracks already on the source playlist
- decade playlists reject out-of-decade tracks deterministically
- focused tests exist for all three behaviors
- logs clearly show why candidates were rejected
