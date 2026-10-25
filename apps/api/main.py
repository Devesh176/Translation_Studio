import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from packages.core.config_loader import load_env

# Load .env before importing anything that reads environment variables
load_env()

# ---------------------------------------------------------------------------
# Observability — must be initialised before route handlers are imported
# ---------------------------------------------------------------------------
from packages.observability import (  # noqa: E402
    setup_logging,
    setup_tracing,
    instrument_httpx,
    instrument_fastapi,
    instrument_sqlalchemy,
    instrument_redis,
    setup_sentry,
)

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
_OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
_SERVICE_NAME = os.getenv("SERVICE_NAME", "translation-studio-api")

# 1. Structured JSON logging (always on)
setup_logging(log_level=_LOG_LEVEL)

# 2. Distributed tracing (OTel → Tempo)
if _OTEL_ENABLED:
    setup_tracing(service_name=_SERVICE_NAME)
    instrument_httpx()
    instrument_sqlalchemy()
    instrument_redis()

# 3. Sentry exception tracking
setup_sentry()

from packages.observability.logging import get_logger  # noqa: E402

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Application routes
# ---------------------------------------------------------------------------
from apps.api.routes.health import router as health_router  # noqa: E402
from apps.api.routes.documents import router as documents_router  # noqa: E402
from apps.api.routes.sections import router as sections_router  # noqa: E402
from packages.storage.postgres.db import init_db  # noqa: E402
from packages.observability.middleware import (  # noqa: E402
    MetricsMiddleware,
    RequestLoggingMiddleware,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api_starting", service=_SERVICE_NAME, log_level=_LOG_LEVEL, otel_enabled=_OTEL_ENABLED)
    try:
        await init_db()
        log.info("database_initialised")
    except Exception as exc:
        log.warning("database_init_skipped", error=str(exc))
    yield
    log.info("api_shutdown")


app = FastAPI(
    title="Translation Studio V1",
    description="Structure-Preserving Document Transformation and Indic Translation Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware (order matters: outer → inner)
# ---------------------------------------------------------------------------

# CORS — outermost so preflight requests are handled before any auth/metrics
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging — runs around the full handler
app.add_middleware(RequestLoggingMiddleware)

# Prometheus metrics — runs around the full handler (after logging)
app.add_middleware(MetricsMiddleware)

# ---------------------------------------------------------------------------
# Prometheus /metrics endpoint
# ---------------------------------------------------------------------------
try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY  # noqa: E402
    from fastapi.responses import Response

    @app.get("/metrics", include_in_schema=False)
    @app.get("/metrics/", include_in_schema=False)
    async def metrics_endpoint():
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
except (ImportError, Exception):
    from fastapi.responses import PlainTextResponse

    @app.get("/metrics", include_in_schema=False)
    @app.get("/metrics/", include_in_schema=False)
    async def metrics_fallback():
        return PlainTextResponse(
            "# HELP translation_studio_up Indicates service is running\n"
            "# TYPE translation_studio_up gauge\n"
            "translation_studio_up 1\n",
            media_type="text/plain; version=0.0.4",
        )


# ---------------------------------------------------------------------------
# OTel FastAPI auto-instrumentation (must run after app + routes are wired)
# ---------------------------------------------------------------------------
if _OTEL_ENABLED:
    instrument_fastapi(app)

# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(sections_router)

# ---------------------------------------------------------------------------
# Static web frontend
# ---------------------------------------------------------------------------
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(WEB_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)
