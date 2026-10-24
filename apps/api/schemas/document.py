from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    file_size_bytes: int
    total_pages: int
    classification: str
    source_language: Optional[str] = None


class TranslationStartRequest(BaseModel):
    target_language: str = Field(..., description="Target language code e.g. hi, ta, te, kn, ml, bn, mr, gu, pa, en")
    source_language: Optional[str] = None
    provider: Optional[str] = None


class TranslationStartResponse(BaseModel):
    job_id: str
    document_id: str
    status: str
    message: str


class SectionEditRequest(BaseModel):
    instruction: str = Field(..., description="User prompt instruction to refine the section")


class SectionEditResponse(BaseModel):
    document_id: str
    version_id: str
    parent_version_id: str
    node_id: str
    edited_translation: str
    status: str


class SelectionModel(BaseModel):
    kind: str = Field(..., pattern="^(box|text)$")
    page: int = Field(..., ge=1)
    rect: Optional[List[float]] = Field(None, description="[x0,y0,x1,y1] in PDF points (kind=box)")
    quote: Optional[str] = Field(None, description="Highlighted text (kind=text)")
    rects: Optional[List[List[float]]] = Field(None, description="Highlight rectangles in PDF points (kind=text)")

    @model_validator(mode="after")
    def _check(self):
        if self.kind == "box" and not (self.rect and len(self.rect) == 4):
            raise ValueError("box selection needs rect=[x0,y0,x1,y1]")
        if self.kind == "text" and not (self.quote or "").strip():
            raise ValueError("text selection needs a non-empty quote")
        if self.kind == "text" and any(len(r) != 4 for r in (self.rects or [])):
            raise ValueError("each rect needs 4 numbers")
        return self


class SelectionEditRequest(BaseModel):
    version_id: str
    instruction: str = Field(..., min_length=1)
    selection: SelectionModel


class SelectionEditResponse(BaseModel):
    status: str  # COMPLETED | REJECTED
    document_id: Optional[str] = None
    version_id: Optional[str] = None
    parent_version_id: Optional[str] = None
    changed_pages: List[int] = []
    changes: List[Dict[str, Any]] = []
    warnings: List[str] = []
    ocr_used: bool = False
    reason: Optional[str] = None
    category: Optional[str] = None
    suggestion: Optional[str] = None
    cost_usd: float = 0.0
