import os
from packages.storage.object_store.local_store import LocalFileObjectStore
from packages.storage.object_store.s3_store import S3ObjectStore
from packages.storage.redis.cache import TranslationCache
from packages.routing.translation_router import TranslationRouter
from apps.worker.tasks.pipeline import DocumentTranslationPipeline
from apps.worker.tasks.section_edit import SectionEditPipeline

_storage = None
_cache = None
_pipeline = None


def get_storage():
    global _storage
    if _storage is None:
        driver = os.getenv("OBJECT_STORAGE_DRIVER", "local")
        if driver == "s3":
            _storage = S3ObjectStore(
                endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT", "http://minio:9000"),
                bucket_name=os.getenv("OBJECT_STORAGE_BUCKET", "translation-studio"),
            )
        else:
            _storage = LocalFileObjectStore(os.getenv("OBJECT_STORAGE_LOCAL_DIR", "./data/storage"))
    return _storage


def get_cache():
    global _cache
    if _cache is None:
        _cache = TranslationCache()
    return _cache


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = DocumentTranslationPipeline(
            storage_store=get_storage(),
            cache=get_cache(),
        )
    return _pipeline


def get_section_edit_pipeline():
    return SectionEditPipeline(storage_store=get_storage())
