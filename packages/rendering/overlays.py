import fitz  # PyMuPDF
from packages.core.domain.node import BoundingBox


from packages.document.scanning.text_removal_mask import TextRemovalMaskManager


class OverlayManager:
    @staticmethod
    def apply_background_mask(page: fitz.Page, bbox: BoundingBox, fill_color: tuple = (1, 1, 1), padding_pt: float = 1.5) -> None:
        """
        Draws an opaque background rectangle with configurable padding (Section 66.10)
        over the original text bounding box before drawing translated text.
        """
        TextRemovalMaskManager.apply_removal_mask(page, bbox, padding_pt=padding_pt, fill_color=fill_color)
