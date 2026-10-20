import pytest
import fitz
from packages.core.domain.node import (
    DocumentIR, DocumentNode, PageNode, NodeType, BoundingBox, NodeStyle, PageProcessingMode
)
from packages.providers.base import OCRBlock
from packages.document.scanning.page_mode_classifier import PageModeClassifier
from packages.document.semantic.reconciler import DualExtractionReconciler
from packages.document.semantic.block_classifier import SemanticBlockClassifier
from packages.document.semantic.protected_spans import ProtectedSpansManager
from packages.rendering.script_segmenter import segment_script_runs, get_grapheme_clusters
from packages.validation.content_completeness import ContentCompletenessValidator
from packages.validation.scorecard import QAScorecard


def test_page_mode_classifier():
    # 1. Digital text page
    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.insert_text(fitz.Point(50, 50), "This is a clean born-digital document page with plenty of text.")
    mode, conf, ev = PageModeClassifier.classify_page(page)
    assert mode == PageProcessingMode.DIGITAL_TEXT
    assert conf >= 0.8
    doc.close()

    # 2. Empty / scanned raster page
    doc2 = fitz.open()
    page2 = doc2.new_page(width=500, height=500)
    mode2, conf2, ev2 = PageModeClassifier.classify_page(page2)
    assert mode2 == PageProcessingMode.SCANNED_IMAGE
    doc2.close()


def test_dual_extraction_reconciler():
    native_node = DocumentNode(
        node_id="n1",
        bbox=BoundingBox(x0=50, y0=50, x1=300, y1=80),
        source_text="Step 1: Install Python 3.12",
    )
    # OCR block that overlaps native node
    ocr_b1 = OCRBlock(
        text="Step 1: Install Python 3.12",
        bbox=BoundingBox(x0=50, y0=50, x1=300, y1=80),
        confidence=0.98,
        block_type="paragraph",
    )
    # OCR block for an image stamp/caption not in digital text layer
    ocr_b2 = OCRBlock(
        text="Official Verified Stamp",
        bbox=BoundingBox(x0=50, y0=400, x1=200, y1=450),
        confidence=0.95,
        block_type="stamp",
    )

    reconciled = DualExtractionReconciler.reconcile_page(
        page_id="p1",
        page_number=1,
        native_nodes=[native_node],
        ocr_blocks=[ocr_b1, ocr_b2],
    )

    assert len(reconciled) == 2
    assert reconciled[0].provenance == "reconciled"
    assert reconciled[1].provenance == "ocr"
    assert reconciled[1].source_text == "Official Verified Stamp"


def test_reconciliation_conflict_detection():
    native_node = DocumentNode(
        node_id="n1",
        bbox=BoundingBox(x0=50, y0=50, x1=300, y1=80),
        source_text="Revenue is $5.2 million",
    )
    # OCR recognized different number
    ocr_b = OCRBlock(
        text="Revenue is $9.2 million",
        bbox=BoundingBox(x0=50, y0=50, x1=300, y1=80),
        confidence=0.92,
        block_type="paragraph",
    )

    reconciled = DualExtractionReconciler.reconcile_page(
        page_id="p1",
        page_number=1,
        native_nodes=[native_node],
        ocr_blocks=[ocr_b],
    )

    assert "reconciliation_warning" in reconciled[0].metadata
    assert "RECONCILIATION_CONFLICT" in reconciled[0].metadata["reconciliation_warning"]


def test_protected_spans_shield_and_restore():
    source_text = "Visit https://anaconda.com/download to install Anaconda in /usr/local/bin."
    shielded, items = ProtectedSpansManager.detect_and_shield(source_text)

    assert "<_P_0_>" in shielded
    assert "<_P_1_>" in shielded
    assert len(items) == 2

    # Simulate translation preserving the placeholders
    mock_translated = "एनाकोंडा को <_P_1_> में स्थापित करने के लिए <_P_0_> पर जाएँ।"
    restored, is_valid, errors = ProtectedSpansManager.restore_and_validate(mock_translated, items)

    assert is_valid is True
    assert len(errors) == 0
    assert "https://anaconda.com/download" in restored
    assert "/usr/local/bin" in restored
    assert "<_P_" not in restored


def test_protected_spans_sentinel_leakage_detection():
    items = []
    text_with_leakage = "Translated text DOCUMENT_CONTENT leaked."
    _, is_valid, errors = ProtectedSpansManager.restore_and_validate(text_with_leakage, items)

    assert is_valid is False
    assert any("LEAKED_SENTINEL" in e for e in errors)


def test_grapheme_safe_script_segmentation():
    # Hindi text with conjuncts (क्ष, त्र, ज्ञ, viramas, matras) and mixed Latin
    hindi_text = "चरण 1: Anaconda डाउनलोड करें https://anaconda.com"
    clusters = get_grapheme_clusters(hindi_text)
    
    # Verify combining characters remain bound
    # e.g. "क" + "र" + "ें" -> "र" and "ें" should be in same cluster
    assert any("ें" in c for c in clusters)
    
    # Segment runs
    runs = segment_script_runs(hindi_text, fitz.Font("helv"), fitz.Font("helv"))
    assert len(runs) > 0


def test_content_completeness_validator():
    ir = DocumentIR()
    p = PageNode(page_number=1)
    n = DocumentNode(
        bbox=BoundingBox(x0=50, y0=50, x1=100, y1=60),
        source_text="Hello world",
        translated_text="नमस्ते दुनिया",
    )
    p.nodes.append(n)
    ir.pages.append(p)

    is_valid, errors, metrics = ContentCompletenessValidator.validate_ir(ir)
    assert is_valid is True
    assert metrics["missing_nodes"] == 0
    assert metrics["completeness_ratio"] == 1.0


from packages.rendering.pdf_renderer import PDFRenderer


def test_qa_scorecard_evaluation():
    ir = DocumentIR()
    ir.target_language = "hi"
    p = PageNode(page_number=1, width=500, height=500)
    n = DocumentNode(
        bbox=BoundingBox(x0=50, y0=50, x1=300, y1=80),
        source_text="Hello world",
        translated_text="नमस्ते दुनिया",
    )
    p.nodes.append(n)
    ir.pages.append(p)

    renderer = PDFRenderer()
    pdf_bytes = renderer.render_ir_to_pdf(ir)

    scorecard = QAScorecard.evaluate(ir, pdf_bytes)
    assert "dimensions" in scorecard
    assert "content_completeness" in scorecard["dimensions"]
    assert "typography_and_visual" in scorecard["dimensions"]
    assert scorecard["dimensions"]["content_completeness"]["status"] == "PASS"
