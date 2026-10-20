from typing import List, Tuple
from packages.core.domain.node import DocumentIR


class IRValidator:
    @staticmethod
    def validate(ir: DocumentIR) -> Tuple[bool, List[str]]:
        errors = []
        if not ir.document_id:
            errors.append("Document ID cannot be empty.")
        if ir.total_pages <= 0:
            errors.append("Total pages must be greater than zero.")
        if len(ir.pages) != ir.total_pages:
            errors.append(f"Page count mismatch: declared {ir.total_pages}, found {len(ir.pages)}.")

        seen_node_ids = set()
        for page in ir.pages:
            for node in page.nodes:
                if node.node_id in seen_node_ids:
                    errors.append(f"Duplicate node ID found: {node.node_id}")
                seen_node_ids.add(node.node_id)
                if node.bbox.x1 < node.bbox.x0 or node.bbox.y1 < node.bbox.y0:
                    errors.append(f"Invalid bounding box in node {node.node_id}")

        return (len(errors) == 0, errors)
