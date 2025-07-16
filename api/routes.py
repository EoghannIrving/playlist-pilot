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

import os
import json
import logging
import asyncio
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from time import perf_counter

import openai
from openai import OpenAI
from fastapi import APIRouter, Request, Form, Query, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from core.templates import templates
from config import settings, save_settings, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM
from core.constants import BASE_DIR
from core.history import (
    save_user_history,
    save_whole_user_history,
    extract_date_from_label,
)
from core.m3u import (
    write_m3u,
    export_history_entry_as_m3u,
    import_m3u_as_history_entry,
)
from core.playlist import (
    fetch_audio_playlists,
    get_playlist_id_by_name,
    get_playlist_tracks,
    parse_suggestion_line,
    get_full_audio_library,
    normalize_popularity,
    combined_popularity_score,
    normalize_popularity_log,
    normalize_track,
    enrich_track,
    enrich_jellyfin_playlist,
)
from services.gpt import gpt_suggest_validated, generate_playlist_analysis_summary
from services.jellyfin import (
    fetch_jellyfin_users,
    search_jellyfin_for_track,
    fetch_tracks_for_playlist_id,
    fetch_jellyfin_track_metadata,
    create_jellyfin_playlist,
    resolve_jellyfin_path,
)
from services.metube import get_youtube_url_single
from core.analysis import summarize_tracks
from utils.cache_manager import playlist_cache, CACHE_TTLS
from utils.helpers import get_cached_playlists, load_sorted_history


logger = logging.getLogger("playlist-pilot")

router = APIRouter()

# Async wrapper to process one suggestion
async def enrich_suggestion(suggestion):
    try:
        text, reason = parse_suggestion_line(suggestion["text"])
        title=suggestion["title"]
        artist=suggestion["artist"]
        jellyfin_data = fetch_jellyfin_track_metadata(title, artist)
        in_jellyfin = bool(jellyfin_data)
        play_count = 0
        genres = []
        duration_ticks = 0
        youtube_url = None
        if in_jellyfin:
            play_count = jellyfin_data.get("UserData", {}).get("PlayCount", 0)
            genres = jellyfin_data.get("Genres", [])
            duration_ticks = jellyfin_data.get("RunTimeTicks", 0)
        else:
            youtube_url = None
        if not in_jellyfin:
            search_query = f"{suggestion['title']} {suggestion['artist']}"
            try:
                _, youtube_url = await get_youtube_url_single(search_query)
            except Exception as e:
                print(f"YTDLP lookup failed for {search_query}: {e}")
        parsed = {
            "title": suggestion["title"],
            "artist": suggestion["artist"],
            "jellyfin_play_count": play_count,
            "Genres": genres,
            "RunTimeTicks": duration_ticks
        }
        enriched = enrich_track(parsed)
        return {
            "text": text,
            "reason": reason,
            "title": suggestion["title"],
            "artist": suggestion["artist"],
            "youtube_url": youtube_url,
            "in_jellyfin": in_jellyfin,
            **enriched
        }

    except Exception as e:
        logger.warning(f"Skipping suggestion: {e}")
        return None  # skip failed item



# ─────────────────────────────────────────────────────────────
# ROUTES

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Render the homepage with a list of audio playlists.
    Uses cached data if available.
    """
    user_id = settings.jellyfin_user_id
    playlists_data = get_cached_playlists(user_id)
    history = load_sorted_history(user_id)

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "jellyfin_playlists": playlists_data["playlists"],
        "history": history
    })

@router.post("/compare", response_class=HTMLResponse)
async def compare_playlists_form(request: Request):
    """
    Compare the overlap between two playlists (GPT or Jellyfin) via HTML form.
    """
    history = load_sorted_history(settings.jellyfin_user_id)
    all_playlists = fetch_audio_playlists()["playlists"]
    try:
        form = await request.form()
        s1_type = form.get("source1_type")
        s1_id = form.get("source1_id")
        s2_type = form.get("source2_type")
        s2_id = form.get("source2_id")

        if not all([s1_type, s1_id, s2_type, s2_id]):
            return templates.TemplateResponse("compare.html", {
                "request": request,
                "history": history,
                "playlists": all_playlists,
                "comparison": ["⚠️ Missing playlist selection."],
                "selected": {
                    "source1_type": s1_type,
                    "source1_id": s1_id,
                    "source2_type": s2_type,
                    "source2_id": s2_id,
                }
            })

        def resolve(source_type, source_id):
            if source_type == "history":
                try:
                    entry = history[int(source_id)]
                    label = entry["label"]
                    tracks = [
                        " - ".join(track["text"].split(" - ")[:2])
                        for track in entry["suggestions"]
                    ]
                    return label, tracks
                except Exception as e:
                    logger.warning(f"❌ Failed to resolve GPT history index {source_id}: {e}")
                    return None, []
            elif source_type == "jellyfin":
                try:
                    tracks = fetch_tracks_for_playlist_id(source_id)
                    label = next(
                        (p["name"] for p in all_playlists if p["id"] == source_id),
                        "Jellyfin Playlist"
                    )
                    formatted = [
                        f'{t["Name"]} - {t.get("AlbumArtist") or t.get("Artist", "")}'
                        for t in tracks
                    ]
                    return label, formatted
                except Exception as e:
                    logger.warning(f"❌ Failed to resolve Jellyfin playlist {source_id}: {e}")
                    return None, []

        label1, tracks1 = resolve(s1_type, s1_id)
        label2, tracks2 = resolve(s2_type, s2_id)

        if not tracks1 or not tracks2:
            return templates.TemplateResponse("compare.html", {
                "request": request,
                "history": history,
                "playlists": all_playlists,
                "comparison": ["⚠️ One or both playlists could not be resolved."],
                "selected": {
                    "source1_type": s1_type,
                    "source1_id": s1_id,
                    "source2_type": s2_type,
                    "source2_id": s2_id,
                }
            })

        normalize = lambda s: s.lower().strip()
        set1_norm = set(map(normalize, tracks1))
        set2_norm = set(map(normalize, tracks2))

        only_in_1 = sorted([t for t in tracks1 if normalize(t) not in set2_norm])
        only_in_2 = sorted([t for t in tracks2 if normalize(t) not in set1_norm])
        common_tracks = sorted([t for t in tracks1 if normalize(t) in set2_norm])

        comparison = []

        if only_in_1:
            comparison.append({"side": "only_in_1", "label": f"🎵 Only in {label1}", "tracks": only_in_1})
        if only_in_2:
            comparison.append({"side": "only_in_2", "label": f"🎶 Only in {label2}", "tracks": only_in_2})
        if common_tracks:
            comparison.append({"side": "shared", "label": "✅ Shared Tracks", "tracks": common_tracks})
        if not comparison:
            comparison.append({"label": "✅ The playlists contain the same tracks.", "tracks": [], "side": "shared"})

        return templates.TemplateResponse("compare.html", {
            "request": request,
            "history": history,
            "playlists": all_playlists,
            "comparison": comparison,
            "selected": {
                "source1_type": s1_type,
                "source1_id": s1_id,
                "source2_type": s2_type,
                "source2_id": s2_id,
            }
        })

    except Exception as e:
        logger.exception("Error in compare_playlists_form")
        return templates.TemplateResponse("compare.html", {
            "request": request,
            "history": history,
            "playlists": all_playlists,
            "comparison": [f"❌ Unexpected error: {str(e)}"],
            "selected": {
                "source1_type": s1_type,
                "source1_id": s1_id,
                "source2_type": s2_type,
                "source2_id": s2_id,
            }
        })

@router.get("/compare", response_class=HTMLResponse)
async def compare_ui(request: Request):
    history = load_sorted_history(settings.jellyfin_user_id)
    all_playlists = fetch_audio_playlists()["playlists"]
    return templates.TemplateResponse("compare.html", {
        "request": request,
        "history": history,
        "playlists": all_playlists
    })


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    sort: str = Query("recent"),
    deleted: int = Query(0)
):
    history = load_sorted_history(settings.jellyfin_user_id)

    if sort == "recent":
        history.sort(key=lambda e: extract_date_from_label(e["label"]), reverse=True)
    elif sort == "oldest":
        history.sort(key=lambda e: extract_date_from_label(e["label"]))
    elif sort == "az":
        history.sort(key=lambda e: e["label"].lower())
    elif sort == "za":
        history.sort(key=lambda e: e["label"].lower(), reverse=True)

    return templates.TemplateResponse("history.html", {
        "request": request,
        "history": history,
        "sort": sort,
        "deleted": deleted
    })

@router.post("/history/delete", response_class=HTMLResponse)
async def delete_history(request: Request):
    """
    Delete a playlist entry from the user's history.
    """
    form = await request.form()
    label = form.get("playlist_name")
    try:
        history = load_sorted_history(settings.jellyfin_user_id)
        updated_history = [item for item in history if item.get("label") != label]
        save_whole_user_history(settings.jellyfin_user_id, updated_history)
        return RedirectResponse(url="/history", status_code=303)
    except Exception as e:
        logger.exception("Error deleting history")
        return JSONResponse(status_code=500, content={"error": str(e)})


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
        settings.validate()
        validation_message = None
    except ValueError as ve:
        validation_message = str(ve)
    users = fetch_jellyfin_users()
    client = OpenAI(api_key=settings.openai_api_key)
    models = [
        m.id for m in client.models.list().data
        if m.id.startswith("gpt")
    ]

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings.dict(),
        "models": models,
        "validation_message": validation_message,
        "jellyfin_users": users
    })


@router.post("/settings", response_class=HTMLResponse)
async def update_settings(
    request: Request,
    jellyfin_url: str = Form(""),
    jellyfin_api_key: str = Form(""),
    jellyfin_user_id: str = Form(""),
    openai_api_key: str = Form(""),
    lastfm_api_key: str = Form(""),
    model: str = Form("gpt-4o-mini"),
    getsongbpm_api_key: str = Form(""),
):
    """
    Update application configuration settings from form input.
    """
    settings.jellyfin_url = jellyfin_url
    settings.jellyfin_api_key = jellyfin_api_key
    settings.jellyfin_user_id = jellyfin_user_id
    settings.openai_api_key = openai_api_key
    settings.lastfm_api_key = lastfm_api_key
    settings.model = model
    client = OpenAI(api_key=settings.openai_api_key)
    models = [
        m.id for m in client.models.list().data
        if m.id.startswith("gpt")
    ]
    settings.getsongbpm_api_key = getsongbpm_api_key

    save_settings(settings)

    try:
        settings.validate()
        validation_message = "Settings saved successfully."
    except ValueError as ve:
        validation_message = str(ve)

    users = fetch_jellyfin_users()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings.dict(),
        "validation_message": validation_message,
        "models": models,
        "jellyfin_users": users
    })

@router.post("/api/test/lastfm")
async def test_lastfm(request: Request):
    import httpx
    data = await request.json()
    key = data.get("key", "").strip()

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://ws.audioscrobbler.com/2.0/", params={
                "method": "artist.search",
                "artist": "radiohead",
                "api_key": key,
                "format": "json"
            })

        json_data = r.json()

        return JSONResponse({
            "success": "error" not in json_data,
            "status": r.status_code,
            "body": json_data
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.post("/api/test/jellyfin")
async def test_jellyfin(request: Request):
    import httpx
    import logging
    data = await request.json()
    url = data.get("url", "").rstrip("/")
    key = data.get("key", "")

    try:
        headers = {
            "X-Emby-Token": key,
            "Accept": "application/json",
            "User-Agent": "PlaylistPilotTest/1.0"
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/System/Info", headers=headers)
        # DEBUG output
        logging.warning("Jellyfin Test: %s", r.text)

        json_data = r.json()
        valid = r.status_code == 200 and any(k.lower() == "version" for k in json_data)
        return JSONResponse({"success": valid, "status": r.status_code, "data": json_data})
    except Exception as e:
        logging.error("Jellyfin test error: %s", str(e))
        return JSONResponse({"success": False, "error": str(e)})


@router.post("/api/test/openai")
async def test_openai(request: Request):
    data = await request.json()
    key = data.get("key")
    try:
        client = openai.OpenAI(api_key=key)
        models = client.models.list()
        valid = any(m.id.startswith("gpt") for m in models.data)
        return JSONResponse({"success": valid})
    except Exception:
        return JSONResponse({"success": False})



@router.get("/analyze", response_class=HTMLResponse)
async def show_analysis_page(request: Request):
    user_id = settings.jellyfin_user_id
    playlists_data = get_cached_playlists(user_id)
    history = load_sorted_history(user_id)

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "jellyfin_playlists": playlists_data["playlists"],
        "history": history
    })


@router.post("/analyze/result", response_class=HTMLResponse)
async def analyze_selected_playlist(
    request: Request,
    source_type: str = Form(...),
    playlist_id: str = Form(...)
):
    if source_type == "jellyfin":
        enriched = enrich_jellyfin_playlist(playlist_id)
        name_data = get_cached_playlists(settings.jellyfin_user_id)
        playlistdetail = name_data.get("playlists", [])
        playlist_name = "Temporary Name"

        for playlist in playlistdetail:
            if playlist.get("id") == playlist_id:
                playlist_name = playlist.get("name")
                break

    else:
        history = load_sorted_history(settings.jellyfin_user_id)
        entry = history[int(playlist_id)]
        suggestions = entry.get("suggestions", [])
        tracks = [s.get("text", "") for s in suggestions if isinstance(s, dict)]
        playlist_name = entry.get("label").rsplit(" - ", 1)[0].strip() + " Suggestions" if " - " in entry.get("label") else entry.get("label") + " Suggestions"
#        playlist_name = "Temporary Name"
        start = perf_counter()
        enriched = [enrich_track(normalize_track(t)) for t in tracks]
        print(f"Enriched Tracks: {perf_counter() - start:.2f}s")
    start = perf_counter()
    parsed_enriched = [s for s in enriched if s is not None]
    print(f"⏱️ Suggestion enrichment loop: {perf_counter() - start:.2f}s")
    # 🔁 Calculate combined popularity
    lastfm_raw = [t["popularity"] for t in parsed_enriched if isinstance(t.get("popularity"), int)]
    jellyfin_raw = [t["jellyfin_play_count"] for t in parsed_enriched if isinstance(t.get("jellyfin_play_count"), int)]

    min_lfm, max_lfm = min(lastfm_raw, default=0), max(lastfm_raw, default=0)
    min_jf, max_jf = min(jellyfin_raw, default=0), max(jellyfin_raw, default=0)
    start = perf_counter()
    for track in parsed_enriched:
        raw_lfm = track.get("popularity")
        raw_jf = track.get("jellyfin_play_count")
        norm_lfm = normalize_popularity_log(raw_lfm, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM) if raw_lfm is not None else None
        norm_jf = normalize_popularity(raw_jf, min_jf, max_jf) if raw_jf is not None else None
        track["combined_popularity"] = combined_popularity_score(norm_lfm, norm_jf, w_lfm=0.3, w_jf=0.7)
    print(f"⏱️ Calculate Combined Popularity: {perf_counter() - start:.2f}s")

    # Compute listener count stats
    listener_counts = [t["popularity"] for t in enriched if isinstance(t.get("popularity"), int)]

    if listener_counts:
        sorted_counts = sorted(listener_counts)
        n = len(sorted_counts)
        summary = {
            "avg_listeners": sum(sorted_counts) // n,
            "median_listeners": (
                sorted_counts[n // 2] if n % 2 else (sorted_counts[n // 2 - 1] + sorted_counts[n // 2]) // 2
            ),
            "max_listeners": max(sorted_counts)
        }
    else:
        summary = {
            "avg_listeners": 0,
            "median_listeners": 0,
            "max_listeners": 0
        }

    # Add your other metrics (e.g. genre diversity, mood profile, etc.)
    from core.analysis import summarize_tracks
    base_summary = summarize_tracks(enriched)
    summary.update(base_summary)

    gpt_summary, removal_suggestions = generate_playlist_analysis_summary(summary, enriched)

    return templates.TemplateResponse("analysis_result.html", {
        "request": request,
        "summary": summary,
        "tracks": parsed_enriched,
        "gpt_summary": gpt_summary,
        "removal_suggestions": removal_suggestions,
        "playlist_name": playlist_name,
    })


from services.lastfm import get_lastfm_tags
@router.get("/test-lastfm-tags")
def test_lastfm(title: str, artist: str):
    tags = get_lastfm_tags(title, artist)
    return {"tags": tags}


@router.post("/suggest-playlist")
async def suggest_from_analyzed(request: Request):
    try:
        data = await request.form()
        tracks_raw = data.get("tracks", "[]")
        playlist_name = data.get("playlist_name","")
        playlist=data.get("playlist","")
        logger.info(f"tracks_raw: {tracks_raw[:100]}")  # just log a portion if it's large

        try:
            tracks = json.loads(tracks_raw)
        except json.JSONDecodeError:
            logger.warning("Failed to decode tracks JSON from form.")
            tracks = []
        start = perf_counter()
        summary = summarize_tracks(tracks)
        print(f"⏱️ Track summary: {perf_counter() - start:.2f}s")
        # Extract just the normalized "Artist - Title" strings
        seed_lines = [f"{t['title']} - {t['artist']}" for t in tracks]
        suggestion_count=10
        text_summary = data.get("text_summary", "")
        start = perf_counter()
        print("Requesting GPT Response using text summary")
        exclude_pairs = set((t["title"], t["artist"]) for t in tracks)
        suggestions_raw = await gpt_suggest_validated(
            seed_lines,
            suggestion_count,
            text_summary,
            exclude_pairs=exclude_pairs
        )
        print(f"⏱️ GPT suggestions: {perf_counter() - start:.2f}s")
        logger.info(f"📥 Route received {len(suggestions_raw)} suggestions from GPT")
        parsed_suggestions = []
        counter=0
        # ✅ Replace your old loop with this:
        start = perf_counter()
        print("Enriching suggestions received from GPT")
        parsed_suggestions_raw = await asyncio.gather(
            *[enrich_suggestion(s) for s in suggestions_raw]
        )
        parsed_suggestions = [s for s in parsed_suggestions_raw if s is not None]
        print(f"⏱️ Suggestion enrichment loop: {perf_counter() - start:.2f}s")
        start = perf_counter()
        parsed_suggestions.sort(key=lambda s: not s["in_jellyfin"])
        print(f"⏱️ Sorting: {perf_counter() - start:.2f}s")
        # 🔁 Calculate combined popularity
        lastfm_raw = [t["popularity"] for t in parsed_suggestions if isinstance(t.get("popularity"), int)]
        jellyfin_raw = [t["jellyfin_play_count"] for t in parsed_suggestions if isinstance(t.get("jellyfin_play_count"), int)]

        min_lfm, max_lfm = min(lastfm_raw, default=0), max(lastfm_raw, default=0)
        min_jf, max_jf = min(jellyfin_raw, default=0), max(jellyfin_raw, default=0)
        start = perf_counter()
        for track in parsed_suggestions:
            raw_lfm = track.get("popularity")
            raw_jf = track.get("jellyfin_play_count")
            norm_lfm = normalize_popularity_log(raw_lfm, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM) if raw_lfm is not None else None
            norm_jf = normalize_popularity(raw_jf, min_jf, max_jf) if raw_jf is not None else None
            track["combined_popularity"] = combined_popularity_score(norm_lfm, norm_jf, w_lfm=0.3, w_jf=0.7)
            logger.info(f"{track['title']} - {track['artist']} | Combined: {track['combined_popularity']:.1f} | "
                  f"Last.fm: {raw_lfm}, Jellyfin: {raw_jf}")
        print(f"⏱️ Calculate Combined Popularity: {perf_counter() - start:.2f}s")
        start = perf_counter()
        playlist_clean = playlist_name.strip('"').strip("'")
        label = f"{playlist_clean} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        user_id = settings.jellyfin_user_id
        save_user_history(user_id, label, parsed_suggestions)
        print(f"⏱️ History save: {perf_counter() - start:.2f}s")
        m3u_path = write_m3u([s["text"] for s in parsed_suggestions])

        return templates.TemplateResponse("results.html", {
            "request": request,
            "suggestions": parsed_suggestions,
            "download_link": f"/download/{m3u_path.name}",
            "count": suggestion_count,
            "playlist_name": playlist_name,
            "Dominant_Genre": summary['dominant_genre'],
            "Moods": summary['mood_profile'].keys(),
            "Average_BPM": int(summary['tempo_avg']),
            "Popularity": int(summary['avg_popularity']),
            "Decades": summary['decades'].keys(),
        })
    except Exception as e:
        logger.error(f"Error in /suggest-playlist: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/history/export")
async def export_history_m3u(request: Request, label: str = Query(...)):
    user_id = settings.jellyfin_user_id
    history = load_sorted_history(user_id)

    entry = next((h for h in history if h.get("label") == label), None)
    if not entry:
        logger.warning(f"No history entry found with label: {label}")
        raise HTTPException(status_code=404, detail="Playlist not found")

    # Call the new helper function
    m3u_path = await export_history_entry_as_m3u(
        entry,
        settings.jellyfin_url,
        settings.jellyfin_api_key
    )

    if not m3u_path or not m3u_path.exists():
        logger.warning(f"Failed to generate M3U for history label: {label}")
        raise HTTPException(status_code=500, detail="Failed to export playlist")

    return FileResponse(
        m3u_path,
        media_type="audio/x-mpegurl",
        filename=f"{label}.m3u"
    )

from services.jellyfin import create_jellyfin_playlist, fetch_jellyfin_track_metadata

class ExportPlaylistRequest(BaseModel):
    name: str
    tracks: list[dict]  # Expecting list of { "title": str, "artist": str }


@router.post("/export/jellyfin")
async def export_playlist_to_jellyfin(payload: ExportPlaylistRequest):
    logger.info(f"🚀 Export playlist request received: {payload.name} with {len(payload.tracks)} tracks")

    item_ids = []

    for track in payload.tracks:
        metadata = fetch_jellyfin_track_metadata(track["title"], track["artist"])
        if metadata:
            item_ids.append(metadata["Id"])
        else:
            logger.warning(f"⚠️ Skipping track not found in Jellyfin: {track['title']} - {track['artist']}")

    if not item_ids:
        raise HTTPException(status_code=400, detail="No valid Jellyfin tracks found for export.")

    playlist_id = create_jellyfin_playlist(payload.name, item_ids)

    if not playlist_id:
        raise HTTPException(status_code=500, detail="Failed to create Jellyfin playlist.")

    return {"status": "success", "playlist_id": playlist_id}

@router.post("/import_m3u")
async def import_m3u_file(request: Request, m3u_file: UploadFile = File(...)):
    temp_path = f"/tmp/{m3u_file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(m3u_file.file, buffer)

    import_m3u_as_history_entry(temp_path)
    return RedirectResponse(url="/history", status_code=303)


@router.post("/analyze/export-m3u")
async def export_m3u(request: Request):
    payload = await request.json()
    name = payload.get("name", "analysis_export")
    tracks = payload.get("tracks", [])

    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks provided")

    lines = ["#EXTM3U"]
    for track in tracks:
        artist = track.get("artist", "")
        title = track.get("title", "")
        path = await resolve_jellyfin_path(title, artist, settings.jellyfin_url, settings.jellyfin_api_key)
        if path:
            lines.append(path)
        else:
            lines.append(f"# Missing Jellyfin path for {artist} - {title}")

    m3u_path = Path(tempfile.gettempdir()) / f"analysis_export_{uuid.uuid4().hex}.m3u"
    m3u_path.write_text("\n".join(lines), encoding="utf-8")

    return FileResponse(
        m3u_path,
        media_type="audio/x-mpegurl",
        filename=f"{name}.m3u"
    )

@router.post("/export/track-metadata")
async def export_track_metadata(request: Request):
    from services import jellyfin

    data = await request.json()
    track = data.get("track")
    force_album_overwrite = data.get("force_album_overwrite", False)
    skip_album = data.get("skip_album", False)
    if not track:
        return JSONResponse({"error": "No track data provided."}, status_code=400)

    title = track.get("title")
    artist = track.get("artist")
    existing_item = jellyfin.fetch_jellyfin_track_metadata(title, artist)
    if not existing_item or not existing_item.get("Id"):
        return JSONResponse({"error": "Could not resolve Jellyfin ItemId for track."}, status_code=404)

    item_id = existing_item["Id"]
    full_item = jellyfin.get_full_item(item_id)
    if not full_item:
        return JSONResponse({"error": "Could not retrieve full item metadata."}, status_code=500)

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
        f"tempo:{track.get('tempo', '')}" if track.get("tempo") else None
    }
    merged_tags = list(set(existing_tags).union(filter(None, new_tags)))

    album_to_use = existing_album
    if not skip_album and incoming_album and existing_album != incoming_album:
        if force_album_overwrite:
            album_to_use = incoming_album
        else:
            return JSONResponse({
                "action": "confirm_overwrite_album",
                "current_album": existing_album,
                "suggested_album": incoming_album
            }, status_code=409)

    # Apply updates to full item
    full_item["Genres"] = merged_genres
    full_item["Tags"] = merged_tags
    full_item["Album"] = album_to_use
    print("Calling update_item_metadata")
    success = jellyfin.update_item_metadata(item_id, full_item)

    if not success:
        return JSONResponse({"error": "Failed to update Jellyfin metadata."}, status_code=500)

    return JSONResponse({"message": f"Metadata for track '{title}' exported to Jellyfin."})
