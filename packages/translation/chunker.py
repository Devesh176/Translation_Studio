from typing import List, Dict
from packages.core.domain.node import DocumentNode, NodeType
from packages.routing.language import detect_unicode_script


class TranslationChunker:
    SCRIPT_TOKEN_MULTIPLIERS = {
        "Latin": 1.0,
        "Devanagari": 2.5,
        "Tamil": 3.0,
        "Telugu": 3.0,
        "Kannada": 3.0,
        "Malayalam": 3.0,
        "Bengali": 2.8,
        "Gujarati": 2.8,
        "Gurmukhi": 2.8,
    }

    @classmethod
    def estimate_tokens(cls, text: str, script: str = "Latin") -> int:
        multiplier = cls.SCRIPT_TOKEN_MULTIPLIERS.get(script, 2.5)
        # Word-based token calibration
        words = len(text.split())
        return max(1, int(words * 1.3 * multiplier))

    @staticmethod
    def chunk_nodes_by_section(nodes: List[DocumentNode]) -> List[List[DocumentNode]]:
        """
        Groups nodes semantically by heading/section boundaries for coherent translation context.
        """
        sections: List[List[DocumentNode]] = []
        current_section: List[DocumentNode] = []

        for node in nodes:
            if node.type == NodeType.HEADING and current_section:
                sections.append(current_section)
                current_section = [node]
            else:
                current_section.append(node)

        if current_section:
            sections.append(current_section)

        return sections
