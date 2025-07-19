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

import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from time import perf_counter

import httpx
import openai
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
from openai import OpenAI
from pydantic import BaseModel

from config import (
    GLOBAL_MAX_LFM,
    GLOBAL_MIN_LFM,
    AppSettings,
    save_settings,
    settings,
)
from core.analysis import summarize_tracks
from core.history import (
    extract_date_from_label,
    save_user_history,
    save_whole_user_history,
)
from core.m3u import (
    export_history_entry_as_m3u,
    import_m3u_as_history_entry,
    write_m3u,
)
from core.playlist import (
    combined_popularity_score,
    enrich_jellyfin_playlist,
    enrich_track,
    fetch_audio_playlists,
    normalize_popularity,
    normalize_popularity_log,
    normalize_track,
    parse_suggestion_line,
)
from core.templates import templates
from services import jellyfin
from services.gpt import generate_playlist_analysis_summary, gpt_suggest_validated
from services.jellyfin import (
    create_jellyfin_playlist,
    fetch_jellyfin_track_metadata,
    fetch_jellyfin_users,
    fetch_tracks_for_playlist_id,
    resolve_jellyfin_path,
)
from services.lastfm import get_lastfm_tags
from services.metube import get_youtube_url_single
from utils.helpers import get_cached_playlists, load_sorted_history


logger = logging.getLogger("playlist-pilot")

router = APIRouter()


class SettingsForm(AppSettings):
    """Pydantic model for updating application settings via form."""

    @classmethod
    def as_form(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        cls,
        jellyfin_url: str = Form(""),
        jellyfin_api_key: str = Form(""),
        jellyfin_user_id: str = Form(""),
        openai_api_key: str = Form(""),
        lastfm_api_key: str = Form(""),
        model: str = Form("gpt-4o-mini"),
        getsongbpm_api_key: str = Form(""),
        global_min_lfm: int = Form(10000),
        global_max_lfm: int = Form(15000000),
        cache_ttls: str = Form(""),
        getsongbpm_base_url: str = Form("https://api.getsongbpm.com/search/"),
        getsongbpm_headers: str = Form(""),
        http_timeout_short: int = Form(5),
        http_timeout_long: int = Form(10),
        youtube_min_duration: int = Form(120),
        youtube_max_duration: int = Form(360),
        library_scan_limit: int = Form(1000),
        music_library_root: str = Form("Movies/Music"),
        lyrics_weight: float = Form(1.5),
        bpm_weight: float = Form(1.0),
        tags_weight: float = Form(0.7),
    ) -> "SettingsForm":
        """Create a SettingsForm instance from submitted form data."""
        return cls(
            jellyfin_url=jellyfin_url,
            jellyfin_api_key=jellyfin_api_key,
            jellyfin_user_id=jellyfin_user_id,
            openai_api_key=openai_api_key,
            lastfm_api_key=lastfm_api_key,
            model=model,
            getsongbpm_api_key=getsongbpm_api_key,
            global_min_lfm=global_min_lfm,
            global_max_lfm=global_max_lfm,
            cache_ttls=(
                json.loads(cache_ttls)
                if cache_ttls
                else AppSettings().cache_ttls
            ),
            getsongbpm_base_url=getsongbpm_base_url,
            getsongbpm_headers=(
                json.loads(getsongbpm_headers)
                if getsongbpm_headers
                else AppSettings().getsongbpm_headers
            ),
            http_timeout_short=http_timeout_short,
            http_timeout_long=http_timeout_long,
            youtube_min_duration=youtube_min_duration,
            youtube_max_duration=youtube_max_duration,
            library_scan_limit=library_scan_limit,
            music_library_root=music_library_root,
            lyrics_weight=lyrics_weight,
            bpm_weight=bpm_weight,
            tags_weight=tags_weight,
        )

# Async wrapper to process one suggestion
async def enrich_suggestion(suggestion):
    """Return enriched data for a single GPT suggestion."""
    try:
        text, reason = parse_suggestion_line(suggestion["text"])
        title=suggestion["title"]
        artist=suggestion["artist"]
        jellyfin_data = await fetch_jellyfin_track_metadata(title, artist)
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
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("YTDLP lookup failed for %s: %s", search_query, e)
        parsed = {
            "title": suggestion["title"],
            "artist": suggestion["artist"],
            "jellyfin_play_count": play_count,
            "Genres": genres,
            "RunTimeTicks": duration_ticks,
        }
        enriched = await enrich_track(parsed)
        return {
            "text": text,
            "reason": reason,
            "title": suggestion["title"],
            "artist": suggestion["artist"],
            "youtube_url": youtube_url,
            "in_jellyfin": in_jellyfin,
            **enriched.dict()
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Skipping suggestion: %s", e)
        return None  # skip failed item


async def _parse_suggest_request(request: Request) -> tuple[list[dict], str, str]:
    """Extract tracks and related fields from the POST request."""
    data = await request.form()
    tracks_raw = data.get("tracks", "[]")
    logger.info("tracks_raw: %s", tracks_raw[:100])  # log only a portion if large
    playlist_name = data.get("playlist_name", "")
    text_summary = data.get("text_summary", "")

    try:
        tracks = json.loads(tracks_raw)
    except json.JSONDecodeError:
        logger.warning("Failed to decode tracks JSON from form.")
        tracks = []

    return tracks, playlist_name, text_summary


async def _fetch_gpt_suggestions(tracks: list[dict], text_summary: str, count: int) -> list[dict]:
    """Request suggestions from GPT based on seed tracks."""
    seed_lines = [f"{t['title']} - {t['artist']}" for t in tracks]
    exclude_pairs = {(t["title"], t["artist"]) for t in tracks}
    return await gpt_suggest_validated(
        seed_lines,
        count,
        text_summary,
        exclude_pairs=exclude_pairs,
    )


async def _enrich_and_score_suggestions(suggestions_raw: list[dict]) -> list[dict]:
    """Enrich suggestions with metadata and compute popularity score."""
    parsed_raw = await asyncio.gather(*[enrich_suggestion(s) for s in suggestions_raw])
    suggestions = [s for s in parsed_raw if s is not None]

    suggestions.sort(key=lambda s: not s["in_jellyfin"])

    jellyfin_raw = [
        t["jellyfin_play_count"]
        for t in suggestions
        if isinstance(t.get("jellyfin_play_count"), int)
    ]
    min_jf, max_jf = min(jellyfin_raw, default=0), max(jellyfin_raw, default=0)

    for track in suggestions:
        raw_lfm = track.get("popularity")
        raw_jf = track.get("jellyfin_play_count")
        norm_lfm = (
            normalize_popularity_log(raw_lfm, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM)
            if raw_lfm is not None
            else None
        )
        norm_jf = (
            normalize_popularity(raw_jf, min_jf, max_jf)
            if raw_jf is not None
            else None
        )
        track["combined_popularity"] = combined_popularity_score(
            norm_lfm,
            norm_jf,
            w_lfm=0.3,
            w_jf=0.7,
        )
        logger.info(
            "%s - %s | Combined: %.1f | Last.fm: %s, Jellyfin: %s",
            track["title"],
            track["artist"],
            track["combined_popularity"],
            raw_lfm,
            raw_jf,
        )

    return suggestions


def _persist_history_and_m3u(suggestions: list[dict], playlist_name: str) -> Path:
    """Save generated playlist to history and disk."""
    playlist_clean = playlist_name.strip('"').strip("'")
    label = f"{playlist_clean} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    user_id = settings.jellyfin_user_id
    save_user_history(user_id, label, suggestions)
    return write_m3u([s["text"] for s in suggestions])



# ─────────────────────────────────────────────────────────────
# ROUTES

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Render the homepage with a list of audio playlists.
    Uses cached data if available.
    """
    user_id = settings.jellyfin_user_id
    playlists_data = await get_cached_playlists(user_id)
    history = load_sorted_history(user_id)

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "jellyfin_playlists": playlists_data["playlists"],
        "history": history
    })

@router.post("/compare", response_class=HTMLResponse)
async def compare_playlists_form(request: Request):  # pylint: disable=too-many-locals
    """
    Compare the overlap between two playlists (GPT or Jellyfin) via HTML form.
    """
    history = load_sorted_history(settings.jellyfin_user_id)
    all_playlists = (await fetch_audio_playlists())["playlists"]
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
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning(
                        "\u274c Failed to resolve GPT history index %s: %s",
                        source_id,
                        e,
                    )
                    return None, []
            elif source_type == "jellyfin":
                try:
                    tracks = await fetch_tracks_for_playlist_id(source_id)
                    label = next(
                        (p["name"] for p in all_playlists if p["id"] == source_id),
                        "Jellyfin Playlist"
                    )
                    formatted = [
                        f'{t["Name"]} - {t.get("AlbumArtist") or t.get("Artist", "")}'
                        for t in tracks
                    ]
                    return label, formatted
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning(
                        "\u274c Failed to resolve Jellyfin playlist %s: %s",
                        source_id,
                        e,
                    )
                    return None, []
            return None, []

        label1, tracks1 = await resolve(s1_type, s1_id)
        label2, tracks2 = await resolve(s2_type, s2_id)

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
            comparison.append({
                "side": "only_in_1",
                "label": f"🎵 Only in {label1}",
                "tracks": only_in_1,
            })
        if only_in_2:
            comparison.append({
                "side": "only_in_2",
                "label": f"🎶 Only in {label2}",
                "tracks": only_in_2,
            })
        if common_tracks:
            comparison.append({
                "side": "shared",
                "label": "✅ Shared Tracks",
                "tracks": common_tracks,
            })
        if not comparison:
            comparison.append({
                "label": "✅ The playlists contain the same tracks.",
                "tracks": [],
                "side": "shared",
            })

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

    except Exception as e:  # pylint: disable=broad-exception-caught
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
    """Render the playlist comparison form."""
    history = load_sorted_history(settings.jellyfin_user_id)
    all_playlists = (await fetch_audio_playlists())["playlists"]
    return templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "history": history,
            "playlists": all_playlists,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    sort: str = Query("recent"),
    deleted: int = Query(0)
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
    except Exception as e:  # pylint: disable=broad-exception-caught
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
        settings.validate_settings()
        validation_message = None
    except ValueError as ve:
        validation_message = str(ve)
    users = await fetch_jellyfin_users()
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
    client = OpenAI(api_key=settings.openai_api_key)
    models = [
        m.id for m in client.models.list().data
        if m.id.startswith("gpt")
    ]
    settings.getsongbpm_api_key = form_data.getsongbpm_api_key
    settings.global_min_lfm = form_data.global_min_lfm
    settings.global_max_lfm = form_data.global_max_lfm
    settings.cache_ttls = form_data.cache_ttls
    settings.getsongbpm_base_url = form_data.getsongbpm_base_url
    settings.getsongbpm_headers = form_data.getsongbpm_headers
    settings.http_timeout_short = form_data.http_timeout_short
    settings.http_timeout_long = form_data.http_timeout_long
    settings.youtube_min_duration = form_data.youtube_min_duration
    settings.youtube_max_duration = form_data.youtube_max_duration
    settings.library_scan_limit = form_data.library_scan_limit
    settings.music_library_root = form_data.music_library_root
    settings.lyrics_weight = form_data.lyrics_weight
    settings.bpm_weight = form_data.bpm_weight
    settings.tags_weight = form_data.tags_weight

    save_settings(settings)

    try:
        settings.validate_settings()
        validation_message = "Settings saved successfully."
    except ValueError as ve:
        validation_message = str(ve)

    users = await fetch_jellyfin_users()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings.dict(),
        "validation_message": validation_message,
        "models": models,
        "jellyfin_users": users
    })

@router.post("/api/test/lastfm")
async def test_lastfm(request: Request):
    """Validate a Last.fm API key by performing a simple search."""
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
    except Exception as e:  # pylint: disable=broad-exception-caught
        return JSONResponse({"success": False, "error": str(e)})


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
            "User-Agent": "PlaylistPilotTest/1.0"
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{url}/System/Info", headers=headers)
        logger.warning("Jellyfin Test: %s", r.text)

        json_data = r.json()
        valid = r.status_code == 200 and any(k.lower() == "version" for k in json_data)
        return JSONResponse({"success": valid, "status": r.status_code, "data": json_data})
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Jellyfin test error: %s", str(e))
        return JSONResponse({"success": False, "error": str(e)})


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
    except Exception:  # pylint: disable=broad-exception-caught
        return JSONResponse({"success": False})



@router.get("/analyze", response_class=HTMLResponse)
async def show_analysis_page(request: Request):
    """Display the playlist analysis form."""
    user_id = settings.jellyfin_user_id
    playlists_data = await get_cached_playlists(user_id)
    history = load_sorted_history(user_id)

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "jellyfin_playlists": playlists_data["playlists"],
        "history": history
    })


@router.post("/analyze/result", response_class=HTMLResponse)
async def analyze_selected_playlist(  # pylint: disable=too-many-locals
    request: Request,
    source_type: str = Form(...),
    playlist_id: str = Form(...)
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

    else:
        history = load_sorted_history(settings.jellyfin_user_id)
        entry = history[int(playlist_id)]
        suggestions = entry.get("suggestions", [])
        tracks = [s.get("text", "") for s in suggestions if isinstance(s, dict)]
        label_parts = entry.get("label").rsplit(" - ", 1)
        clean_label = label_parts[0].strip() if len(label_parts) > 1 else entry.get("label")
        playlist_name = f"{clean_label} Suggestions"
        start = perf_counter()
        enriched = []
        for t in tracks:
            res = await enrich_track(normalize_track(t))
            enriched.append(res.dict())
        logger.debug("Enriched Tracks: %.2fs", perf_counter() - start)
    start = perf_counter()
    parsed_enriched = [s for s in enriched if s is not None]
    logger.debug("\u23F1\ufe0f Suggestion enrichment loop: %.2fs", perf_counter() - start)
    # 🔁 Calculate combined popularity
    jellyfin_raw = [
        t["jellyfin_play_count"]
        for t in parsed_enriched
        if isinstance(t.get("jellyfin_play_count"), int)
    ]

    min_jf, max_jf = min(jellyfin_raw, default=0), max(jellyfin_raw, default=0)
    start = perf_counter()
    for track in parsed_enriched:
        raw_lfm = track.get("popularity")
        raw_jf = track.get("jellyfin_play_count")
        norm_lfm = (
            normalize_popularity_log(raw_lfm, GLOBAL_MIN_LFM, GLOBAL_MAX_LFM)
            if raw_lfm is not None
            else None
        )
        norm_jf = (
            normalize_popularity(raw_jf, min_jf, max_jf)
            if raw_jf is not None
            else None
        )
        track["combined_popularity"] = combined_popularity_score(
            norm_lfm,
            norm_jf,
            w_lfm=0.3,
            w_jf=0.7,
        )
    logger.debug("\u23F1\ufe0f Calculate Combined Popularity: %.2fs", perf_counter() - start)

    # Compute listener count stats
    listener_counts = [t["popularity"] for t in enriched if isinstance(t.get("popularity"), int)]

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
        summary = {
            "avg_listeners": 0,
            "median_listeners": 0,
            "max_listeners": 0
        }

    # Add your other metrics (e.g. genre diversity, mood profile, etc.)
    base_summary = summarize_tracks(enriched)
    summary.update(base_summary)

    gpt_summary, removal_suggestions = await generate_playlist_analysis_summary(summary, enriched)

    return templates.TemplateResponse("analysis_result.html", {
        "request": request,
        "summary": summary,
        "tracks": parsed_enriched,
        "gpt_summary": gpt_summary,
        "removal_suggestions": removal_suggestions,
        "playlist_name": playlist_name,
    })



@router.get("/test-lastfm-tags")
def debug_lastfm_tags(title: str, artist: str):
    """Return tags for a given track from Last.fm for debugging."""
    tags = get_lastfm_tags(title, artist)
    return {"tags": tags}


# pylint: disable=too-many-locals,too-many-statements
@router.post("/suggest-playlist")
async def suggest_from_analyzed(request: Request):
    """Generate playlist suggestions from the analyzed tracks."""
    try:
        tracks, playlist_name, text_summary = await _parse_suggest_request(request)

        start = perf_counter()
        summary = summarize_tracks(tracks)
        logger.debug("\u23F1\ufe0f Track summary: %.2fs", perf_counter() - start)

        suggestion_count = 10
        start = perf_counter()
        logger.debug("Requesting GPT Response using text summary")
        suggestions_raw = await _fetch_gpt_suggestions(tracks, text_summary, suggestion_count)
        logger.debug("\u23F1\ufe0f GPT suggestions: %.2fs", perf_counter() - start)
        logger.info("\ud83d\udce5 Route received %d suggestions from GPT", len(suggestions_raw))

        start = perf_counter()
        logger.debug("Enriching suggestions received from GPT")
        parsed_suggestions = await _enrich_and_score_suggestions(suggestions_raw)
        logger.debug("\u23F1\ufe0f Suggestion enrichment loop: %.2fs", perf_counter() - start)

        start = perf_counter()
        m3u_path = _persist_history_and_m3u(parsed_suggestions, playlist_name)
        logger.debug("\u23F1\ufe0f History save: %.2fs", perf_counter() - start)

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
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error in /suggest-playlist: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

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
        entry,
        settings.jellyfin_url,
        settings.jellyfin_api_key
    )

    if not m3u_path or not m3u_path.exists():
        logger.warning("Failed to generate M3U for history label: %s", label)
        raise HTTPException(status_code=500, detail="Failed to export playlist")

    return FileResponse(
        m3u_path,
        media_type="audio/x-mpegurl",
        filename=f"{label}.m3u"
    )


class ExportPlaylistRequest(BaseModel):
    """Payload model for exporting playlists to Jellyfin."""

    name: str
    tracks: list[dict]  # Expecting list of { "title": str, "artist": str }


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
        raise HTTPException(status_code=400, detail="No valid Jellyfin tracks found for export.")

    playlist_id = await create_jellyfin_playlist(payload.name, item_ids)

    if not playlist_id:
        raise HTTPException(status_code=500, detail="Failed to create Jellyfin playlist.")

    return {"status": "success", "playlist_id": playlist_id}

@router.post("/import_m3u")
async def import_m3u_file(m3u_file: UploadFile = File(...)):
    """Import an uploaded M3U file into the user's history."""
    temp_path = f"/tmp/{m3u_file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(m3u_file.file, buffer)

    await import_m3u_as_history_entry(temp_path)
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
        filename=f"{name}.m3u"
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
    logger.debug("Calling update_item_metadata")
    success = await jellyfin.update_item_metadata(item_id, full_item)

    if not success:
        return JSONResponse({"error": "Failed to update Jellyfin metadata."}, status_code=500)

    return JSONResponse({"message": f"Metadata for track '{title}' exported to Jellyfin."})
