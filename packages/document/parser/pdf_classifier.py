import fitz  # PyMuPDF
from typing import Tuple


class PDFClassifier:
    @staticmethod
    def classify(pdf_bytes: bytes) -> Tuple[str, int, bool]:
        """
        Classifies PDF into DIGITAL, SCANNED, or MIXED.
        Returns: (classification, total_pages, is_valid)
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)
            if total_pages == 0:
                return "CORRUPT", 0, False

            digital_pages = 0
            scanned_pages = 0

            for page in doc:
                text = page.get_text().strip()
                images = page.get_images()
                
                # Check if page has large background scanned image
                has_large_image = False
                if len(images) > 0:
                    for img in images:
                        for img_r in page.get_image_rects(img[0]):
                            if img_r.width * img_r.height > 0.20 * (page.rect.width * page.rect.height):
                                has_large_image = True
                                break

                if has_large_image:
                    scanned_pages += 1
                elif len(text) > 50:
                    digital_pages += 1
                elif len(images) > 0:
                    scanned_pages += 1
                else:
                    digital_pages += 1  # Blank or vector digital page

            doc.close()

            if scanned_pages == 0:
                classification = "DIGITAL"
            elif digital_pages == 0:
                classification = "SCANNED"
            else:
                classification = "MIXED"

            return classification, total_pages, True
        except Exception:
            return "CORRUPT", 0, False
