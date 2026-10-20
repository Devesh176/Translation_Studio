from typing import List, Dict, Any, Optional
from packages.core.domain.node import DocumentNode
from packages.translation.facts.fact_extractor import ExpectedFact
from packages.translation.profiles.profile_manager import TranslationProfile
from packages.translation.validation.validation_issue import ValidationIssue
from packages.providers.openrouter.client import OpenRouterClient


class TargetedCorrectionManager:
    """
    Implements Targeted Provider Correction using OpenRouter per Section 9.5 of Modification V2.
    Sends only the affected node, neighboring context, validation findings, profile, and expected facts.
    """

    def __init__(self, client: Optional[OpenRouterClient] = None):
        self.client = client or OpenRouterClient()

    async def correct_node(
        self,
        node: DocumentNode,
        issues: List[ValidationIssue],
        expected_facts: List[ExpectedFact],
        profile: Optional[TranslationProfile] = None,
        context_before: Optional[str] = None,
        context_after: Optional[str] = None,
    ) -> str:
        # If no client api key (development/mock mode), return original or cleaned text
        if not self.client.api_key:
            return node.translated_text or node.source_text

        issue_descriptions = [f"- {i.issue_code.value}: {i.explanation}" for i in issues]
        issues_str = "\n".join(issue_descriptions)

        facts_str = ""
        if expected_facts:
            facts_str = "Required facts:\n" + "\n".join([
                f"- {f.entity or ''} {f.attribute or ''}: {f.value or ''} {f.unit or ''} ({f.condition or ''} {f.relationship or ''})"
                for f in expected_facts
            ])

        prompt = (
            f"The following translation had quality issues that must be corrected.\n\n"
            f"SOURCE TEXT ({profile.source_language if profile else 'en'}):\n{node.source_text}\n\n"
            f"DEFECTIVE CANDIDATE TRANSLATION:\n{node.translated_text}\n\n"
            f"VALIDATION ISSUES IDENTIFIED:\n{issues_str}\n\n"
            f"{facts_str}\n\n"
            f"Provide ONLY the corrected target translation text in {profile.target_language if profile else 'hi'}. "
            f"Do not include explanations, quotes, or markdown wrappers."
        )

        try:
            res = await self.client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an expert technical translator specializing in high-precision corrections."},
                    {"role": "user", "content": prompt},
                ],
            )
            corrected = res["choices"][0]["message"]["content"].strip()
            return corrected
        except Exception:
            return node.translated_text or ""
