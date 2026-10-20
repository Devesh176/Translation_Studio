from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


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
