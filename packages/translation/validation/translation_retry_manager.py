from typing import List, Optional
from pydantic import BaseModel
from packages.translation.validation.validation_issue import ValidationIssue, GateStatus, IssueSeverity, IssueCode


class RetryDecision(BaseModel):
    action: GateStatus
    should_retry: bool
    explanation: str
    attempt: int
    max_retries: int


class TranslationRetryManager:
    """
    Implements Retry and Correction Policy per Section 8 of Modification V1:
    - Bounded retries (default max_retries = 2).
    - Decides whether a candidate block with issues should be retried or sent to REVIEW_REQUIRED.
    - Prevents unvalidated automatic rewriting.
    """

    RETRYABLE_CODES = {
        IssueCode.DUPLICATE_WORD,
        IssueCode.DUPLICATE_PHRASE,
        IssueCode.DUPLICATE_SENTENCE,
        IssueCode.NUMERIC_VALUE_MISMATCH,
        IssueCode.PLACEHOLDER_LEAKAGE,
        IssueCode.PUNCTUATION_ANOMALY,
        IssueCode.PROTECTED_TOKEN_MISSING,
    }

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def decide(self, issues: List[ValidationIssue], attempt: int) -> RetryDecision:
        if not issues:
            return RetryDecision(
                action=GateStatus.PASS,
                should_retry=False,
                explanation="All validation checks passed.",
                attempt=attempt,
                max_retries=self.max_retries,
            )

        # Check if any issue is retryable
        has_retryable = any(issue.issue_code in self.RETRYABLE_CODES for issue in issues)

        if has_retryable and attempt < self.max_retries:
            return RetryDecision(
                action=GateStatus.RETRY,
                should_retry=True,
                explanation=f"Retry attempt {attempt + 1}/{self.max_retries} triggered for retryable quality issues.",
                attempt=attempt + 1,
                max_retries=self.max_retries,
            )

        # If retries exhausted or issues are non-retryable
        return RetryDecision(
            action=GateStatus.REVIEW_REQUIRED,
            should_retry=False,
            explanation=f"Quality issues require human review after {attempt} attempt(s).",
            attempt=attempt,
            max_retries=self.max_retries,
        )
