# Playlist Pilot 🎵

Playlist Pilot is a FastAPI application that generates and manages music playlists using GPT, Jellyfin and a few helper services. It caches results on disk so repeated requests stay fast and ships with a small web UI built with Jinja2 and Tailwind.

See [Docs/architecture.md](Docs/architecture.md) for a high level overview of the code structure.

## Features

- **Playlist suggestions** from moods, genres or existing songs using GPT with Last.fm metadata and Jellyfin library sampling.
- **Playlist analysis** of Jellyfin or saved GPT playlists measuring mood, tempo, decade distribution and popularity.
- **Playlist comparison** showing overlap between two Jellyfin or GPT playlists.
- **BPM and audio data** from GetSongBPM to enrich mood scoring.
- **YouTube link lookup** via yt‑dlp for tracks not in Jellyfin.
- **Import/export** `.m3u` files and create playlists directly in Jellyfin.
- **Track metadata export** back to Jellyfin (genre, mood tags, album, etc.).
- **History management** with the ability to view and delete past GPT suggestions.
- **DiskCache based caching** for GPT prompts, Jellyfin queries, Last.fm lookups and more.
- Runs as a Docker container or directly with Python.

## Requirements

- Python 3.11+
- `pip install -r requirements.txt` or use Docker
- Run tests with `pytest`

## Docker Usage

Copy `env.example` to `.env` and update the paths for your machine. Docker
Compose will read this file and mount the specified directories and
`settings.json` into the container.

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

## Configuration

Navigate to [http://localhost:8010/settings](http://localhost:8010/settings) and supply:

- Jellyfin server URL, API key and user ID
- OpenAI API key
- Last.fm API key
- Optional GetSongBPM key
- Preferred GPT model (for example `gpt-4o-mini`)

All values are saved in `settings.json` in the project root or mounted volume.
You can also place these keys in your `.env` file so they are available when the container first starts.
Read [Docs/secure_credentials.md](Docs/secure_credentials.md) for tips on keeping API keys and other secrets out of your repository. An example set of environment variables is provided in [env.example](env.example).

## API Endpoints

The API is exposed via several HTTP routes. A full table describing each route is available in [Docs/api_reference.md](Docs/api_reference.md).

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
- Jellyfin, Last.fm and GetSongBPM integrations

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

## License

Playlist Pilot is released under the terms of the [GNU GPLv3](LICENSE).

---
© 2025 Playlist Pilot Team
