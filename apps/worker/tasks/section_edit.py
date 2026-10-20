import uuid
from typing import Dict, Any, Optional
from packages.core.domain.node import DocumentIR, DocumentNode, TranslationStatus
from packages.document.ir.serializer import IRSerializer
from packages.providers.openrouter.client import OpenRouterClient
from packages.translation.prompts import PromptManager
from packages.translation.normalizer import TextNormalizer
from packages.rendering.pdf_renderer import PDFRenderer
from packages.validation.invariants import InvariantValidator
from packages.storage.object_store.base import ObjectStore


class SectionEditPipeline:
    def __init__(self, storage_store: ObjectStore, openrouter_client: Optional[OpenRouterClient] = None):
        self.storage = storage_store
        self.openrouter = openrouter_client or OpenRouterClient()
        self.renderer = PDFRenderer()

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
