import fitz
import re
from typing import List, Dict, Any, Optional
from packages.core.domain.node import DocumentIR
from packages.translation.validation.validation_issue import (
    ValidationIssue, IssueCode, IssueSeverity, GateStatus
)
from packages.translation.validation.validation_report import ValidationReport


class PdfTextRoundTripValidator:
    """
    Implements GATE D: Generated PDF Text Round-Trip Validation per Section 11.
    Re-opens the generated PDF, extracts text and spans from every page,
    and compares extracted text with the approved translated IR to ensure
    text and numbers survived rendering without clipping or loss.
    """

    @classmethod
    def validate(
        cls,
        rendered_pdf_bytes: bytes,
        ir: DocumentIR,
        report: ValidationReport,
    ) -> GateStatus:
        if not rendered_pdf_bytes:
            report.record_issue("pdf_round_trip", ValidationIssue(
                issue_code=IssueCode.ROUNDTRIP_TEXT_MISSING,
                severity=IssueSeverity.CRITICAL,
                stage="GATE_D",
                explanation="Rendered PDF bytes are empty.",
            ))
            report.set_gate_status("pdf_round_trip", GateStatus.FAIL)
            return GateStatus.FAIL

        try:
            doc = fitz.open(stream=rendered_pdf_bytes, filetype="pdf")
        except Exception as e:
            report.record_issue("pdf_round_trip", ValidationIssue(
                issue_code=IssueCode.ROUNDTRIP_TEXT_MISSING,
                severity=IssueSeverity.CRITICAL,
                stage="GATE_D",
                explanation=f"Cannot open generated PDF for round-trip validation: {e}",
            ))
            report.set_gate_status("pdf_round_trip", GateStatus.FAIL)
            return GateStatus.FAIL

        total_pages_pdf = len(doc)
        total_pages_ir = len(ir.pages)

        if total_pages_pdf < total_pages_ir:
            report.record_issue("pdf_round_trip", ValidationIssue(
                issue_code=IssueCode.ROUNDTRIP_TEXT_MISSING,
                severity=IssueSeverity.CRITICAL,
                stage="GATE_D",
                explanation=f"Generated PDF page count ({total_pages_pdf}) is less than IR ({total_pages_ir}).",
            ))

        total_expected_chars = 0
        total_extracted_chars = 0
        missing_numbers = 0

        for page_idx, page_node in enumerate(ir.pages):
            if page_idx >= total_pages_pdf:
                break

            pdf_page = doc[page_idx]
            extracted_text = pdf_page.get_text().strip()
            total_extracted_chars += len(extracted_text)

            # Check each node's translation in the rendered page
            for node in page_node.nodes:
                target_text = (node.translated_text or "").strip()
                if not target_text:
                    continue

                total_expected_chars += len(target_text)

                # Extract digits from target_text and ensure they exist in rendered page
                expected_nums = re.findall(r"\b\d+\b", target_text)
                for num in expected_nums:
                    if num not in extracted_text:
                        missing_numbers += 1
                        report.record_issue("pdf_round_trip", ValidationIssue(
                            issue_code=IssueCode.NUMERIC_VALUE_MISMATCH,
                            severity=IssueSeverity.ERROR,
                            stage="GATE_D",
                            block_id=node.node_id,
                            page_index=page_idx,
                            explanation=f"Number '{num}' from block {node.node_id} was not recovered from rendered PDF text.",
                        ))

        doc.close()

        # Coverage ratio
        char_ratio = total_extracted_chars / max(1, total_expected_chars)
        metrics = {
            "total_expected_chars": total_expected_chars,
            "total_extracted_chars": total_extracted_chars,
            "char_coverage_ratio": round(min(1.0, char_ratio), 3),
            "missing_numbers": missing_numbers,
        }

        current_status = report.gates["pdf_round_trip"].status
        if current_status == GateStatus.NOT_RUN:
            if missing_numbers > 0 or char_ratio < 0.50:
                status = GateStatus.REVIEW_REQUIRED if missing_numbers <= 2 else GateStatus.FAIL
            else:
                status = GateStatus.PASS
            report.set_gate_status("pdf_round_trip", status, metrics)
        else:
            report.gates["pdf_round_trip"].metrics.update(metrics)

        return report.gates["pdf_round_trip"].status
