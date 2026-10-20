import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from packages.core.config_loader import load_env

load_env()

from apps.api.routes.health import router as health_router
from apps.api.routes.documents import router as documents_router
from apps.api.routes.sections import router as sections_router
from packages.storage.postgres.db import init_db



WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite/Postgres DB schema on startup
    try:
        await init_db()
    except Exception as e:
        print(f"Warning: Database initialization skipped: {e}")
    yield


app = FastAPI(
    title="Translation Studio V1",
    description="Structure-Preserving Document Transformation and Indic Translation Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for Web / UI clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(sections_router)

# Serve web frontend
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(WEB_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)

