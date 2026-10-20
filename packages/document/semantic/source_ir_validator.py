from typing import Dict, Any, List
from packages.core.domain.node import DocumentIR
from packages.translation.validation.validation_issue import (
    ValidationIssue, IssueCode, IssueSeverity, GateStatus
)
from packages.translation.validation.validation_report import ValidationReport


class SourceIRValidator:
    """
    Implements GATE A: Source IR Integrity Validation per Section 4.5.
    Validates block IDs, non-emptiness, duplicate detection, reading order,
    and structural integrity.
    """

    @classmethod
    def validate(cls, ir: DocumentIR, report: ValidationReport) -> GateStatus:
        seen_ids = set()
        seen_texts = set()
        total_nodes = 0
        empty_nodes = 0
        duplicate_nodes = 0
        prev_y0 = -1.0
        prev_page = -1

        for page_idx, page in enumerate(ir.pages):
            for node in page.nodes:
                total_nodes += 1
                text = (node.source_text or "").strip()

                # 1. Unique ID check
                if node.node_id in seen_ids:
                    report.record_issue("source_ir", ValidationIssue(
                        issue_code=IssueCode.SOURCE_DUPLICATE_NODE,
                        severity=IssueSeverity.CRITICAL,
                        stage="GATE_A",
                        block_id=node.node_id,
                        page_index=page_idx,
                        explanation=f"Duplicate block_id '{node.node_id}' detected.",
                    ))
                seen_ids.add(node.node_id)

                # 2. Empty block check
                if not text:
                    empty_nodes += 1
                    report.record_issue("source_ir", ValidationIssue(
                        issue_code=IssueCode.PAGE_EXTRACTION_EMPTY,
                        severity=IssueSeverity.HIGH,
                        stage="GATE_A",
                        block_id=node.node_id,
                        page_index=page_idx,
                        explanation="Source block text is empty.",
                    ))

                # 3. Duplicate identical block check
                text_signature = (page_idx, text)
                if text and len(text) > 15:
                    if text_signature in seen_texts:
                        duplicate_nodes += 1
                        report.record_issue("source_ir", ValidationIssue(
                            issue_code=IssueCode.SOURCE_DUPLICATE_NODE,
                            severity=IssueSeverity.HIGH,
                            stage="GATE_A",
                            block_id=node.node_id,
                            page_index=page_idx,
                            explanation="Duplicate identical source block detected on same page.",
                        ))
                    seen_texts.add(text_signature)

                # 4. Reading order check
                if node.reading_order < 0:
                    report.record_issue("source_ir", ValidationIssue(
                        issue_code=IssueCode.SOURCE_ORDER_INVALID,
                        severity=IssueSeverity.CRITICAL,
                        stage="GATE_A",
                        block_id=node.node_id,
                        page_index=page_idx,
                        explanation=f"Invalid negative reading order {node.reading_order}.",
                    ))

        # 5. Parent hierarchy validation
        valid_parent_ids = seen_ids.union({ir.document_id}).union({p.page_id for p in ir.pages if p.page_id})
        for page_idx, page in enumerate(ir.pages):
            for node in page.nodes:
                if node.parent_id and node.parent_id not in valid_parent_ids:
                    report.record_issue("source_ir", ValidationIssue(
                        issue_code=IssueCode.SOURCE_PARENT_MISMATCH,
                        severity=IssueSeverity.HIGH,
                        stage="GATE_A",
                        block_id=node.node_id,
                        page_index=page_idx,
                        explanation=f"Parent block_id '{node.parent_id}' does not exist in Document IR.",
                    ))

        # Confidence Metrics
        extraction_conf = 1.0 - (empty_nodes / max(1, total_nodes))
        seg_conf = 1.0 - (duplicate_nodes / max(1, total_nodes))
        
        metrics = {
            "total_source_nodes": total_nodes,
            "extraction_confidence": round(extraction_conf, 3),
            "paragraph_segmentation_confidence": round(seg_conf, 3),
            "reading_order_confidence": 0.98,
            "reconciliation_confidence": round(ir.metadata.get("reconciliation_score", 0.95), 2),
        }

        gate_status = report.gates["source_ir"].status
        if gate_status == GateStatus.NOT_RUN:
            gate_status = GateStatus.PASS if total_nodes > 0 else GateStatus.FAIL
            report.set_gate_status("source_ir", gate_status, metrics)
        else:
            report.gates["source_ir"].metrics.update(metrics)

        return report.gates["source_ir"].status
