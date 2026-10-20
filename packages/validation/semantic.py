from typing import Dict, Any, Optional
from packages.providers.openrouter.evaluator import OpenRouterSemanticEvaluator


class SemanticValidator:
    def __init__(self, evaluator: Optional[OpenRouterSemanticEvaluator] = None):
        self.evaluator = evaluator or OpenRouterSemanticEvaluator()

    async def validate(
        self,
        source_text: str,
        translated_text: str,
        source_language: str,
        target_language: str,
    ) -> Dict[str, Any]:
        return await self.evaluator.evaluate(
            source_text=source_text,
            translated_text=translated_text,
            source_language=source_language,
            target_language=target_language,
        )
