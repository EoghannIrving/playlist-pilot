Below is an updated high-level roadmap for Playlist Pilot reflecting the new information.

---

## Phase 1 – Stabilization and Finishing Core Features ✅ Completed
1. **Polish existing functionality**
   - Ensure playlist suggestions from similar tracks work reliably (no mood/genre generation). **Complete**
   - Keep Jellyfin and Last.fm integrations resilient to failures. - **Complete**
   - Finalize importing and exporting `.m3u` playlists. **Complete**
2. **Lyrics Toggle**
   - Lyrics are currently processed automatically—add a configuration option to disable this when desired. **Complete**
3. **Documentation & Testing** 
   - Expand documentation beyond the current README. **Complete**
   - Increase test coverage. **Complete**
4. **User Experience Improvements**
   - Refine the web interface for editing settings, viewing history, and displaying clearer error messages and logs. **Complete**

## Phase 2 – Advanced Analysis & Playlist Management
1. **Enhanced Analysis ✅ Completed**
   - Mood badges display confidence levels and analyses highlight up to five outliers. **Complete**
2. **Playlist Management Tools**
   - Add functions for renaming playlists and reordering tracks, and handle duplicates.
   - Track removal from Jellyfin playlists was removed after testing proved unreliable.
   - Integrate Jellyfin's playlist API to rename playlists and change item order. Leverage the `MoveItem` and `UpdatePlaylist` endpoints.
3. **Improved History & Settings**
   - Continue refining playlist history views and configuration editing from the UI. **Complete**

## Phase 3 – Cross-Service Integration & Scaling
1. **Integrations with Other Streaming Services**
   - Investigate fetching metadata or play links from sources such as Spotify or Apple Music.
2. **Scalability Enhancements**
   - Optimize caching and asynchronous calls, and improve containerization for larger libraries.
3. **Download Support (Future)**
   - Since there is currently no MeTube integration and yt-dlp is only used for finding links, evaluate if/when actual downloading should be introduced.
4. **Integration Watchdog Visibility**
   - Surface external service failure counts in the UI and allow configuring the watchdog threshold.

## Phase 4 – API Expansion & Future Explorations
1. **API Expansion**
   - Once the core features are stable, extend the FastAPI endpoints into a fully documented API for remote clients or potential mobile apps.
2. **Machine Learning Enhancements**
   - Experiment with advanced or fine-tuned models for mood analysis and similarity scoring.
3. **Client Applications & Community Feedback**
   - Explore building a mobile app or PWA and gather community feedback for further iteration.

---

This roadmap removes the previous “moods/genres playlist generation” item, notes that lyrics are processed automatically with a possible toggle, clarifies that no download capability or MeTube code exists, postpones broad API expansion to a later phase, and introduces playlist management tasks such as renaming and removing tracks.
