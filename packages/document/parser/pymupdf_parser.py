import hashlib
import uuid
import fitz  # PyMuPDF
from typing import List, Optional
from packages.core.domain.node import (
    DocumentIR,
    PageNode,
    DocumentNode,
    NodeType,
    BoundingBox,
    NodeStyle,
    TextSpan,
    TableCellNode,
    TableNode,
    FootnoteNode,
)
from packages.core.exceptions import InvalidPDFError
from packages.routing.language import detect_unicode_script, infer_language_from_script


class PyMuPDFParser:
    def __init__(self):
        pass

    def parse(self, pdf_bytes: bytes, document_id: Optional[str] = None) -> DocumentIR:
        doc_id = document_id or str(uuid.uuid4())
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise InvalidPDFError(f"Failed to parse PDF bytes: {str(e)}")

        total_pages = len(doc)
        pages: List[PageNode] = []
        all_text_accum = []

        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            rect = page.rect
            page_node = PageNode(
                page_id=f"{doc_id}_p{page_num}",
                page_number=page_num,
                width=rect.width,
                height=rect.height,
                rotation=page.rotation,
            )

            # Extract structured text blocks with span detail
            page_dict = page.get_text("dict")
            reading_order = 0

            # Sort blocks primarily by y0, then x0 for multi-column heuristic
            blocks = page_dict.get("blocks", [])
            # Filter text blocks (type 0)
            text_blocks = [b for b in blocks if b.get("type") == 0]
            # Multi-column sort: if page has distinct column split
            text_blocks.sort(key=lambda b: (round(b["bbox"][1] / 20) * 20, b["bbox"][0]))

            for block in text_blocks:
                bbox_raw = block.get("bbox", [0, 0, 0, 0])
                bbox = BoundingBox(
                    x0=bbox_raw[0],
                    y0=bbox_raw[1],
                    x1=bbox_raw[2],
                    y1=bbox_raw[3],
                )

                spans_list: List[TextSpan] = []
                full_block_text_parts = []
                max_font_size = 11.0
                is_bold_block = False

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        if not span_text.strip():
                            continue
                        full_block_text_parts.append(span_text)
                        
                        f_size = span.get("size", 11.0)
                        if f_size > max_font_size:
                            max_font_size = f_size
                        
                        flags = span.get("flags", 0)
                        # PyMuPDF flags: 2 is bold, 1 is italic
                        is_bold = bool(flags & 2 or "bold" in span.get("font", "").lower())
                        is_italic = bool(flags & 1 or "italic" in span.get("font", "").lower())
                        if is_bold:
                            is_bold_block = True

                        s_bbox_raw = span.get("bbox", [0, 0, 0, 0])
                        s_bbox = BoundingBox(
                            x0=s_bbox_raw[0],
                            y0=s_bbox_raw[1],
                            x1=s_bbox_raw[2],
                            y1=s_bbox_raw[3],
                        )

                        color_int = span.get("color", 0)
                        r = ((color_int >> 16) & 255) / 255.0
                        g = ((color_int >> 8) & 255) / 255.0
                        b = (color_int & 255) / 255.0

                        span_style = NodeStyle(
                            font_family=span.get("font", "NotoSans-Regular"),
                            font_size=f_size,
                            font_weight="bold" if is_bold else "normal",
                            is_italic=is_italic,
                            color_rgb=(r, g, b),
                        )

                        spans_list.append(
                            TextSpan(
                                text=span_text,
                                bbox=s_bbox,
                                style=span_style,
                                is_bold=is_bold,
                                is_italic=is_italic,
                            )
                        )

                block_text = " ".join(full_block_text_parts).strip()
                if not block_text:
                    continue

                all_text_accum.append(block_text)

                # Classify node type
                node_type = NodeType.PARAGRAPH
                if max_font_size >= 14.0 or (is_bold_block and len(block_text) < 120 and not block_text.endswith(".")):
                    node_type = NodeType.HEADING
                elif bbox.y0 < 50.0:
                    node_type = NodeType.HEADER
                elif bbox.y1 > (rect.height - 50.0):
                    # Check if footnote or footer
                    if block_text[0:2].strip().isdigit() and len(block_text) > 10:
                        node_type = NodeType.FOOTNOTE
                    else:
                        node_type = NodeType.FOOTER

                source_hash = hashlib.sha256(block_text.encode("utf-8")).hexdigest()
                node_style = NodeStyle(
                    font_size=max_font_size,
                    font_weight="bold" if is_bold_block else "normal",
                )

                doc_node = DocumentNode(
                    node_id=f"{page_node.page_id}_n{reading_order}",
                    parent_id=page_node.page_id,
                    page_id=page_node.page_id,
                    page_number=page_num,
                    type=node_type,
                    bbox=bbox,
                    reading_order=reading_order,
                    style=node_style,
                    source_text=block_text,
                    source_hash=source_hash,
                    spans=spans_list,
                )
                page_node.nodes.append(doc_node)
                reading_order += 1

            pages.append(page_node)

        doc.close()

        combined_sample = " ".join(all_text_accum[:10])
        script, conf = detect_unicode_script(combined_sample)
        detected_lang = infer_language_from_script(script)

        return DocumentIR(
            document_id=doc_id,
            version_id=str(uuid.uuid4()),
            total_pages=total_pages,
            classification="DIGITAL" if len(all_text_accum) > 0 else "SCANNED",
            source_language=detected_lang,
            pages=pages,
            metadata={"script": script, "script_confidence": conf},
        )
