import os
from typing import Dict, List, Optional


class FontRegistry:
    FONT_MAP = {
        "en": "Helvetica",
        "hi": "NotoSansDevanagari",
        "ta": "NotoSansTamil",
        "te": "NotoSansTelugu",
        "kn": "NotoSansKannada",
        "ml": "NotoSansMalayalam",
        "bn": "NotoSansBengali",
        "mr": "NotoSansDevanagari",
        "gu": "NotoSansGujarati",
        "pa": "NotoSansGurmukhi",
    }

    @classmethod
    def get_font_for_language(cls, lang_code: str, is_bold: bool = False, is_italic: bool = False) -> str:
        lang = lang_code.lower().split("-")[0]
        base_font = cls.FONT_MAP.get(lang, "Helvetica")
        if base_font == "Helvetica":
            if is_bold and is_italic:
                return "Helvetica-BoldOblique"
            elif is_bold:
                return "Helvetica-Bold"
            elif is_italic:
                return "Helvetica-Oblique"
            return "Helvetica"
        return base_font
