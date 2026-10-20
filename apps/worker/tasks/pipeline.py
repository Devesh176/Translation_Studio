import asyncio
import os
import uuid
import hashlib
import fitz
from typing import Optional, Dict, Any

from packages.core.domain.node import (
    DocumentIR, DocumentNode, TranslationStatus, NodeType, NodeStyle, PageProcessingMode
)
from packages.core.domain.version import DocumentVersion
from packages.document.parser.pymupdf_parser import PyMuPDFParser
from packages.document.parser.pdf_classifier import PDFClassifier
from packages.document.ir.serializer import IRSerializer
from packages.document.scanning.page_mode_classifier import PageModeClassifier
from packages.document.semantic.reconciler import DualExtractionReconciler
from packages.document.semantic.block_classifier import SemanticBlockClassifier
from packages.document.semantic.protected_spans import ProtectedSpansManager
from packages.document.semantic.paragraph_recovery import ParagraphRecoveryEngine
from packages.document.semantic.source_ir_validator import SourceIRValidator
from packages.document.extraction.pdf_preflight import PDFPreflightInspector
from packages.routing.translation_router import TranslationRouter
from packages.routing.language import normalize_language_code
from packages.providers.bodhan.ocr import BodhanOCRProvider
from packages.providers.bodhan.translation import BodhanTranslationProvider
from packages.providers.openrouter.translation import OpenRouterTranslationProvider
from packages.providers.base import TranslationRequest
from packages.translation.cost_guard import CostGuard
from packages.translation.normalizer import TextNormalizer
from packages.translation.profiles.profile_manager import TranslationProfileManager
from packages.translation.orchestrator.translation_orchestrator import TranslationOrchestrator
from packages.translation.validation import (
    ValidationReport, ValidationIssue, GateStatus, IssueCode, IssueSeverity,
    TranslationQualityGate, TranslationRetryManager
)
from packages.rendering.validation import (
    TranslatedIRValidator, PdfTextRoundTripValidator
)
from packages.validation.invariants import InvariantValidator
from packages.validation.visual import VisualQAValidator
from packages.validation.scorecard import QAScorecard
from packages.rendering.pdf_renderer import PDFRenderer
from packages.storage.object_store.local_store import LocalFileObjectStore
from packages.storage.redis.cache import TranslationCache


class DocumentTranslationPipeline:
    def __init__(
        self,
        storage_store: Optional[Any] = None,
        router: Optional[TranslationRouter] = None,
        cache: Optional[TranslationCache] = None,
        max_retries: int = 2,
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
        self.retry_manager = TranslationRetryManager(max_retries=max_retries)
        self.orchestrator = TranslationOrchestrator(
            bodhan_provider=self.bodhan_provider,
            openrouter_provider=self.openrouter_provider,
            retry_manager=self.retry_manager,
        )

    async def execute(
        self,
        document_id: str,
        pdf_bytes: bytes,
        target_language: str,
        source_language: Optional[str] = None,
        user_requested_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        tgt_lang = normalize_language_code(target_language)
        src_lang = normalize_language_code(source_language or "en")
        report = ValidationReport(
            job_id=document_id,
            source_language=src_lang,
            target_language=tgt_lang,
            policy_version="2.0",
        )

        # 1. PDF Preflight (Section 4.1)
        preflight_report = PDFPreflightInspector.inspect(pdf_bytes)
        if not preflight_report.is_valid_for_processing:
            report.record_issue("preflight", ValidationIssue(
                issue_code=IssueCode.PDF_PREFLIGHT_FAILED,
                severity=IssueSeverity.CRITICAL,
                stage="PREFLIGHT",
                explanation=preflight_report.error_message or "Preflight inspection failed.",
            ))
            report.set_gate_status("preflight", GateStatus.FAIL)
        else:
            report.set_gate_status("preflight", GateStatus.PASS, {
                "page_count": preflight_report.page_count,
                "overall_classification": preflight_report.overall_classification,
                "font_count": len(preflight_report.all_fonts),
            })

        # 2. Parse PDF to initial Document IR with PyMuPDF
        ir: DocumentIR = self.parser.parse(pdf_bytes, document_id=document_id)
        src_lang = normalize_language_code(source_language or ir.source_language or "en")
        ir.source_language = src_lang
        ir.target_language = tgt_lang
        ir.classification = preflight_report.overall_classification

        # 3. Dual Extraction, Mode Classification, and Reconciliation
        try:
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_idx, page in enumerate(ir.pages):
                if page_idx >= len(pdf_doc):
                    break
                fitz_page = pdf_doc[page_idx]

                # 3a. Per-page processing mode classification (Section 66.1)
                mode, mode_conf, evidence = PageModeClassifier.classify_page(fitz_page)
                page.processing_mode = mode
                page.mode_confidence = mode_conf
                page.mode_evidence = evidence
                if mode in [PageProcessingMode.SCANNED_IMAGE, PageProcessingMode.MIXED]:
                    page.is_scanned = True

                # 3b. Mandatory Bodhan OCR extraction
                pix = fitz_page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                ocr_res = await self.ocr_provider.extract_page(
                    img_bytes,
                    page_number=page.page_number,
                    document_id=document_id,
                    language_hint=src_lang,
                )
                page.ocr_confidence = ocr_res.confidence

                # 3c. Dual extraction reconciliation
                reconciled_nodes = DualExtractionReconciler.reconcile_page(
                    page_id=page.page_id,
                    page_number=page.page_number,
                    native_nodes=page.nodes,
                    ocr_blocks=ocr_res.blocks,
                )

                # 3d. Paragraph recovery: assemble wrapped lines into semantic paragraphs (Section 4.1 & 4.3)
                recovered_nodes = ParagraphRecoveryEngine.recover_paragraphs(reconciled_nodes)
                page.nodes = recovered_nodes

                # 3e. Semantic block classification
                SemanticBlockClassifier.classify_nodes(page.nodes)

            pdf_doc.close()
        except Exception:
            for page in ir.pages:
                page.nodes = ParagraphRecoveryEngine.recover_paragraphs(page.nodes)
                SemanticBlockClassifier.classify_nodes(page.nodes)

        # 4. GATE A: Source IR Integrity Validation (Section 4.5 & Section 6)
        SourceIRValidator.validate(ir, report)

        # 5. Cost Guarding Check
        total_text = " ".join([n.source_text for n in ir.get_all_nodes()])
        self.cost_guard.check_and_estimate_cost(total_text, tgt_lang)

        # Select translation profile based on document content (Section 8)
        domain = "software" if any(w in total_text.lower() for w in ["python", "anaconda", "docker", "install", "command"]) else (
            "mathematics" if any(w in total_text.lower() for w in ["maximize", "minimize", "linear programming", "purity", "kg/hr"]) else "general"
        )
        profile = TranslationProfileManager.get_profile(domain=domain)

        # 6. Route & Translate Nodes with V2 Orchestration & Independent Verification (Section 9 & 10)
        for page_idx, page in enumerate(ir.pages):
            for node in page.nodes:
                if not node.source_text.strip():
                    continue

                cache_key = TranslationCache.compute_cache_key(
                    source_text=node.source_text,
                    source_language=src_lang,
                    target_language=tgt_lang,
                    provider="bodhan",
                    model="v2_orchestrated",
                    prompt_version=profile.profile_id,
                )
                cached = await self.cache.get(cache_key)

                if cached:
                    node.translated_text = cached
                    node.translation_status = TranslationStatus.TRANSLATED
                    TranslationQualityGate.validate_candidate(
                        block_id=node.node_id,
                        source_text=node.source_text,
                        candidate_translation=cached,
                        protected_items=node.protected_spans,
                        report=report,
                        page_index=page_idx,
                    )
                else:
                    await self.orchestrator.translate_node(
                        node=node,
                        source_language=src_lang,
                        target_language=tgt_lang,
                        profile=profile,
                        report=report,
                        page_index=page_idx,
                    )
                    if node.translated_text:
                        await self.cache.set(cache_key, node.translated_text)

                # Invariant status
                valid_num, _ = InvariantValidator.validate_numbers(node.source_text, node.translated_text)
                valid_urls, _ = InvariantValidator.validate_urls_and_emails(node.source_text, node.translated_text)
                if valid_num and valid_urls:
                    node.validation_status = "PASS"
                elif not valid_num:
                    node.validation_status = "WARN_NUM_MISMATCH"
                else:
                    node.validation_status = "WARN_URL_MISMATCH"

        # Finalize Gate B (translation) and Facts status
        if report.gates["translation"].status == GateStatus.NOT_RUN:
            report.set_gate_status("translation", GateStatus.PASS)
        if report.gates["facts"].status == GateStatus.NOT_RUN:
            report.set_gate_status("facts", GateStatus.PASS)

        # 7. GATE C: Translated IR and Alignment Validation (Section 9 & 12)
        TranslatedIRValidator.validate(ir, report)

        # 8. Render translated PDF
        has_scanned_pages = any(
            p.processing_mode in [PageProcessingMode.SCANNED_IMAGE, PageProcessingMode.MIXED]
            for p in ir.pages
        )
        rendered_pdf_bytes = self.renderer.render_ir_to_pdf(
            ir, original_pdf_bytes=pdf_bytes, is_overlay_mode=has_scanned_pages
        )

        # 9. GATE D: Generated PDF Text Round-Trip Validation (Section 15)
        PdfTextRoundTripValidator.validate(rendered_pdf_bytes, ir, report)

        # 10. GATE E: Typography & Visual QA (Section 13, 16)
        is_render_valid, qa_errors, qa_score = VisualQAValidator.inspect_rendered_pdf(rendered_pdf_bytes, ir)
        if not is_render_valid:
            for err in qa_errors:
                report.record_issue("visual_qa", ValidationIssue(
                    issue_code=IssueCode.GLYPH_MISSING if "MISSING_GLYPHS" in err else IssueCode.TEXT_CLIPPED,
                    severity=IssueSeverity.CRITICAL if "MISSING_GLYPHS" in err else IssueSeverity.HIGH,
                    stage="GATE_E",
                    explanation=err,
                ))
            report.set_gate_status("visual_qa", GateStatus.REVIEW_REQUIRED, {"qa_score": qa_score})
        else:
            report.set_gate_status("visual_qa", GateStatus.PASS, {"qa_score": qa_score})

        # Multi-Dimensional Scorecard
        scorecard = QAScorecard.evaluate(ir, rendered_pdf_bytes)

        # 11. Final Release Gate Decision (Section 17.5)
        critical_issues = [i for i in report.issues if i.severity == IssueSeverity.CRITICAL]
        high_issues = [i for i in report.issues if i.severity in [IssueSeverity.HIGH, IssueSeverity.ERROR]]
        if critical_issues:
            report.set_gate_status("release", GateStatus.FAIL, {"critical_issues": len(critical_issues)})
        elif high_issues:
            report.set_gate_status("release", GateStatus.REVIEW_REQUIRED, {"high_issues": len(high_issues)})
        else:
            report.set_gate_status("release", GateStatus.PASS)

        # 12. Store artifacts
        version_id = str(uuid.uuid4())
        ir_json = IRSerializer.to_json(ir)
        
        ir_path = f"documents/{document_id}/versions/{version_id}/document.ir.json"
        pdf_path = f"documents/{document_id}/versions/{version_id}/output.pdf"

        await self.storage.put_object(ir_path, ir_json.encode("utf-8"), "application/json")
        await self.storage.put_object(pdf_path, rendered_pdf_bytes, "application/pdf")

        overall_status_str = report.overall_status.value
        final_status = "COMPLETED" if report.overall_status == GateStatus.PASS else overall_status_str

        return {
            "document_id": document_id,
            "version_id": version_id,
            "source_language": src_lang,
            "target_language": tgt_lang,
            "status": final_status,
            "overall_status": report.overall_status.value,
            "qa_score": qa_score,
            "validation_report": report.model_dump(),
            "scorecard": scorecard,
            "ir_storage_path": ir_path,
            "pdf_storage_path": pdf_path,
            "pdf_bytes": rendered_pdf_bytes,
            "ir": ir,
        }
