# Playlist Pilot 🎵

Playlist Pilot is a FastAPI application that generates and manages music playlists using GPT, supported media-server backends, and a few helper services. It caches results on disk so repeated requests stay fast and ships with a small web UI built with Jinja2 and Tailwind.

See [Docs/architecture.md](Docs/architecture.md) for a high level overview of the code structure.

## Features

- **Playlist suggestions** from existing playlists using GPT with Last.fm metadata and media-server library sampling.
- **Playlist analysis** of server playlists, saved GPT suggested playlists, or imported m3u playlists, measuring mood, tempo, decade distribution and popularity.
- **Playlist comparison** showing overlap between two server playlists or GPT/m3u imported playlists.
- **Playlist order suggestions** using GPT to arrange tracks for optimal flow.
- **BPM and audio data** from GetSongBPM to enrich mood scoring.
- **Lyrics-based mood analysis** when `.lrc` files or server-provided lyrics are
  available.
- **Toggle for lyrics processing** if you want to disable GPT lyric analysis.
- **Customizable weights** for lyrics, BPM and tag matching to fine tune
  playlist mood detection.
- **YouTube link lookup** via yt‑dlp for tracks not in your library, with duration filtering, VEVO prioritization and cached search results.
- **Import/export** `.m3u` files and create playlists directly in the active server when supported.
- **Track metadata export** back to Jellyfin-compatible flows where supported.
- **Combined popularity scoring** blends Last.fm listener data with server play counts to highlight mainstream and obscure tracks alike.
- **History management** with the ability to view and delete past GPT suggestions.
- **DiskCache based caching** for GPT prompts, media-server queries, Last.fm lookups and more. Aggressively caches for both speed and to reduce API costs.
- **Integration monitoring** with a simple watchdog that logs repeated backend and Last.fm failures.
- Runs as a Docker container or directly with Python.

## Requirements

- Python 3.10+
- `pip install -r requirements.txt` or use Docker
- Run the [test suite](Docs/tests.md) with `pytest`

## Testing

After installing the requirements you can execute all unit tests. Either install
the package in editable mode:

```bash
pip install -e .
pytest
```

Or set the `PYTHONPATH` environment variable before running:

```bash
PYTHONPATH=$PWD pytest
```

The [tests directory](tests/) contains standalone tests for key helpers and services. See [Docs/tests.md](Docs/tests.md) for a description of each file.

## Docker Usage

Copy `env.example` to `.env` and update the paths for your machine. Docker
Compose will read this file and mount the specified directories and
`settings.json` into the container.
Make sure the path you set for `SETTINGS_PATH` points to an **existing file**.
If the file does not exist Docker will create a directory with that name,
which causes the application to fail. You can create a blank file beforehand
with `touch /path/to/settings.json`.

Use Docker Compose to build and start the app:

```bash
docker compose up --build
```

A step‑by‑step guide is available in [Docs/docker_compose_installation.md](Docs/docker_compose_installation.md). Once running, visit [http://localhost:8010](http://localhost:8010). If required settings are missing you'll be redirected to the settings page.

## Running Locally

To start the application without Docker install the dependencies and run Uvicorn:

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8010
```

See [Docs/local_installation.md](Docs/local_installation.md) for a detailed walkthrough.
For a tour of the main screens and how to generate playlists see
[Docs/usage_guide.md](Docs/usage_guide.md).

## Development

Install the development requirements to run the linters and type checker:

```bash
pip install -r requirements-dev.txt
```

`mypy` is executed in CI, so you can optionally run it locally with:

```bash
mypy . --ignore-missing-imports
```

## Configuration

Navigate to [http://localhost:8010/settings](http://localhost:8010/settings) and supply:

- Media server backend and connection details
- For Jellyfin: server URL, API key, and user ID
- For Navidrome: server URL, username, and password
- OpenAI API key
- Last.fm API key
- Optional GetSongBPM key
- Preferred GPT model (for example `gpt-4o-mini`)

All values are saved in `settings.json` in the project root or mounted volume.
You can also place these keys in your `.env` file so they are available when the container first starts.
Read [Docs/secure_credentials.md](Docs/secure_credentials.md) for tips on keeping API keys and other secrets out of your repository. An example set of environment variables is provided in [env.example](env.example).

## API Endpoints

The API is exposed via several HTTP routes. A full table describing each route is available in [Docs/api_reference.md](Docs/api_reference.md).
For container orchestration a simple liveness probe is provided at `/health`.

## Data Persistence

- `settings.json` – saved configuration
- `cache/` – cached GPT responses and API results
- `logs/` – application logs
- `user_data/` – exported playlists and user history

These directories are excluded from version control via `.gitignore`. When
running the Docker container, mount them to host paths so logs and cached data
persist across upgrades.

## Tech Stack

- FastAPI & Jinja2 templates
- Pydantic settings
- DiskCache for persistent caching
- yt-dlp for YouTube lookups
- Jellyfin, Navidrome, Last.fm and GetSongBPM integrations

The overall architecture is described in [Docs/architecture.md](Docs/architecture.md).

## Contributing

1. Fork the repository and create a feature branch.
2. Install dependencies with `pip install -r requirements.txt`.
3. Run the tests:
   ```bash
   pytest
   ```
4. Format the code:
   ```bash
   black .
   ```
5. Lint the code:
   ```bash
   pylint core api services utils
   ```
6. Push your branch and open a pull request against `main`.

For additional details see [Docs/contributing.md](Docs/contributing.md) and the other documents in the [Docs](Docs/) directory.
See the [ROADMAP](ROADMAP.md) for future plans and open issues.
Known problems uncovered during code audits are listed in [BUGS.md](BUGS.md).

## Security

Please report security issues by following the process in [SECURITY.md](.github/SECURITY.md).

## License

Playlist Pilot is released under the terms of the [GNU GPLv3](LICENSE).

---
© 2025 Playlist Pilot Team
