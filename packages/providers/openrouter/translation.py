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

        if request.segments and len(request.segments) > 1:
            seg_result = await self._translate_segments(request, src_str, tgt_str)
            if seg_result is not None:
                return seg_result

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

    async def _translate_segments(self, request: TranslationRequest, src_str: str, tgt_str: str) -> Optional[TranslationResult]:
        """Segment-ID contract. Returns None (caller falls back to plain paragraph translation) if the
        model response is malformed or its ids don't match exactly."""
        import json
        import re
        messages = PromptManager.get_unit_translation_messages(
            request.segments, request.context or {}, src_str, tgt_str)
        model = (request.model_policy if request.model_policy and request.model_policy != "default"
                 else self.default_model)
        response = await self.client.chat_completion(
            messages=messages, model=model, response_format={"type": "json_object"})
        usage = response.get("usage", {})
        inp, out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        cost = (inp * 0.0007 + out * 0.0009) / 1000.0
        expected = [s["id"] for s in request.segments]
        alignment = {"mode": "segments", "confidence": 1.0, "issue": None}
        text = None
        try:
            raw = response["choices"][0]["message"]["content"].strip()
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw).strip())
            items = data["translations"]
            got = [str(i["id"]) for i in items]
            if sorted(got) != sorted(expected) or len(set(got)) != len(got):
                alignment["issue"] = f"id_mismatch got={got} expected={expected}"
            else:
                by_id = {str(i["id"]): str(i["text"]).strip() for i in items}
                if any(not by_id[i] for i in expected):
                    alignment["issue"] = "empty_segment"
                else:
                    text = " ".join(by_id[i] for i in expected)
                    alignment["segment_ids"] = got
        except Exception as exc:
            alignment["issue"] = f"malformed:{type(exc).__name__}"
        if text is None:
            return None
        return TranslationResult(
            node_id=request.node_id, translated_text=text, source_language=request.source_language,
            target_language=request.target_language, provider="openrouter", model=model,
            prompt_version="unit_translation_v1", latency_ms=response.get("latency_ms", 500),
            input_tokens=inp, output_tokens=out, estimated_cost_usd=cost,
            raw_response={"alignment": alignment})
