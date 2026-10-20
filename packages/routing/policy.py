from typing import Optional, List
from pydantic import BaseModel


class RoutingDecision(BaseModel):
    source_language: str
    target_language: str
    provider: str
    model: Optional[str] = None
    reason: str
    policy_version: str = "routing-v1"


class OCRDecision(BaseModel):
    provider: str
    fallback_provider: Optional[str] = None
    reason: str
    policy_version: str = "ocr-v1"
