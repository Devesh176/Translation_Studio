from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


class DocumentVersion(BaseModel):
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    parent_version_id: Optional[str] = None
    version_number: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    source_language: str
    target_language: str
    
    ocr_provider: Optional[str] = None
    ocr_policy: Optional[str] = None
    
    translation_provider: str
    translation_model: str
    translation_policy: str
    prompt_version: str
    
    renderer_version: str = "renderer_v1"
    fonts_bundle: str = "fonts_v1"
    
    status: str = "PENDING"
    is_published: bool = False
    
    storage_ir_path: Optional[str] = None
    storage_pdf_path: Optional[str] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
