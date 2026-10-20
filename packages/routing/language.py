"""
Language registry and detection utilities.

The canonical language list is sourced from config/languages.yaml so that
adding new Indic languages requires only a YAML edit.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import Dict, Optional, Tuple

from pydantic import BaseModel

from packages.core.config_loader import get_languages_config


class LanguageInfo(BaseModel):
    code: str
    name: str
    script: str
    bodhan_mt_code: str
    bodhan_ocr_code: str
    openrouter_name: str


@lru_cache(maxsize=None)
def _build_registry() -> Dict[str, LanguageInfo]:
    """Build the LANGUAGE_REGISTRY from config/languages.yaml."""
    cfg = get_languages_config()
    registry: Dict[str, LanguageInfo] = {}
    for code, attrs in cfg.get("languages", {}).items():
        registry[code] = LanguageInfo(
            code=code,
            name=attrs["name"],
            script=attrs["script"],
            bodhan_mt_code=attrs.get("bodhan_mt_code", code),
            bodhan_ocr_code=attrs.get("bodhan_ocr_code", code),
            openrouter_name=attrs.get("openrouter_name", attrs["name"]),
        )
    return registry


# Module-level alias — populated lazily from YAML
@property  # type: ignore[misc]
def LANGUAGE_REGISTRY() -> Dict[str, LanguageInfo]:  # noqa: N802
    return _build_registry()


# Eager convenience reference (populated at import time)
def get_language_registry() -> Dict[str, LanguageInfo]:
    return _build_registry()


# ------------------------------------------------------------------ #
#  Public helpers                                                      #
# ------------------------------------------------------------------ #

def normalize_language_code(code: str) -> str:
    """
    Map any reasonable language code variant to its canonical 2-letter code.
    Falls back to the cleaned prefix if not found.
    """
    registry = _build_registry()
    code_clean = code.strip().lower().replace("-", "_")
    prefix = code_clean.split("_")[0]
    if prefix in registry:
        return prefix
    for k, v in registry.items():
        if code_clean == v.bodhan_mt_code or code_clean == v.name.lower():
            return k
    return prefix


def detect_unicode_script(text: str) -> Tuple[str, float]:
    """
    Detect the dominant Unicode script in *text*.

    Returns a (script_name, confidence) tuple where confidence is the
    fraction of alphabetic characters belonging to the dominant script.
    """
    if not text.strip():
        return "Latin", 1.0

    script_counts: Dict[str, int] = {}
    total_letters = 0

    for char in text:
        if not char.isalpha():
            continue
        total_letters += 1
        name = unicodedata.name(char, "")
        if "DEVANAGARI" in name:
            s = "Devanagari"
        elif "TAMIL" in name:
            s = "Tamil"
        elif "TELUGU" in name:
            s = "Telugu"
        elif "KANNADA" in name:
            s = "Kannada"
        elif "MALAYALAM" in name:
            s = "Malayalam"
        elif "BENGALI" in name:
            s = "Bengali"
        elif "GUJARATI" in name:
            s = "Gujarati"
        elif "GURMUKHI" in name:
            s = "Gurmukhi"
        elif "LATIN" in name:
            s = "Latin"
        else:
            s = "Other"
        script_counts[s] = script_counts.get(s, 0) + 1

    if total_letters == 0:
        return "Latin", 1.0

    dominant_script = max(script_counts.items(), key=lambda x: x[1])
    confidence = dominant_script[1] / total_letters
    return dominant_script[0], confidence


def infer_language_from_script(script: str, default_if_ambiguous: str = "hi") -> str:
    """
    Heuristically infer the most likely language code from a Unicode script name.
    Devanagari is ambiguous (Hindi/Marathi/Sanskrit); caller must supply a default.
    """
    script_map: Dict[str, str] = {
        "Latin": "en",
        "Tamil": "ta",
        "Telugu": "te",
        "Kannada": "kn",
        "Malayalam": "ml",
        "Bengali": "bn",
        "Gujarati": "gu",
        "Gurmukhi": "pa",
        "Devanagari": default_if_ambiguous,
    }
    return script_map.get(script, "en")
