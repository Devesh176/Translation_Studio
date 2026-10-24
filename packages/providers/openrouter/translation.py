"""
OpenRouter Translation Provider.

Uses PromptManager (backed by config/prompts.yaml) for all prompt
construction so prompts can be tuned in YAML without touching Python.
"""
from __future__ import annotations

from typing import Optional

from packages.providers.base import TranslationProvider, TranslationRequest, TranslationResult
from packages.providers.openrouter.client import OpenRouterClient
from packages.routing.language import get_language_registry
from packages.translation.prompts import PromptManager


class OpenRouterTranslationProvider(TranslationProvider):
    def __init__(
        self,
        client: Optional[OpenRouterClient] = None,
        default_model: str = "meta-llama/llama-3.3-70b-instruct",
    ) -> None:
        self.client = client or OpenRouterClient(default_model=default_model)
        self.default_model = default_model

    async def translate(self, request: TranslationRequest) -> TranslationResult:
        registry = get_language_registry()

        src_info = registry.get(request.source_language)
        tgt_info = registry.get(request.target_language)
        src_str = src_info.name if src_info else request.source_language
        tgt_str = tgt_info.name if tgt_info else request.target_language

        # Build messages from config/prompts.yaml via PromptManager
        messages = PromptManager.get_translation_messages(
            text=request.source_text,
            src_lang=src_str,
            tgt_lang=tgt_str,
            user_prompt=request.user_prompt or None,
        )

        model = (
            request.model_policy
            if request.model_policy and request.model_policy != "default"
            else self.default_model
        )
        response = await self.client.chat_completion(messages=messages, model=model)

        content = response["choices"][0]["message"]["content"].strip()
        # Strip any accidental wrapping fences the LLM added
        from packages.translation.normalizer import TextNormalizer
        content = TextNormalizer.strip_sentinels(content)

        usage = response.get("usage", {})
        inp_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        # Pricing sourced from limits.yaml via CostGuard; use same values here
        # for result recording (not for enforcement — CostGuard handles that).
        cost = (inp_tokens * 0.0007 + out_tokens * 0.0009) / 1000.0

        return TranslationResult(
            node_id=request.node_id,
            translated_text=content,
            source_language=request.source_language,
            target_language=request.target_language,
            provider="openrouter",
            model=model,
            prompt_version="translation_v1",
            latency_ms=response.get("latency_ms", 500),
            input_tokens=inp_tokens,
            output_tokens=out_tokens,
            estimated_cost_usd=cost,
            raw_response=response,
        )
