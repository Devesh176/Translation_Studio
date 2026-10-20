import json
from typing import Dict, Any
from packages.core.domain.node import DocumentIR


class IRSerializer:
    @staticmethod
    def to_json(ir: DocumentIR) -> str:
        return ir.model_dump_json(indent=2)

    @staticmethod
    def from_json(json_str: str) -> DocumentIR:
        return DocumentIR.model_validate_json(json_str)

    @staticmethod
    def to_dict(ir: DocumentIR) -> Dict[str, Any]:
        return ir.model_dump()

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> DocumentIR:
        return DocumentIR.model_validate(data)
