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
    from main import app
    from utils import http_client

    long_client = http_client.get_http_client()
    short_client = http_client.get_http_client(short=True)

    with TestClient(app):
        pass

    assert long_client.is_closed
    assert short_client.is_closed
