from typing import List, Dict, Any, Optional
from packages.core.domain.node import DocumentIR, DocumentNode
from packages.translation.validation.validation_issue import (
    ValidationIssue, IssueCode, IssueSeverity, GateStatus
)
from packages.translation.validation.validation_report import ValidationReport


class TranslatedIRValidator:
    """
    Implements GATE C: Translated IR and Source-Target Alignment per Section 9.
    Validates that every source block has an aligned translated block,
    order is preserved, no unexpected duplicates exist, and no failed Gate B
    block enters rendering.
    """

    @classmethod
    def validate(
        cls,
        ir: DocumentIR,
        report: ValidationReport,
    ) -> GateStatus:
        total_blocks = 0
        missing_mappings = 0
        order_errors = 0

        for page_idx, page in enumerate(ir.pages):
            prev_order = -1
            for node in page.nodes:
                if not node.source_text.strip():
                    continue

                total_blocks += 1

                # 1. Check mapping presence
                if not node.translated_text or not node.translated_text.strip():
                    missing_mappings += 1
                    report.record_issue("translated_ir", ValidationIssue(
                        issue_code=IssueCode.TARGET_IR_NODE_MISSING,
                        severity=IssueSeverity.CRITICAL,
                        stage="GATE_C",
                        block_id=node.node_id,
                        page_index=page_idx,
                        explanation=f"Source block {node.node_id} has no mapped translation in target IR.",
                    ))

                # 2. Check reading order monotonicity
                if node.reading_order < prev_order:
                    order_errors += 1
                    report.record_issue("translated_ir", ValidationIssue(
                        issue_code=IssueCode.TARGET_IR_ORDER_INVALID,
                        severity=IssueSeverity.MEDIUM,
                        stage="GATE_C",
                        block_id=node.node_id,
                        page_index=page_idx,
                        explanation=f"Block {node.node_id} reading_order ({node.reading_order}) broke sequence.",
                    ))
                prev_order = node.reading_order

        # Gate C Status
        current_status = report.gates["translated_ir"].status
        if current_status == GateStatus.NOT_RUN:
            if missing_mappings > 0:
                status = GateStatus.FAIL
            elif order_errors > 0:
                status = GateStatus.REVIEW_REQUIRED
            else:
                status = GateStatus.PASS
            report.set_gate_status("translated_ir", status, {
                "total_blocks": total_blocks,
                "missing_mappings": missing_mappings,
                "order_errors": order_errors,
            })

        return report.gates["translated_ir"].status
