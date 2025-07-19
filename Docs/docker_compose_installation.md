# Docker Compose Setup

Follow these steps to run **Playlist Pilot** using Docker Compose.

## Prerequisites

- Docker and Docker Compose installed
- Optional: edit `docker-compose.yml` to adjust volume paths for your environment

## Steps

1. **Clone the repository**
   ```bash
   git clone <REPO_URL>
   cd playlist-pilot
   ```
2. **Build and start the containers**
   ```bash
   docker compose up --build -d
   ```
   The `-d` flag runs the app in the background. Omit it if you want to follow the logs.
3. **Open the web interface**
   Go to [http://localhost:8010](http://localhost:8010) in your browser.
4. **Configure Playlist Pilot**
   Visit [http://localhost:8010/settings](http://localhost:8010/settings) to enter API keys and other settings. These persist in `settings.json`.
5. **Stop the containers**
   ```bash
   docker compose down
   ```

That's it! Playlist Pilot is now running via Docker Compose.
