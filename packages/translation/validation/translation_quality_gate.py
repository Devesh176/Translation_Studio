from typing import List, Dict, Any, Optional
from packages.translation.validation.validation_issue import (
    ValidationIssue, IssueCode, IssueSeverity, GateStatus
)
from packages.translation.validation.validation_report import ValidationReport
from packages.translation.validation.duplicate_content_detector import DuplicateContentDetector
from packages.translation.validation.character_anomaly_detector import CharacterAnomalyDetector
from packages.translation.validation.numerical_consistency import NumericalConsistencyValidator
from packages.translation.validation.protected_span_validator import ProtectedSpanValidator


class TranslationQualityGate:
    """
    Implements GATE B: Independent Translation Verification per Section 7 of Modification V1.
    Evaluates candidate translations independently from the provider.
    Runs response validity, protected spans, duplicates, character anomalies,
    and numerical consistency.
    """

    @classmethod
    def validate_candidate(
        cls,
        block_id: str,
        source_text: str,
        candidate_translation: str,
        protected_items: List[Dict[str, Any]],
        report: Optional[ValidationReport] = None,
        page_index: Optional[int] = None,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        # 1. Response validity check
        clean_target = (candidate_translation or "").strip()
        if not clean_target:
            issues.append(ValidationIssue(
                issue_code=IssueCode.EMPTY_TRANSLATION,
                severity=IssueSeverity.CRITICAL,
                stage="GATE_B",
                block_id=block_id,
                page_index=page_index,
                explanation="Candidate translation is empty.",
            ))
            if report:
                report.record_issue("translation", issues[-1])
            return issues

        # 2. Check for provider error envelopes treated as text
        if any(err_sig in clean_target.lower() for err_sig in ["502 bad gateway", "404 not found", "error 500", "rate limit exceeded"]):
            issues.append(ValidationIssue(
                issue_code=IssueCode.PROVIDER_ERROR_AS_TEXT,
                severity=IssueSeverity.CRITICAL,
                stage="GATE_B",
                block_id=block_id,
                page_index=page_index,
                explanation=f"Provider error envelope leaked as translated text: '{clean_target[:50]}...'",
            ))

        # 3. Protected-Span Integrity
        span_issues = ProtectedSpanValidator.validate_spans(clean_target, protected_items)
        for si in span_issues:
            issues.append(ValidationIssue(
                issue_code=IssueCode[si["type"]],
                severity=IssueSeverity[si["severity"]],
                stage="GATE_B",
                block_id=block_id,
                page_index=page_index,
                explanation=si["evidence"],
            ))

        # 4. Duplicate Content Detection (Problem 47 regression coverage)
        dup_issues = DuplicateContentDetector.detect_duplicates(clean_target)
        for di in dup_issues:
            issues.append(ValidationIssue(
                issue_code=IssueCode[di["type"]],
                severity=IssueSeverity.WARNING,
                stage="GATE_B",
                block_id=block_id,
                page_index=page_index,
                explanation=di["evidence"],
                evidence={"phrase": di.get("phrase")},
            ))

        # 5. Character & Unicode Anomaly Detection
        char_anomalies = CharacterAnomalyDetector.detect_anomalies(clean_target)
        for ca in char_anomalies:
            issues.append(ValidationIssue(
                issue_code=IssueCode[ca["type"]],
                severity=IssueSeverity[ca["severity"]],
                stage="GATE_B",
                block_id=block_id,
                page_index=page_index,
                explanation=ca["evidence"],
            ))

        # 6. Numerical & Unit Consistency Validation
        num_issues = NumericalConsistencyValidator.validate_consistency(source_text, clean_target)
        for ni in num_issues:
            issues.append(ValidationIssue(
                issue_code=IssueCode[ni["type"]],
                severity=IssueSeverity[ni["severity"]],
                stage="GATE_B",
                block_id=block_id,
                page_index=page_index,
                explanation=ni["evidence"],
            ))

        # Record to report if provided
        if report:
            for issue in issues:
                report.record_issue("translation", issue)

        return issues
