"""Combined API routers for Playlist Pilot."""

from fastapi import APIRouter

from .analysis_routes import router as analysis_router
from .settings_routes import (
    router as settings_router,
    api_router as settings_api_router,
)
from .monitoring_routes import router as monitoring_router

router = APIRouter()
router.include_router(analysis_router)
router.include_router(settings_router)

api_router = APIRouter()
api_router.include_router(settings_api_router)
api_router.include_router(monitoring_router)

__all__ = ["router", "api_router"]
