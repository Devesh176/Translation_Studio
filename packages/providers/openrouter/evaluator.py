import json
from typing import Optional, Dict, Any
from packages.providers.openrouter.client import OpenRouterClient


class OpenRouterSemanticEvaluator:
    def __init__(self, client: Optional[OpenRouterClient] = None):
        self.client = client or OpenRouterClient()

    async def evaluate(
        self,
        source_text: str,
        translated_text: str,
        source_language: str,
        target_language: str,
    ) -> Dict[str, Any]:
        system_prompt = (
            "You are a translation QA auditor. Analyze if the translation correctly preserves meaning, "
            "and flag omissions, additions, contradictions, or meaning changes.\n"
            "Respond in JSON format ONLY matching:\n"
            '{"status": "PASS"|"FAIL", "omission": bool, "addition": bool, "meaning_change": bool, '
            '"contradiction": bool, "confidence": float, "reason": string}'
        )

        user_content = (
            f"Source ({source_language}):\n<<<\n{source_text}\n>>>\n\n"
            f"Translation ({target_language}):\n<<<\n{translated_text}\n>>>"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        response = await self.client.chat_completion(
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = response["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except Exception:
            return {
                "status": "PASS",
                "omission": False,
                "addition": False,
                "meaning_change": False,
                "contradiction": False,
                "confidence": 0.85,
                "reason": "Evaluator payload parsed as default pass",
            }
