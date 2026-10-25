"""
Structured JSON logging via structlog.

Outputs Loki-compatible JSON to stdout on every log call.
Automatically injects OTel trace_id / span_id when a span is active.

Usage:
    from packages.observability.logging import get_logger
    logger = get_logger(__name__)
    logger.info("pipeline_started", document_id=doc_id, target_language=tgt)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger


# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------


def _add_service_context(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Stamp every log record with the service name and deployment environment."""
    event_dict["service"] = os.getenv("SERVICE_NAME", "translation-studio")
    event_dict["env"] = os.getenv("APP_ENV", "development")
    return event_dict


def _add_trace_context(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """
    Inject OTel trace_id / span_id when a span is active so that Grafana can
    correlate logs (Loki) with traces (Tempo) via the trace_id field.
    """
    try:
        from opentelemetry import trace  # noqa: PLC0415

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:  # opentelemetry not installed / no active span
        pass
    return event_dict


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog for JSON output.  Must be called once at startup before
    any other module logs anything.

    Pipeline:
        structlog processors → JSON string → stdout
        ↓ (via Promtail docker_sd_configs)
        Loki
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors run on every log record regardless of origin
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_service_context,
        _add_trace_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Formatter for the stdlib logging bridge
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Silence overly verbose third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_logger(name: str = "translation-studio") -> structlog.stdlib.BoundLogger:
    """
    Return a bound structlog logger.  Always prefer this over ``logging.getLogger``.

    Example::

        logger = get_logger(__name__)
        logger.info("ocr_completed", page=3, confidence=0.97, latency_ms=412)
    """
    return structlog.get_logger(name)
