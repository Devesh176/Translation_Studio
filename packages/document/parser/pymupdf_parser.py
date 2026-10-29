import hashlib
import itertools
import re
import uuid
import fitz  # PyMuPDF
from typing import List, Optional
from packages.core.domain.node import (
    DocumentIR,
    PageNode,
    DocumentNode,
    NodeType,
    BoundingBox,
    NodeStyle,
    TextSpan,
    TableCellNode,
    TableNode,
    FootnoteNode,
)
from packages.translation.protected_content import is_code_line, is_yaml_line
from packages.core.exceptions import InvalidPDFError
from packages.routing.language import detect_unicode_script, infer_language_from_script


_BULLET_CHARS = {"\u2022", "\u25cf", "\u25aa", "\u25e6", "\u2023", "\uf0b7", "\uf0a7", "-", "\u2013", "*"}
_NUM_MARKER_RE = re.compile(r"^(\d+[.)]|[a-zA-Z][.)]|\([\da-zA-Z]+\))$")
_NUM_PREFIX_RE = re.compile(r"^(\d+[.)]|[a-zA-Z][.)])\s+")


MATH_OPEN, MATH_CLOSE = "\ue000", "\ue001"
MATH_RE = re.compile(MATH_OPEN + r"(\d+)" + MATH_CLOSE)
_MATH_FONT_RE = re.compile(r"^(?:[A-Z]{6}\+)?(?:cmmi|cmsy|cmex|msbm|msam|cmmib|cmbsy|lmmath|stix|cambriamath|cmr[5-9]$|cmbx[5-9]$)", re.I)
_CONNECTOR = set("()[]{}=+-\u2212\u2013\u00d7\u00b7,./|<>:;")


def _is_math_font(font: str) -> bool:
    return bool(_MATH_FONT_RE.match(font or ""))


def _is_connector(sp: dict) -> bool:
    t = sp["text"].strip()
    return len(t) <= 3 and all(ch in _CONNECTOR or ch.isdigit() for ch in t)


def strip_math(text: str) -> str:
    return MATH_RE.sub("", text)


def _fold_math(body: List[dict], counter) -> tuple:
    """Replace runs of math-font spans (plus short connectors between them) with marker tokens."""
    n = len(body)
    ism = [_is_math_font(sp.get("font", "")) for sp in body]
    solid = [ism[i] and body[i]["text"].strip() != "" for i in range(n)]
    parts, regions, i = [], [], 0
    while i < n:
        if not solid[i]:
            parts.append(body[i]["text"])
            i += 1
            continue
        j = i
        k = i + 1
        while k < n:
            if ism[k]:
                if solid[k]:
                    j = k
                k += 1
            elif _is_connector(body[k]) and k + 1 < n and any(solid[m] for m in range(k + 1, min(n, k + 3))):
                k += 1
            else:
                break
        members = body[i:j + 1]
        lead = len(members[0]["text"]) - len(members[0]["text"].lstrip())
        trail = len(members[-1]["text"]) - len(members[-1]["text"].rstrip())
        mb = [sp["bbox"] for sp in members if sp["text"].strip()]
        rid = next(counter)
        big = max(members, key=lambda sp: sp["size"])
        regions.append({"id": rid, "bbox": [min(b[0] for b in mb), min(b[1] for b in mb),
                                            max(b[2] for b in mb), max(b[3] for b in mb)],
                        "baseline": big["origin"][1], "size": big["size"]})
        parts.append(" " * min(lead, 1) + MATH_OPEN + str(rid) + MATH_CLOSE + " " * min(trail, 1))
        i = j + 1
    return "".join(parts), regions


def _rgb(color_int: int):
    return (((color_int >> 16) & 255) / 255.0, ((color_int >> 8) & 255) / 255.0, (color_int & 255) / 255.0)


_FUNC_WORDS = {"Var", "Cov", "rank", "Col", "Row", "dim", "det", "tr", "diag", "exp", "log", "Pr", "Null"}


def _is_display_math(node: DocumentNode) -> bool:
    if node.type not in (NodeType.PARAGRAPH, NodeType.LIST_ITEM):
        return False
    t = strip_math(node.source_text)
    words = [w for w in re.findall(r"[^\W\d_]{2,}", t) if w not in _FUNC_WORDS]
    if words:
        return False
    return bool(node.metadata.get("math_regions")) or bool(re.search(r"[\u0370-\u03ff=\d]", t))


def merge_display_math(nodes: List[DocumentNode], page_node: PageNode) -> List[DocumentNode]:
    out: List[DocumentNode] = []
    run: List[DocumentNode] = []

    def flush():
        if not run:
            return
        regions = [r for n in run for r in n.metadata.get("math_regions", [])]
        b = [n.bbox for n in run]
        first = run[0]
        text = " ".join(n.source_text for n in run)
        md = {"math_block": True, "math_only": True, "line_count": len(run), "math_regions": regions}
        out.append(first.model_copy(update={
            "type": NodeType.PARAGRAPH, "source_text": text,
            "source_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "bbox": BoundingBox(x0=min(x.x0 for x in b), y0=min(x.y0 for x in b),
                                x1=max(x.x1 for x in b), y1=max(x.y1 for x in b)),
            "metadata": md}))
        run.clear()

    for n in nodes:
        if _is_display_math(n):
            if run and n.bbox.y0 - max(x.bbox.y1 for x in run) > 2.0 * max(6.0, n.style.font_size):
                flush()
            run.append(n)
        else:
            flush()
            out.append(n)
    flush()
    for i, n in enumerate(out):
        n.reading_order = i
        n.node_id = f"{page_node.page_id}_n{i}"
    return out


class PyMuPDFParser:
    def __init__(self):
        pass

    @staticmethod
    def _extract_lines(page, counter=None) -> List[dict]:
        """One entry per visual line: raw text (with indentation), body spans, optional list marker."""
        out: List[dict] = []
        pending = None
        counter = counter or itertools.count(1)
        for bi, block in enumerate(page.get_text("dict").get("blocks", [])):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                raw_spans = [sp for sp in line.get("spans", []) if sp.get("text", "") != ""]
                if not "".join(sp["text"] for sp in raw_spans).strip():
                    continue
                marker = None
                marker_bbox = None
                body = list(raw_spans)
                first = body[0]
                ftxt = first["text"].strip()
                if len(body) > 1 and (ftxt in _BULLET_CHARS or "symbol" in first.get("font", "").lower()
                                      or _NUM_MARKER_RE.match(ftxt)) and len(ftxt) <= 4:
                    marker, marker_bbox = ftxt, first["bbox"]
                    body = body[1:]
                raw = "".join(sp["text"] for sp in body)
                if marker is not None and not raw.strip():
                    pending = (marker, marker_bbox)
                    continue
                if marker is None and pending is not None:
                    marker, marker_bbox = pending
                    pending = None
                if marker is None and body:
                    m = _NUM_PREFIX_RE.match(raw.strip())
                    if m and len(body) >= 1 and not _is_math_font(body[0].get("font", "")) and body[0]["text"].strip().startswith(m.group(1)) and len(raw.strip()) > len(m.group(0)):
                        marker = m.group(1)
                        mb = body[0]["bbox"]
                        marker_bbox = mb
                        raw = raw.strip()[len(m.group(0)):]
                        body = [dict(body[0], text=raw, bbox=(mb[0] + 0.0, mb[1], mb[2], mb[3]))] + body[1:]
                bx = [sp["bbox"] for sp in body]
                if not bx:
                    continue
                folded, regions = _fold_math(body, counter)
                if regions:
                    raw = folded
                out.append({
                    "block": bi,
                    "raw": raw,
                    "spans": body,
                    "marker": marker,
                    "marker_bbox": marker_bbox,
                    "math": regions,
                    "bbox": (min(b[0] for b in bx), min(b[1] for b in bx), max(b[2] for b in bx), max(b[3] for b in bx)),
                    "size": max(sp["size"] for sp in ([x for x in body if not _is_math_font(x.get("font", ""))] or body)),
                    "indent": len(raw) - len(raw.lstrip(" ")),
                })
        out.sort(key=lambda l: (round(l["bbox"][1], 0), l["bbox"][0]))
        return out

    @staticmethod
    def _is_mono(line) -> bool:
        return any("mono" in sp.get("font", "").lower() or "consol" in sp.get("font", "").lower()
                   or "courier" in sp.get("font", "").lower() for sp in line["spans"])

    @staticmethod
    def _body_size(lines: List[dict]) -> float:
        """Character-weighted most common font size (the body text size)."""
        w: dict = {}
        for ln in lines:
            if ln.get("marker") is None and PyMuPDFParser._is_mono(ln):
                continue
            w[round(ln["size"], 1)] = w.get(round(ln["size"], 1), 0) + len(ln["raw"].strip())
        return max(w.items(), key=lambda kv: kv[1])[0] if w else 10.0

    @staticmethod
    def _heading_threshold(lines: List[dict], doc_body: float) -> float:
        """Headings are clearly larger than the document's body text; scale-independent (12.5pt floor)."""
        return max(12.5, doc_body * 1.15)

    @staticmethod
    def _same_center(a: dict, b: dict) -> bool:
        ca = (a["bbox"][0] + a["bbox"][2]) / 2
        cb = (b["bbox"][0] + b["bbox"][2]) / 2
        return abs(ca - cb) < b["size"] * 0.5 and abs(a["bbox"][0] - b["bbox"][0]) > b["size"] * 0.5

    @staticmethod
    def _aligned(a: dict, b: dict) -> bool:
        """Different extraction blocks, but tightly stacked and sharing left edge or centre: same paragraph."""
        if b["bbox"][1] - a["bbox"][3] > b["size"] * 0.4 or b["bbox"][1] < a["bbox"][1] + b["size"] * 0.6:
            return False
        if min(a["bbox"][2], b["bbox"][2]) - max(a["bbox"][0], b["bbox"][0]) < 0.3 * (b["bbox"][2] - b["bbox"][0]):
            return False
        return abs(a["bbox"][0] - b["bbox"][0]) < b["size"] * 0.5 or PyMuPDFParser._same_center(a, b)

    def _group_lines(self, lines: List[dict], rect, head_thr: float = 12.5) -> List[dict]:
        groups: List[dict] = []
        prev_code = False
        for ln in lines:
            text = ln["raw"].rstrip()
            is_code = False
            if ln["marker"] is None and self._is_mono(ln):
                if ln["indent"] >= 4 or is_code_line(text):
                    is_code = True
                elif is_yaml_line(text):
                    is_code = True
            prev_code = is_code
            cur = groups[-1] if groups else None
            if is_code:
                if cur and cur["kind"] == "code" and ln["bbox"][1] - cur["lines"][-1]["bbox"][3] < ln["size"] * 1.2:
                    cur["lines"].append(ln)
                else:
                    groups.append({"kind": "code", "lines": [ln]})
                continue
            joinable = (
                cur and cur["kind"] == "text" and ln["marker"] is None and (cur["lines"][-1]["block"] == ln["block"]
                                                                   or self._aligned(cur["lines"][-1], ln))
                and abs(cur["lines"][-1]["size"] - ln["size"]) < 0.5
                and ln["bbox"][1] - cur["lines"][-1]["bbox"][3] < ln["size"] * 0.8
                and (cur["lines"][-1]["bbox"][2] >= cur["bbox_x1"] - ln["size"] * 2.5
                     or self._same_center(cur["lines"][-1], ln))
                and not cur["lines"][-1]["raw"].rstrip().endswith(":")
            )
            if joinable:
                cur["lines"].append(ln)
                cur["bbox_x1"] = max(cur["bbox_x1"], ln["bbox"][2])
            else:
                groups.append({"kind": "text", "lines": [ln], "bbox_x1": ln["bbox"][2]})
        return groups

    def _make_node(self, g: dict, page_node: PageNode, order: int, head_thr: float = 12.5) -> Optional[DocumentNode]:
        lines = g["lines"]
        x0 = min(l["bbox"][0] for l in lines)
        y0 = min(l["bbox"][1] for l in lines)
        x1 = max(l["bbox"][2] for l in lines)
        y1 = max(l["bbox"][3] for l in lines)
        if g["kind"] == "code":
            text = "\n".join(l["raw"].rstrip() for l in lines)
        else:
            text = " ".join(l["raw"].strip() for l in lines).strip()
            text = re.sub(r" {2,}", " ", text)
        if not text.strip():
            return None

        spans: List[TextSpan] = []
        for l in lines:
            for sp in l["spans"]:
                if not sp["text"].strip():
                    continue
                font = sp.get("font", "")
                flags = sp.get("flags", 0)
                bold = bool(flags & 16 or "bold" in font.lower())
                italic = bool(flags & 2 or "italic" in font.lower() or "oblique" in font.lower())
                style = NodeStyle(font_family=font, font_size=sp["size"], font_weight="bold" if bold else "normal",
                                  is_italic=italic, color_rgb=_rgb(sp.get("color", 0)))
                bb = sp["bbox"]
                spans.append(TextSpan(text=sp["text"], bbox=BoundingBox(x0=bb[0], y0=bb[1], x1=bb[2], y1=bb[3]),
                                      style=style, is_bold=bold, is_italic=italic))
        if not spans:
            return None
        main = max(spans, key=lambda s: len(s.text))
        size = max(s.style.font_size for s in spans)
        all_bold = all(s.is_bold for s in spans)
        first_line = lines[0]

        if g["kind"] == "code":
            ntype = NodeType.CODE_BLOCK
        elif first_line["marker"] is not None:
            ntype = NodeType.LIST_ITEM
        elif (size >= head_thr and not (len(lines) >= 2 and len(text) > 60 or len(text) > 160)) or (
                all_bold and len(text) < 120 and not text.endswith(".")):
            ntype = NodeType.HEADING
        elif y0 < page_node.height * 0.06:
            ntype = NodeType.HEADER
        elif y1 > page_node.height * 0.94:
            ntype = NodeType.FOOTNOTE if text[:2].strip().isdigit() and len(text) > 10 else NodeType.FOOTER
        else:
            ntype = NodeType.PARAGRAPH

        math = [r for l in lines for r in l.get("math", [])]
        md = {"line_count": len(lines), "line_height": (y1 - y0) / max(1, len(lines))}
        if len(lines) >= 2 and first_line["marker"] is None:
            cx = [(l["bbox"][0] + l["bbox"][2]) / 2 for l in lines]
            lx = [l["bbox"][0] for l in lines]
            if max(cx) - min(cx) < 0.02 * page_node.width and max(lx) - min(lx) > 0.01 * page_node.width:
                md["centered"] = True
        if first_line["marker"] is not None:
            md["marker"] = first_line["marker"]
            md["marker_bbox"] = list(first_line["marker_bbox"])
        if math:
            md["math_regions"] = math
            if not re.search(r"[^\W\d_]", strip_math(text)):
                md["math_only"] = True
        if g["kind"] == "code":
            md["is_code"] = True
            md["indent"] = first_line["indent"]

        return DocumentNode(
            node_id=f"{page_node.page_id}_n{order}",
            parent_id=page_node.page_id,
            page_id=page_node.page_id,
            page_number=page_node.page_number,
            type=ntype,
            bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
            reading_order=order,
            style=NodeStyle(font_family=main.style.font_family, font_size=size,
                            font_weight="bold" if all_bold else "normal", is_italic=main.is_italic,
                            color_rgb=main.style.color_rgb, line_height=(y1 - y0) / max(1, len(lines))),
            source_text=text,
            source_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            spans=spans,
            metadata=md,
        )

    def parse(self, pdf_bytes: bytes, document_id: Optional[str] = None) -> DocumentIR:
        doc_id = document_id or str(uuid.uuid4())
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise InvalidPDFError(f"Failed to parse PDF bytes: {str(e)}")

        total_pages = len(doc)
        pages: List[PageNode] = []
        all_text_accum = []

        doc_body = self._body_size([ln for pg in doc for ln in self._extract_lines(pg)])
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            rect = page.rect
            page_node = PageNode(
                page_id=f"{doc_id}_p{page_num}",
                page_number=page_num,
                width=rect.width,
                height=rect.height,
                rotation=page.rotation,
            )

            lines = self._extract_lines(page)
            head_thr = self._heading_threshold(lines, doc_body)
            groups = self._group_lines(lines, rect, head_thr)
            reading_order = 0
            for g in groups:
                node = self._make_node(g, page_node, reading_order, head_thr)
                if node is None:
                    continue
                all_text_accum.append(node.source_text)
                page_node.nodes.append(node)
                reading_order += 1

            page_node.nodes = merge_display_math(page_node.nodes, page_node)
            pages.append(page_node)

        doc.close()

        combined_sample = " ".join(all_text_accum[:10])
        script, conf = detect_unicode_script(combined_sample)
        detected_lang = infer_language_from_script(script)

        return DocumentIR(
            document_id=doc_id,
            version_id=str(uuid.uuid4()),
            total_pages=total_pages,
            classification="DIGITAL" if len(all_text_accum) > 0 else "SCANNED",
            source_language=detected_lang,
            pages=pages,
            metadata={"script": script, "script_confidence": conf},
        )
