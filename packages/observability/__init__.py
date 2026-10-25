"""
Observability package for Translation Studio.

Provides four pillars of production observability:

1. **Structured logging** (structlog → JSON stdout → Promtail → Loki → Grafana)
2. **Distributed tracing** (OTel SDK → OTLP HTTP → OTel Collector → Tempo → Grafana)
3. **Metrics** (prometheus_client → /metrics → Prometheus → Grafana)
4. **Exception tracking** (Sentry SDK)

Quick-start for application code
---------------------------------
    from packages.observability import get_logger, get_tracer
    from packages.observability.metrics import TRANSLATION_REQUESTS_TOTAL

    logger = get_logger(__name__)
    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("key", "value")
        logger.info("my_event", key="value")
        TRANSLATION_REQUESTS_TOTAL.labels(provider="bodhan", ...).inc()
"""

from packages.observability.logging import get_logger, setup_logging
from packages.observability.tracing import (
    get_tracer,
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    instrument_sqlalchemy,
    setup_tracing,
)
from packages.observability.sentry import setup_sentry

__all__ = [
    "get_logger",
    "setup_logging",
    "get_tracer",
    "setup_tracing",
    "instrument_fastapi",
    "instrument_httpx",
    "instrument_sqlalchemy",
    "instrument_redis",
    "setup_sentry",
]
