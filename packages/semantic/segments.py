"""Sentence segmentation, echo detection and glossary helpers for semantic units."""
import hashlib
import re
from typing import Dict, List

ABBREV = {"e.g", "i.e", "etc", "vs", "fig", "figs", "eq", "eqs", "et al", "al", "dr", "mr", "mrs", "ms", "no", "sec", "approx", "cf", "resp", "ref"}
_SPLIT = re.compile(r"(?<=[.?!।॥])\s+")


def split_segments(text: str) -> List[Dict[str, str]]:
    """Split on sentence terminators; keep abbreviations/decimals together. IDs are stable per order."""
    parts: List[str] = []
    cur = ""
    for piece in _SPLIT.split(text.strip()):
        if not piece:
            continue
        if cur:
            prev_word = re.findall(r"([A-Za-z.]+)\.$", cur)
            nxt_lower = piece[:1].islower()
            if (prev_word and prev_word[-1].lower().rstrip(".") in ABBREV) or nxt_lower or len(cur) < 12:
                cur += " " + piece
                continue
            parts.append(cur)
        cur = piece
    if cur:
        parts.append(cur)
    return [{"id": f"s{i}", "text": p} for i, p in enumerate(parts, 1)]


def _words(t: str) -> List[str]:
    return re.findall(r"[^\W\d_]{2,}", t)


def is_label_like(text: str) -> bool:
    """Figure/table labels, model names, identifiers: no lowercase prose words, so an unchanged output is fine."""
    prose = [w for w in _words(re.sub(r"⟦P\d+⟧", " ", text)) if w[0].islower() and len(w) > 2]
    return len(prose) == 0


def glossary_hash(glossary: Dict[str, str]) -> str:
    return hashlib.sha1("|".join(f"{k}={v}" for k, v in sorted(glossary.items())).encode()).hexdigest()[:8]


def glossary_findings(source: str, target: str, glossary: Dict[str, str]) -> List[Dict]:
    out = []
    low = source.lower()
    for term, tr in glossary.items():
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", low) and tr not in target:
            out.append({"severity": "medium", "category": "terminology", "segments": [],
                        "detail": f"'{term}' should be rendered as '{tr}'"})
    return out
