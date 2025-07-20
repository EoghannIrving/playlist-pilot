# Architecture Overview

Playlist Pilot is organized into a few key packages:

- **`main.py`** – application entry point that configures logging, loads settings and creates the FastAPI app.
- **`api/`** – request handlers and HTML forms. `routes.py` registers all endpoints and uses services and core helpers.
- **`core/`** – core business logic such as playlist analysis, history management and template helpers.
- **`services/`** – integrations with external APIs like Jellyfin, Last.fm, OpenAI and GetSongBPM.
- **`utils/`** – utility modules including caching helpers.
- **`templates/`** and **`static/`** – Jinja2 templates and static assets for the web UI.

Settings are managed via `config.py` and stored in `settings.json`. Caching uses DiskCache in the `cache/` directory. The FastAPI app serves both the HTML interface and JSON endpoints. Tests live in the `tests/` directory.
