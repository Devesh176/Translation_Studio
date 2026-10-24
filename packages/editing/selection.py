"""Resolve a user selection (box or highlighted text on a page) to IR nodes / a text span.

The IR is only a server-side lookup index: the user never picks nodes."""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from packages.core.domain.node import DocumentIR, DocumentNode, NodeType
from packages.document.parser.pymupdf_parser import MATH_OPEN, MATH_CLOSE

Rect = Tuple[float, float, float, float]
MIN_NODE_COVERAGE = 0.3   # share of a node covered by the box to count it
MIN_BOX_COVERAGE = 0.5    # or share of the box lying inside a (larger) node


@dataclass
class Span:
    node_id: str
    start: int
    end: int
    text: str


@dataclass
class Resolved:
    kind: str                       # "box" | "text"
    page: int
    nodes: List[DocumentNode] = field(default_factory=list)   # editable nodes
    locked: List[DocumentNode] = field(default_factory=list)  # math/code nodes in the selection
    span: Optional[Span] = None
    context_before: str = ""
    context_after: str = ""
    span_fallback: bool = False
    reason: Optional[str] = None    # set when nothing editable was found

    @property
    def types(self) -> str:
        t = {n.type.value for n in self.nodes} | {("MATH" if n.metadata.get("math_only") else "CODE") for n in self.locked}
        return ", ".join(sorted(t)) or "none"

    @property
    def selected_text(self) -> str:
        if self.span:
            return self.span.text
        return "\n".join(node_text(n) for n in self.nodes)


def node_text(n: DocumentNode) -> str:
    return n.translated_text if n.translated_text is not None else n.source_text


def is_locked(n: DocumentNode) -> bool:
    return n.type == NodeType.CODE_BLOCK or bool(n.metadata.get("is_code")) or bool(n.metadata.get("math_only"))


def _overlap(a: Rect, b: Rect) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _area(r: Rect) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _node_rect(n: DocumentNode) -> Rect:
    return n.bbox.as_tuple()


def _hits(n: DocumentNode, rect: Rect) -> bool:
    ov = _overlap(_node_rect(n), rect)
    if ov <= 0:
        return False
    na, ra = _area(_node_rect(n)), _area(rect)
    return (na > 0 and ov / na >= MIN_NODE_COVERAGE) or (ra > 0 and ov / ra >= MIN_BOX_COVERAGE)


def _norm_index(text: str) -> Tuple[str, List[int]]:
    """Collapse whitespace and drop math markers, keeping a map back to original offsets."""
    out: List[str] = []
    idx: List[int] = []
    in_marker = False
    prev_space = True
    for i, ch in enumerate(text):
        if ch == MATH_OPEN:
            in_marker = True
            continue
        if ch == MATH_CLOSE:
            in_marker = False
            continue
        if in_marker:
            continue
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch)
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def find_quote(text: str, quote: str) -> Optional[Tuple[int, int]]:
    q, _ = _norm_index(quote)
    q = q.strip()
    if not q:
        return None
    hay, idx = _norm_index(text)
    pos = hay.find(q)
    if pos < 0:
        return None
    return idx[pos], idx[pos + len(q) - 1] + 1


def _reading_order(nodes: List[DocumentNode]) -> List[DocumentNode]:
    return sorted(nodes, key=lambda n: (n.reading_order, n.bbox.y0, n.bbox.x0))


def _context(page_nodes: List[DocumentNode], chosen: List[DocumentNode]) -> Tuple[str, str]:
    ordered = _reading_order(page_nodes)
    ids = {n.node_id for n in chosen}
    pos = [i for i, n in enumerate(ordered) if n.node_id in ids]
    if not pos:
        return "", ""
    before = next((node_text(ordered[i]) for i in range(pos[0] - 1, -1, -1) if not ordered[i].metadata.get("math_only")), "")
    after = next((node_text(ordered[i]) for i in range(pos[-1] + 1, len(ordered)) if not ordered[i].metadata.get("math_only")), "")
    return before[-400:], after[:400]


def resolve_selection(ir: DocumentIR, selection: dict) -> Resolved:
    kind = selection["kind"]
    page_no = int(selection["page"])
    page = next((p for p in ir.pages if p.page_number == page_no), None)
    res = Resolved(kind=kind, page=page_no)
    if page is None:
        res.reason = f"Page {page_no} does not exist in this document."
        return res

    if kind == "box":
        rects: List[Rect] = [tuple(selection["rect"])]  # type: ignore[list-item]
    else:
        rects = [tuple(r) for r in (selection.get("rects") or [])]  # type: ignore[misc]

    hit = [n for n in page.nodes if n.source_text.strip() and any(_hits(n, r) for r in rects)]
    hit = _reading_order(hit)

    if kind == "text":
        quote = selection.get("quote") or ""
        pool = hit or page.nodes
        found: List[Tuple[float, DocumentNode, Tuple[int, int]]] = []
        for pass_nodes in (pool, page.nodes):
            for n in pass_nodes:
                if is_locked(n):
                    continue
                m = find_quote(node_text(n), quote)
                if m:
                    score = sum(_overlap(_node_rect(n), r) for r in rects)
                    found.append((score, n, m))
            if found:
                break
        if found:
            _, n, (s, e) = max(found, key=lambda t: t[0])
            res.nodes = [n]
            res.span = Span(n.node_id, s, e, node_text(n)[s:e])
            res.context_before, res.context_after = _context(page.nodes, [n])
            return res
        res.span_fallback = True  # quote not found verbatim: fall back to the overlapped nodes

    res.nodes = [n for n in hit if not is_locked(n)]
    res.locked = [n for n in hit if is_locked(n)]
    if not res.nodes:
        res.reason = (
            "The selection only covers math or code, which is kept as-is." if res.locked
            else "No editable text was found in the selection."
        )
        return res
    res.context_before, res.context_after = _context(page.nodes, res.nodes)
    return res
