import re
import hashlib
from typing import List, Tuple, Dict, Any, Optional
from packages.core.domain.node import DocumentNode, NodeType, NodeStyle, BoundingBox
from packages.providers.base import OCRBlock


class DualExtractionReconciler:
    """
    Reconciles PyMuPDF native digital text extraction with Bodhan OCR extraction
    according to Section 7 and Section 66.2/66.3.
    
    Principles:
    1. Align OCR blocks with native text using normalized text similarity and geometry.
    2. Do not concatenate duplicate OCR and native text. Select a canonical text observation.
    3. Prefer native text for exact character fidelity when geometrically aligned.
    4. Use OCR to detect omissions, raster-only regions, diagrams, and stamps.
    5. When sources disagree on numbers, commands, or protected content, mark RECONCILIATION_CONFLICT.
    6. Retain provenance and alternate observations for auditability.
    """

    @staticmethod
    def _normalize_str(s: str) -> str:
        return re.sub(r"[^\w]", "", s.lower())

    @staticmethod
    def _extract_numbers(s: str) -> List[str]:
        return re.findall(r"\b\d+(?:\.\d+)?\b", s)

    @classmethod
    def _calculate_overlap(cls, box1: BoundingBox, box2: BoundingBox) -> float:
        """Calculates IoU between two bounding boxes."""
        ix0 = max(box1.x0, box2.x0)
        iy0 = max(box1.y0, box2.y0)
        ix1 = min(box1.x1, box2.x1)
        iy1 = min(box1.y1, box2.y1)

        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0

        intersection = (ix1 - ix0) * (iy1 - iy0)
        area1 = max(1.0, (box1.x1 - box1.x0) * (box1.y1 - box1.y0))
        area2 = max(1.0, (box2.x1 - box2.x0) * (box2.y1 - box2.y0))
        union = area1 + area2 - intersection

        return intersection / max(1.0, union)

    @classmethod
    def reconcile_page(
        cls,
        page_id: str,
        page_number: int,
        native_nodes: List[DocumentNode],
        ocr_blocks: List[OCRBlock],
    ) -> List[DocumentNode]:
        reconciled_nodes: List[DocumentNode] = []
        matched_ocr_indices = set()

        # Step 1: Align native nodes with OCR blocks
        for node in native_nodes:
            norm_native = cls._normalize_str(node.source_text)
            best_ocr_idx: Optional[int] = None
            best_score = 0.0

            for idx, ocr_b in enumerate(ocr_blocks):
                norm_ocr = cls._normalize_str(ocr_b.text)
                spatial_iou = cls._calculate_overlap(node.bbox, ocr_b.bbox)

                # Text similarity (simple char overlap ratio)
                text_sim = 0.0
                if norm_native and norm_ocr:
                    if norm_native in norm_ocr or norm_ocr in norm_native:
                        text_sim = min(len(norm_native), len(norm_ocr)) / max(len(norm_native), len(norm_ocr))
                    else:
                        common = set(norm_native) & set(norm_ocr)
                        text_sim = len(common) / max(len(set(norm_native)), len(set(norm_ocr)))

                score = (spatial_iou * 0.5) + (text_sim * 0.5)
                if score > best_score and (spatial_iou > 0.20 or text_sim > 0.50):
                    best_score = score
                    best_ocr_idx = idx

            if best_ocr_idx is not None:
                matched_ocr_indices.add(best_ocr_idx)
                matched_ocr = ocr_blocks[best_ocr_idx]

                # Check for critical number/data conflicts
                native_nums = cls._extract_numbers(node.source_text)
                ocr_nums = cls._extract_numbers(matched_ocr.text)
                
                node.provenance = "reconciled"
                node.ocr_confidence = matched_ocr.confidence
                node.metadata["ocr_alternate_text"] = matched_ocr.text
                node.metadata["alignment_score"] = round(best_score, 3)

                if native_nums != ocr_nums and len(native_nums) > 0 and len(ocr_nums) > 0:
                    node.metadata["reconciliation_warning"] = "RECONCILIATION_CONFLICT: Number mismatch between native and OCR"
                
                reconciled_nodes.append(node)
            else:
                # Native text with no OCR alignment (e.g. OCR missed faint text or tiny font)
                node.provenance = "native_pdf"
                reconciled_nodes.append(node)

        # Step 2: Unmatched OCR blocks (e.g. raster diagrams, scanned annotations, stamps)
        for idx, ocr_b in enumerate(ocr_blocks):
            if idx in matched_ocr_indices:
                continue

            cleaned_text = ocr_b.text.strip()
            if not cleaned_text:
                continue

            # Ingest as new node with ocr provenance
            ocr_node = DocumentNode(
                node_id=f"{page_id}_ocr_{idx}",
                parent_id=page_id,
                page_id=page_id,
                page_number=page_number,
                type=NodeType.PARAGRAPH,
                bbox=ocr_b.bbox,
                reading_order=len(reconciled_nodes),
                style=NodeStyle(font_size=11.0),
                source_text=cleaned_text,
                source_hash=hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest(),
                provenance="ocr",
                ocr_confidence=ocr_b.confidence,
                metadata={
                    "reconciliation_note": "Extracted exclusively by Bodhan OCR (not present in digital text layer)",
                    "ocr_block_type": ocr_b.block_type,
                },
            )
            reconciled_nodes.append(ocr_node)

        # Sort reading order by y0 coordinate
        reconciled_nodes.sort(key=lambda n: (n.bbox.y0, n.bbox.x0))
        for idx, n in enumerate(reconciled_nodes):
            n.reading_order = idx

        return reconciled_nodes
