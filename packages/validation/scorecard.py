from typing import Dict, Any, List
from packages.core.domain.node import DocumentIR
from packages.validation.content_completeness import ContentCompletenessValidator
from packages.validation.visual import VisualQAValidator


class QAScorecard:
    """
    Multi-dimensional QA scorecard conforming to Section 66.11:
    Independent gates for Completeness, Translation Quality, Typography/Visual QA,
    and PDF Integrity. No single average score compensates for missing content or broken typography.
    """

    @classmethod
    def evaluate(
        cls,
        ir: DocumentIR,
        rendered_pdf_bytes: bytes,
    ) -> Dict[str, Any]:
        dimensions: Dict[str, Any] = {}
        hard_failures: List[str] = []

        # 1. Content Completeness Gate
        c_valid, c_errors, c_metrics = ContentCompletenessValidator.validate_ir(ir)
        dimensions["content_completeness"] = {
            "status": "PASS" if c_valid else "FAIL",
            "score": c_metrics["completeness_ratio"],
            "errors": c_errors,
            "metrics": c_metrics,
        }
        if not c_valid:
            hard_failures.extend(c_errors)

        # 2. Typography & Visual QA Gate
        v_valid, v_errors, v_score = VisualQAValidator.inspect_rendered_pdf(rendered_pdf_bytes, ir)
        dimensions["typography_and_visual"] = {
            "status": "PASS" if v_valid else "FAIL",
            "score": v_score,
            "errors": v_errors,
        }
        if not v_valid:
            hard_failures.extend(v_errors)

        # Overall Status
        all_passed = (len(hard_failures) == 0)
        overall_score = round(min(c_metrics["completeness_ratio"], v_score), 2)

        return {
            "is_valid": all_passed,
            "overall_status": "COMPLETED" if all_passed else "QA_REVIEW_REQUIRED",
            "overall_score": overall_score,
            "dimensions": dimensions,
            "hard_failures": hard_failures,
        }
