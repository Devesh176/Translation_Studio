from typing import Optional
from packages.providers.base import TranslationProvider, TranslationRequest, TranslationResult
from packages.providers.bodhan.client import BodhanClient
from packages.routing.language import normalize_language_code


class BodhanTranslationProvider(TranslationProvider):
    def __init__(self, client: Optional[BodhanClient] = None):
        self.client = client or BodhanClient()

    async def translate(self, request: TranslationRequest) -> TranslationResult:
        tgt_code = normalize_language_code(request.target_language)
        src_code = normalize_language_code(request.source_language)

        res = await self.client.translate(
            text=request.source_text,
            source_lang=src_code,
            target_lang=tgt_code,
            target_script="native",
        )
        translated_text = res.get("translated_text", "")
        latency = res.get("latency_ms", 100)

        return TranslationResult(
            node_id=request.node_id,
            translated_text=translated_text,
            source_language=request.source_language,
            target_language=request.target_language,
            provider="bodhan",
            model="indic-translate",
            prompt_version="bodhan_native_v1",
            latency_ms=latency,
            raw_response=res,
        )
