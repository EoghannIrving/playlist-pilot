
# Playlist Pilot 🎵

A modular FastAPI app that helps you generate and manage music playlists using GPT, Jellyfin, and MeTube.

## 🚀 Features

- Generate playlists based on moods, genres, or similar tracks
- Pull audio data from Jellyfin
- Suggest additional tracks using OpenAI's GPT
- Download missing tracks via MeTube
- Export to `.m3u` playlists
- Editable configuration from web UI
- Docker + Docker Compose ready

## 🧰 Requirements

- Python 3.11+
- `pip install -r requirements.txt` OR use Docker

## 🐳 Docker Usage

Build and run with Docker Compose:

```bash
docker compose up --build
```

Then open your browser to: [http://localhost:8010](http://localhost:8010)

## ⚙️ Configuration

Visit [http://localhost:8010/settings](http://localhost:8010/settings) to set:

- Jellyfin URL, API key, and User ID
- OpenAI API key
- Last.fm API key
- Model (e.g., `gpt-4o-mini`)

These are saved in `settings.json`.

## 🧪 API Endpoints

| Method | Path               | Description                      |
|--------|--------------------|----------------------------------|
| GET    | `/`                | Home                             |
| GET    | `/settings`        | Show settings form               |
| POST   | `/settings`        | Update settings                  |
| GET    | `/compare`         | Playlist comparison (view)       |
| POST   | `/compare`         | Playlist comparison (JSON post)  |
| POST   | `/suggest`         | Suggest tracks (from form)       |
| GET/POST | `/library-suggest` | Generate from library           |
| GET    | `/health`          | Health check for Docker          |

## 📂 Data Persistence

- `settings.json`: saved settings
- `logs/`: log output
- `cache/`: GPT and Jellyfin results
- `user_data/`: exports and more

## 🧠 Tech Stack

- FastAPI + Jinja2
- Pydantic for config
- DiskCache for storage
- yt-dlp and MeTube for downloads
- Jellyfin API

---

© 2025 Playlist Pilot Team
