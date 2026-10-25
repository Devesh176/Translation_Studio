"""
OpenTelemetry distributed tracing setup.

Initialises a TracerProvider that exports spans via OTLP HTTP to the
OTel Collector, which forwards them to Tempo.

Usage:
    from packages.observability.tracing import setup_tracing, get_tracer

    # At startup (before handling requests):
    setup_tracing(service_name="translation-studio-api")

    # In application code:
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("translate_node") as span:
        span.set_attribute("node.id", node_id)
        span.set_attribute("provider", "bodhan")
        ...
"""

from __future__ import annotations

import os
from typing import Optional, Any

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
    _OTEL_AVAILABLE = True
except (ImportError, Exception):
    _OTEL_AVAILABLE = False
    trace = None
    Resource = None
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"
    TracerProvider = None
    BatchSpanProcessor = None
    SpanExporter = None


class _NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def set_attribute(self, *args, **kwargs):
        pass

    def record_exception(self, *args, **kwargs):
        pass


class _NoOpTracer:
    def start_as_current_span(self, *args, **kwargs):
        return _NoOpSpan()


# ---------------------------------------------------------------------------
# Provider initialisation
# ---------------------------------------------------------------------------


def setup_tracing(
    service_name: str = "translation-studio",
    service_version: str = "1.0.0",
    otlp_endpoint: Optional[str] = None,
) -> Optional[TracerProvider]:
    """
    Configure and globally register the TracerProvider.

    If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (or ``otlp_endpoint`` is passed),
    spans are exported via OTLP HTTP.  Otherwise the provider is registered
    with no exporter so the rest of the application is completely unaffected
    (spans are created but immediately discarded).

    Args:
        service_name: The ``service.name`` resource attribute.
        service_version: The ``service.version`` resource attribute.
        otlp_endpoint: Base URL of the OTel Collector
                       (e.g. ``http://otel-collector:4318``).
                       Defaults to the ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var.

    Returns:
        The configured :class:`TracerProvider`, or None if OTel is not installed.
    """
    if not _OTEL_AVAILABLE or TracerProvider is None:
        return None

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": os.getenv("APP_ENV", "development"),
        }
    )

    provider = TracerProvider(resource=resource)
    exporter: Optional[SpanExporter] = _build_exporter(otlp_endpoint)

    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    return provider


def _build_exporter(otlp_endpoint: Optional[str]) -> Optional[SpanExporter]:
    """Construct an OTLP HTTP span exporter or return None."""
    endpoint = (
        otlp_endpoint
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    ).strip().rstrip("/")

    if not endpoint:
        return None

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )

        traces_url = (
            endpoint
            if endpoint.endswith("/v1/traces")
            else f"{endpoint}/v1/traces"
        )
        return OTLPSpanExporter(endpoint=traces_url)
    except ImportError:
        # opentelemetry-exporter-otlp-proto-http not installed
        return None


# ---------------------------------------------------------------------------
# Auto-instrumentation helpers
# ---------------------------------------------------------------------------


def instrument_fastapi(app: object) -> None:
    """
    Auto-instrument a FastAPI application so every HTTP request gets a root
    span with method, path, status_code and query params.

    Must be called *after* all routes are registered.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415

        FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
    except ImportError:
        pass


def instrument_httpx() -> None:
    """
    Auto-instrument httpx so every outbound HTTP call (Bodhan, OpenRouter)
    gets a child span with URL, method and status code.
    """
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: PLC0415

        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass


def instrument_sqlalchemy() -> None:
    """Auto-instrument SQLAlchemy so DB queries appear in traces."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: PLC0415

        SQLAlchemyInstrumentor().instrument()
    except ImportError:
        pass


def instrument_redis() -> None:
    """Auto-instrument redis-py so cache lookups appear in traces."""
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor  # noqa: PLC0415

        RedisInstrumentor().instrument()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def get_tracer(name: str = "translation-studio") -> Any:
    """
    Return a named :class:`~opentelemetry.trace.Tracer`, or a No-op tracer
    if OpenTelemetry is not installed.

    Example::

        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("render_pdf") as span:
            span.set_attribute("document.id", document_id)
            ...
    """
    if not _OTEL_AVAILABLE or trace is None:
        return _NoOpTracer()
    try:
        return trace.get_tracer(name)
    except Exception:
        return _NoOpTracer()

