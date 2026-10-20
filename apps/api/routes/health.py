from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/healthz")
async def health_check():
    return {
        "status": "HEALTHY",
        "service": "translation-studio-api",
        "version": "1.0.0",
    }
