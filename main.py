"""
main.py

Entry point for the Playlist Pilot FastAPI application.

This module initializes:
- Logging with rotating file handlers
- Settings validation
- FastAPI app with templates and static files
- API routing
- Disk-backed caching (via diskcache, indirectly)

Modules used:
- FastAPI: Web framework
- diskcache: Persistent caching of GPT responses
- Jinja2Templates: HTML rendering
- logging: App logging to disk
"""

import logging
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from api.routes import router, api_router
from config import settings
from core.constants import BASE_DIR, LOG_FILE
from utils.http_client import aclose_http_clients

API_VERSION = "1.0.0"

tags_metadata = [
    {"name": "UI", "description": "User-facing HTML pages."},
    {"name": "Comparison", "description": "Compare playlists from various sources."},
    {"name": "History", "description": "Access and manage analysis history."},
    {"name": "Analysis", "description": "Analyze playlists and tracks."},
    {"name": "Exports", "description": "Export playlists or analysis results."},
    {
        "name": "Suggestions",
        "description": "Generate playlist or ordering suggestions.",
    },
    {"name": "Metadata", "description": "Read or write track metadata."},
    {"name": "Import", "description": "Import playlists or track lists."},
    {"name": "Settings", "description": "Configure application options."},
    {"name": "Testing", "description": "Endpoints used for integration testing."},
    {"name": "Monitoring", "description": "Monitoring and health check routes."},
    {"name": "System", "description": "System-level endpoints."},
    {"name": "Jellyfin", "description": "Jellyfin-specific validation endpoints."},
]


# ─────────────────────────────────────────────────────────────
# Logging Configuration
logger = logging.getLogger("playlist-pilot")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
    handler.setLevel(logging.DEBUG)  # Capture DEBUG logs!
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)8s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ─────────────────────────────────────────────────────────────
# Validate Configuration
try:
    settings.validate_settings()
except ValueError as e:
    logger.warning("[Startup] Missing configuration: %s", e)

# ─────────────────────────────────────────────────────────────
# FastAPI App Setup
app = FastAPI(
    title="Playlist Pilot",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
)


@app.middleware("http")
async def add_version_header(request: Request, call_next):
    """Attach semantic version information to all responses."""
    response = await call_next(request)
    response.headers["X-API-Version"] = API_VERSION
    return response


# Include all route handlers
app.include_router(router)
app.include_router(api_router)
# Serve static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Close shared HTTP clients on application shutdown."""
    await aclose_http_clients()


# ─────────────────────────────────────────────────────────────
# Additional routes and startup events could be added here.
