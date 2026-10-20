import fitz  # PyMuPDF
from packages.core.domain.node import BoundingBox


class OverlayManager:
    @staticmethod
    def apply_background_mask(page: fitz.Page, bbox: BoundingBox, fill_color: tuple = (1, 1, 1)) -> None:
        """
        Draws an opaque white/background rectangle over the original scanned bounding box
        before drawing the translated text to prevent text collisions.
        """
        rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        page.draw_rect(rect, color=fill_color, fill=fill_color, overlay=True)
