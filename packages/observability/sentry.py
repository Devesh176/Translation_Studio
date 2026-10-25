"""
Sentry SDK initialisation for application exception tracking.

Captures unhandled exceptions from FastAPI request handlers and Celery tasks
and reports them to the Sentry project configured via SENTRY_DSN.
"""

from __future__ import annotations

import os
from typing import Optional


def setup_sentry(
    dsn: Optional[str] = None,
    environment: Optional[str] = None,
    release: str = "translation-studio@1.0.0",
    traces_sample_rate: float = 0.1,
) -> bool:
    """
    Initialise the Sentry SDK.

    Returns ``True`` if Sentry was successfully initialised, ``False`` if the
    DSN is not configured (treated as a deliberate opt-out, not an error).

    Args:
        dsn: Sentry DSN.  Defaults to the ``SENTRY_DSN`` environment variable.
        environment: Deployment environment label (e.g. ``production``).
                     Defaults to ``APP_ENV``.
        release: Release identifier for source-map and regression tracking.
        traces_sample_rate: Fraction of transactions forwarded as Sentry
                            performance traces (0.0–1.0).  Keep low in
                            production to avoid double-counting with OTel.
    """
    resolved_dsn = (dsn or os.getenv("SENTRY_DSN", "")).strip()
    if not resolved_dsn:
        return False

    try:
        import sentry_sdk  # noqa: PLC0415
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.starlette import StarletteIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.logging import LoggingIntegration  # noqa: PLC0415
        import logging  # noqa: PLC0415

        sentry_sdk.init(
            dsn=resolved_dsn,
            environment=environment or os.getenv("APP_ENV", "development"),
            release=release,
            traces_sample_rate=traces_sample_rate,
            # Send all ERROR+ log records as Sentry breadcrumbs
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
                LoggingIntegration(
                    level=logging.WARNING,       # breadcrumbs from WARNING+
                    event_level=logging.ERROR,   # Sentry events from ERROR+
                ),
            ],
            # Never include raw PDF content or API keys in payloads
            before_send=_scrub_sensitive_data,
        )
        return True
    except ImportError:
        # sentry-sdk not installed; silently skip
        return False


def _scrub_sensitive_data(event: dict, hint: dict) -> dict:
    """
    Strip API keys, PDF content and other sensitive data from Sentry events
    before they are transmitted.  Applied via the ``before_send`` hook.
    """
    _REDACT = frozenset(
        {
            "api_key",
            "authorization",
            "bodhan_api_key",
            "openrouter_api_key",
            "aws_secret_access_key",
            "sentry_dsn",
            "pdf_bytes",
            "image_bytes",
            "source_text",
            "translated_text",
        }
    )

    def _scrub(obj: object) -> object:
        if isinstance(obj, dict):
            return {
                k: "[REDACTED]" if k.lower() in _REDACT else _scrub(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_scrub(i) for i in obj]
        return obj

    return _scrub(event)  # type: ignore[return-value]
