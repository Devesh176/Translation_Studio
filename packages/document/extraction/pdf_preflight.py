import fitz  # PyMuPDF
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import uuid


class PagePreflightRecord(BaseModel):
    page_number: int
    width: float
    height: float
    rotation: float
    embedded_fonts: List[str] = Field(default_factory=list)
    has_text: bool = False
    has_images: bool = False
    is_scanned: bool = False
    text_density: float = 0.0  # chars per square point
    image_coverage: float = 0.0  # ratio 0.0 to 1.0
    text_block_count: int = 0
    classification: str = "DIGITAL_TEXT"  # DIGITAL_TEXT, SCANNED_IMAGE, MIXED, IMAGE_HEAVY, TEXT_HEAVY
    annotations_count: int = 0


class PDFPreflightReport(BaseModel):
    preflight_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    page_count: int = 0
    is_encrypted: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    all_fonts: List[str] = Field(default_factory=list)
    pages: List[PagePreflightRecord] = Field(default_factory=list)
    overall_classification: str = "DIGITAL"  # DIGITAL, SCANNED, MIXED, IMAGE_HEAVY
    is_valid_for_processing: bool = True
    error_message: Optional[str] = None


class PDFPreflightInspector:
    """
    Implements PDF Preflight Inspection according to Section 4.1 of Modification V2.
    Collects page dimensions, rotation, metadata, embedded fonts, text/image density,
    and classifies pages prior to extraction.
    """

    @classmethod
    def inspect(cls, pdf_bytes: bytes) -> PDFPreflightReport:
        report = PDFPreflightReport()
        if not pdf_bytes:
            report.is_valid_for_processing = False
            report.error_message = "Empty PDF stream provided."
            return report

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            report.is_valid_for_processing = False
            report.error_message = f"Failed to open PDF document: {str(e)}"
            return report

        try:
            report.page_count = len(doc)
            report.is_encrypted = doc.is_encrypted
            report.metadata = doc.metadata or {}

            all_fonts_set = set()
            scanned_pages = 0
            digital_pages = 0

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_rect = page.rect
                page_area = max(1.0, page_rect.width * page_rect.height)

                # Extract fonts on page
                page_fonts = []
                try:
                    for f in page.get_fonts():
                        font_name = f[3] if len(f) > 3 else f[0]
                        page_fonts.append(font_name)
                        all_fonts_set.add(font_name)
                except Exception:
                    pass

                text = page.get_text()
                char_count = len(text.strip())
                text_density = round(char_count / page_area, 5)

                images = page.get_images()
                image_count = len(images)
                image_area = 0.0
                for img in images:
                    try:
                        rects = page.get_image_rects(img[0])
                        for r in rects:
                            image_area += max(0.0, r.width * r.height)
                    except Exception:
                        pass
                image_coverage = round(min(1.0, image_area / page_area), 3)

                # Text blocks
                blocks = page.get_text("blocks")
                text_block_count = sum(1 for b in blocks if b[4].strip())

                # Classify page
                is_scanned = (char_count < 20 and (image_count > 0 or image_coverage > 0.40))
                classification = "DIGITAL_TEXT"
                if is_scanned:
                    classification = "SCANNED_IMAGE"
                    scanned_pages += 1
                elif image_coverage > 0.50:
                    classification = "IMAGE_HEAVY"
                elif text_density > 0.003:
                    classification = "TEXT_HEAVY"
                    digital_pages += 1
                elif char_count > 0 and image_count > 0:
                    classification = "MIXED"
                else:
                    digital_pages += 1

                page_record = PagePreflightRecord(
                    page_number=page_idx + 1,
                    width=page_rect.width,
                    height=page_rect.height,
                    rotation=page.rotation,
                    embedded_fonts=page_fonts,
                    has_text=char_count > 0,
                    has_images=image_count > 0,
                    is_scanned=is_scanned,
                    text_density=text_density,
                    image_coverage=image_coverage,
                    text_block_count=text_block_count,
                    classification=classification,
                    annotations_count=len(list(page.annots() or [])),
                )
                report.pages.append(page_record)

            report.all_fonts = sorted(list(all_fonts_set))

            # Overall classification
            if scanned_pages == report.page_count:
                report.overall_classification = "SCANNED"
            elif scanned_pages > 0:
                report.overall_classification = "MIXED"
            else:
                report.overall_classification = "DIGITAL"

        finally:
            doc.close()

        return report
