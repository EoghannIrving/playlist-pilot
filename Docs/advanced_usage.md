# Advanced Usage

Once you are comfortable generating playlists there are several ways to customise Playlist Pilot.

- **Weights** – The influence of lyrics, BPM and Last.fm tags on mood detection can be tweaked in the settings page.
- **Cache control** – Clear individual caches from the settings page or via the CLI to force fresh lookups.
- **Library scans** – Increase `library_scan_limit` if your Jellyfin library is large and you want more tracks analysed per request.
- **Models** – Provide your own OpenAI model name if you have access to a custom one.

These options allow power users to fine‑tune the suggestion engine and metadata enrichment process.

## Understanding analysis results

Playlist analyses show mood badges next to each track. Badge colours convey how
confident Playlist Pilot is about the detected mood—grey for low confidence,
yellow for moderate, green for high and blue for very high. Hovering over a
badge reveals the exact confidence score.

The results also include an **Outliers** list highlighting tracks that differ
from the playlist's dominant mood, genre, tempo or popularity. Up to five
tracks are flagged so you can quickly spot songs that may not fit well.

These features form part of the planned *Enhanced Analysis* work described in
the [ROADMAP](../ROADMAP.md#phase-2-%E2%80%93-advanced-analysis--playlist-management).
