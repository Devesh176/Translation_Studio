"""Protected spans: commands, filenames, identifiers, URLs and product names are
swapped for placeholders before translation and restored afterwards."""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

OPEN, CLOSE = "⟦", "⟧"  # ⟦ ⟧
_TOKEN_RE = re.compile(OPEN + r"P(\d+)" + CLOSE)
_LOOSE_TOKEN_RE = re.compile(OPEN + r"\s*[^\d\u27e6\u27e7]{0,4}?\s*(\d+)\s*" + CLOSE)

PRODUCT_NAMES = [
    "Anaconda", "Miniconda", "Python", "Jupyter", "JupyterLab", "Nomura", "Windows", "macOS",
    "Linux", "Ubuntu", "VS Code", "Visual Studio Code", "GitHub", "Git", "NumPy", "pandas",
    "conda", "pip", "PyTorch", "TensorFlow", "Excel", "Docker",
]

_CLI = r"(?:conda|pip3?|python3?|jupyter|git|cd|ls|mkdir|source|npm|export|sudo|apt|apt-get|brew|set|where|which|echo|activate|deactivate)"
_CODE_LINE_RE = re.compile(rf"^\s*(?:[$>#]\s*)?{_CLI}\b(?:\s+[-\w.=:/\\\"'<>@~,\[\]*]+)*\s*$")
_YAML_LINE_RE = re.compile(r"^\s*(?:-\s+[\w.=<>~*\"'-]+|[A-Za-z_][\w.-]*:\s*(?:[\w.=<>~*\"'/-]+)?)\s*$")

_INLINE_PATTERNS: List[str] = [
    r"^[A-Z]\d{1,2}\.(?=\s)",
    r"\ue000\d+\ue001",
    r"`[^`\n]+`",
    r"https?://[^\s<>\"')]+|www\.[^\s<>\"')]+",
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    rf"\b(?:conda|pip3?|python3?|jupyter)(?:\s+(?:--?[\w-]+|(?:activate|deactivate|create|install|env|list|update|remove|config|init|run|notebook|lab)\b))+(?:\s+--?[\w-]+(?:=[\w.:/-]+)?(?:\s+[\w.=/-]+)?|\s+[\w.-]*[\d=./\\_-][\w.=/\\-]*)*",
    r"(?<![\w/])[\w./\\-]+\.(?:ya?ml|py|ipynb|txt|json|md|csv|sh|bat|exe|toml|cfg|ini|env|zip|pdf)\b",
    r"\b[A-Za-z][\w-]*=[\w.*<>=-]+",
    r"\b(?=[A-Za-z_]*\d)(?=\d*[A-Za-z_])[A-Za-z_][A-Za-z_]+\d[\w]*\b",
    r"\b\w+_\w+(?:_\w+)*\b",
]
_PRODUCT_RE = re.compile(r"(?<![\w])(" + "|".join(re.escape(p) for p in sorted(PRODUCT_NAMES, key=len, reverse=True)) + r")(?![\w])")
_INLINE_RE = re.compile("|".join(f"(?:{p})" for p in _INLINE_PATTERNS))


@dataclass
class ProtectedText:
    masked: str
    mapping: Dict[str, str] = field(default_factory=dict)


def is_code_line(text: str) -> bool:
    return bool(_CODE_LINE_RE.match(text.rstrip("\n")))


def is_yaml_line(text: str) -> bool:
    return bool(_YAML_LINE_RE.match(text.rstrip("\n")))


def looks_like_code(text: str) -> bool:
    """True if every non-empty line is a shell command or YAML-ish line."""
    lines = [l for l in text.split("\n") if l.strip()]
    return bool(lines) and all(is_code_line(l) or is_yaml_line(l) for l in lines)


def protect(text: str) -> ProtectedText:
    mapping: Dict[str, str] = {}
    counter = [0]

    def sub(m: "re.Match[str]") -> str:
        counter[0] += 1
        tok = f"{OPEN}P{counter[0]}{CLOSE}"
        mapping[tok] = m.group(0)
        return tok

    out = _INLINE_RE.sub(sub, text)
    # Product names are matched outside already-created tokens
    parts = re.split(f"({OPEN}P\\d+{CLOSE})", out)
    parts = [p if p.startswith(OPEN) else _PRODUCT_RE.sub(sub, p) for p in parts]
    return ProtectedText("".join(parts), mapping)


def validate_and_restore(translated: str, mapping: Dict[str, str]) -> Tuple[str, List[str]]:
    """Restore placeholders; return (text, errors). Each token must occur exactly once."""
    errors: List[str] = []
    translated = _LOOSE_TOKEN_RE.sub(lambda m: f"{OPEN}P{int(m.group(1))}{CLOSE}", translated)
    for tok in mapping:
        n = translated.count(tok)
        if n != 1:
            errors.append(f"PROTECTED_TOKEN_{'MISSING' if n == 0 else 'DUPLICATED'}:{tok}={mapping[tok]!r}")
    for tok in set(_TOKEN_RE.findall(translated)):
        if f"{OPEN}P{tok}{CLOSE}" not in mapping:
            errors.append(f"UNKNOWN_PLACEHOLDER:P{tok}")
    restored = translated
    for tok, original in mapping.items():
        restored = restored.replace(tok, original)
    if has_placeholder(restored):
        errors.append("PLACEHOLDER_LEAK")
    return restored, errors


def has_placeholder(text: str) -> bool:
    return bool(text) and (OPEN in text or CLOSE in text)
