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

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import router as main_router
from config import settings
from core.constants import BASE_DIR


# ─────────────────────────────────────────────────────────────
# Logging Configuration
logger = logging.getLogger("playlist-pilot")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = RotatingFileHandler(
        "logs/playlist_pilot.log", maxBytes=1_000_000, backupCount=3
    )
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
app = FastAPI(title="Playlist Pilot")
# Include all route handlers
app.include_router(main_router)
# Serve static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ─────────────────────────────────────────────────────────────
# Additional routes and startup events could be added here.
