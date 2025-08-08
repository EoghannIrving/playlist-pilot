"""Tests for the integration watchdog utilities."""

# pylint: disable=protected-access, duplicate-code

import logging

from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

from config import settings
from api.schemas import IntegrationFailuresResponse
from api.routes.monitoring_routes import integration_failures
from utils import integration_watchdog as watchdog


def test_failure_warning_respects_threshold(caplog):
    """record_failure should log a warning when limit is exceeded."""
    old_limit = settings.integration_failure_limit
    settings.integration_failure_limit = 2
    watchdog._failure_counts.clear()

    with caplog.at_level(logging.WARNING):
        watchdog.record_failure("svc")
        assert "repeatedly failing" not in caplog.text
        watchdog.record_failure("svc")
        assert "repeatedly failing" in caplog.text

    # Changing the limit should affect subsequent warnings
    settings.integration_failure_limit = 4
    watchdog.record_success("svc")
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            watchdog.record_failure("svc")
        assert "repeatedly failing" not in caplog.text
        watchdog.record_failure("svc")
        assert "repeatedly failing" in caplog.text

    settings.integration_failure_limit = old_limit


def test_integration_failures_endpoint_returns_counts():
    """The monitoring endpoint should expose current failure counts."""
    watchdog._failure_counts.clear()
    watchdog.record_failure("a")
    watchdog.record_failure("b")
    watchdog.record_failure("b")

    router = APIRouter()
    router.get("/api/integration-failures", response_model=IntegrationFailuresResponse)(
        integration_failures
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/integration-failures")
    assert resp.status_code == 200
    assert resp.json() == {"failures": {"a": 1, "b": 2}}
