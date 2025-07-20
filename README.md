# Playlist Pilot 🎵

Playlist Pilot is a FastAPI application that generates and manages music playlists using GPT, Jellyfin and a few helper services. It caches results on disk so repeated requests stay fast and ships with a small web UI built with Jinja2 and Tailwind.

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

## Configuration

Navigate to [http://localhost:8010/settings](http://localhost:8010/settings) and supply:

- Jellyfin server URL, API key and user ID
- OpenAI API key
- Last.fm API key
- Optional GetSongBPM key
- Preferred GPT model (for example `gpt-4o-mini`)

All values are saved in `settings.json` in the project root or mounted volume.
You can also place these keys in your `.env` file so they are available when the
container first starts.

## API Endpoints

| Method | Path | Description |
|-------|------|-------------|
| GET | `/` | Home page / manual suggestions |
| POST | `/suggest` | Suggest tracks from form input |
| GET | `/analyze` | Analyze a Jellyfin or history playlist |
| POST | `/analyze/result` | Display analysis results |
| POST | `/analyze/export-m3u` | Export analysis results as M3U |
| POST | `/suggest-playlist` | Suggest playlist from analysis |
| GET | `/compare` | Playlist comparison form |
| POST | `/compare` | Compare two playlists |
| GET | `/history` | View suggestion history |
| POST | `/history/delete` | Delete a history entry |
| GET | `/history/export` | Export a history entry as `.m3u` |
| POST | `/import_m3u` | Import an `.m3u` into history |
| POST | `/export/jellyfin` | Create a Jellyfin playlist |
| POST | `/export/track-metadata` | Update Jellyfin track metadata |
| GET | `/settings` | Show settings form |
| POST | `/settings` | Update settings |
| POST | `/api/test/lastfm` | Check Last.fm connectivity |
| POST | `/api/test/jellyfin` | Check Jellyfin connectivity |
| GET | `/health` | Health check |

## Data Persistence

- `settings.json` – saved configuration
- `cache/` – cached GPT responses and API results
- `logs/` – application logs
- `user_data/` – exported playlists and user history

## Tech Stack

- FastAPI & Jinja2 templates
- Pydantic settings
- DiskCache for persistent caching
- yt-dlp for YouTube lookups
- Jellyfin, Last.fm and GetSongBPM integrations

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

For additional setup guidance see the files in the [Docs](Docs/) directory.
See the [ROADMAP](ROADMAP.md) for future plans and open issues.

## License

Playlist Pilot is released under the terms of the [GNU GPLv3](LICENSE).

---
© 2025 Playlist Pilot Team
