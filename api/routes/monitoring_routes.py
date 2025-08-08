"""Monitoring and health check routes."""

from fastapi import APIRouter

from api.schemas import HealthResponse, IntegrationFailuresResponse
from utils.integration_watchdog import get_failure_counts

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Simple endpoint for container liveness monitoring."""
    return {"status": "ok"}


@router.get(
    "/integration-failures",
    response_model=IntegrationFailuresResponse,
    tags=["Monitoring"],
)
async def integration_failures() -> IntegrationFailuresResponse:
    """Return current integration failure counters."""
    return IntegrationFailuresResponse(failures=get_failure_counts())


__all__ = ["router"]
