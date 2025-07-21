"""Simple watchdog for external integrations."""

from collections import defaultdict
import logging

logger = logging.getLogger("playlist-pilot")

_FAILURE_THRESHOLD = 3
_failure_counts: defaultdict[str, int] = defaultdict(int)


def record_success(service: str) -> None:
    """Reset failure count for a service on successful call."""
    _failure_counts[service] = 0
    logger.debug("[watchdog] %s success", service)


def record_failure(service: str) -> None:
    """Increment failure count and log when threshold exceeded."""
    _failure_counts[service] += 1
    count = _failure_counts[service]
    logger.error("[watchdog] %s failure #%d", service, count)
    if count >= _FAILURE_THRESHOLD:
        logger.warning("⚠️ %s integration repeatedly failing (%d)", service, count)


def get_failure_counts() -> dict[str, int]:
    """Return current failure counters for all services."""
    return dict(_failure_counts)
