import hashlib
import json
import re
import uuid
from typing import Dict, Any, List, Optional
from packages.core.domain.node import DocumentIR, DocumentNode, TranslationStatus
from packages.document.ir.serializer import IRSerializer
from packages.providers.openrouter.client import OpenRouterClient
from packages.translation.prompts import PromptManager
from packages.translation.normalizer import TextNormalizer
from packages.rendering.pdf_renderer import PDFRenderer
from packages.validation.invariants import InvariantValidator
from packages.storage.object_store.base import ObjectStore
from packages.core.domain.node import NodeType, NodeStyle, BoundingBox
from packages.costs.ledger import CostCollector, CostLedger
from packages.editing.selection import resolve_selection, node_text, Resolved
from packages.editing.feasibility import check_feasibility
from packages.providers.bodhan.ocr import BodhanOCRProvider
from packages.translation.protected_content import protect, validate_and_restore
import pymupdf

OCR_DPI = 200
MAX_GROWTH = 1.8


class SectionEditPipeline:
    def __init__(self, storage_store: ObjectStore, openrouter_client: Optional[OpenRouterClient] = None):
        self.storage = storage_store
        self.openrouter = openrouter_client or OpenRouterClient()
        self.renderer = PDFRenderer()
        self.ocr = BodhanOCRProvider()

    async def edit_section(
        self,
        document_id: str,
        current_version_id: str,
        node_id: str,
        user_instruction: str,
    ) -> Dict[str, Any]:
        # 1. Load current Document IR
        ir_key = f"documents/{document_id}/versions/{current_version_id}/document.ir.json"
        ir_bytes = await self.storage.get_object(ir_key)
        ir: DocumentIR = IRSerializer.from_json(ir_bytes.decode("utf-8"))

        # 2. Locate target node
        target_node = ir.find_node(node_id)
        if not target_node:
            raise ValueError(f"Node {node_id} not found in document {document_id}")

        # 3. Apply Prompt Edit via OpenRouter using config/prompts.yaml templates
        messages = PromptManager.get_section_edit_messages(
            source_text=target_node.source_text,
            current_translation=target_node.translated_text or target_node.source_text,
            instruction=user_instruction,
            src_lang=ir.source_language or "English",
            tgt_lang=ir.target_language or "Hindi",
        )

        response = await self.openrouter.chat_completion(messages=messages)

        raw_edited = response["choices"][0]["message"]["content"]
        refined_text = TextNormalizer.clean_llm_markdown_wrappers(raw_edited)
        refined_text = TextNormalizer.normalize_indic_text(refined_text)

        # 4. Update Node & edit history
        previous_translation = target_node.translated_text or target_node.source_text
        target_node.translated_text = refined_text
        target_node.translation_status = TranslationStatus.EDITED
        target_node.edit_history.append({
            "instruction": user_instruction,
            "previous_translation": previous_translation,
            "new_translation": refined_text,
        })

        # Validate
        valid_num, _ = InvariantValidator.validate_numbers(target_node.source_text, refined_text)
        target_node.validation_status = "PASS" if valid_num else "WARN_NUM_MISMATCH"

        # 5. Create new immutable version and rerender
        new_version_id = str(uuid.uuid4())
        ir.parent_version_id = current_version_id
        ir.version_id = new_version_id

        orig_key = f"documents/{document_id}/original.pdf"
        original_pdf_bytes = None
        if await self.storage.exists(orig_key):
            original_pdf_bytes = await self.storage.get_object(orig_key)

        is_overlay = ir.classification in ["SCANNED", "MIXED"]
        rendered_pdf_bytes = self.renderer.render_ir_to_pdf(
            ir, original_pdf_bytes=original_pdf_bytes, is_overlay_mode=is_overlay
        )


        # 6. Save new version artifacts
        new_ir_path = f"documents/{document_id}/versions/{new_version_id}/document.ir.json"
        new_pdf_path = f"documents/{document_id}/versions/{new_version_id}/output.pdf"

        await self.storage.put_object(new_ir_path, IRSerializer.to_json(ir).encode("utf-8"), "application/json")
        await self.storage.put_object(new_pdf_path, rendered_pdf_bytes, "application/pdf")

        return {
            "document_id": document_id,
            "version_id": new_version_id,
            "parent_version_id": current_version_id,
            "node_id": node_id,
            "edited_translation": refined_text,
            "status": "COMPLETED",
            "pdf_storage_path": new_pdf_path,
            "ir_storage_path": new_ir_path,
        }


    # ------------------------------------------------------------------ #
    #  Selection based editing (box / text highlight)                      #
    # ------------------------------------------------------------------ #

    async def _ocr_selection(self, ir: DocumentIR, selection: dict, document_id: str, costs: CostCollector) -> int:
        """Scanned/image-only content: OCR the selected region and add the lines as nodes."""
        orig_key = f"documents/{document_id}/original.pdf"
        if not await self.storage.exists(orig_key):
            return 0
        page_no = int(selection["page"])
        page = next((p for p in ir.pages if p.page_number == page_no), None)
        if page is None:
            return 0
        rects = [selection["rect"]] if selection["kind"] == "box" else selection.get("rects") or []
        if not rects:
            return 0
        clip = pymupdf.Rect(min(r[0] for r in rects), min(r[1] for r in rects),
                            max(r[2] for r in rects), max(r[3] for r in rects))
        pdf = pymupdf.open(stream=await self.storage.get_object(orig_key), filetype="pdf")
        try:
            pix = pdf[page_no - 1].get_pixmap(clip=clip, dpi=OCR_DPI)
            img = pix.tobytes("png")
        finally:
            pdf.close()
        res = await self.ocr.extract_page(img, page_number=page_no, document_id=document_id,
                                          language_hint=ir.source_language)
        costs.add("bodhan", "ocr", 0, 0, cost_usd=0.0, purpose="ocr")
        scale = OCR_DPI / 72.0
        added = 0
        for i, b in enumerate(res.blocks):
            text = b.text.strip()
            if not text:
                continue
            bb = BoundingBox(x0=clip.x0 + b.bbox.x0 / scale, y0=clip.y0 + b.bbox.y0 / scale,
                             x1=clip.x0 + b.bbox.x1 / scale, y1=clip.y0 + b.bbox.y1 / scale)
            page.nodes.append(DocumentNode(
                node_id=f"{page.page_id}_sel_ocr_{uuid.uuid4().hex[:6]}", parent_id=page.page_id,
                page_id=page.page_id, page_number=page_no, type=NodeType.PARAGRAPH, bbox=bb,
                reading_order=1000 + i, style=NodeStyle(font_size=max(6.0, min(14.0, bb.height * 0.7))),
                source_text=text, translated_text=text,
                source_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                metadata={"ocr_on_selection": True},
            ))
            added += 1
        return added

    @staticmethod
    def _parse_json_map(raw: str) -> Optional[Dict[str, str]]:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else None

    @staticmethod
    def _rejected(reason: str, category: str, suggestion: str = "", costs: Optional[CostCollector] = None,
                  checked_by: str = "") -> Dict[str, Any]:
        return {"status": "REJECTED", "reason": reason, "category": category, "suggestion": suggestion,
                "checked_by": checked_by, "cost_usd": costs.total if costs else 0.0}

    async def edit_selection(
        self,
        document_id: str,
        current_version_id: str,
        instruction: str,
        selection: Dict[str, Any],
    ) -> Dict[str, Any]:
        costs = CostCollector("edit")
        ledger = CostLedger(self.storage)

        ir_key = f"documents/{document_id}/versions/{current_version_id}/document.ir.json"
        if not await self.storage.exists(ir_key):
            raise ValueError("Version not found.")
        ir: DocumentIR = IRSerializer.from_json((await self.storage.get_object(ir_key)).decode("utf-8"))

        resolved: Resolved = resolve_selection(ir, selection)
        ocr_used = False
        if not resolved.nodes and not resolved.locked and ir.classification in ("SCANNED", "MIXED"):
            if await self._ocr_selection(ir, selection, document_id, costs):
                ocr_used = True
                resolved = resolve_selection(ir, selection)

        tgt = ir.target_language or "Hindi"
        feas = await check_feasibility(resolved, instruction, tgt, self.openrouter, costs)
        if not feas.feasible:
            await ledger.record(document_id, costs, current_version_id)
            return self._rejected(feas.reason or "This request cannot be fulfilled.", feas.category,
                                  feas.suggestion, costs, feas.checked_by)

        # Build items (protected + masked) --------------------------------
        items: List[Dict[str, Any]] = []
        if resolved.span:
            n = resolved.nodes[0]
            prot = protect(resolved.span.text)
            items.append({"id": "s1", "node": n, "old": resolved.span.text, "prot": prot})
        else:
            for i, n in enumerate(resolved.nodes, 1):
                old = node_text(n)
                items.append({"id": f"n{i}", "node": n, "old": old, "prot": protect(old)})
        multi = len(items) > 1
        items_txt = (
            "\n".join(f'[{it["id"]}]\n<<<\n{it["prot"].masked}\n>>>' for it in items)
            if multi else f'<<<\n{items[0]["prot"].masked}\n>>>'
        )
        context = "\n".join(x for x in (resolved.context_before, "[...selected...]", resolved.context_after) if x)
        messages = PromptManager.get_selection_edit_messages(
            items=items_txt, context=context, instruction=instruction,
            src_lang=ir.source_language or "English", tgt_lang=tgt, multi=multi,
        )

        new_masked: Dict[str, str] = {}
        last_err = "The edit could not be validated."
        for attempt in range(2):
            response = await self.openrouter.chat_completion(messages=messages)
            costs.add_llm_response(response, "edit")
            raw = TextNormalizer.clean_llm_markdown_wrappers(response["choices"][0]["message"]["content"])
            if multi:
                data = self._parse_json_map(raw)
                if not data or set(data) != {it["id"] for it in items}:
                    last_err = "The model did not return an edit for every selected paragraph."
                    continue
                outs = data
            else:
                outs = {items[0]["id"]: raw}
            ok = True
            for it in items:
                masked_out = TextNormalizer.normalize_indic_text(outs[it["id"]]).strip()
                restored, errs = validate_and_restore(masked_out, it["prot"].mapping)
                if errs or not restored.strip():
                    ok = False
                    last_err = "The edit would have altered protected content (code, links, names or math)."
                    break
                new_masked[it["id"]] = restored
            if ok:
                break
            new_masked = {}
        if not new_masked:
            await ledger.record(document_id, costs, current_version_id)
            return self._rejected(last_err, "validation", "Try rephrasing the request or select a smaller area.", costs, "validator")

        if all(new_masked[it["id"]].strip() == it["old"].strip() for it in items):
            await ledger.record(document_id, costs, current_version_id)
            return self._rejected("The edit produced no change to the selected text.", "no_change",
                                  "Describe more specifically what should change.", costs, "validator")

        # Apply -------------------------------------------------------------
        warnings: List[str] = []
        changes: List[Dict[str, Any]] = []
        pages = set()
        for it in items:
            n: DocumentNode = it["node"]
            new_text = new_masked[it["id"]]
            before = node_text(n)
            if resolved.span:
                after = before[: resolved.span.start] + new_text + before[resolved.span.end:]
            else:
                after = new_text
            if len(after) > MAX_GROWTH * max(1, len(before)) and len(after) - len(before) > 40:
                warnings.append("The edited text is much longer and may be shrunk or clipped to fit its box.")
            valid_num, _ = InvariantValidator.validate_numbers(n.source_text, after)
            n.validation_status = "PASS" if valid_num else "WARN_NUM_MISMATCH"
            if not valid_num:
                warnings.append("Numbers in the edited text differ from the source.")
            n.translated_text = after
            n.translation_status = TranslationStatus.EDITED
            n.edit_history.append({
                "instruction": instruction, "previous_translation": before, "new_translation": after,
                "selection": {"kind": selection["kind"], "page": selection["page"]},
                "span": [resolved.span.start, resolved.span.end] if resolved.span else None,
            })
            pages.add(n.page_number)
            changes.append({"node_id": n.node_id, "page": n.page_number, "before": before, "after": after})

        new_version_id = str(uuid.uuid4())
        ir.parent_version_id = current_version_id
        ir.version_id = new_version_id

        orig_key = f"documents/{document_id}/original.pdf"
        original_pdf_bytes = await self.storage.get_object(orig_key) if await self.storage.exists(orig_key) else None
        rendered = self.renderer.render_ir_to_pdf(
            ir, original_pdf_bytes=original_pdf_bytes, is_overlay_mode=ir.classification in ["SCANNED", "MIXED"]
        )
        base = f"documents/{document_id}/versions/{new_version_id}"
        await self.storage.put_object(f"{base}/document.ir.json", IRSerializer.to_json(ir).encode("utf-8"), "application/json")
        await self.storage.put_object(f"{base}/output.pdf", rendered, "application/pdf")
        await ledger.record(document_id, costs, new_version_id)

        return {
            "status": "COMPLETED",
            "document_id": document_id,
            "version_id": new_version_id,
            "parent_version_id": current_version_id,
            "changed_pages": sorted(pages),
            "changes": changes,
            "warnings": sorted(set(warnings)),
            "ocr_used": ocr_used,
            "cost_usd": costs.total,
        }
