# Configuration

Playlist Pilot reads its settings from `settings.json` and environment variables. Use `env.example` as a reference and copy it to `.env` with your own values.

Key options include:

- `jellyfin_url`, `jellyfin_api_key`, and `jellyfin_user_id` for connecting to your Jellyfin server.
- `openai_api_key` and `lastfm_api_key` for metadata enrichment and suggestions.
- `spotify_client_id` and `spotify_client_secret` to enable optional Spotify metadata lookups.
- `apple_client_id` and `apple_client_secret` to enable optional Apple Music metadata lookups.
- Cache TTLs and feature weights found in `config.py` can be adjusted to tune performance.

After editing the configuration restart the application for changes to take effect.
