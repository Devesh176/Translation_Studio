import pytest
import fitz  # PyMuPDF
from apps.worker.tasks.pipeline import DocumentTranslationPipeline
from apps.worker.tasks.section_edit import SectionEditPipeline
from packages.storage.object_store.local_store import MemoryObjectStore


@pytest.mark.asyncio
async def test_end_to_end_translation_and_section_edit():
    # 1. Create a synthetic test PDF in memory
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    
    # Add Heading and Paragraph with numbers
    page.insert_text(fitz.Point(50, 70), "Quarterly Financial Overview", fontsize=16)
    page.insert_text(fitz.Point(50, 120), "Total revenue increased by 15.5% to $4.2 million in FY2026.", fontsize=11)
    page.insert_text(fitz.Point(50, 160), "Please review details at https://company.example/report.", fontsize=11)
    
    pdf_bytes = doc.tobytes()
    doc.close()

    # 2. Run DocumentTranslationPipeline
    storage = MemoryObjectStore()
    pipeline = DocumentTranslationPipeline(storage_store=storage)

    result = await pipeline.execute(
        document_id="doc-test-123",
        pdf_bytes=pdf_bytes,
        target_language="hi",
        source_language="en",
    )

    assert result["status"] == "COMPLETED"
    assert result["target_language"] == "hi"
    assert len(result["pdf_bytes"]) > 0
    assert result["qa_score"] > 0.8

    # Verify translated PDF can be opened and parsed
    translated_doc = fitz.open(stream=result["pdf_bytes"], filetype="pdf")
    assert len(translated_doc) == 1
    translated_doc.close()

    # 3. Test Prompt-Edit on a specific section
    ir = result["ir"]
    first_node_id = ir.pages[0].nodes[0].node_id
    version_id = result["version_id"]

    edit_pipeline = SectionEditPipeline(storage_store=storage)
    edit_res = await edit_pipeline.edit_section(
        document_id="doc-test-123",
        current_version_id=version_id,
        node_id=first_node_id,
        user_instruction="Make this heading more formal and punchy.",
    )

    assert edit_res["status"] == "COMPLETED"
    assert edit_res["parent_version_id"] == version_id
    assert edit_res["version_id"] != version_id
    assert len(edit_res["edited_translation"]) > 0
