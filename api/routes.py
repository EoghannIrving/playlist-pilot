"""
routes.py

This module defines all FastAPI route handlers for Playlist Pilot,
including:

- Home page with playlist suggestions
- GPT-augmented suggestion flow
- Playlist comparison
- User history view and deletion
- Settings management
"""

# pylint: disable=too-many-lines

import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from time import perf_counter

import asyncio
from urllib.parse import quote_plus

import httpx
import openai
import cloudscraper
from fastapi import (
    APIRouter,
    Request,
    Form,
    Query,
    UploadFile,
    File,
    HTTPException,
    Depends,
)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from starlette.background import BackgroundTask

from config import (
    save_settings,
    settings,
)
from core.analysis import summarize_tracks, add_combined_popularity
from core.history import (
    extract_date_from_label,
    delete_history_entry_by_id,
)
from core.m3u import (
    export_history_entry_as_m3u,
    import_m3u_as_history_entry,
    persist_history_and_m3u,
    cleanup_temp_file,
)
from core.playlist import (
    enrich_jellyfin_playlist,
    enrich_track,
    fetch_audio_playlists,
    normalize_track,
    enrich_and_score_suggestions,
)
from core.templates import templates
from core.models import ExportPlaylistRequest
from services import jellyfin
from services.gpt import (
    generate_playlist_analysis_summary,
    fetch_gpt_suggestions,
    fetch_order_suggestions,
    fetch_openai_models,
)
from services.jellyfin import (
    create_jellyfin_playlist,
    fetch_jellyfin_track_metadata,
    fetch_jellyfin_users,
    fetch_tracks_for_playlist_id,
    resolve_jellyfin_path,
)
from services.lastfm import get_lastfm_tags
from utils.helpers import (
    get_cached_playlists,
    load_sorted_history,
    parse_suggest_request,
    get_log_excerpt,
)
from api.forms import SettingsForm


logger = logging.getLogger("playlist-pilot")


router = APIRouter()


# ─────────────────────────────────────────────────────────────
# ROUTES


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Render the homepage with a list of audio playlists.
    Uses cached data if available.
    """
    try:
        settings.validate_settings()
    except ValueError:
        return RedirectResponse(url="/settings", status_code=302)

    user_id = settings.jellyfin_user_id
    playlists_data = await get_cached_playlists(user_id)
    error_message = playlists_data.get("error")
    history = load_sorted_history(user_id)

    return templates.TemplateResponse(
        "analyze.html",
        {
            "request": request,
            "jellyfin_playlists": playlists_data["playlists"],
            "history": history,
            "error_message": error_message,
        },
    )


@router.post("/compare", response_class=HTMLResponse)
async def compare_playlists_form(request: Request):  # pylint: disable=too-many-locals
    """Compare the overlap between two playlists (GPT or Jellyfin)."""
    history = load_sorted_history(settings.jellyfin_user_id)
    pf_data = await fetch_audio_playlists()
    all_playlists = pf_data["playlists"]
    error_message = pf_data.get("error")

    form = await request.form()
    s1_type = form.get("source1_type")
    s1_id = form.get("source1_id")
    s2_type = form.get("source2_type")
    s2_id = form.get("source2_id")

    if not all([s1_type, s1_id, s2_type, s2_id]):
        return templates.TemplateResponse(
            "compare.html",
            {
                "request": request,
                "history": history,
                "playlists": all_playlists,
                "error_message": error_message,
                "comparison": ["⚠️ Missing playlist selection."],
                "selected": {
                    "source1_type": s1_type,
                    "source1_id": s1_id,
                    "source2_type": s2_type,
                    "source2_id": s2_id,
                },
            },
        )

    async def resolve(source_type, source_id):
        """Resolve playlist details for comparison."""
        if source_type == "history":
            try:
                entry = history[int(source_id)]
                label = entry["label"]
                tracks = [
                    " - ".join(track["text"].split(" - ")[:2])
                    for track in entry["suggestions"]
                ]
                return label, tracks
            except (ValueError, IndexError, KeyError) as exc:
                logger.warning(
                    "\u274c Failed to resolve GPT history index %s: %s", source_id, exc
                )
                return None, []
        if source_type == "jellyfin":
            tracks = await fetch_tracks_for_playlist_id(source_id)
            label = next(
                (p["name"] for p in all_playlists if p["id"] == source_id),
                "Jellyfin Playlist",
            )
            formatted = [
                f'{t["Name"]} - {(t.get("Artists") or [None])[0] or t.get("AlbumArtist", "")}'
                for t in tracks
            ]
            return label, formatted
        return None, []

    label1, tracks1 = await resolve(s1_type, s1_id)
    label2, tracks2 = await resolve(s2_type, s2_id)

    if not tracks1 or not tracks2:
        return templates.TemplateResponse(
            "compare.html",
            {
                "request": request,
                "history": history,
                "playlists": all_playlists,
                "error_message": error_message,
                "comparison": ["⚠️ One or both playlists could not be resolved."],
                "selected": {
                    "source1_type": s1_type,
                    "source1_id": s1_id,
                    "source2_type": s2_type,
                    "source2_id": s2_id,
                },
            },
        )

    def normalize(string: str) -> str:
        """Normalize track string for comparison."""
        return string.lower().strip()

    set1_norm = set(map(normalize, tracks1))
    set2_norm = set(map(normalize, tracks2))

    only_in_1 = sorted([t for t in tracks1 if normalize(t) not in set2_norm])
    only_in_2 = sorted([t for t in tracks2 if normalize(t) not in set1_norm])
    common_tracks = sorted([t for t in tracks1 if normalize(t) in set2_norm])

    comparison = []

    if only_in_1:
        comparison.append(
            {
                "side": "only_in_1",
                "label": f"🎵 Only in {label1}",
                "tracks": only_in_1,
            }
        )
    if only_in_2:
        comparison.append(
            {
                "side": "only_in_2",
                "label": f"🎶 Only in {label2}",
                "tracks": only_in_2,
            }
        )
    if common_tracks:
        comparison.append(
            {"side": "shared", "label": "✅ Shared Tracks", "tracks": common_tracks}
        )
    if not comparison:
        comparison.append(
            {
                "label": "✅ The playlists contain the same tracks.",
                "tracks": [],
                "side": "shared",
            }
        )

    return templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "history": history,
            "playlists": all_playlists,
            "error_message": error_message,
            "comparison": comparison,
            "selected": {
                "source1_type": s1_type,
                "source1_id": s1_id,
                "source2_type": s2_type,
                "source2_id": s2_id,
            },
        },
    )


@router.get("/compare", response_class=HTMLResponse)
async def compare_ui(request: Request):
    """Render the playlist comparison form."""
    history = load_sorted_history(settings.jellyfin_user_id)
    pf_data = await fetch_audio_playlists()
    all_playlists = pf_data["playlists"]
    error_message = pf_data.get("error")
    return templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "history": history,
            "playlists": all_playlists,
            "error_message": error_message,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request, sort: str = Query("recent"), deleted: int = Query(0)
):
    """Display the user's GPT history with optional sorting."""
    history = load_sorted_history(settings.jellyfin_user_id)

    if sort == "recent":
        history.sort(key=lambda e: extract_date_from_label(e["label"]), reverse=True)
    elif sort == "oldest":
        history.sort(key=lambda e: extract_date_from_label(e["label"]))
    elif sort == "az":
        history.sort(key=lambda e: e["label"].lower())
    elif sort == "za":
        history.sort(key=lambda e: e["label"].lower(), reverse=True)

    log_excerpt = get_log_excerpt()
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "history": history,
            "sort": sort,
            "deleted": deleted,
            "log_excerpt": log_excerpt,
        },
    )


@router.post("/history/delete", response_class=HTMLResponse)
async def delete_history(request: Request):
    """
    Delete a playlist entry from the user's history.
    """
    form = await request.form()
    raw_id = form.get("entry_id")
    entry_id = raw_id if isinstance(raw_id, str) else ""
    delete_history_entry_by_id(settings.jellyfin_user_id, entry_id)
    return RedirectResponse(url="/history", status_code=303)


@router.get("/health", response_class=JSONResponse)
async def health_check():
    """
    Simple endpoint for liveness monitoring.
    """
    return {"status": "ok"}


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    """
    Display current configuration and available Jellyfin users.
    """
    try:
        settings.validate_settings()
        validation_message = None
        validation_error = False
    except ValueError as ve:
        validation_message = str(ve)
        validation_error = True
    users = await fetch_jellyfin_users()
    models = await fetch_openai_models(settings.openai_api_key)
    log_excerpt = get_log_excerpt()

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings.dict(),
            "models": models,
            "validation_message": validation_message,
            "validation_error": validation_error,
            "jellyfin_users": users,
            "log_excerpt": log_excerpt,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def update_settings(
    request: Request,
    form_data: SettingsForm = Depends(SettingsForm.as_form),
):
    """
    Update application configuration settings from form input.
    """
    settings.jellyfin_url = form_data.jellyfin_url
    settings.jellyfin_api_key = form_data.jellyfin_api_key
    settings.jellyfin_user_id = form_data.jellyfin_user_id
    settings.openai_api_key = form_data.openai_api_key
    settings.lastfm_api_key = form_data.lastfm_api_key
    settings.model = form_data.model
    models = await fetch_openai_models(settings.openai_api_key)
    settings.getsongbpm_api_key = form_data.getsongbpm_api_key
    settings.global_min_lfm = form_data.global_min_lfm
    settings.global_max_lfm = form_data.global_max_lfm
    settings.cache_ttls = form_data.cache_ttls
    # Update shared cache TTLs in-place so other modules
    # that imported the dictionary see the new values
    # Import lazily to avoid a circular dependency
    from utils import cache_manager  # pylint: disable=import-outside-toplevel

    cache_manager.CACHE_TTLS.clear()
    cache_manager.CACHE_TTLS.update(settings.cache_ttls)
    settings.getsongbpm_base_url = form_data.getsongbpm_base_url
    settings.getsongbpm_headers = form_data.getsongbpm_headers
    settings.http_timeout_short = form_data.http_timeout_short
    settings.http_timeout_long = form_data.http_timeout_long
    settings.youtube_min_duration = form_data.youtube_min_duration
    settings.youtube_max_duration = form_data.youtube_max_duration
    settings.library_scan_limit = form_data.library_scan_limit
    settings.music_library_root = form_data.music_library_root
    settings.lyrics_enabled = form_data.lyrics_enabled
    settings.lyrics_weight = form_data.lyrics_weight
    settings.bpm_weight = form_data.bpm_weight
    settings.tags_weight = form_data.tags_weight

    try:
        settings.validate_settings()
        save_settings(settings)
        validation_message = "Settings saved successfully."
        validation_error = False
    except ValueError as ve:
        validation_message = str(ve)
        validation_error = True

    users = await fetch_jellyfin_users()
    log_excerpt = get_log_excerpt()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings.dict(),
            "validation_message": validation_message,
            "validation_error": validation_error,
            "models": models,
            "jellyfin_users": users,
            "log_excerpt": log_excerpt,
        },
    )


@router.post("/api/test/lastfm")
async def test_lastfm(request: Request):
    """Validate a Last.fm API key by performing a simple search."""
    data = await request.json()
    key = data.get("key", "").strip()

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "artist.search",
                    "artist": "radiohead",
                    "api_key": key,
                    "format": "json",
                },
            )

        json_data = r.json()
        return JSONResponse(
            {
                "success": "error" not in json_data,
                "status": r.status_code,
                "body": json_data,
            }
        )
    except httpx.HTTPError as exc:
        logger.error("HTTP error during Last.fm API test: %s", str(exc))
        return JSONResponse(
            {
                "success": False,
                "error": "An internal error occurred while testing the Last.fm API.",
            }
        )


@router.post("/api/test/jellyfin")
async def test_jellyfin(request: Request):
    """Verify the provided Jellyfin URL and API key."""
    data = await request.json()
    url = data.get("url", "").rstrip("/")
    key = data.get("key", "")

    try:
        headers = {
            "X-Emby-Token": key,
            "Accept": "application/json",
            "User-Agent": "PlaylistPilotTest/1.0",
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/System/Info", headers=headers)
        logger.debug("Jellyfin Test: %s", r.text)

        json_data = r.json()
        valid = r.status_code == 200 and any(k.lower() == "version" for k in json_data)
        return JSONResponse(
            {"success": valid, "status": r.status_code, "data": json_data}
        )
    except httpx.HTTPError as exc:
        logger.error("HTTP error during Jellyfin API test: %s", str(exc))
        return JSONResponse(
            {
                "success": False,
                "error": "An internal error occurred while testing the Jellyfin API.",
            }
        )


@router.post("/api/test/openai")
async def test_openai(request: Request):
    """Check if the OpenAI API key is valid by listing models."""
    data = await request.json()
    key = data.get("key")
    try:
        client = openai.OpenAI(api_key=key)
        models = client.models.list()
        valid = any(m.id.startswith("gpt") for m in models.data)
        return JSONResponse({"success": valid})
    except openai.OpenAIError as exc:
        logger.error("OpenAI test error: %s", str(exc))
        return JSONResponse(
            {
                "success": False,
                "error": "An internal error has occurred. Please try again later.",
            }
        )


@router.post("/api/test/getsongbpm")
async def test_getsongbpm(request: Request):
    """Check if the GetSongBPM API key is valid by performing a sample query."""
    data = await request.json()
    key = data.get("key", "")
    lookup = quote_plus("song:creep artist:radiohead")
    url = f"{settings.getsongbpm_base_url}?api_key={key}&type=both&lookup={lookup}"
    try:

        def _fetch():
            return cloudscraper.create_scraper(browser="chrome").get(
                url,
                headers=settings.getsongbpm_headers,
                timeout=settings.http_timeout_short,
            )

        r = await asyncio.to_thread(_fetch)

        try:
            json_data = r.json()
        except ValueError as exc:  # json.JSONDecodeError inherits from ValueError
            logger.error("JSON decode error during GetSongBPM API test: %s", str(exc))
            return JSONResponse(
                {
                    "success": False,
                    "status": r.status_code,
                    "error": "Invalid JSON response from GetSongBPM.",
                }
            )
        valid = r.status_code == 200 and "search" in json_data
        return JSONResponse(
            {"success": valid, "status": r.status_code, "data": json_data}
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("HTTP error during GetSongBPM API test: %s", str(exc))
        return JSONResponse(
            {
                "success": False,
                "error": "An internal error occurred while testing the GetSongBPM API.",
            }
        )


@router.get("/analyze", response_class=HTMLResponse)
async def show_analysis_page(request: Request):
    """Display the playlist analysis form."""
    user_id = settings.jellyfin_user_id
    playlists_data = await get_cached_playlists(user_id)
    error_message = playlists_data.get("error")
    history = load_sorted_history(user_id)

    return templates.TemplateResponse(
        "analyze.html",
        {
            "request": request,
            "jellyfin_playlists": playlists_data["playlists"],
            "history": history,
            "error_message": error_message,
        },
    )


@router.post("/analyze/result", response_class=HTMLResponse)
async def analyze_selected_playlist(  # pylint: disable=too-many-locals
    request: Request, source_type: str = Form(...), playlist_id: str = Form(...)
):
    """Analyze a selected playlist from Jellyfin or GPT history."""
    if source_type == "jellyfin":
        enriched = await enrich_jellyfin_playlist(playlist_id)
        name_data = await get_cached_playlists(settings.jellyfin_user_id)
        playlistdetail = name_data.get("playlists", [])
        playlist_name = "Temporary Name"

        for playlist in playlistdetail:
            if playlist.get("id") == playlist_id:
                playlist_name = playlist.get("name")
                break

        playlist_id_to_use = playlist_id
    else:
        history = load_sorted_history(settings.jellyfin_user_id)
        entry = history[int(playlist_id)]
        suggestions = entry.get("suggestions", [])
        tracks = [s.get("text", "") for s in suggestions if isinstance(s, dict)]
        label_parts = entry.get("label").rsplit(" - ", 1)
        clean_label = (
            label_parts[0].strip() if len(label_parts) > 1 else entry.get("label")
        )
        playlist_name = f"{clean_label} Suggestions"
        playlist_id_to_use = None
        start = perf_counter()
        enriched = []
        for t in tracks:
            res = await enrich_track(normalize_track(t))
            enriched.append(res.dict())
        logger.debug("Enriched Tracks: %.2fs", perf_counter() - start)
    start = perf_counter()
    parsed_enriched = [s for s in enriched if s is not None]
    logger.debug(
        "\u23f1\ufe0f Suggestion enrichment loop: %.2fs", perf_counter() - start
    )
    # 🔁 Calculate combined popularity
    start = perf_counter()
    add_combined_popularity(parsed_enriched, w_lfm=0.3, w_jf=0.7)
    logger.debug(
        "\u23f1\ufe0f Calculate Combined Popularity: %.2fs",
        perf_counter() - start,
    )

    # Compute listener count stats
    listener_counts = [
        t["popularity"] for t in enriched if isinstance(t.get("popularity"), int)
    ]

    if listener_counts:
        sorted_counts = sorted(listener_counts)
        n = len(sorted_counts)
        summary = {
            "avg_listeners": sum(sorted_counts) // n,
            "median_listeners": (
                sorted_counts[n // 2]
                if n % 2
                else (sorted_counts[n // 2 - 1] + sorted_counts[n // 2]) // 2
            ),
            "max_listeners": max(sorted_counts),
        }
    else:
        summary = {"avg_listeners": 0, "median_listeners": 0, "max_listeners": 0}

    # Add your other metrics (e.g. genre diversity, mood profile, etc.)
    base_summary = summarize_tracks(enriched)
    summary.update(base_summary)

    gpt_summary, removal_suggestions = await generate_playlist_analysis_summary(
        summary, enriched
    )

    return templates.TemplateResponse(
        "analysis_result.html",
        {
            "request": request,
            "summary": summary,
            "tracks": parsed_enriched,
            "gpt_summary": gpt_summary,
            "removal_suggestions": removal_suggestions,
            "playlist_name": playlist_name,
            "playlist_id": playlist_id_to_use,
        },
    )


@router.get("/test-lastfm-tags")
def debug_lastfm_tags(title: str, artist: str):
    """Return tags for a given track from Last.fm for debugging."""
    tags = get_lastfm_tags(title, artist)
    return {"tags": tags}


# pylint: disable=too-many-locals,too-many-statements
@router.post("/suggest-playlist")
async def suggest_from_analyzed(request: Request):
    """Generate playlist suggestions from the analyzed tracks."""
    tracks, playlist_name, text_summary = await parse_suggest_request(request)

    start = perf_counter()
    summary = summarize_tracks(tracks)
    logger.debug("\u23f1\ufe0f Track summary: %.2fs", perf_counter() - start)

    suggestion_count = 10
    start = perf_counter()
    logger.debug("Requesting GPT Response using text summary")
    suggestions_raw = await fetch_gpt_suggestions(
        tracks, text_summary, suggestion_count
    )
    logger.debug("\u23f1\ufe0f GPT suggestions: %.2fs", perf_counter() - start)
    logger.info(
        "\ud83d\udce5 Route received %d suggestions from GPT", len(suggestions_raw)
    )

    start = perf_counter()
    logger.debug("Enriching suggestions received from GPT")
    parsed_suggestions = await enrich_and_score_suggestions(suggestions_raw)
    logger.debug(
        "\u23f1\ufe0f Suggestion enrichment loop: %.2fs", perf_counter() - start
    )

    start = perf_counter()
    m3u_path = persist_history_and_m3u(parsed_suggestions, playlist_name)
    logger.debug("\u23f1\ufe0f History save: %.2fs", perf_counter() - start)

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "suggestions": parsed_suggestions,
            "download_link": f"/download/{m3u_path.name}",
            "count": suggestion_count,
            "playlist_name": playlist_name,
            "Dominant_Genre": summary["dominant_genre"],
            "Moods": summary["mood_profile"].keys(),
            "Average_BPM": int(summary["tempo_avg"]),
            "Popularity": int(summary["avg_popularity"]),
            "Decades": summary["decades"].keys(),
        },
    )


@router.post("/suggest-order")
async def suggest_order_from_analyzed(request: Request):
    """Return a recommended track order from GPT."""
    tracks, playlist_name, text_summary = await parse_suggest_request(request)
    ordered = await fetch_order_suggestions(tracks, text_summary)
    if request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"ordered_tracks": ordered})
    return templates.TemplateResponse(
        "order_results.html",
        {
            "request": request,
            "ordered_tracks": ordered,
            "playlist_name": playlist_name,
        },
    )


@router.get("/history/export")
async def export_history_m3u(label: str = Query(...)):
    """Export a stored GPT playlist from history as an M3U file."""
    user_id = settings.jellyfin_user_id
    history = load_sorted_history(user_id)

    entry = next((h for h in history if h.get("label") == label), None)
    if not entry:
        logger.warning("No history entry found with label: %s", label)
        raise HTTPException(status_code=404, detail="Playlist not found")

    # Call the new helper function
    m3u_path = await export_history_entry_as_m3u(
        entry, settings.jellyfin_url, settings.jellyfin_api_key
    )

    if not m3u_path or not m3u_path.exists():
        logger.warning("Failed to generate M3U for history label: %s", label)
        raise HTTPException(status_code=500, detail="Failed to export playlist")

    return FileResponse(
        m3u_path,
        media_type="audio/x-mpegurl",
        filename=f"{label}.m3u",
        background=BackgroundTask(cleanup_temp_file, m3u_path),
    )


@router.post("/export/jellyfin")
async def export_playlist_to_jellyfin(payload: ExportPlaylistRequest):
    """Create a new Jellyfin playlist populated with the given tracks."""
    logger.info(
        "🚀 Export playlist request received: %s with %d tracks",
        payload.name,
        len(payload.tracks),
    )

    item_ids = []

    for track in payload.tracks:
        metadata = await fetch_jellyfin_track_metadata(track["title"], track["artist"])
        if metadata:
            item_ids.append(metadata["Id"])
        else:
            logger.warning(
                "⚠️ Skipping track not found in Jellyfin: %s - %s",
                track["title"],
                track["artist"],
            )

    if not item_ids:
        raise HTTPException(
            status_code=400, detail="No valid Jellyfin tracks found for export."
        )

    playlist_id = await create_jellyfin_playlist(payload.name, item_ids)

    if not playlist_id:
        raise HTTPException(
            status_code=500, detail="Failed to create Jellyfin playlist."
        )

    return {"status": "success", "playlist_id": playlist_id}


@router.post("/import_m3u")
async def import_m3u_file(m3u_file: UploadFile = File(...)):
    """Import an uploaded M3U file into the user's history."""
    if not m3u_file.filename or not m3u_file.filename.lower().endswith(".m3u"):
        raise HTTPException(status_code=400, detail="Only .m3u files are supported")

    with tempfile.NamedTemporaryFile(
        prefix="import_", suffix=".m3u", delete=False
    ) as tmp:
        shutil.copyfileobj(m3u_file.file, tmp)
        temp_path = tmp.name

    try:
        await import_m3u_as_history_entry(temp_path)
    finally:
        cleanup_temp_file(Path(temp_path))

    return RedirectResponse(url="/history", status_code=303)


@router.post("/analyze/export-m3u")
async def export_m3u(request: Request):
    """Generate an M3U file from analysis results for download."""
    payload = await request.json()
    name = payload.get("name", "analysis_export")
    tracks = payload.get("tracks", [])

    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks provided")

    lines = ["#EXTM3U"]
    for track in tracks:
        artist = track.get("artist", "")
        title = track.get("title", "")
        path = await resolve_jellyfin_path(
            title,
            artist,
            settings.jellyfin_url,
            settings.jellyfin_api_key,
        )
        if path:
            lines.append(path)
        else:
            lines.append(f"# Missing Jellyfin path for {artist} - {title}")

    m3u_path = Path(tempfile.gettempdir()) / f"analysis_export_{uuid.uuid4().hex}.m3u"
    m3u_path.write_text("\n".join(lines), encoding="utf-8")

    return FileResponse(
        m3u_path,
        media_type="audio/x-mpegurl",
        filename=f"{name}.m3u",
        background=BackgroundTask(cleanup_temp_file, m3u_path),
    )


@router.post("/export/track-metadata")
async def export_track_metadata(request: Request):  # pylint: disable=too-many-locals
    """Write enriched metadata for a track back to Jellyfin."""

    data = await request.json()
    track = data.get("track")
    force_album_overwrite = data.get("force_album_overwrite", False)
    skip_album = data.get("skip_album", False)
    if not track:
        return JSONResponse({"error": "No track data provided."}, status_code=400)

    title = track.get("title")
    artist = track.get("artist")
    existing_item = await jellyfin.fetch_jellyfin_track_metadata(title, artist)
    if not existing_item or not existing_item.get("Id"):
        return JSONResponse(
            {"error": "Could not resolve Jellyfin ItemId for track."},
            status_code=404,
        )

    item_id = existing_item["Id"]
    full_item = await jellyfin.get_full_item(item_id)
    if not full_item:
        return JSONResponse(
            {"error": "Could not retrieve full item metadata."}, status_code=500
        )

    existing_genres = full_item.get("Genres", [])
    existing_tags = full_item.get("Tags", [])
    existing_album = full_item.get("Album", "")
    incoming_album = track.get("album", "")

    selected_genre = track.get("genre")
    merged_genres = list(set(existing_genres))
    if selected_genre and selected_genre not in merged_genres:
        merged_genres.append(selected_genre)

    new_tags = {
        f"mood:{track.get('mood', '').lower()}" if track.get("mood") else None,
        f"tempo:{track.get('tempo', '')}" if track.get("tempo") else None,
    }
    merged_tags = list(set(existing_tags).union(filter(None, new_tags)))

    album_to_use = existing_album
    if not skip_album and incoming_album and existing_album != incoming_album:
        if force_album_overwrite:
            album_to_use = incoming_album
        else:
            return JSONResponse(
                {
                    "action": "confirm_overwrite_album",
                    "current_album": existing_album,
                    "suggested_album": incoming_album,
                },
                status_code=409,
            )

    # Apply updates to full item
    full_item["Genres"] = merged_genres
    full_item["Tags"] = merged_tags
    full_item["Album"] = album_to_use
    logger.debug("Calling update_item_metadata")
    success = await jellyfin.update_item_metadata(item_id, full_item)

    if not success:
        return JSONResponse(
            {"error": "Failed to update Jellyfin metadata."}, status_code=500
        )

    return JSONResponse(
        {"message": f"Metadata for track '{title}' exported to Jellyfin."}
    )


@router.post("/playlist/remove-item")
async def remove_playlist_item(request: Request):
    """Remove a track from a Jellyfin playlist."""
    data = await request.json()
    playlist_id = data.get("playlist_id")
    item_id = data.get("item_id")
    if not playlist_id or not item_id:
        raise HTTPException(
            status_code=400, detail="playlist_id and item_id are required"
        )

    success = await jellyfin.remove_item_from_playlist(playlist_id, item_id)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to remove item from playlist",
        )

    return {"status": "success"}
