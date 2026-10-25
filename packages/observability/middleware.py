"""
FastAPI middleware for HTTP-level observability.

MetricsMiddleware      — records Prometheus HTTP counters + duration histogram.
RequestLoggingMiddleware — emits one structured JSON log line per request/response.
"""

from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from packages.observability.logging import get_logger
from packages.observability.metrics import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)

logger = get_logger(__name__)

# Paths that produce very high request volumes and should not be individually
# logged or metered to avoid cardinality explosions.
_EXCLUDED_LOG_PATHS = frozenset({"/health", "/metrics", "/favicon.ico"})


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Record Prometheus HTTP metrics for every request.

    Labels ``method``, ``endpoint``, and ``status_code`` are low-cardinality
    by design: dynamic path parameters (document_id, version_id) are NOT
    included in the endpoint label.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        method = request.method
        # Collapse dynamic segments to avoid label cardinality explosion.
        # e.g. /api/v1/documents/abc-123/versions/xyz/pdf → /api/v1/documents/{id}/versions/{id}/pdf
        endpoint = _normalise_path(request.url.path)

        response = await call_next(request)

        duration = time.perf_counter() - start
        status = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(
            method=method, endpoint=endpoint, status_code=status
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(
            duration
        )
        if response.status_code >= 500:
            HTTP_ERRORS_TOTAL.labels(method=method, endpoint=endpoint).inc()

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Emit one structured log record per HTTP request.

    The trace_id injected by ``_add_trace_context`` in logging.py links this
    log record to the OTel span so Grafana can jump from Loki → Tempo.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in _EXCLUDED_LOG_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        log_fn = logger.info
        if response.status_code >= 500:
            log_fn = logger.error
        elif response.status_code >= 400:
            log_fn = logger.warning

        log_fn(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else None,
        )

        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UUID_RE = None


def _normalise_path(path: str) -> str:
    """
    Replace UUID-like and numeric segments with ``{id}`` so that Prometheus
    label cardinality stays bounded.
    """
    import re  # noqa: PLC0415

    global _UUID_RE
    if _UUID_RE is None:
        _UUID_RE = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
            r"|[0-9a-f]{32}"
            r"|\b\d+\b",
            re.IGNORECASE,
        )
    return _UUID_RE.sub("{id}", path)
