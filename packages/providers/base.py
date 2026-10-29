from dataclasses import dataclass, field
from typing import Protocol, Optional, List, Dict, Any
from packages.core.domain.node import NodeType, BoundingBox, NodeStyle, TextSpan


@dataclass
class OCRBlock:
    text: str
    bbox: BoundingBox
    confidence: float = 1.0
    block_type: str = "paragraph"
    font_size: float = 11.0
    is_bold: bool = False
    is_italic: bool = False
    language: Optional[str] = None


@dataclass
class OCRResult:
    page_number: int
    text: str
    blocks: List[OCRBlock]
    language: Optional[str] = None
    confidence: Optional[float] = 1.0
    provider: str = "bodhan"
    provider_request_id: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None


@dataclass
class TranslationRequest:
    node_id: str
    source_text: str
    source_language: str
    target_language: str
    node_type: NodeType = NodeType.PARAGRAPH
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    document_title: Optional[str] = None
    terminology: Dict[str, str] = field(default_factory=dict)
    user_prompt: Optional[str] = None
    model_policy: str = "default"
    spans: List[TextSpan] = field(default_factory=list)
    segments: Optional[List[Dict[str, str]]] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class TranslationResult:
    node_id: str
    translated_text: str
    source_language: str
    target_language: str
    provider: str
    model: str
    prompt_version: str
    latency_ms: int
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    translated_spans: List[TextSpan] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None


class OCRProvider(Protocol):
    async def extract_page(
        self,
        image_bytes: bytes,
        *,
        page_number: int,
        document_id: str,
        language_hint: Optional[str] = None,
    ) -> OCRResult:
        ...


class TranslationProvider(Protocol):
    async def translate(
        self,
        request: TranslationRequest,
    ) -> TranslationResult:
        ...
