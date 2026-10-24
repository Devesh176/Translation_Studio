import asyncio
import os
import uuid
import hashlib
import re
import fitz
from typing import Optional, Dict, Any

from packages.core.domain.node import DocumentIR, DocumentNode, TranslationStatus, NodeType, NodeStyle
from packages.core.domain.version import DocumentVersion
from packages.document.parser.pymupdf_parser import PyMuPDFParser
from packages.document.parser.pdf_classifier import PDFClassifier
from packages.document.ir.serializer import IRSerializer
from packages.routing.translation_router import TranslationRouter
from packages.routing.language import normalize_language_code
from packages.providers.bodhan.ocr import BodhanOCRProvider
from packages.providers.bodhan.translation import BodhanTranslationProvider
from packages.providers.openrouter.translation import OpenRouterTranslationProvider
from packages.providers.base import TranslationRequest
from packages.translation.cost_guard import CostGuard
from packages.translation.normalizer import TextNormalizer
from packages.translation.protected_content import protect, validate_and_restore
from packages.validation.invariants import InvariantValidator
from packages.validation.visual import VisualQAValidator
from packages.rendering.pdf_renderer import PDFRenderer
from packages.storage.object_store.local_store import LocalFileObjectStore
from packages.storage.redis.cache import TranslationCache


class DocumentTranslationPipeline:
    def __init__(
        self,
        storage_store: Optional[Any] = None,
        router: Optional[TranslationRouter] = None,
        cache: Optional[TranslationCache] = None,
    ):
        self.storage = storage_store or LocalFileObjectStore(os.getenv("OBJECT_STORAGE_LOCAL_DIR", "./data/storage"))
        self.router = router or TranslationRouter()
        self.cache = cache or TranslationCache()
        self.cost_guard = CostGuard()
        self.ocr_provider = BodhanOCRProvider()
        self.bodhan_provider = BodhanTranslationProvider()
        self.openrouter_provider = OpenRouterTranslationProvider()
        self.renderer = PDFRenderer()
        self.parser = PyMuPDFParser()

    async def execute(
        self,
        document_id: str,
        pdf_bytes: bytes,
        target_language: str,
        source_language: Optional[str] = None,
        user_requested_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        tgt_lang = normalize_language_code(target_language)
        
        # 1. Parse PDF to Document IR
        ir: DocumentIR = self.parser.parse(pdf_bytes, document_id=document_id)
        src_lang = normalize_language_code(source_language or ir.source_language or "en")
        ir.source_language = src_lang
        ir.target_language = tgt_lang

        # 1b. Fallback to OCR for any scanned/image pages with no text blocks
        if any(len(p.nodes) == 0 for p in ir.pages):
            try:
                pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for page_idx, page in enumerate(ir.pages):
                    if len(page.nodes) == 0 and page_idx < len(pdf_doc):
                        pix = pdf_doc[page_idx].get_pixmap()
                        img_bytes = pix.tobytes("png")
                        ocr_res = await self.ocr_provider.extract_page(
                            img_bytes,
                            page_number=page.page_number,
                            document_id=document_id,
                            language_hint=src_lang,
                        )
                        for r_idx, b in enumerate(ocr_res.blocks):
                            if not b.text.strip():
                                continue
                            node = DocumentNode(
                                node_id=f"{page.page_id}_ocr_n{r_idx}",
                                parent_id=page.page_id,
                                page_id=page.page_id,
                                page_number=page.page_number,
                                type=NodeType.PARAGRAPH,
                                bbox=b.bbox,
                                reading_order=r_idx,
                                style=NodeStyle(font_size=11.0),
                                source_text=b.text,
                                source_hash=hashlib.sha256(b.text.encode("utf-8")).hexdigest(),
                            )
                            page.nodes.append(node)
                pdf_doc.close()
            except Exception:
                pass


        # 2. Cost Guarding Check
        total_text = " ".join([n.source_text for n in ir.get_all_nodes()])
        self.cost_guard.check_and_estimate_cost(total_text, tgt_lang)

        # 3. Route & Translate Nodes
        for page in ir.pages:
            for node in page.nodes:
                if not node.source_text.strip():
                    continue

                if node.type == NodeType.CODE_BLOCK or node.metadata.get("is_code") or node.metadata.get("math_only"):
                    node.translated_text = node.source_text
                    node.translation_status = TranslationStatus.SKIPPED
                    node.validation_status = "PASS"
                    continue

                protected = protect(node.source_text)
                node.metadata["protected_tokens"] = protected.mapping
                if not re.search(r"[^\W\d_]", re.sub(r"\u27e6P\d+\u27e7", "", protected.masked)):
                    # nothing translatable left (only protected tokens / numbers / symbols)
                    node.translated_text = node.source_text
                    node.translation_status = TranslationStatus.SKIPPED
                    node.validation_status = "PASS"
                    continue

                routing = self.router.route(
                    source_language=src_lang,
                    target_language=tgt_lang,
                    user_requested_provider=user_requested_provider,
                )

                cache_key = TranslationCache.compute_cache_key(
                    source_text=protected.masked,
                    source_language=src_lang,
                    target_language=tgt_lang,
                    provider=routing.provider,
                    model=routing.model or "native",
                    prompt_version="v2",
                )
                cached = await self.cache.get(cache_key)

                masked_out = cached
                if masked_out is not None and validate_and_restore(masked_out, protected.mapping)[1]:
                    masked_out = None  # stale/poisoned cache entry: retranslate
                failed_errors: list = []
                if masked_out is None:
                    req = TranslationRequest(
                        node_id=node.node_id,
                        source_text=protected.masked,
                        source_language=src_lang,
                        target_language=tgt_lang,
                        node_type=node.type,
                        spans=node.spans,
                    )
                    errors: list = []
                    attempts = ["bodhan"] * 4 + ["openrouter"] if routing.provider == "bodhan" else ["openrouter"] * 2
                    for attempt, prov in enumerate(attempts):
                        try:
                            result = await (self.bodhan_provider if prov == "bodhan" else self.openrouter_provider).translate(req)
                        except Exception as exc:
                            errors = [f"PROVIDER_ERROR:{type(exc).__name__}"]
                            await asyncio.sleep(1.5 * (attempt + 1))
                            continue
                        masked_out = TextNormalizer.normalize_indic_text(
                            TextNormalizer.clean_llm_markdown_wrappers(result.translated_text)
                        )
                        _, errors = validate_and_restore(masked_out, protected.mapping)
                        if not errors and src_lang != tgt_lang and masked_out.strip() == protected.masked.strip():
                            errors = ["UNTRANSLATED_ECHO"]
                        if not errors:
                            break
                        await asyncio.sleep(0.3)
                    if errors:
                        failed_errors = errors
                        if masked_out is None:
                            masked_out = protected.masked
                    if not errors:
                        await self.cache.set(cache_key, masked_out)

                restored, perrors = validate_and_restore(masked_out, protected.mapping)
                if perrors:
                    # Never ship broken tokens: fall back to the source text for this node
                    node.metadata["protected_errors"] = perrors
                    node.metadata["raw_output"] = masked_out
                    node.translated_text = node.source_text
                    node.translation_status = TranslationStatus.FAILED
                    node.validation_status = "FAIL_PROTECTED_TOKENS"
                    continue
                node.translated_text = restored
                if failed_errors:
                    node.metadata["translation_errors"] = failed_errors
                    node.translation_status = TranslationStatus.FAILED
                    node.validation_status = "FAIL_UNTRANSLATED"
                    continue
                node.translation_status = TranslationStatus.TRANSLATED

                if not node.translated_text.strip():
                    node.validation_status = "FAIL_EMPTY"
                elif TextNormalizer.has_sentinel(node.translated_text):
                    node.validation_status = "FAIL_SENTINEL_LEAK"
                else:
                    valid_num, _ = InvariantValidator.validate_numbers(node.source_text, node.translated_text)
                    valid_urls, _ = InvariantValidator.validate_urls_and_emails(node.source_text, node.translated_text)
                    if valid_num and valid_urls:
                        node.validation_status = "PASS"
                    elif not valid_num:
                        node.validation_status = "WARN_NUM_MISMATCH"
                    else:
                        node.validation_status = "WARN_URL_MISMATCH"

        # 5. Render translated PDF
        is_overlay = ir.classification in ["SCANNED", "MIXED"]
        rendered_pdf_bytes = self.renderer.render_ir_to_pdf(
            ir, original_pdf_bytes=pdf_bytes, is_overlay_mode=is_overlay
        )

        # 6. Visual QA & Rendered Output Verification
        is_render_valid, qa_errors, qa_score = VisualQAValidator.inspect_rendered_pdf(rendered_pdf_bytes, ir)


        # 7. Store artifacts
        version_id = str(uuid.uuid4())
        ir_json = IRSerializer.to_json(ir)
        
        ir_path = f"documents/{document_id}/versions/{version_id}/document.ir.json"
        pdf_path = f"documents/{document_id}/versions/{version_id}/output.pdf"

        await self.storage.put_object(ir_path, ir_json.encode("utf-8"), "application/json")
        await self.storage.put_object(pdf_path, rendered_pdf_bytes, "application/pdf")

        return {
            "document_id": document_id,
            "version_id": version_id,
            "source_language": src_lang,
            "target_language": tgt_lang,
            "status": "COMPLETED",
            "qa_score": qa_score,
            "qa_errors": qa_errors,
            "ir_storage_path": ir_path,
            "pdf_storage_path": pdf_path,
            "pdf_bytes": rendered_pdf_bytes,
            "ir": ir,
        }

