import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "translation_studio_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "apps.worker.tasks.pdf_ingest.*": {"queue": "pdf_ingestion"},
        "apps.worker.tasks.ocr.*": {"queue": "ocr"},
        "apps.worker.tasks.translate.*": {"queue": "translation"},
        "apps.worker.tasks.render.*": {"queue": "rendering"},
    },
)
