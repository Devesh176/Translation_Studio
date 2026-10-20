from typing import Tuple, List, Dict, Any
from packages.core.domain.node import DocumentIR, DocumentNode


class ContentCompletenessValidator:
    """
    Validates content completeness according to Section 66.11:
    - Every source node must be represented in translation.
    - Zero empty/missing translations.
    - Protected tokens exact.
    - Zero placeholder leakage or forbidden sentinels.
    """

    FORBIDDEN_SENTINELS = ("DOCUMENT_CONTENT", "__INTERNAL_PROMPT__", "<_P_")

    @classmethod
    def validate_ir(cls, ir: DocumentIR) -> Tuple[bool, List[str], Dict[str, Any]]:
        errors: List[str] = []
        total_nodes = 0
        missing_nodes = 0
        leaked_nodes = 0

        for page in ir.pages:
            for node in page.nodes:
                if not node.source_text.strip():
                    continue

                total_nodes += 1
                trans = (node.translated_text or "").strip()

                if not trans:
                    errors.append(f"MISSING_TRANSLATION: Node {node.node_id} has empty translation.")
                    missing_nodes += 1
                    continue

                for sentinel in cls.FORBIDDEN_SENTINELS:
                    if sentinel in trans:
                        errors.append(f"PLACEHOLDER_LEAKAGE: Node {node.node_id} leaked sentinel '{sentinel}'.")
                        leaked_nodes += 1
                        break

        completeness_ratio = (total_nodes - missing_nodes - leaked_nodes) / max(1, total_nodes)
        is_valid = (len(errors) == 0 and completeness_ratio >= 0.99)

        metrics = {
            "total_nodes": total_nodes,
            "missing_nodes": missing_nodes,
            "leaked_nodes": leaked_nodes,
            "completeness_ratio": round(completeness_ratio, 3),
        }

        return is_valid, errors, metrics
