import json
import os
import pytest
from packages.translation.validation.duplicate_content_detector import DuplicateContentDetector
from packages.translation.validation.translation_quality_gate import TranslationQualityGate
from packages.translation.validation.validation_report import ValidationReport
from packages.translation.validation.validation_issue import GateStatus, IssueCode


def load_problem_47_fixture():
    fixture_path = os.path.join(os.path.dirname(__file__), "../fixtures/problem_47_fixture.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_problem_47_duplicate_phrase_detection():
    """
    Section 10 Regression Test:
    Ensures that the repeated 'शुद्धता' phrase in the defective translation of Problem 47
    is correctly detected as DUPLICATE_PHRASE / DUPLICATE_WORD.
    """
    data = load_problem_47_fixture()
    defective_text = data["defective_translation"]

    # 1. Direct detector test
    dup_issues = DuplicateContentDetector.detect_duplicates(defective_text)
    assert len(dup_issues) > 0

    # Ensure 'शुद्धता' was caught
    phrases_detected = [d.get("phrase", "") for d in dup_issues]
    assert any("शुद्धता" in p for p in phrases_detected), f"Expected 'शुद्धता' in detected duplicates: {phrases_detected}"


def test_problem_47_gate_b_quality_gate():
    """
    Section 10 Acceptance Test:
    Defective Problem 47 candidate must yield REVIEW_REQUIRED or FAIL, never PASS.
    """
    data = load_problem_47_fixture()
    source_text = data["source_text"]
    defective_text = data["defective_translation"]

    report = ValidationReport(
        job_id="test-p47",
        source_language="en",
        target_language="hi",
    )

    issues = TranslationQualityGate.validate_candidate(
        block_id="p47_b1",
        source_text=source_text,
        candidate_translation=defective_text,
        protected_items=[],
        report=report,
        page_index=0,
    )

    assert len(issues) > 0
    # Must contain duplicate phrase issue
    assert any(i.issue_code in [IssueCode.DUPLICATE_PHRASE, IssueCode.DUPLICATE_WORD] for i in issues)

    # Gate B status must be REVIEW_REQUIRED or FAIL, never PASS
    gate_b_status = report.gates["translation"].status
    assert gate_b_status in [GateStatus.REVIEW_REQUIRED, GateStatus.FAIL]
    assert gate_b_status != GateStatus.PASS


def test_problem_47_clean_translation_passes():
    """
    Verifies that a clean translation of Problem 47 without stuttering / duplication
    passes Gate B validation.
    """
    data = load_problem_47_fixture()
    source_text = data["source_text"]

    # Clean translation without the repeated "शुद्धता।"
    clean_text = (
        "समस्या 47: एक एथिलीन शोधन संयंत्र को 50% शुद्ध एथिलीन का 500 kg/hr प्राप्त होता है। "
        "यह इसे दो प्रकार के आउटपुट 1 और 2 में परिष्कृत करता है। टाइप 1 की शुद्धता 90% है और "
        "टाइप 2 की शुद्धता 70% है। कच्चा माल की लागत Rs 40/kg है। टाइप 1 का विक्रय मूल्य "
        "Rs 200/kg है और टाइप 2 का Rs 120/kg है। पैकेजिंग सुविधाएँ टाइप 1 के 200 kg/hr और "
        "टाइप 2 के 225 kg/hr तक संभाल सकती हैं। परिवहन लागत टाइप 1 के लिए Rs 8/kg और "
        "टाइप 2 के लिए Rs 16/kg है, और कुल परिवहन लागत Rs 4000/hr से अधिक नहीं होनी चाहिए। "
        "लाभ को अधिकतम करने के लिए रैखिक प्रोग्रामिंग (LP) की ग्राफिकल विधि द्वारा इष्टतम समाधान निर्धारित करें।"
    )

    report = ValidationReport(
        job_id="test-p47-clean",
        source_language="en",
        target_language="hi",
    )

    issues = TranslationQualityGate.validate_candidate(
        block_id="p47_b1",
        source_text=source_text,
        candidate_translation=clean_text,
        protected_items=[],
        report=report,
        page_index=0,
    )

    # Should not have duplicate phrase issues
    dup_issues = [i for i in issues if i.issue_code in [IssueCode.DUPLICATE_PHRASE, IssueCode.DUPLICATE_WORD]]
    assert len(dup_issues) == 0
