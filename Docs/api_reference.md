# API Reference

The table below summarises the main endpoints exposed by Playlist Pilot. All endpoints return JSON or HTML depending on the route.

| Method | Path | Description |
|-------|------|-------------|
| GET | `/` | Home page showing Jellyfin playlists and history |
| POST | `/suggest` | Generate a playlist from manual input |
| GET | `/analyze` | Choose a playlist for analysis |
| POST | `/analyze/result` | Display analysis results |
| POST | `/analyze/export-m3u` | Export analyzed tracks as M3U |
| POST | `/suggest-playlist` | Suggest a playlist from analysis results |
| GET | `/compare` | Display comparison form |
| POST | `/compare` | Compare two playlists |
| GET | `/history` | View past GPT suggestions |
| POST | `/history/delete` | Delete a history entry |
| GET | `/history/export` | Export a history entry as `.m3u` |
| POST | `/import_m3u` | Import an `.m3u` file |
| POST | `/export/jellyfin` | Create a Jellyfin playlist |
| POST | `/export/track-metadata` | Update Jellyfin track metadata |
| GET | `/settings` | View current configuration |
| POST | `/settings` | Update settings |
| POST | `/api/test/lastfm` | Verify Last.fm connectivity |
| POST | `/api/test/jellyfin` | Verify Jellyfin connectivity |
| GET | `/health` | Simple health check |

Return codes generally follow HTTP conventions: 200 for success, 4xx for invalid input and 5xx for unexpected errors.
