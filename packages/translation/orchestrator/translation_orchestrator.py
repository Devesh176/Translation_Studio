from typing import List, Dict, Any, Optional
from packages.core.domain.node import DocumentNode, TranslationStatus
from packages.providers.base import TranslationRequest
from packages.providers.bodhan.translation import BodhanTranslationProvider
from packages.providers.openrouter.translation import OpenRouterTranslationProvider
from packages.document.semantic.protected_spans import ProtectedSpansManager
from packages.translation.normalizer import TextNormalizer
from packages.translation.profiles.profile_manager import TranslationProfile, TranslationProfileManager
from packages.translation.facts.fact_extractor import ExpectedFactsExtractor, ExpectedFact
from packages.translation.facts.fact_validator import ExpectedFactsValidator
from packages.translation.validation.translation_quality_gate import TranslationQualityGate
from packages.translation.validation.translation_retry_manager import TranslationRetryManager
from packages.translation.validation.validation_issue import ValidationIssue, GateStatus, IssueSeverity, IssueCode
from packages.translation.validation.validation_report import ValidationReport
from packages.translation.orchestrator.reviewer import OpenRouterTranslationReviewer
from packages.translation.orchestrator.targeted_correction import TargetedCorrectionManager


class TranslationOrchestrator:
    """
    Coordinates primary translation, independent review, expected-facts validation,
    and targeted correction per Section 9 of Modification V2.
    """

    def __init__(
        self,
        bodhan_provider: Optional[BodhanTranslationProvider] = None,
        openrouter_provider: Optional[OpenRouterTranslationProvider] = None,
        retry_manager: Optional[TranslationRetryManager] = None,
    ):
        self.bodhan = bodhan_provider or BodhanTranslationProvider()
        self.openrouter = openrouter_provider or OpenRouterTranslationProvider()
        self.retry_manager = retry_manager or TranslationRetryManager(max_retries=2)
        self.reviewer = OpenRouterTranslationReviewer()
        self.corrector = TargetedCorrectionManager()

    async def translate_node(
        self,
        node: DocumentNode,
        source_language: str,
        target_language: str,
        profile: Optional[TranslationProfile] = None,
        report: Optional[ValidationReport] = None,
        page_index: int = 0,
    ) -> List[ValidationIssue]:
        profile = profile or TranslationProfileManager.get_profile(domain="general")
        source_text = node.source_text.strip()
        if not source_text:
            node.translated_text = ""
            node.translation_status = TranslationStatus.TRANSLATED
            return []

        # 1. Detect & shield protected spans
        shielded_text, protected_items = ProtectedSpansManager.detect_and_shield(source_text)
        node.protected_spans = protected_items

        # 2. Extract expected facts from source text
        expected_facts = ExpectedFactsExtractor.extract_facts(node.node_id, source_text)

        # 3. Translation attempt loop with bounded targeted retries
        attempt = 0
        final_text = ""
        node_issues: List[ValidationIssue] = []

        while attempt <= self.retry_manager.max_retries:
            if attempt == 0:
                # Primary translation via Bodhan
                req = TranslationRequest(
                    node_id=node.node_id,
                    source_text=shielded_text,
                    source_language=source_language,
                    target_language=target_language,
                    node_type=node.type,
                    spans=node.spans,
                )
                try:
                    res = await self.bodhan.translate(req)
                    candidate_raw = res.translated_text
                except Exception:
                    # Fallback to OpenRouter if primary is unavailable
                    res = await self.openrouter.translate(req)
                    candidate_raw = res.translated_text
            else:
                # Targeted correction via OpenRouter
                candidate_raw = await self.corrector.correct_node(
                    node=node,
                    issues=node_issues,
                    expected_facts=expected_facts,
                    profile=profile,
                )

            # Clean and normalize text
            clean_text = TextNormalizer.clean_llm_markdown_wrappers(candidate_raw)
            clean_text = TextNormalizer.normalize_indic_text(clean_text)

            # Restore protected spans
            restored_text, p_valid, p_errors = ProtectedSpansManager.restore_and_validate(
                clean_text, protected_items
            )
            final_text = restored_text
            node.translated_text = final_text

            # 4. Gate B Independent Quality Validation
            node_issues = TranslationQualityGate.validate_candidate(
                block_id=node.node_id,
                source_text=source_text,
                candidate_translation=restored_text,
                protected_items=protected_items,
                page_index=page_index,
            )

            # 5. Expected-Facts Semantic Validation
            fact_issues = ExpectedFactsValidator.validate_facts(
                facts=expected_facts,
                target_text=restored_text,
                page_index=page_index,
            )
            node_issues.extend(fact_issues)

            # 6. Check if retries needed
            decision = self.retry_manager.decide(node_issues, attempt=attempt)
            if decision.should_retry and attempt < self.retry_manager.max_retries:
                attempt += 1
                continue
            else:
                break

        # 7. Independent Review for critical nodes or flagged ambiguities
        has_critical_facts = any(f.criticality == "HIGH" for f in expected_facts)
        has_warnings = any(i.severity in [IssueSeverity.HIGH, IssueSeverity.MEDIUM] for i in node_issues)
        if (has_critical_facts or has_warnings) and not any(i.severity == IssueSeverity.CRITICAL for i in node_issues):
            review_finding = await self.reviewer.review_node(
                node=node,
                expected_facts=expected_facts,
                profile=profile,
                protected_spans=protected_items,
            )
            if review_finding.status != GateStatus.PASS:
                node_issues.extend(review_finding.issues)

        node.translated_text = final_text
        node.translation_status = TranslationStatus.TRANSLATED

        if report:
            for issue in node_issues:
                report.record_issue("translation", issue)

        return node_issues
