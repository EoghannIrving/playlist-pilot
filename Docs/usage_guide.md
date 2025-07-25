# Usage Guide

This document provides a quick walkthrough of the typical workflow once Playlist Pilot is installed and configured.

## Generating playlists

1. Open the web interface at [http://localhost:8010](http://localhost:8010).
2. On the home page you will be prompted to select a playlist source (either Jellyfin or History) and to select a Playlist to analyze.
3. Click **Analyze** and Playlist-Pilot will provide you with an analysis of that playlist including a Summary, suggested tracks to remove, stats about the decade, mood, popularity and tempo of the tracks and then a track by track listing.
4. Click "Suggest Similar Playlist" and Playlist Pilot will use GPT to suggest additional tracks with a similar theme, mood etc.
5. Click "Suggest Playlist Order" to get a recommended track sequence for the analyzed playlist.
6. Review the suggestions, edit any tracks if needed and press **Save** to create the playlist in Jellyfin. (not yet available)

You can also download the results as an `.m3u` file from the history page.

## Viewing history

- The **History** link in the navigation bar lists all past suggestions for the current Jellyfin user.
- Entries are sorted by date with the newest first. Selecting one shows the full suggestion list and provides buttons to export or delete the entry.
- Playlists can be exported as an m3u file, or imported directly into Jellyfin.

## Managing playlists

Use the **Compare** page to view existing Jellyfin playlists or playlist suggestions. From here you can compare two playlists to see what tracks overlap.

For more advanced concepts see the other documents in this directory.
