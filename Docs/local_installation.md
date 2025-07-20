# Local Installation

You can run Playlist Pilot without Docker by installing the Python requirements and running the app directly.

1. **Clone the repo** and install dependencies:
   ```bash
   git clone <REPO_URL>
   cd playlist-pilot
   pip install -r requirements.txt
   ```
2. **Create a settings file** by copying `env.example` to `.env` and filling in your API keys and paths. You can also create `settings.json` manually following the fields in `config.py`.
3. **Start the server**:
   ```bash
   uvicorn main:app --reload --port 8010
   ```
4. Visit [http://localhost:8010](http://localhost:8010) and configure the application via the settings page.

Logs and cache files are stored in the directories defined by your environment variables.
