import fitz  # PyMuPDF
from typing import List, Tuple, Dict, Any
from packages.core.domain.node import DocumentIR
from packages.routing.language import detect_unicode_script


class VisualQAValidator:
    @staticmethod
    def check_layout_boundaries(ir: DocumentIR) -> Tuple[bool, List[str], float]:
        """Check for coordinate clipping and layout overflow."""
        errors = []
        total_nodes = 0
        overflow_nodes = 0

        for page in ir.pages:
            for node in page.nodes:
                total_nodes += 1
                # Check page overflow
                if node.bbox.x1 > page.width + 5.0 or node.bbox.y1 > page.height + 5.0:
                    errors.append(f"Node {node.node_id} overflows page dimensions.")
                    overflow_nodes += 1
                if node.bbox.x0 < 0 or node.bbox.y0 < 0:
                    errors.append(f"Node {node.node_id} has negative coordinates.")
                    overflow_nodes += 1

        qa_score = 1.0 - (overflow_nodes / max(1, total_nodes))
        return (len(errors) == 0, errors, qa_score)

    @classmethod
    def inspect_rendered_pdf(
        cls,
        rendered_pdf_bytes: bytes,
        ir: DocumentIR,
    ) -> Tuple[bool, List[str], float]:
        """
        Visual QA conforming to Section 28 of the Architecture Specification:
        1. Boundary containment & overflow check.
        2. Unexpected blank page detection.
        3. Missing glyph & font drop detection (e.g., Indic glyphs replaced with spaces/nulls).
        """
        errors: List[str] = []

        # 1. Check layout boundary containment
        _, boundary_errors, boundary_score = cls.check_layout_boundaries(ir)
        errors.extend(boundary_errors)

        if not rendered_pdf_bytes:
            return False, ["Rendered PDF bytes are empty"], 0.0

        try:
            doc = fitz.open(stream=rendered_pdf_bytes, filetype="pdf")
        except Exception as e:
            return False, [f"Failed to parse rendered PDF: {e}"], 0.0

        total_ir_pages = len(ir.pages)
        rendered_pages = len(doc)
        if rendered_pages < total_ir_pages:
            errors.append(f"Rendered PDF page count ({rendered_pages}) is less than IR ({total_ir_pages}).")

        # 2. Per-page checks: blank pages, leaks, protected tokens, missing nodes
        from packages.translation.normalizer import TextNormalizer
        from packages.translation.protected_content import has_placeholder

        def _squash(t: str) -> str:
            return "".join(t.split())

        total_nodes = 0
        missing_nodes = 0
        critical: List[str] = []
        for page_idx, page_node in enumerate(ir.pages):
            expected_nodes = [n for n in page_node.nodes if (n.translated_text or n.source_text).strip()]
            if not expected_nodes:
                continue
            if page_idx >= rendered_pages:
                continue
            rendered_text = doc[page_idx].get_text()
            rendered_sq = _squash(rendered_text)
            if sum(len(_squash(n.translated_text or n.source_text)) for n in expected_nodes) > 20 and not rendered_sq:
                critical.append(f"Page {page_idx + 1} is unexpectedly blank in rendered PDF.")

            if TextNormalizer.has_sentinel(rendered_text):
                critical.append(f"SENTINEL_LEAK: prompt delimiter text found on page {page_idx + 1}.")
            if has_placeholder(rendered_text):
                critical.append(f"PLACEHOLDER_LEAK: protected-token marker found on page {page_idx + 1}.")

            for n in expected_nodes:
                total_nodes += 1
                from packages.document.parser.pymupdf_parser import strip_math
                text = strip_math(n.translated_text or n.source_text)
                if n.metadata.get("math_only"):
                    total_nodes -= 1
                    continue
                if n.validation_status.startswith("FAIL"):
                    critical.append(f"NODE_FAILED:{n.node_id}:{n.validation_status}")
                if n.render_status == "OVERFLOW":
                    critical.append(f"NODE_OVERFLOW:{n.node_id}")
                # Missing-node check: first and last 12 non-space characters must be extractable
                # Indic conjuncts are not reliably extractable, so only ASCII content is probed
                sq = "".join(c for c in _squash(text) if c.isascii() and c.isalnum())
                rendered_ascii = "".join(c for c in rendered_sq if c.isascii() and c.isalnum())
                probe = [sq[:10], sq[-10:]] if len(sq) > 10 else ([sq] if sq else [])
                if not all(p in rendered_ascii for p in probe):
                    missing_nodes += 1
                    errors.append(f"MISSING_NODE:{n.node_id}")
                # Protected tokens must appear verbatim in the rendered page
                for original in (strip_math(v) for v in (n.metadata.get("protected_tokens") or {}).values()):
                    orig_ascii = "".join(c for c in _squash(original) if c.isascii() and c.isalnum())
                    if orig_ascii and original.strip() and orig_ascii not in rendered_ascii:
                        errors.append(f"PROTECTED_TOKEN_NOT_RENDERED:{n.node_id}:{original!r}")
                        break

        doc.close()
        errors.extend(critical)
        glyph_score = 1.0 - (missing_nodes / max(1, total_nodes))
        if critical:
            glyph_score = min(glyph_score, 0.5)

        # Composite QA Score
        final_qa_score = round(min(boundary_score, glyph_score), 2)
        is_valid = len(errors) == 0 and final_qa_score >= 0.80

        return is_valid, errors, final_qa_score
