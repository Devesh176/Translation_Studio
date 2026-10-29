"""Semantic Translation Units: group adjacent layout nodes that form one paragraph.

Original nodes are never mutated here; an STU only references them by id.
"""
import os
import re
from dataclasses import dataclass, field
from typing import List

from packages.core.domain.node import DocumentIR, DocumentNode, NodeType, PageNode

TERMINAL = ".?!:;।॥…\"'”’)]"


@dataclass
class GroupingConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("STU_GROUPING", "1") != "0")
    max_gap_factor: float = 1.0      # vertical gap <= factor * font size
    x_tolerance_factor: float = 1.5  # left-edge tolerance * font size (+ same column)
    size_tolerance: float = 0.6
    min_confidence: float = 0.75


@dataclass
class STU:
    unit_id: str
    unit_type: str
    source_node_ids: List[str]
    page_ids: List[str]
    confidence: float
    reasons: List[str]
    source_text: str = ""


def _lead_text(n: DocumentNode) -> str:
    return (n.source_text or "").strip()


def _numeric_heavy(t: str) -> bool:
    chars = [c for c in t if not c.isspace()]
    return bool(chars) and sum(c.isdigit() or c in "%$±" for c in chars) / len(chars) > 0.15


def _groupable(n: DocumentNode) -> bool:
    return (
        not _numeric_heavy(n.source_text or "") and
        n.type == NodeType.PARAGRAPH
        and bool(_lead_text(n))
        and not n.metadata.get("math_only")
        and not n.metadata.get("is_code")
        and not n.metadata.get("math_regions")
        and not n.metadata.get("marker_bbox")
        and not n.metadata.get("ocr_on_selection")
    )


def join_text(parts: List[str]) -> str:
    out = ""
    for p in (x.strip() for x in parts):
        if not out:
            out = p
        elif re.search(r"[A-Za-z]-$", out) and p[:1].islower():
            out = out[:-1] + p
        else:
            out += " " + p
    return out


def continuation_score(a: DocumentNode, b: DocumentNode, cfg: GroupingConfig):
    """Return (confidence, reasons). Conservative: any hard separator -> 0."""
    if not (_groupable(a) and _groupable(b)):
        return 0.0, ["not_groupable"]
    sa, sb = a.style, b.style
    if abs(sa.font_size - sb.font_size) > cfg.size_tolerance or sa.font_weight != sb.font_weight \
            or sa.is_italic != sb.is_italic:
        return 0.0, ["style_differs"]
    size = max(6.0, sa.font_size)
    # same column: horizontal overlap and aligned left edge
    overlap = min(a.bbox.x1, b.bbox.x1) - max(a.bbox.x0, b.bbox.x0)
    if overlap < 0.6 * min(a.bbox.width, b.bbox.width):
        return 0.0, ["different_column"]
    gap = b.bbox.y0 - a.bbox.y1
    if gap < -2.0 or gap > cfg.max_gap_factor * size:
        return 0.0, ["vertical_gap"]
    if abs(a.bbox.x0 - b.bbox.x0) > cfg.x_tolerance_factor * size:
        return 0.0, ["indent_differs"]

    ta, tb = _lead_text(a), _lead_text(b)
    if re.match(r"^(\d+[.)]|[•●▪\-–*]|\(?[a-zA-Z0-9ivx]+\))\s", tb):
        return 0.0, ["list_marker"]
    score, reasons = 0.4, ["adjacent_same_style_column"]
    if ta[-1] not in TERMINAL:
        score += 0.35
        reasons.append("source_incomplete")
    else:
        score -= 0.2
        reasons.append("source_terminated")
    if tb[:1].islower() or not tb[:1].isalpha():
        score += 0.3 if tb[:1].islower() else 0.0
        if tb[:1].islower():
            reasons.append("next_lowercase_start")
    elif ta[-1] in TERMINAL:
        score -= 0.2
    if len(ta) < 3 * 1 or (len(ta.split()) <= 3 and ta[-1] not in TERMINAL):
        score -= 0.4  # short unpunctuated line looks like a heading/label
        reasons.append("short_label_like")
    return max(0.0, min(1.0, score)), reasons


def build_units(ir: DocumentIR, cfg: GroupingConfig = None) -> List[List[DocumentNode]]:
    """Return runs of nodes (per page, reading order) that form one unit. Singletons included."""
    cfg = cfg or GroupingConfig()
    runs: List[List[DocumentNode]] = []
    for page in ir.pages:
        nodes = sorted(page.nodes, key=lambda n: n.reading_order)
        cur: List[DocumentNode] = []
        for n in nodes:
            if cur and cfg.enabled:
                conf, reasons = continuation_score(cur[-1], n, cfg)
                if conf >= cfg.min_confidence:
                    n.metadata["grouping"] = {"confidence": round(conf, 2), "reasons": reasons}
                    cur.append(n)
                    continue
            if cur:
                runs.append(cur)
            cur = [n]
        if cur:
            runs.append(cur)
    return runs


def union_bbox(nodes: List[DocumentNode]) -> List[float]:
    return [min(n.bbox.x0 for n in nodes), min(n.bbox.y0 for n in nodes),
            max(n.bbox.x1 for n in nodes), max(n.bbox.y1 for n in nodes)]
