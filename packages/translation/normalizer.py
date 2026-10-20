import re
import unicodedata


class TextNormalizer:
    @staticmethod
    def normalize_indic_text(text: str) -> str:
        if not text:
            return ""
        # Unicode NFC normalization
        normalized = unicodedata.normalize("NFC", text)
        # Clean extra repeated whitespaces
        normalized = re.sub(r"[ \t]+", " ", normalized)
        # Clean zero-width non-joiner abuse
        normalized = normalized.replace("\u200c\u200c", "\u200c")
        return normalized.strip()

    @staticmethod
    def clean_llm_markdown_wrappers(text: str) -> str:
        t = text.strip()
        if t.startswith("```") and t.endswith("```"):
            lines = t.split("\n")
            if len(lines) >= 2:
                t = "\n".join(lines[1:-1]).strip()
        if t.startswith("<<<") and t.endswith(">>>"):
            t = t[3:-3].strip()
        return t
