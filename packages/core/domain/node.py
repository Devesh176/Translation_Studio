from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
import uuid


class NodeType(str, Enum):
    DOCUMENT = "DOCUMENT"
    PAGE = "PAGE"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    CODE_BLOCK = "CODE_BLOCK"
    TABLE = "TABLE"
    TABLE_ROW = "TABLE_ROW"
    TABLE_CELL = "TABLE_CELL"
    TABLE_CAPTION = "TABLE_CAPTION"
    FIGURE = "FIGURE"
    EQUATION = "EQUATION"
    FOOTNOTE_REFERENCE = "FOOTNOTE_REFERENCE"
    FOOTNOTE = "FOOTNOTE"


class TranslationStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    TRANSLATED = "TRANSLATED"
    EDITED = "EDITED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class BoundingBox(BaseModel):
    x0: float = Field(..., description="Left x coordinate in points")
    y0: float = Field(..., description="Top y coordinate in points")
    x1: float = Field(..., description="Right x coordinate in points")
    y1: float = Field(..., description="Bottom y coordinate in points")

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    def as_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


class NodeStyle(BaseModel):
    font_family: Optional[str] = "NotoSans-Regular"
    font_size: float = 11.0
    font_weight: str = "normal"  # normal, bold
    is_italic: bool = False
    is_underline: bool = False
    color_rgb: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    line_height: float = 14.0
    alignment: str = "left"  # left, center, right, justify


class TextSpan(BaseModel):
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    translated_text: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    style: Optional[NodeStyle] = None
    link_url: Optional[str] = None
    is_bold: bool = False
    is_italic: bool = False


class DocumentNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    page_id: Optional[str] = None
    page_number: int = 1
    type: NodeType = NodeType.PARAGRAPH
    bbox: BoundingBox
    rotation: float = 0.0
    reading_order: int = 0
    style: NodeStyle = Field(default_factory=NodeStyle)
    
    source_text: str = ""
    translated_text: Optional[str] = None
    
    source_hash: Optional[str] = None
    translation_hash: Optional[str] = None
    
    language: Optional[str] = None
    target_language: Optional[str] = None
    confidence: Optional[float] = 1.0
    z_index: int = 0
    
    spans: List[TextSpan] = Field(default_factory=list)
    
    translation_status: TranslationStatus = TranslationStatus.PENDING
    validation_status: str = "PENDING"
    render_status: str = "PENDING"
    
    # Metadata for provenance & prompt editing
    metadata: Dict[str, Any] = Field(default_factory=dict)
    edit_history: List[Dict[str, Any]] = Field(default_factory=list)


class TableCellNode(BaseModel):
    cell_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    row_idx: int
    col_idx: int
    row_span: int = 1
    col_span: int = 1
    bbox: BoundingBox
    source_text: str = ""
    translated_text: Optional[str] = None
    style: NodeStyle = Field(default_factory=NodeStyle)
    is_header: bool = False


class TableNode(DocumentNode):
    type: NodeType = NodeType.TABLE
    num_rows: int = 0
    num_cols: int = 0
    cells: List[TableCellNode] = Field(default_factory=list)
    caption: Optional[str] = None


class FootnoteNode(DocumentNode):
    type: NodeType = NodeType.FOOTNOTE
    reference_id: str
    footnote_number: str


class PageNode(BaseModel):
    page_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    page_number: int
    width: float = 595.276  # A4 width in pt
    height: float = 841.890  # A4 height in pt
    rotation: float = 0.0
    is_scanned: bool = False
    ocr_confidence: Optional[float] = None
    nodes: List[DocumentNode] = Field(default_factory=list)


class DocumentIR(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_version_id: Optional[str] = None
    title: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    total_pages: int = 0
    classification: str = "DIGITAL"  # DIGITAL, SCANNED, MIXED
    pages: List[PageNode] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def find_node(self, node_id: str) -> Optional[DocumentNode]:
        for page in self.pages:
            for node in page.nodes:
                if node.node_id == node_id:
                    return node
        return None

    def get_all_nodes(self) -> List[DocumentNode]:
        nodes = []
        for page in self.pages:
            nodes.extend(page.nodes)
        return nodes

