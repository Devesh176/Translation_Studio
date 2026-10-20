from packages.routing.language import (
    get_language_registry,
    LanguageInfo,
    normalize_language_code,
    detect_unicode_script,
    infer_language_from_script,
)
from packages.routing.policy import RoutingDecision, OCRDecision
from packages.routing.translation_router import TranslationRouter
from packages.routing.ocr_router import OCRRouter

# Backward-compat alias: callers can use get_language_registry() for the dict
LANGUAGE_REGISTRY = get_language_registry()

__all__ = [
    "LANGUAGE_REGISTRY",
    "get_language_registry",
    "LanguageInfo",
    "normalize_language_code",
    "detect_unicode_script",
    "infer_language_from_script",
    "RoutingDecision",
    "OCRDecision",
    "TranslationRouter",
    "OCRRouter",
]
