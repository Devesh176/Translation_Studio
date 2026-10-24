import re
import unicodedata

_SENTINEL_RE = re.compile(
    r"<<<\s*DOCUMENT_CONTENT|DOCUMENT_CONTENT\s*>>>|</?source_segment>|<<<|>>>",
    re.IGNORECASE,
)


class TextNormalizer:
    @staticmethod
    def normalize_indic_text(text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFC", text)
        # Collapse spaces/tabs but keep newlines and leading indentation of each line
        lines = []
        for line in normalized.split("\n"):
            indent = re.match(r"[ \t]*", line).group(0)
            lines.append(indent + re.sub(r"[ \t]+", " ", line[len(indent):]).rstrip())
        normalized = "\n".join(lines)
        normalized = normalized.replace("‌‌", "‌")
        return normalized.strip("\n").strip()

    @staticmethod
    def strip_sentinels(text: str) -> str:
        return _SENTINEL_RE.sub("", text).strip()

    @staticmethod
    def has_sentinel(text: str) -> bool:
        return bool(text and _SENTINEL_RE.search(text))

    @staticmethod
    def clean_llm_markdown_wrappers(text: str) -> str:
        t = text.strip()
        if t.startswith("```") and t.endswith("```"):
            lines = t.split("\n")
            if len(lines) >= 2:
                t = "\n".join(lines[1:-1]).strip()
        return TextNormalizer.strip_sentinels(t)
