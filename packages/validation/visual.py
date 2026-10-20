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

        # 2. Check for unexpected blank pages and missing glyphs
        total_expected_chars = 0
        total_rendered_chars = 0
        expected_indic_chars = 0
        rendered_indic_chars = 0

        for page_idx, page_node in enumerate(ir.pages):
            expected_text = " ".join([n.translated_text or n.source_text for n in page_node.nodes if (n.translated_text or n.source_text).strip()])
            if not expected_text:
                continue

            page_expected_chars = len(expected_text.replace(" ", ""))
            total_expected_chars += page_expected_chars

            # Count expected non-Latin / Indic characters
            for ch in expected_text:
                if ord(ch) > 255:
                    expected_indic_chars += 1

            if page_idx < rendered_pages:
                rendered_page_text = doc[page_idx].get_text().strip()
                page_rendered_chars = len(rendered_page_text.replace(" ", ""))
                total_rendered_chars += page_rendered_chars

                for ch in rendered_page_text:
                    if ord(ch) > 255:
                        rendered_indic_chars += 1

                # Check blank page
                if page_expected_chars > 20 and page_rendered_chars == 0:
                    errors.append(f"Page {page_idx + 1} is unexpectedly blank in rendered PDF.")

        doc.close()

        # 3. Missing glyph detection
        glyph_score = 1.0
        if expected_indic_chars > 0:
            glyph_retention = rendered_indic_chars / max(1, expected_indic_chars)
            if glyph_retention < 0.60:
                errors.append(
                    f"MISSING_GLYPHS: Rendered PDF retained only {glyph_retention * 100:.1f}% "
                    f"of Indic glyphs ({rendered_indic_chars}/{expected_indic_chars}). "
                    "Font rendering failed to output target script characters."
                )
                glyph_score = max(0.0, glyph_retention)
            else:
                glyph_score = min(1.0, glyph_retention)

        # Composite QA Score
        final_qa_score = round(min(boundary_score, glyph_score), 2)
        is_valid = len(errors) == 0 and final_qa_score >= 0.80

        return is_valid, errors, final_qa_score
