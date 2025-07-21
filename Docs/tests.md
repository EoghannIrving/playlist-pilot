# Test Suite

Playlist Pilot ships with a lightweight set of unit tests located in the `tests/` directory. They use **pytest** and rely on small stubs instead of network calls so they run quickly with minimal dependencies.

## Running the tests

1. Install the requirements and development tools:
   ```bash
   pip install -r requirements.txt
   pip install pytest black pylint
   ```
2. Execute the full test suite from the project root:
   ```bash
   pytest
   ```
   You can run a single file with `pytest tests/test_file.py` or filter by name with `pytest -k <pattern>`.

## Test files

- `test_analysis.py` – checks popularity scoring and summary helpers in `core.analysis`.
- `test_api_routes.py` – loads the `health_check` endpoint and verifies it returns `{"status": "ok"}`.
- `test_config.py` – ensures settings files are created correctly and that cache clearing works.
- `test_gpt_jellyfin.py` – uses stubs to test Jellyfin search helpers and GPT line parsing.
- `test_history.py` – validates date extraction from history labels.
- `test_history_suggestions.py` – covers persisting suggestions, `enrich_suggestion` failures and Last.fm lookups.
- `test_lastfm.py` – tests the `normalize` helper used by the Last.fm service.
- `test_m3u.py` – verifies M3U import/export helpers and path metadata parsing.
- `test_playlist.py` – exercises the `extract_year` helper.
- `test_text_utils.py` – ensures Markdown stripping works as expected.
