import fitz
from typing import Tuple, Optional
from packages.core.domain.node import BoundingBox


class TextRemovalMaskManager:
    """
    Manages safe local text removal masks for scan-preserving overlay mode
    according to Section 66.10:
    - Expands bounding box by configurable padding (mask_padding_pt: 1.5 pt).
    - Constrains mask within page boundaries to protect neighboring borders/margins.
    - Draws clean background-color matched opaque mask.
    """

    @classmethod
    def apply_removal_mask(
        cls,
        page: fitz.Page,
        bbox: BoundingBox,
        padding_pt: float = 1.5,
        fill_color: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> None:
        page_rect = page.rect
        
        # Expand by padding while constraining to page boundaries
        x0 = max(0.0, bbox.x0 - padding_pt)
        y0 = max(0.0, bbox.y0 - padding_pt)
        x1 = min(page_rect.width, bbox.x1 + padding_pt)
        y1 = min(page_rect.height, bbox.y1 + padding_pt)

        mask_rect = fitz.Rect(x0, y0, x1, y1)
        page.draw_rect(mask_rect, color=fill_color, fill=fill_color, overlay=True)
