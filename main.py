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



from config import settings
from fastapi import FastAPI
from api.routes import router as main_router
from fastapi.templating import Jinja2Templates
from pathlib import Path
from fastapi.staticfiles import StaticFiles
import logging
from core.constants import *
import diskcache
from diskcache import Cache
from core.templates import templates


# ─────────────────────────────────────────────────────────────
# Logging Configuration
from logging.handlers import RotatingFileHandler
logger = logging.getLogger("playlist-pilot")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = RotatingFileHandler("logs/playlist_pilot.log", maxBytes=1_000_000, backupCount=3)
    handler.setLevel(logging.DEBUG)  # Capture DEBUG logs!
    formatter = logging.Formatter("%(asctime)s | %(levelname)8s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ─────────────────────────────────────────────────────────────
# Validate Configuration
try:
    settings.validate()
except ValueError as e:
    import sys
    print(f"[Startup Error] {e}", file=sys.stderr)
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────
# FastAPI App Setup
app = FastAPI(title="Playlist Pilot")
# Include all route handlers
app.include_router(main_router)
# Serve static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ─────────────────────────────────────────────────────────────
# Additional routes and startup events could be added here.
