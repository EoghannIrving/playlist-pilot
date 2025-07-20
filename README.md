
# Playlist Pilot 🎵

A modular FastAPI app that helps you generate, analyze, and manage music playlists using GPT, and Jellyfin.

## 🚀 Features

- Generate playlists based on moods, genres or similar tracks
- Pull audio data from Jellyfin
- Suggest additional tracks using GPT with Last.fm enrichment
- Download missing tracks via MeTube/yt-dlp
- Analyze playlists for mood, tempo and popularity
- Sample your Jellyfin library to seed new ideas
- Export playlists as `.m3u` or directly back to Jellyfin
- Import `.m3u` files into your history
- Update track metadata in Jellyfin
- View and manage suggestion history
- Editable configuration from the web UI
- Docker & Docker Compose ready

## 🧰 Requirements

- Python 3.11+
- `pip install -r requirements.txt` OR use Docker
- Run tests with `pytest`

## 🐳 Docker Usage

Build and run with Docker Compose. Provide the location of your settings file
and music library using environment variables:

```bash
HOST_SETTINGS_FILE=/path/to/your/settings.json \
HOST_MUSIC_DIR=/path/to/your/music \
docker compose up --build
```

If these variables are not set, the compose file falls back to example paths.

See [Docs/docker_compose_installation.md](Docs/docker_compose_installation.md) for a step-by-step setup guide.

Then open your browser to: [http://localhost:8010](http://localhost:8010)
If required settings are missing, you'll be automatically redirected to the
settings page to enter them.

## ⚙️ Configuration

Visit [http://localhost:8010/settings](http://localhost:8010/settings) to set:

- Jellyfin URL, API key, and User ID
- OpenAI API key
- Last.fm API key
- Model (e.g., `gpt-4o-mini`)

These are saved in `settings.json`.

## 🧪 API Endpoints

| Method | Path                 | Description                      |
|--------|----------------------|----------------------------------|
| GET    | `/`                  | Home & manual suggestions        |
| POST   | `/suggest`           | Suggest tracks from form input   |
| GET    | `/analyze`           | Analyze a Jellyfin or history playlist |
| POST   | `/analyze/result`    | Display analysis results         |
| POST   | `/suggest-playlist`  | Suggest playlist from analysis   |
| GET    | `/history`           | View suggestion history          |
| GET    | `/history/export`    | Export saved playlist to `.m3u`  |
| POST   | `/import_m3u`        | Import an `.m3u` into history    |
| POST   | `/export/jellyfin`   | Create Jellyfin playlist         |
| POST   | `/export/track-metadata` | Update Jellyfin track metadata |
| GET    | `/settings`          | Show settings form               |
| POST   | `/settings`          | Update settings                  |
| GET    | `/compare`           | Playlist comparison (view)       |
| POST   | `/compare`           | Playlist comparison (JSON post)  |
| GET    | `/health`            | Health check for Docker          |

## 📂 Data Persistence

- `settings.json`: saved settings
- `logs/`: log output
- `cache/`: GPT and Jellyfin results
- `user_data/`: exports and more

## 🧠 Tech Stack

- FastAPI + Jinja2
- Pydantic for config
- DiskCache for storage
- yt-dlp for Youtube links
- Jellyfin API

---

© 2025 Playlist Pilot Team
