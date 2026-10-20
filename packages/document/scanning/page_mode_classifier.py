from typing import Tuple, Dict, Any, List
import fitz
from packages.core.domain.node import PageProcessingMode


class PageModeClassifier:
    """
    Classifies the processing mode per page according to Section 66.1:
    - DIGITAL_TEXT: Selectable text and reliable geometry.
    - SCANNED_IMAGE: Page content is primarily raster; no reliable text layer.
    - MIXED: Native text plus scanned/image regions.
    - DIGITAL_UNTRUSTED: Text layer exists but is sparse, corrupt, duplicated, or misaligned.
    """

    @classmethod
    def classify_page(
        cls,
        page: fitz.Page,
        min_chars: int = 20,
    ) -> Tuple[PageProcessingMode, float, Dict[str, Any]]:
        text = page.get_text().strip()
        char_count = len(text)
        image_list = page.get_images()
        image_count = len(image_list)
        drawings = page.get_drawings()
        drawing_count = len(drawings)
        
        # Calculate coverage of images
        page_rect = page.rect
        page_area = max(1.0, page_rect.width * page_rect.height)
        
        image_area = 0.0
        for img in image_list:
            try:
                # img[0] is xref
                img_rects = page.get_image_rects(img[0])
                for r in img_rects:
                    image_area += max(0.0, r.width * r.height)
            except Exception:
                pass
        
        image_coverage = min(1.0, image_area / page_area)
        
        # Check for corrupt or replacement characters
        corrupt_chars = text.count("\ufffd") + text.count("\x00")
        is_corrupt = (char_count > 0 and (corrupt_chars / char_count) > 0.15)
        
        evidence: Dict[str, Any] = {
            "char_count": char_count,
            "image_count": image_count,
            "drawing_count": drawing_count,
            "image_coverage": round(image_coverage, 3),
            "corrupt_chars": corrupt_chars,
        }
        
        if is_corrupt:
            evidence["reason"] = "High percentage of replacement or null characters in text layer"
            return PageProcessingMode.DIGITAL_UNTRUSTED, 0.90, evidence
            
        if char_count < min_chars and (image_count > 0 or image_coverage > 0.40):
            evidence["reason"] = "Sparse or zero selectable text with raster image presence"
            return PageProcessingMode.SCANNED_IMAGE, 0.95, evidence
            
        if char_count < min_chars and image_count == 0:
            evidence["reason"] = "Very low character count, treated as scanned or empty"
            return PageProcessingMode.SCANNED_IMAGE, 0.80, evidence
            
        if char_count >= min_chars and (image_count > 0 or image_coverage > 0.15 or drawing_count > 10):
            evidence["reason"] = "Native text alongside significant raster or vector regions"
            return PageProcessingMode.MIXED, 0.88, evidence
            
        evidence["reason"] = "Clean selectable text layer without dominant raster imagery"
        return PageProcessingMode.DIGITAL_TEXT, 0.95, evidence
