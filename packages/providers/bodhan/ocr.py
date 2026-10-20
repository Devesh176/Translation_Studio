import json
from typing import Optional, List
from packages.core.domain.node import BoundingBox
from packages.providers.base import OCRProvider, OCRResult, OCRBlock
from packages.providers.bodhan.client import BodhanClient


class BodhanOCRProvider(OCRProvider):
    def __init__(self, client: Optional[BodhanClient] = None):
        self.client = client or BodhanClient()

    async def extract_page(
        self,
        image_bytes: bytes,
        *,
        page_number: int,
        document_id: str,
        language_hint: Optional[str] = "hi",
    ) -> OCRResult:
        res = await self.client.ocr(image_bytes, language=language_hint or "hi")
        
        blocks: List[OCRBlock] = []
        raw_text = res.get("text", "")
        raw_blocks = res.get("blocks", [])

        if raw_blocks:
            for b in raw_blocks:
                bbox_coords = b.get("bbox", [50.0, 50.0, 500.0, 100.0])
                bbox = BoundingBox(
                    x0=float(bbox_coords[0]),
                    y0=float(bbox_coords[1]),
                    x1=float(bbox_coords[2]),
                    y1=float(bbox_coords[3]),
                )
                blocks.append(
                    OCRBlock(
                        text=b.get("text", ""),
                        bbox=bbox,
                        confidence=float(b.get("confidence", 0.98)),
                        block_type=b.get("type", "paragraph"),
                    )
                )
        else:
            # Parse text lines and construct layout blocks
            lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
            curr_y = 50.0
            line_height = 24.0
            for line in lines:
                bbox = BoundingBox(
                    x0=50.0,
                    y0=curr_y,
                    x1=545.0,
                    y1=curr_y + line_height,
                )
                blocks.append(
                    OCRBlock(
                        text=line,
                        bbox=bbox,
                        confidence=float(res.get("confidence", 0.98)),
                        block_type="paragraph",
                    )
                )
                curr_y += line_height + 6.0

        return OCRResult(
            page_number=page_number,
            text=raw_text,
            blocks=blocks,
            language=res.get("language", language_hint),
            confidence=float(res.get("confidence", 0.98)),
            provider="bodhan",
            provider_request_id=res.get("request_id"),
            raw_payload=res,
        )
