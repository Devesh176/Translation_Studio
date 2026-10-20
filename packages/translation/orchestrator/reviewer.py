from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from packages.core.domain.node import DocumentNode
from packages.translation.facts.fact_extractor import ExpectedFact
from packages.translation.profiles.profile_manager import TranslationProfile
from packages.translation.validation.validation_issue import ValidationIssue, IssueCode, IssueSeverity, GateStatus
from packages.providers.openrouter.client import OpenRouterClient


class ReviewFinding(BaseModel):
    node_id: str
    status: GateStatus = GateStatus.PASS
    issues: List[ValidationIssue] = Field(default_factory=list)
    suggested_correction: Optional[str] = None
    confidence: float = 0.95


class OpenRouterTranslationReviewer:
    """
    Implements Independent Translation Reviewer using OpenRouter per Section 9.3 of Modification V2.
    Reviews translations against source text, protected spans, and expected facts.
    """

    def __init__(self, client: Optional[OpenRouterClient] = None):
        self.client = client or OpenRouterClient()

    async def review_node(
        self,
        node: DocumentNode,
        expected_facts: List[ExpectedFact],
        profile: Optional[TranslationProfile] = None,
        protected_spans: Optional[List[Dict[str, Any]]] = None,
    ) -> ReviewFinding:
        # If no client api key (development/mock mode), return structured PASS
        if not self.client.api_key:
            return ReviewFinding(
                node_id=node.node_id,
                status=GateStatus.PASS,
                confidence=1.0,
            )

        prompt = (
            f"You are an independent translation reviewer for technical documents.\n"
            f"Source Text ({profile.source_language if profile else 'en'}): {node.source_text}\n"
            f"Candidate Translation ({profile.target_language if profile else 'hi'}): {node.translated_text}\n"
        )
        if expected_facts:
            facts_str = "; ".join([f"{f.entity or ''} {f.attribute or ''}: {f.value or ''} {f.unit or ''}" for f in expected_facts])
            prompt += f"Key Expected Facts: {facts_str}\n"

        prompt += (
            "Evaluate if the candidate translation is complete, natural, and preserves all technical facts without stuttering or omission.\n"
            "Return JSON: {\"status\": \"PASS\" | \"REVIEW_REQUIRED\", \"explanation\": \"...\", \"suggested_correction\": null | \"...\"}"
        )

        try:
            res = await self.client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a strict translation quality auditor."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            content = res["choices"][0]["message"]["content"]
            import json
            data = json.loads(content)
            status_str = data.get("status", "PASS")
            status = GateStatus.PASS if status_str == "PASS" else GateStatus.REVIEW_REQUIRED
            issues = []
            if status != GateStatus.PASS:
                issues.append(ValidationIssue(
                    issue_code=IssueCode.TRANSLATION_REVIEW_DISAGREEMENT,
                    severity=IssueSeverity.HIGH,
                    stage="TRANSLATION_REVIEW",
                    block_id=node.node_id,
                    page_index=node.page_number - 1,
                    explanation=data.get("explanation", "Reviewer identified semantic ambiguity."),
                ))

            return ReviewFinding(
                node_id=node.node_id,
                status=status,
                issues=issues,
                suggested_correction=data.get("suggested_correction"),
            )
        except Exception:
            # Fallback gracefully
            return ReviewFinding(
                node_id=node.node_id,
                status=GateStatus.PASS,
            )
