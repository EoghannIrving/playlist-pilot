"""Integration tests for versioned API endpoints."""

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_endpoint():
    """The health endpoint should return status ok."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_integration_failures_endpoint():
    """Integration failures endpoint should return a failures dictionary."""
    response = client.get("/api/v1/integration-failures")
    assert response.status_code == 200
    data = response.json()
    assert "failures" in data
    assert isinstance(data["failures"], dict)
