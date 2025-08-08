"""Tests for the application's shutdown event."""

import importlib
import sys
from fastapi.testclient import TestClient


def test_shutdown_closes_http_clients() -> None:
    """Shutdown event closes shared HTTP clients."""
    for module in [
        "httpx",
        "utils.http_client",
        "utils.cache_manager",
        "utils.helpers",
        "api.routes",
        "main",
        "diskcache",
    ]:
        sys.modules.pop(module, None)

    importlib.import_module("httpx")
    app_module = importlib.import_module("main")
    http_client_module = importlib.import_module("utils.http_client")

    long_client = http_client_module.get_http_client()
    short_client = http_client_module.get_http_client(short=True)

    with TestClient(app_module.app):
        pass

    assert long_client.is_closed
    assert short_client.is_closed
