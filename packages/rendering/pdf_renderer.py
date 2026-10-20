import os
import fitz  # PyMuPDF
from typing import Optional, Dict, List, Tuple
from packages.core.domain.node import DocumentIR, DocumentNode
from packages.rendering.layout_engine import LayoutEngine
from packages.rendering.font_registry import FontRegistry
from packages.rendering.overlays import OverlayManager


_FONT_FILE_CACHE: Dict[str, Optional[str]] = {}
_LATIN_FONT_FILE_CACHE: Optional[str] = None


def _find_font_file(lang_code: str) -> Optional[str]:
    """Find a system or local font file for the given language code."""
    if lang_code in _FONT_FILE_CACHE:
        return _FONT_FILE_CACHE[lang_code]

    noto_name = FontRegistry.get_font_for_language(lang_code)

    font_search_dirs = [
        "/app/fonts",
        "./fonts",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
    ]

    # Map FontRegistry names -> specific script font filename hints (DO NOT include generic NotoSans)
    noto_file_hints: dict[str, list[str]] = {
        "NotoSansDevanagari": ["NotoSansDevanagari-Regular", "NotoSansDevanagari", "NotoSerifDevanagari", "Devanagari"],
        "NotoSansTamil": ["NotoSansTamil-Regular", "NotoSansTamil", "NotoSerifTamil", "Tamil"],
        "NotoSansTelugu": ["NotoSansTelugu-Regular", "NotoSansTelugu", "NotoSerifTelugu", "Telugu"],
        "NotoSansKannada": ["NotoSansKannada-Regular", "NotoSansKannada", "NotoSerifKannada", "Kannada"],
        "NotoSansMalayalam": ["NotoSansMalayalam-Regular", "NotoSansMalayalam", "NotoSerifMalayalam", "Malayalam"],
        "NotoSansBengali": ["NotoSansBengali-Regular", "NotoSansBengali", "NotoSerifBengali", "Bengali"],
        "NotoSansGujarati": ["NotoSansGujarati-Regular", "NotoSansGujarati", "NotoSerifGujarati", "Gujarati"],
        "NotoSansGurmukhi": ["NotoSansGurmukhi-Regular", "NotoSansGurmukhi", "NotoSerifGurmukhi", "Gurmukhi"],
    }

    hints = noto_file_hints.get(noto_name, [noto_name])
    found_file: Optional[str] = None

    for search_dir in font_search_dirs:
        if not os.path.isdir(search_dir):
            continue
        try:
            for root, _, files in os.walk(search_dir):
                for hint in hints:
                    for fname in files:
                        if not fname.endswith((".ttf", ".otf")):
                            continue
                        if hint.lower() in fname.lower():
                            found_file = os.path.join(root, fname)
                            break
                    if found_file:
                        break
                if found_file:
                    break
        except Exception:
            continue
        if found_file:
            break

    _FONT_FILE_CACHE[lang_code] = found_file
    return found_file


def _find_latin_font_file() -> Optional[str]:
    """Find a Latin/English font file for rendering ASCII and mixed script tokens."""
    global _LATIN_FONT_FILE_CACHE
    if _LATIN_FONT_FILE_CACHE is not None:
        return _LATIN_FONT_FILE_CACHE

    font_search_dirs = [
        "/app/fonts",
        "./fonts",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]

    for search_dir in font_search_dirs:
        if not os.path.isdir(search_dir):
            continue
        try:
            for root, _, files in os.walk(search_dir):
                for fname in files:
                    if fname.lower() in ("notosans-regular.ttf", "notosans-regular.otf", "arial.ttf", "helvetica.ttf"):
                        _LATIN_FONT_FILE_CACHE = os.path.join(root, fname)
                        return _LATIN_FONT_FILE_CACHE
        except Exception:
            continue

    return None


from packages.rendering.script_segmenter import segment_script_runs


def split_text_runs(text: str, primary_font: Optional[fitz.Font], fallback_font: Optional[fitz.Font]) -> List[Tuple[str, bool]]:
    """
    Grapheme-safe script run segmentation conforming to Section 66.9.
    Ensures combining marks, viramas, and matras remain bound to base characters,
    preventing broken Indic shaping.
    """
    return segment_script_runs(text, primary_font, fallback_font)


class PDFRenderer:
    def __init__(self, layout_engine: Optional[LayoutEngine] = None):
        self.layout_engine = layout_engine or LayoutEngine()

    def render_ir_to_pdf(
        self,
        ir: DocumentIR,
        original_pdf_bytes: Optional[bytes] = None,
        is_overlay_mode: bool = False,
    ) -> bytes:
        if original_pdf_bytes and is_overlay_mode:
            doc = fitz.open(stream=original_pdf_bytes, filetype="pdf")
        else:
            doc = fitz.open()

        target_lang = ir.target_language or "en"
        primary_font_path = _find_font_file(target_lang)
        latin_font_path = _find_latin_font_file()

        primary_font_obj: Optional[fitz.Font] = None
        fallback_font_obj: Optional[fitz.Font] = None

        if primary_font_path:
            try:
                primary_font_obj = fitz.Font(fontfile=primary_font_path)
            except Exception:
                primary_font_obj = None

        if latin_font_path:
            try:
                fallback_font_obj = fitz.Font(fontfile=latin_font_path)
            except Exception:
                fallback_font_obj = None

        for page_node in ir.pages:
            if is_overlay_mode and original_pdf_bytes:
                # 0-indexed page lookup
                page = doc[page_node.page_number - 1]
            else:
                page = doc.new_page(
                    pno=-1,
                    width=page_node.width,
                    height=page_node.height,
                )

            # Register fonts on this page
            primary_font_tag: Optional[str] = None
            latin_font_tag: Optional[str] = None

            if primary_font_path:
                tag = f"f_{target_lang}"
                try:
                    page.insert_font(fontname=tag, fontfile=primary_font_path, set_simple=False)
                    primary_font_tag = tag
                except Exception:
                    primary_font_tag = None

            if latin_font_path:
                tag_lat = "f_latin"
                try:
                    page.insert_font(fontname=tag_lat, fontfile=latin_font_path, set_simple=False)
                    latin_font_tag = tag_lat
                except Exception:
                    latin_font_tag = None

            for node in page_node.nodes:
                text = node.translated_text or node.source_text
                if not text.strip():
                    continue

                fitted_font_size, lines, needs_reflow = self.layout_engine.compute_layout_for_node(node)

                # If overlay mode on scanned/mixed PDF, mask background
                if is_overlay_mode:
                    OverlayManager.apply_background_mask(page, node.bbox)

                # Render text lines at precise geometry
                line_height = fitted_font_size * 1.25
                curr_y = node.bbox.y0 + fitted_font_size

                for line in lines:
                    if curr_y > node.bbox.y1 + 10.0:
                        break

                    # Split line into script runs for mixed content
                    runs = split_text_runs(line, primary_font_obj, fallback_font_obj)
                    curr_x = node.bbox.x0

                    for run_text, use_primary in runs:
                        fn = primary_font_tag if (use_primary and primary_font_tag) else latin_font_tag
                        font_for_len = primary_font_obj if (use_primary and primary_font_obj) else fallback_font_obj

                        point = fitz.Point(curr_x, curr_y)
                        try:
                            if fn:
                                page.insert_text(
                                    point,
                                    run_text,
                                    fontname=fn,
                                    fontsize=fitted_font_size,
                                    color=node.style.color_rgb,
                                )
                            else:
                                page.insert_text(
                                    point,
                                    run_text,
                                    fontsize=fitted_font_size,
                                    color=node.style.color_rgb,
                                )
                        except Exception:
                            page.insert_text(
                                point,
                                run_text,
                                fontsize=fitted_font_size,
                                color=node.style.color_rgb,
                            )

                        # Advance curr_x
                        if font_for_len:
                            try:
                                curr_x += font_for_len.text_length(run_text, fontsize=fitted_font_size)
                            except Exception:
                                curr_x += len(run_text) * fitted_font_size * 0.55
                        else:
                            curr_x += len(run_text) * fitted_font_size * 0.55

                    curr_y += line_height

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
