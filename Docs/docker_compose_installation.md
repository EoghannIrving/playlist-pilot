# Docker Compose Setup

Follow these steps to run **Playlist Pilot** using Docker Compose.

## Prerequisites

- Docker and Docker Compose installed
- Copy `env.example` to `.env` and update the paths and API keys for your environment.
  Docker Compose will substitute these values into `docker-compose.yml`.

## Steps

1. **Clone the repository**
   ```bash
   git clone <REPO_URL>
   cd playlist-pilot
   ```
2. **Configure paths and secrets**
   Copy `env.example` to `.env` and update the variables to match your system.
   This file controls where logs, cache and other data are stored and can hold
   your API keys. The provided `docker-compose.yml` uses these variables for
   volume mounts so you can keep data anywhere you like.
   Ensure the path specified by `SETTINGS_PATH` already exists as a file.
   If the file is missing Docker will create a directory with that name and
   Playlist Pilot will be unable to load its configuration. Create the file
   manually with `touch /path/to/settings.json` before starting the container.
3. **Build and start the containers**
   ```bash
   docker compose up --build -d
   ```
   The `-d` flag runs the app in the background. Omit it if you want to follow the logs.
4. **Open the web interface**
   Go to [http://localhost:8010](http://localhost:8010) in your browser.
5. **Configure Playlist Pilot**
   Visit [http://localhost:8010/settings](http://localhost:8010/settings) to enter API keys and other settings. These persist in `settings.json`.
6. **Stop the containers**
   ```bash
   docker compose down
   ```

That's it! Playlist Pilot is now running via Docker Compose.
