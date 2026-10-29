import asyncio
import os
import time
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
from packages.costs.ledger import CostCollector, CostLedger, estimate_tokens
from packages.semantic.units import build_units, join_text, union_bbox, GroupingConfig
from packages.semantic.segments import split_segments, is_label_like, glossary_hash
from packages.semantic.qa import check_unit, llm_review
from packages.core.config_loader import get_glossary
from packages.translation.normalizer import TextNormalizer
from packages.translation.protected_content import protect, validate_and_restore
from packages.validation.invariants import InvariantValidator
from packages.validation.visual import VisualQAValidator
from packages.rendering.pdf_renderer import PDFRenderer
from packages.storage.object_store.local_store import LocalFileObjectStore
from packages.storage.redis.cache import TranslationCache

# Observability
from packages.observability.logging import get_logger
from packages.observability.tracing import get_tracer
from packages.observability.metrics import (
    ACTIVE_JOBS,
    DOCUMENTS_PROCESSED_TOTAL,
    FONT_MISSING_GLYPH_TOTAL,
    LAYOUT_OVERFLOW_TOTAL,
    OCR_LATENCY_SECONDS,
    OCR_PAGES_TOTAL,
    OCR_PROVIDER_FAILURES_TOTAL,
    PIPELINE_DURATION_SECONDS,
    RENDER_FAILURES_TOTAL,
    RENDER_LATENCY_SECONDS,
    RENDER_PAGES_TOTAL,
    ROUTING_DECISIONS_TOTAL,
    TRANSLATION_CACHE_HITS_TOTAL,
    TRANSLATION_CACHE_MISSES_TOTAL,
    TRANSLATION_COST_USD_TOTAL,
    TRANSLATION_INPUT_TOKENS_TOTAL,
    TRANSLATION_LATENCY_SECONDS,
    TRANSLATION_OUTPUT_TOKENS_TOTAL,
    TRANSLATION_PROVIDER_FAILURES_TOTAL,
    TRANSLATION_REQUESTS_TOTAL,
    TRANSLATION_RETRIES_TOTAL,
    VALIDATION_FAILURES_TOTAL,
    VISUAL_QA_FAILURES_TOTAL,
    VISUAL_QA_SCORE_HISTOGRAM,
)

logger = get_logger(__name__)
tracer = get_tracer(__name__)


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
        pipeline_start = time.perf_counter()
        ACTIVE_JOBS.inc()

        with tracer.start_as_current_span("document_translation_pipeline") as root_span:
            root_span.set_attribute("document.id", document_id)
            root_span.set_attribute("target_language", target_language)
            if source_language:
                root_span.set_attribute("source_language", source_language)

            logger.info(
                "pipeline_started",
                document_id=document_id,
                target_language=target_language,
                source_language=source_language,
            )

            try:
                result = await self._run(
                    document_id=document_id,
                    pdf_bytes=pdf_bytes,
                    target_language=target_language,
                    source_language=source_language,
                    user_requested_provider=user_requested_provider,
                    root_span=root_span,
                )

                duration = time.perf_counter() - pipeline_start
                DOCUMENTS_PROCESSED_TOTAL.labels(status="COMPLETED").inc()
                PIPELINE_DURATION_SECONDS.labels(status="COMPLETED").observe(duration)

                logger.info(
                    "pipeline_completed",
                    document_id=document_id,
                    version_id=result.get("version_id"),
                    source_language=result.get("source_language"),
                    target_language=result.get("target_language"),
                    qa_score=result.get("qa_score"),
                    cost_usd=result.get("cost_usd"),
                    duration_ms=round(duration * 1000, 1),
                )
                return result

            except Exception as exc:
                duration = time.perf_counter() - pipeline_start
                DOCUMENTS_PROCESSED_TOTAL.labels(status="FAILED").inc()
                PIPELINE_DURATION_SECONDS.labels(status="FAILED").observe(duration)
                logger.error(
                    "pipeline_failed",
                    document_id=document_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    duration_ms=round(duration * 1000, 1),
                )
                root_span.set_attribute("error", True)
                root_span.set_attribute("error.message", str(exc))
                raise
            finally:
                ACTIVE_JOBS.dec()

    async def _run(
        self,
        document_id: str,
        pdf_bytes: bytes,
        target_language: str,
        source_language: Optional[str],
        user_requested_provider: Optional[str],
        root_span: Any,
    ) -> Dict[str, Any]:
        tgt_lang = normalize_language_code(target_language)
        costs = CostCollector("translate")

        # ------------------------------------------------------------------
        # 1. Parse PDF → Document IR
        # ------------------------------------------------------------------
        with tracer.start_as_current_span("parse_pdf") as span:
            span.set_attribute("document.id", document_id)
            logger.info("parsing_pdf", document_id=document_id, pdf_size_bytes=len(pdf_bytes))
            ir: DocumentIR = self.parser.parse(pdf_bytes, document_id=document_id)
            span.set_attribute("page_count", ir.total_pages)
            span.set_attribute("classification", ir.classification)

        src_lang = normalize_language_code(source_language or ir.source_language or "en")
        ir.source_language = src_lang
        ir.target_language = tgt_lang
        root_span.set_attribute("source_language", src_lang)

        logger.info(
            "pdf_parsed",
            document_id=document_id,
            pages=ir.total_pages,
            classification=ir.classification,
            source_language=src_lang,
        )

        # ------------------------------------------------------------------
        # 1b. OCR fallback for scanned/image pages
        # ------------------------------------------------------------------
        with tracer.start_as_current_span("ocr_fallback") as span:
            empty_pages = [p for p in ir.pages if len(p.nodes) == 0]
            span.set_attribute("empty_page_count", len(empty_pages))

            if empty_pages:
                await self._run_ocr_on_empty_pages(
                    ir=ir,
                    pdf_bytes=pdf_bytes,
                    document_id=document_id,
                    src_lang=src_lang,
                )

        # ------------------------------------------------------------------
        # 2. Cost guard
        # ------------------------------------------------------------------
        with tracer.start_as_current_span("cost_guard"):
            total_text = " ".join([n.source_text for n in ir.get_all_nodes()])
            self.cost_guard.check_and_estimate_cost(total_text, tgt_lang)

        # ------------------------------------------------------------------
        # 3. Route & Translate nodes
        # ------------------------------------------------------------------
        with tracer.start_as_current_span("translate_document") as span:
            all_nodes = ir.get_all_nodes()
            translatable = [n for n in all_nodes if n.source_text.strip()]
            span.set_attribute("translatable_node_count", len(translatable))

            logger.info(
                "translation_started",
                document_id=document_id,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                node_count=len(translatable),
            )

            runs = build_units(ir, GroupingConfig())
            grouped = [r for r in runs if len(r) > 1]
            logger.info("stu_built", document_id=document_id, nodes=len(all_nodes), units=len(runs),
                        grouped_units=len(grouped), max_nodes_per_unit=max((len(r) for r in runs), default=0))
            glossary = get_glossary(tgt_lang)
            heading = ""
            unit_texts = [join_text([n.source_text for n in r]) if len(r) > 1 else r[0].source_text for r in runs]
            semantic_flags = 0
            for idx, run in enumerate(runs):
                lead = run[0]
                override = None
                if lead.type == NodeType.HEADING:
                    heading = lead.source_text.strip()
                if len(run) > 1:
                    uid = f"stu_{lead.node_id}"
                    override = unit_texts[idx]
                    lead.metadata["stu"] = {"unit_id": uid, "role": "lead", "member_ids": [n.node_id for n in run[1:]],
                                            "union_bbox": union_bbox(run),
                                            "grouping": [dict(n.metadata.get("grouping", {}), node_id=n.node_id) for n in run[1:]]}
                    for m in run[1:]:
                        m.metadata["stu"] = {"unit_id": uid, "role": "member", "lead_id": lead.node_id}
                        m.translated_text = ""
                        m.translation_status = TranslationStatus.TRANSLATED
                        m.validation_status = "PASS"
                prose = lead.type in (NodeType.PARAGRAPH, NodeType.LIST_ITEM)
                prev_t = next((unit_texts[j] for j in range(idx - 1, -1, -1)
                               if runs[j][0].page_number == lead.page_number and runs[j][0].type != NodeType.CODE_BLOCK), "") if prose else ""
                next_t = next((unit_texts[j] for j in range(idx + 1, len(runs))
                               if runs[j][0].page_number == lead.page_number and runs[j][0].type != NodeType.CODE_BLOCK), "") if prose else ""
                ctx = {"heading": heading, "previous": prev_t[-400:], "following": next_t[:400],
                       "glossary": {k: v for k, v in glossary.items() if k.lower() in (override or lead.source_text).lower()}}
                await self._translate_node(
                    node=lead,
                    document_id=document_id,
                    src_lang=src_lang,
                    tgt_lang=tgt_lang,
                    user_requested_provider=user_requested_provider,
                    costs=costs,
                    text_override=override,
                    unit_ctx=ctx,
                )
                if lead.translation_status == TranslationStatus.TRANSLATED and prose and lead.translated_text:
                    src_t = override or lead.source_text
                    seg_ids = (lead.metadata.get("alignment") or {}).get("segment_ids")
                    findings = check_unit(src_t, lead.translated_text, ctx["glossary"], src_lang=src_lang, tgt_lang=tgt_lang)
                    if any(f["severity"] in ("medium", "high") for f in findings) and self.openrouter_provider.client.api_key:
                        findings += await llm_review(self.openrouter_provider.client, src_t, lead.translated_text,
                                                     ctx["glossary"], f"{prev_t[-200:]}\n...\n{next_t[:200:]}",
                                                     src_lang, tgt_lang, costs)
                    if findings:
                        lead.metadata["semantic_findings"] = findings
                        semantic_flags += 1
                        logger.warning("semantic_findings", document_id=document_id, node_id=lead.node_id,
                                       categories=[f["category"] for f in findings])
            logger.info("semantic_qa_completed", document_id=document_id, flagged_units=semantic_flags,
                        alignment_uncertain=sum(1 for n in all_nodes if (n.metadata.get("alignment") or {}).get("confidence", 1) < 1))

        # ------------------------------------------------------------------
        # 5. Render translated PDF
        # ------------------------------------------------------------------
        with tracer.start_as_current_span("render_pdf") as span:
            is_overlay = ir.classification in ["SCANNED", "MIXED"]
            span.set_attribute("is_overlay_mode", is_overlay)
            span.set_attribute("page_count", ir.total_pages)

            render_start = time.perf_counter()
            logger.info("rendering_started", document_id=document_id, overlay_mode=is_overlay)

            try:
                rendered_pdf_bytes = self.renderer.render_ir_to_pdf(
                    ir, original_pdf_bytes=pdf_bytes, is_overlay_mode=is_overlay
                )
                render_duration = time.perf_counter() - render_start
                RENDER_LATENCY_SECONDS.observe(render_duration)
                RENDER_PAGES_TOTAL.labels(status="success").inc(ir.total_pages)
                logger.info(
                    "rendering_completed",
                    document_id=document_id,
                    output_size_bytes=len(rendered_pdf_bytes),
                    duration_ms=round(render_duration * 1000, 1),
                )
            except Exception as exc:
                RENDER_FAILURES_TOTAL.labels(failure_code="RENDER_ERROR").inc()
                logger.error("rendering_failed", document_id=document_id, error=str(exc))
                raise

        # ------------------------------------------------------------------
        # 6. Visual QA
        # ------------------------------------------------------------------
        with tracer.start_as_current_span("visual_qa") as span:
            logger.info("visual_qa_started", document_id=document_id)
            is_render_valid, qa_errors, qa_score = VisualQAValidator.inspect_rendered_pdf(
                rendered_pdf_bytes, ir
            )
            VISUAL_QA_SCORE_HISTOGRAM.observe(qa_score)
            span.set_attribute("qa_score", qa_score)
            span.set_attribute("qa_valid", is_render_valid)

            for err in qa_errors:
                VISUAL_QA_FAILURES_TOTAL.labels(failure_code=err).inc()

            log_fn = logger.info if is_render_valid else logger.warning
            log_fn(
                "visual_qa_completed",
                document_id=document_id,
                qa_score=qa_score,
                qa_valid=is_render_valid,
                qa_errors=qa_errors,
            )

        # ------------------------------------------------------------------
        # 7. Store artifacts
        # ------------------------------------------------------------------
        with tracer.start_as_current_span("store_artifacts"):
            version_id = str(uuid.uuid4())
            ir_json = IRSerializer.to_json(ir)

            ir_path = f"documents/{document_id}/versions/{version_id}/document.ir.json"
            pdf_path = f"documents/{document_id}/versions/{version_id}/output.pdf"

            await self.storage.put_object(ir_path, ir_json.encode("utf-8"), "application/json")
            await self.storage.put_object(pdf_path, rendered_pdf_bytes, "application/pdf")
            await CostLedger(self.storage).record(document_id, costs, version_id)

            logger.info(
                "artifacts_stored",
                document_id=document_id,
                version_id=version_id,
                ir_path=ir_path,
                pdf_path=pdf_path,
            )

        return {
            "cost_usd": costs.total,
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

    # -----------------------------------------------------------------------
    # OCR helper
    # -----------------------------------------------------------------------

    async def _run_ocr_on_empty_pages(
        self,
        ir: DocumentIR,
        pdf_bytes: bytes,
        document_id: str,
        src_lang: str,
    ) -> None:
        """Run Bodhan OCR on pages that have no native text nodes."""
        try:
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_idx, page in enumerate(ir.pages):
                if len(page.nodes) > 0 or page_idx >= len(pdf_doc):
                    continue

                with tracer.start_as_current_span("ocr_page") as span:
                    span.set_attribute("page_number", page.page_number)
                    span.set_attribute("document.id", document_id)
                    ocr_start = time.perf_counter()

                    try:
                        pix = pdf_doc[page_idx].get_pixmap()
                        img_bytes = pix.tobytes("png")
                        ocr_res = await self.ocr_provider.extract_page(
                            img_bytes,
                            page_number=page.page_number,
                            document_id=document_id,
                            language_hint=src_lang,
                        )
                        ocr_duration = time.perf_counter() - ocr_start
                        OCR_LATENCY_SECONDS.labels(provider="bodhan").observe(ocr_duration)
                        OCR_PAGES_TOTAL.labels(provider="bodhan", status="success").inc()

                        if ocr_res.confidence is not None:
                            from packages.observability.metrics import OCR_CONFIDENCE_HISTOGRAM
                            OCR_CONFIDENCE_HISTOGRAM.labels(provider="bodhan").observe(ocr_res.confidence)

                        logger.info(
                            "ocr_page_completed",
                            document_id=document_id,
                            page_number=page.page_number,
                            block_count=len(ocr_res.blocks),
                            confidence=ocr_res.confidence,
                            duration_ms=round(ocr_duration * 1000, 1),
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

                    except Exception as exc:
                        OCR_PAGES_TOTAL.labels(provider="bodhan", status="error").inc()
                        OCR_PROVIDER_FAILURES_TOTAL.labels(
                            provider="bodhan", failure_code=type(exc).__name__
                        ).inc()
                        logger.error(
                            "ocr_page_failed",
                            document_id=document_id,
                            page_number=page.page_number,
                            error=str(exc),
                        )

            pdf_doc.close()
        except Exception as exc:
            logger.error("ocr_fallback_failed", document_id=document_id, error=str(exc))

    # -----------------------------------------------------------------------
    # Translation helper
    # -----------------------------------------------------------------------

    async def _translate_node(
        self,
        node: DocumentNode,
        document_id: str,
        src_lang: str,
        tgt_lang: str,
        user_requested_provider: Optional[str],
        costs: CostCollector,
        text_override: Optional[str] = None,
        unit_ctx: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Translate a single DocumentNode (or its STU text) in-place, recording all metrics."""
        src_text = text_override if text_override is not None else node.source_text

        if not src_text.strip():
            return

        # Skip non-translatable node types
        if node.type == NodeType.CODE_BLOCK or node.metadata.get("is_code") or node.metadata.get("math_only"):
            node.translated_text = node.source_text
            node.translation_status = TranslationStatus.SKIPPED
            node.validation_status = "PASS"
            return

        protected = protect(src_text)
        node.metadata["protected_tokens"] = protected.mapping

        # If nothing translatable remains after protecting tokens, skip
        if not re.search(r"[^\W\d_]", re.sub(r"\u27e6P\d+\u27e7", "", protected.masked)):
            node.translated_text = src_text
            node.translation_status = TranslationStatus.SKIPPED
            node.validation_status = "PASS"
            return

        unit_ctx = unit_ctx or {}
        glossary = unit_ctx.get("glossary") or {}
        ctx_sig = "g" + glossary_hash(glossary) + (
            "|c" + glossary_hash({"p": unit_ctx.get("previous", "")[-120:], "n": unit_ctx.get("following", "")[:120:],
                                  "h": unit_ctx.get("heading", "")}) if unit_ctx.get("previous") or unit_ctx.get("following")
            or unit_ctx.get("heading") else "")
        routing = self.router.route(
            source_language=src_lang,
            target_language=tgt_lang,
            user_requested_provider=user_requested_provider,
        )
        ROUTING_DECISIONS_TOTAL.labels(
            provider=routing.provider,
            reason=getattr(routing, "reason", "policy"),
        ).inc()

        # Cache lookup
        cache_key = TranslationCache.compute_cache_key(
            source_text=protected.masked,
            source_language=src_lang,
            target_language=tgt_lang,
            provider=routing.provider,
            model=routing.model or "native",
            prompt_version="v3",
            terminology_version=ctx_sig,
        )
        cached = await self.cache.get(cache_key)

        masked_out = cached
        if masked_out is not None and validate_and_restore(masked_out, protected.mapping)[1]:
            masked_out = None  # stale/poisoned cache entry

        if masked_out is not None:
            TRANSLATION_CACHE_HITS_TOTAL.inc()
        else:
            TRANSLATION_CACHE_MISSES_TOTAL.inc()

        # Translation attempts with retry
        failed_errors: list = []
        if masked_out is None:
            req = TranslationRequest(
                node_id=node.node_id,
                source_text=protected.masked,
                source_language=src_lang,
                target_language=tgt_lang,
                node_type=node.type,
                spans=node.spans,
                terminology=glossary,
                context_before=unit_ctx.get("previous"),
                context_after=unit_ctx.get("following"),
            )
            segs = split_segments(protected.masked) if len(protected.masked) > 80 else []
            if len(segs) > 1:
                req.segments = segs
                req.context = {"heading": unit_ctx.get("heading", ""), "previous_paragraph": unit_ctx.get("previous", ""),
                               "following_paragraph": unit_ctx.get("following", ""), "glossary": glossary}
            errors: list = []
            attempts = (
                ["bodhan"] * 4 + ["openrouter"]
                if routing.provider == "bodhan"
                else ["openrouter"] * 2
            )

            for attempt, prov in enumerate(attempts):
                if attempt > 0:
                    TRANSLATION_RETRIES_TOTAL.labels(provider=prov).inc()

                t_start = time.perf_counter()
                try:
                    provider_obj = (
                        self.bodhan_provider if prov == "bodhan" else self.openrouter_provider
                    )
                    result = await provider_obj.translate(req)
                    if prov == "openrouter" and req.segments and not (result.raw_response or {}).get("alignment"):
                        node.metadata["alignment"] = {"mode": "paragraph", "confidence": 0.5,
                                                      "issue": "segment_contract_unavailable"}
                    elif (result.raw_response or {}).get("alignment"):
                        node.metadata["alignment"] = (result.raw_response or {})["alignment"]
                    elif prov == "bodhan" and req.segments:
                        node.metadata["alignment"] = {"mode": "paragraph", "confidence": 0.5,
                                                      "issue": "provider_has_no_segment_contract"}
                    t_dur = time.perf_counter() - t_start
                    TRANSLATION_LATENCY_SECONDS.labels(provider=prov).observe(t_dur)

                except Exception as exc:
                    t_dur = time.perf_counter() - t_start
                    TRANSLATION_PROVIDER_FAILURES_TOTAL.labels(
                        provider=prov, failure_code=type(exc).__name__
                    ).inc()
                    logger.warning(
                        "translation_attempt_failed",
                        document_id=document_id,
                        node_id=node.node_id,
                        provider=prov,
                        attempt=attempt,
                        error=str(exc),
                    )
                    errors = [f"PROVIDER_ERROR:{type(exc).__name__}"]
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

                # Record cost / token metrics
                if result.estimated_cost_usd is not None:
                    costs.add(
                        result.provider, result.model,
                        result.input_tokens or 0,
                        result.output_tokens or 0,
                        cost_usd=result.estimated_cost_usd,
                        purpose="translate",
                    )
                    TRANSLATION_COST_USD_TOTAL.labels(provider=prov).inc(result.estimated_cost_usd)
                else:
                    in_tok = estimate_tokens(protected.masked)
                    out_tok = estimate_tokens(result.translated_text)
                    costs.add(result.provider, result.model, in_tok, out_tok, purpose="translate")

                if result.input_tokens:
                    TRANSLATION_INPUT_TOKENS_TOTAL.labels(provider=prov).inc(result.input_tokens)
                if result.output_tokens:
                    TRANSLATION_OUTPUT_TOKENS_TOTAL.labels(provider=prov).inc(result.output_tokens)

                masked_out = TextNormalizer.normalize_indic_text(
                    TextNormalizer.clean_llm_markdown_wrappers(result.translated_text)
                )
                _, errors = validate_and_restore(masked_out, protected.mapping)
                if (not errors and src_lang != tgt_lang and masked_out.strip() == protected.masked.strip()
                        and not is_label_like(protected.masked)):
                    errors = ["UNTRANSLATED_ECHO"]

                if not errors:
                    TRANSLATION_REQUESTS_TOTAL.labels(
                        provider=prov,
                        source_language=src_lang,
                        target_language=tgt_lang,
                        status="success",
                    ).inc()
                    break

                await asyncio.sleep(0.3)

            if errors:
                TRANSLATION_REQUESTS_TOTAL.labels(
                    provider=routing.provider,
                    source_language=src_lang,
                    target_language=tgt_lang,
                    status="failed",
                ).inc()
                failed_errors = errors
                if masked_out is None:
                    masked_out = protected.masked
            else:
                await self.cache.set(cache_key, masked_out)

        # Restore protected tokens
        restored, perrors = validate_and_restore(masked_out, protected.mapping)
        if perrors:
            node.metadata["protected_errors"] = perrors
            node.metadata["raw_output"] = masked_out
            node.translated_text = src_text
            node.translation_status = TranslationStatus.FAILED
            node.validation_status = "FAIL_PROTECTED_TOKENS"
            VALIDATION_FAILURES_TOTAL.labels(check_type="protected_tokens").inc()
            logger.warning(
                "protected_token_restore_failed",
                document_id=document_id,
                node_id=node.node_id,
                errors=perrors,
            )
            return

        node.translated_text = restored

        if failed_errors:
            node.metadata["translation_errors"] = failed_errors
            node.translation_status = TranslationStatus.FAILED
            node.validation_status = "FAIL_UNTRANSLATED"
            return

        node.translation_status = TranslationStatus.TRANSLATED

        # Invariant validation
        if not node.translated_text.strip():
            node.validation_status = "FAIL_EMPTY"
            VALIDATION_FAILURES_TOTAL.labels(check_type="empty_translation").inc()
        elif TextNormalizer.has_sentinel(node.translated_text):
            node.validation_status = "FAIL_SENTINEL_LEAK"
            VALIDATION_FAILURES_TOTAL.labels(check_type="sentinel_leak").inc()
        else:
            valid_num, _ = InvariantValidator.validate_numbers(src_text, node.translated_text)
            valid_urls, _ = InvariantValidator.validate_urls_and_emails(src_text, node.translated_text)
            if valid_num and valid_urls:
                node.validation_status = "PASS"
            elif not valid_num:
                node.validation_status = "WARN_NUM_MISMATCH"
                VALIDATION_FAILURES_TOTAL.labels(check_type="number_mismatch").inc()
            else:
                node.validation_status = "WARN_URL_MISMATCH"
                VALIDATION_FAILURES_TOTAL.labels(check_type="url_mismatch").inc()
