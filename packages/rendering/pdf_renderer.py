import html
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import pymupdf

from packages.core.domain.node import DocumentIR, DocumentNode, NodeType
from packages.rendering.layout_engine import LayoutEngine
from packages.rendering.font_registry import FontRegistry
from packages.document.parser.pymupdf_parser import MATH_RE, MATH_OPEN, MATH_CLOSE
from packages.translation.protected_content import PRODUCT_NAMES

MIN_SCALE = 0.9  # plan §66: max ~10% shrink before flagging
PAGE_MARGIN = 28.0
_FONT_DIRS = [
    Path(__file__).resolve().parents[2] / "fonts",
    Path("/app/fonts"),
    Path("./fonts"),
    Path("/usr/share/fonts/truetype/noto"),
]


def _fonts_dir() -> Optional[Path]:
    for d in _FONT_DIRS:
        if (d / "NotoSans-Regular.ttf").is_file():
            return d
    return None


def _script_font_prefix(lang_code: str) -> Optional[str]:
    name = FontRegistry.get_font_for_language(lang_code)
    return None if name.startswith("Helvetica") else name


def _build_css(fonts_dir: Path, lang_code: str) -> str:
    def face(family: str, file: str, weight: str = "normal", style: str = "normal") -> str:
        if not (fonts_dir / file).is_file():
            return ""
        return (f"@font-face{{font-family:{family};font-weight:{weight};font-style:{style};"
                f"src:url({file});}}\n")

    css = (face("lat", "NotoSans-Regular.ttf") + face("lat", "NotoSans-Bold.ttf", "bold")
           + face("lat", "NotoSans-Italic.ttf", "normal", "italic")
           + face("lat", "NotoSans-BoldItalic.ttf", "bold", "italic")
           + face("mono", "NotoSansMono-Regular.ttf") + face("mono", "NotoSansMono-Bold.ttf", "bold"))
    prefix = _script_font_prefix(lang_code)
    if prefix:
        css += face("scr", f"{prefix}-Regular.ttf") + face("scr", f"{prefix}-Bold.ttf", "bold")
    return css


def _hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


_LATIN_RUN_RE = re.compile(r"[\x21-\x7e]+(?: [\x21-\x7e]+)*")


def _escape_with_latin(text: str, split_latin: bool) -> str:
    esc = lambda t: html.escape(t).replace("\n", "<br>")
    if not split_latin:
        return esc(text)
    out, pos = [], 0
    for m in _LATIN_RUN_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        out.append(f'<span class="l">{html.escape(m.group(0))}</span>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def _inline_html(text: str, protected: Dict[str, str], split_latin: bool = False,
                 math_imgs: Optional[Dict[int, str]] = None) -> str:
    """Escape text; render protected code-like tokens in monospace, Latin runs in the Latin font,
    math markers as inline images clipped from the source page."""
    if math_imgs and MATH_OPEN in text:
        out = []
        for i, part in enumerate(MATH_RE.split(text)):
            if i % 2 == 0:
                out.append(_inline_html(part, protected, split_latin) if part else "")
            else:
                out.append(math_imgs.get(int(part), ""))
        return "".join(out)
    codey = sorted({v for v in protected.values() if v not in PRODUCT_NAMES and not v.startswith(("http", "www")) and not re.fullmatch(r"[A-Z]\d{1,2}\.", v)},
                   key=len, reverse=True)
    if not codey:
        return _escape_with_latin(text, split_latin)
    rx = re.compile("(" + "|".join(re.escape(c) for c in codey) + ")")
    out = []
    for part in rx.split(text):
        out.append(f'<span class="m">{html.escape(part)}</span>' if part in codey
                   else _escape_with_latin(part, split_latin))
    return "".join(out)


class PDFRenderer:
    def __init__(self, layout_engine: Optional[LayoutEngine] = None):
        self.layout_engine = layout_engine or LayoutEngine()

    def render_ir_to_pdf(
        self,
        ir: DocumentIR,
        original_pdf_bytes: Optional[bytes] = None,
        is_overlay_mode: bool = False,
    ) -> bytes:
        src = pymupdf.open(stream=original_pdf_bytes, filetype="pdf") if original_pdf_bytes else None
        doc = src if src is not None else pymupdf.open()

        fonts_dir = _fonts_dir()
        target_lang = ir.target_language or "en"
        css = _build_css(fonts_dir, target_lang) if fonts_dir else ""
        archive = pymupdf.Archive(str(fonts_dir)) if fonts_dir else None
        families = "scr, lat" if _script_font_prefix(target_lang) else "lat"
        css += f"\nbody{{font-family:{families};margin:0;}} .m{{font-family:mono, scr, lat;}} .l{{font-family:lat;}}\n"

        for page_node in ir.pages:
            idx = page_node.page_number - 1
            math_imgs: Dict[str, Dict[int, str]] = {}
            if src is not None and idx < len(doc):
                math_imgs = self._clip_math(doc[idx], page_node, archive)
            if src is not None and idx < len(doc):
                page = doc[idx]
                self._clear_source_text(page, page_node.nodes, is_overlay_mode)
            else:
                page = doc.new_page(pno=-1, width=page_node.width, height=page_node.height)

            for node in page_node.nodes:
                self._draw_node(page, page_node, node, css, archive, families, math_imgs.get(node.node_id))

        try:
            doc.subset_fonts()
        except Exception:
            pass
        out = doc.tobytes(garbage=4, deflate=True)
        doc.close()
        return out

    @staticmethod
    def _text_rect(node: DocumentNode) -> pymupdf.Rect:
        b = node.bbox
        ub = (node.metadata.get("stu") or {}).get("union_bbox")
        if ub:
            return pymupdf.Rect(*ub)
        x0 = b.x0
        mb = node.metadata.get("marker_bbox")
        if mb and mb[2] > b.x0 and mb[0] <= b.x0 + 0.5:
            x0 = mb[2] + 4.0
        return pymupdf.Rect(x0, b.y0, b.x1, b.y1)

    @staticmethod
    def _clip_math(page, page_node, archive) -> Dict[str, Dict[int, str]]:
        res: Dict[str, Dict[int, str]] = {}
        if archive is None:
            return res
        for node in page_node.nodes:
            regs = node.metadata.get("math_regions") or []
            if not regs or node.metadata.get("math_only"):
                continue
            d: Dict[int, str] = {}
            for r in regs:
                x0, y0, x1, y1 = r["bbox"]
                clip = pymupdf.Rect(x0 - 0.6, y0 - 0.3, x1 + 0.6, y1 + 0.3) & page.rect
                name = f"m_{page_node.page_number}_{node.node_id}_{r['id']}.png"
                archive.add(page.get_pixmap(clip=clip, dpi=300, alpha=True).tobytes("png"), name)
                drop = max(0.0, clip.y1 - r["baseline"])
                d[r["id"]] = (f'<img src="{name}" width="{clip.width:.2f}" height="{clip.height:.2f}" '
                              f'style="vertical-align:-{drop:.2f}pt">')
            res[node.node_id] = d
        return res

    def _clear_source_text(self, page, nodes: List[DocumentNode], overlay: bool) -> None:
        for node in nodes:
            is_member = (node.metadata.get("stu") or {}).get("role") == "member"
            if not (node.translated_text or "").strip() and not is_member:
                continue
            if node.metadata.get("math_only"):
                continue
            if node.translated_text == node.source_text and node.type == NodeType.CODE_BLOCK:
                continue  # verbatim code stays exactly as authored
            r = self._text_rect(node)
            pad_l = 0.0 if node.metadata.get("marker_bbox") else 0.5
            r = pymupdf.Rect(r.x0 - pad_l, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5)
            mb = node.metadata.get("marker_bbox")
            if mb and node.bbox.y1 > mb[3] + 2.0:
                # wrapped source lines below the marker line sit left of the text rect
                below = pymupdf.Rect(node.bbox.x0 - 0.5, mb[3] - 1.0, r.x0, node.bbox.y1 + 0.5)
                if overlay:
                    page.draw_rect(below, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                else:
                    page.add_redact_annot(below, fill=False)
            if overlay:
                page.draw_rect(r, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
            else:
                page.add_redact_annot(r, fill=False)
        if not overlay:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                  graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                  text=0)

    def _available_rect(self, page_node, node: DocumentNode) -> pymupdf.Rect:
        tr = self._text_rect(node)
        right_edge = max([n.bbox.x1 for n in page_node.nodes] + [tr.x1])
        right_edge = min(right_edge, page_node.width - PAGE_MARGIN)
        x1 = max(tr.x1, right_edge)
        y1_limit = page_node.height - PAGE_MARGIN
        for other in page_node.nodes:
            if other is node or (other.metadata.get("stu") or {}).get("lead_id") == node.node_id:
                continue
            if other.bbox.y0 >= tr.y1 - 1.0 and other.bbox.x0 < x1 and other.bbox.x1 > tr.x0:
                y1_limit = min(y1_limit, other.bbox.y0 - 1.0)
        return pymupdf.Rect(tr.x0, tr.y0, x1, max(tr.y1, y1_limit))

    def _draw_node(self, page, page_node, node: DocumentNode, css: str, archive, families: str, math_imgs=None) -> None:
        if (node.metadata.get("stu") or {}).get("role") == "member":
            return
        text = node.translated_text or node.source_text
        if not text.strip():
            return
        if node.metadata.get("math_only") or (node.type == NodeType.CODE_BLOCK and text == node.source_text):
            return  # untouched original code stays on the page

        st = node.style
        size = max(6.0, st.font_size)
        weight = "bold" if st.font_weight == "bold" else "normal"
        italic = "italic" if st.is_italic else "normal"
        color = _hex(st.color_rgb)
        line_h = 1.25
        centered = (
            node.type != NodeType.LIST_ITEM
            and abs((node.bbox.x0 + node.bbox.x1) / 2 - page_node.width / 2) < 6.0
            and node.bbox.x0 > 60
            and node.type == NodeType.HEADING
        )

        rect = self._available_rect(page_node, node)
        if centered:
            half = max(node.bbox.width / 2, min(page_node.width / 2 - PAGE_MARGIN - 20, 260))
            rect = pymupdf.Rect(page_node.width / 2 - half, rect.y0, page_node.width / 2 + half, rect.y1)

        body = _inline_html(text, node.metadata.get("protected_tokens", {}), split_latin="scr" in families,
                            math_imgs=math_imgs)
        is_code = node.type == NodeType.CODE_BLOCK
        fam = "font-family:mono, scr, lat;white-space:pre-wrap;" if is_code else ""
        align = "center" if centered else "left"
        html_text = (f'<div style="font-size:{size}pt;font-weight:{weight};font-style:{italic};color:{color};'
                     f'line-height:{line_h};text-align:{align};{fam}">{body}</div>')

        scratch = pymupdf.open()
        probe_page = scratch.new_page(width=page_node.width, height=page_node.height)
        spare, scale = probe_page.insert_htmlbox(rect, html_text, css=css, archive=archive, scale_low=MIN_SCALE)
        scratch.close()

        if spare >= 0:
            page.insert_htmlbox(rect, html_text, css=css, archive=archive, scale_low=MIN_SCALE)
            node.metadata["render_scale"] = round(scale, 3)
            node.render_status = "OK" if scale >= 0.999 else "SHRUNK"
        else:
            spare, scale = page.insert_htmlbox(rect, html_text, css=css, archive=archive, scale_low=0)
            node.metadata["render_scale"] = round(scale, 3)
            node.render_status = "SHRUNK_BELOW_FLOOR" if spare >= 0 else "OVERFLOW"
