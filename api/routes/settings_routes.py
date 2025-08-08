"""FastAPI routes for application settings and integration tests."""

import logging
import asyncio
from urllib.parse import quote_plus

import httpx
import openai
import cloudscraper
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

from config import save_settings, settings
from core.templates import templates
from services.gpt import fetch_openai_models
from services.jellyfin import fetch_jellyfin_users, fetch_tracks_for_playlist_id
from utils.helpers import get_log_excerpt
from api.forms import SettingsForm
from api.schemas import (
    LastfmTestRequest,
    LastfmTestResponse,
    JellyfinTestRequest,
    JellyfinTestResponse,
    OpenAITestRequest,
    OpenAITestResponse,
    GetSongBPMTestRequest,
    GetSongBPMTestResponse,
    VerifyEntryRequest,
    VerifyEntryResponse,
)

logger = logging.getLogger("playlist-pilot")

router = APIRouter()
api_router = APIRouter(prefix="/api/v1")


@router.get("/settings", response_class=HTMLResponse, tags=["Settings"])
async def get_settings(request: Request):
    """Display current configuration and available Jellyfin users."""
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


@router.post("/settings", response_class=HTMLResponse, tags=["Settings"])
async def update_settings(
    request: Request,
    form_data: SettingsForm = Depends(SettingsForm.as_form),
):
    """Update application configuration settings from form input."""
    settings.jellyfin_url = form_data.jellyfin_url
    settings.jellyfin_api_key = form_data.jellyfin_api_key
    settings.jellyfin_user_id = form_data.jellyfin_user_id
    settings.openai_api_key = form_data.openai_api_key
    settings.lastfm_api_key = form_data.lastfm_api_key
    settings.spotify_client_id = form_data.spotify_client_id
    settings.spotify_client_secret = form_data.spotify_client_secret
    settings.apple_client_id = form_data.apple_client_id
    settings.apple_client_secret = form_data.apple_client_secret
    settings.model = form_data.model
    models = await fetch_openai_models(settings.openai_api_key)
    settings.getsongbpm_api_key = form_data.getsongbpm_api_key
    settings.global_min_lfm = form_data.global_min_lfm
    settings.global_max_lfm = form_data.global_max_lfm
    settings.set_cache_ttls(form_data.cache_ttls)
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
    settings.integration_failure_limit = form_data.integration_failure_limit

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


@api_router.post("/test/lastfm", response_model=LastfmTestResponse, tags=["Testing"])
async def test_lastfm(payload: LastfmTestRequest) -> LastfmTestResponse:
    """Validate a Last.fm API key by performing a simple artist search."""
    key = payload.key.strip()

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
        return LastfmTestResponse(
            success="error" not in json_data,
            status=r.status_code,
            body=json_data,
        )
    except httpx.HTTPError as exc:
        logger.error("HTTP error during Last.fm API test: %s", str(exc))
        return LastfmTestResponse(
            success=False,
            error="An internal error occurred while testing the Last.fm API.",
        )


@api_router.post(
    "/test/jellyfin", response_model=JellyfinTestResponse, tags=["Testing"]
)
async def test_jellyfin(payload: JellyfinTestRequest) -> JellyfinTestResponse:
    """Verify the provided Jellyfin URL and API key."""
    url = payload.url.rstrip("/")
    key = payload.key

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
        return JellyfinTestResponse(success=valid, status=r.status_code, data=json_data)
    except httpx.HTTPError as exc:
        logger.error("HTTP error during Jellyfin API test: %s", str(exc))
        return JellyfinTestResponse(
            success=False,
            error="An internal error occurred while testing the Jellyfin API.",
        )


@api_router.post("/test/openai", response_model=OpenAITestResponse, tags=["Testing"])
async def test_openai(payload: OpenAITestRequest) -> OpenAITestResponse:
    """Check if the OpenAI API key is valid by listing available models."""
    key = payload.key
    try:

        def _list_models():
            client = openai.OpenAI(api_key=key)
            return client.models.list()

        models = await asyncio.to_thread(_list_models)
        valid = any(m.id.startswith("gpt") for m in models.data)
        return OpenAITestResponse(success=valid)
    except openai.OpenAIError as exc:
        logger.error("OpenAI test error: %s", str(exc))
        return OpenAITestResponse(
            success=False,
            error="An internal error has occurred. Please try again later.",
        )


@api_router.post(
    "/test/getsongbpm",
    response_model=GetSongBPMTestResponse,
    tags=["Testing"],
)
async def test_getsongbpm(payload: GetSongBPMTestRequest) -> GetSongBPMTestResponse:
    """Check if the GetSongBPM API key is valid by performing a sample query."""
    key = payload.key
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
            return GetSongBPMTestResponse(
                success=False,
                status=r.status_code,
                error="Invalid JSON response from GetSongBPM.",
            )
        valid = r.status_code == 200 and "search" in json_data
        return GetSongBPMTestResponse(
            success=valid, status=r.status_code, data=json_data
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("HTTP error during GetSongBPM API test: %s", str(exc))
        return GetSongBPMTestResponse(
            success=False,
            error="An internal error occurred while testing the GetSongBPM API.",
        )


@api_router.post(
    "/verify-entry",
    response_model=VerifyEntryResponse,
    tags=["Jellyfin"],
)
async def verify_playlist_entry(payload: VerifyEntryRequest) -> VerifyEntryResponse:
    """Confirm that a playlist contains the specified entry ID."""
    playlist_id = payload.playlist_id
    entry_id = payload.entry_id

    if not playlist_id or not entry_id:
        return VerifyEntryResponse(
            success=False, error="playlist_id and entry_id are required"
        )

    tracks = await fetch_tracks_for_playlist_id(playlist_id)
    match = next((t for t in tracks if t.get("PlaylistItemId") == entry_id), None)

    if match:
        return VerifyEntryResponse(success=True, track=match)

    return VerifyEntryResponse(success=False, error="Entry not found in playlist")


__all__ = ["router", "api_router"]
