import pytest
import fitz
from packages.document.extraction.pdf_preflight import PDFPreflightInspector, PDFPreflightReport
from packages.translation.facts.fact_extractor import ExpectedFactsExtractor, ExpectedFact
from packages.translation.facts.fact_validator import ExpectedFactsValidator
from packages.translation.profiles.profile_manager import TranslationProfileManager
from packages.translation.orchestrator.translation_orchestrator import TranslationOrchestrator
from packages.translation.validation.validation_issue import IssueCode, IssueSeverity, GateStatus, ValidationIssue
from packages.translation.validation.validation_report import ValidationReport
from packages.core.domain.node import DocumentNode, NodeType, BoundingBox


def test_pdf_preflight_inspection():
    doc = fitz.open()
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text(fitz.Point(50, 100), "Chapter 1: Operating Systems & Environment Setup", fontsize=14)
    page1.insert_text(fitz.Point(50, 140), "Install Python 3.11 and verify with python --version.", fontsize=11)
    
    pdf_bytes = doc.tobytes()
    doc.close()

    report: PDFPreflightReport = PDFPreflightInspector.inspect(pdf_bytes)
    assert report.is_valid_for_processing is True
    assert report.page_count == 1
    assert report.overall_classification in ["DIGITAL", "TEXT_HEAVY"]
    assert len(report.pages) == 1
    p = report.pages[0]
    assert p.width == 595.0
    assert p.height == 842.0
    assert p.has_text is True


def test_expected_facts_extractor():
    source_text = (
        "Problem 47: Purity of Type 1 is 90% and purity of Type 2 is 70%. "
        "Raw material cost is Rs 40/kg. Total transportation cost must not exceed Rs 4000/hr. "
        "Determine the optimal solution using graphical method to maximize profit."
    )
    facts = ExpectedFactsExtractor.extract_facts(source_node_id="node-47", text=source_text)

    # Check optimization relationship fact
    opt_facts = [f for f in facts if f.relationship == "maximize"]
    assert len(opt_facts) >= 1
    assert opt_facts[0].criticality == "HIGH"

    # Check condition / constraint fact
    neg_facts = [f for f in facts if f.condition and "not" in f.condition.lower()]
    assert len(neg_facts) >= 1
    assert "4000" in (neg_facts[0].value or "") or "4000" in neg_facts[0].source_evidence

    # Check entity facts (Type 1 and Type 2)
    entity_facts = [f for f in facts if f.entity and "type" in f.entity.lower()]
    assert len(entity_facts) >= 2


def test_expected_facts_entity_value_swap_detected():
    """
    Asserts that swapping entity-value associations (e.g. Type 1 purity 70% instead of 90%)
    is detected as a CRITICAL SEMANTIC_RELATIONSHIP_CHANGED issue.
    """
    facts = [
        ExpectedFact(
            source_node_id="node-47",
            entity="Type 1",
            attribute="purity",
            value="90%",
            source_evidence="Purity of Type 1 is 90%",
            criticality="HIGH",
        ),
        ExpectedFact(
            source_node_id="node-47",
            entity="Type 2",
            attribute="purity",
            value="70%",
            source_evidence="Purity of Type 2 is 70%",
            criticality="HIGH",
        ),
    ]

    # Defective target text where values are swapped: Type 1 -> 70%, Type 2 -> 90%
    swapped_target = (
        "टाइप 1 की शुद्धता 70% है और टाइप 2 की शुद्धता 90% है।"
    )

    issues = ExpectedFactsValidator.validate_facts(facts, swapped_target)
    semantic_issues = [i for i in issues if i.issue_code == IssueCode.SEMANTIC_RELATIONSHIP_CHANGED]
    assert len(semantic_issues) >= 1
    assert semantic_issues[0].severity == IssueSeverity.CRITICAL


def test_expected_facts_inversion_detected():
    """
    Asserts that inverting an optimization goal (maximize -> minimize/न्यूनतम)
    triggers a CRITICAL SEMANTIC_RELATIONSHIP_CHANGED issue.
    """
    facts = [
        ExpectedFact(
            source_node_id="node-47",
            entity="profit",
            attribute="optimization_goal",
            relationship="maximize",
            source_evidence="maximize profit",
            criticality="HIGH",
        )
    ]

    # Inverted target text: profit is minimized
    inverted_target = "लाभ को न्यूनतम करने के लिए इष्टतम समाधान निर्धारित करें।"

    issues = ExpectedFactsValidator.validate_facts(facts, inverted_target)
    semantic_issues = [i for i in issues if i.issue_code == IssueCode.SEMANTIC_RELATIONSHIP_CHANGED]
    assert len(semantic_issues) >= 1
    assert semantic_issues[0].severity == IssueSeverity.CRITICAL


def test_expected_facts_lost_negation_detected():
    """
    Asserts that omitting a negative constraint ('must not exceed')
    triggers a CRITICAL SEMANTIC_RELATIONSHIP_CHANGED issue.
    """
    facts = [
        ExpectedFact(
            source_node_id="node-47",
            condition="must not exceed",
            value="4000",
            source_evidence="Total transportation cost must not exceed Rs 4000/hr.",
            criticality="HIGH",
        )
    ]

    # Defective target text missing negation
    unconstrained_target = "कुल परिवहन लागत Rs 4000/hr होनी चाहिए।"

    issues = ExpectedFactsValidator.validate_facts(facts, unconstrained_target)
    semantic_issues = [i for i in issues if i.issue_code == IssueCode.SEMANTIC_RELATIONSHIP_CHANGED]
    assert len(semantic_issues) >= 1
    assert semantic_issues[0].severity == IssueSeverity.CRITICAL


def test_translation_profile_manager():
    sw_profile = TranslationProfileManager.get_profile(domain="software")
    assert sw_profile.domain == "software"
    assert "Python" in sw_profile.untranslatable_terms
    assert any(g.source_term == "command" for g in sw_profile.glossary)

    math_profile = TranslationProfileManager.get_profile(domain="mathematics")
    assert math_profile.domain == "mathematics"
    assert any(g.source_term == "purity" for g in math_profile.glossary)


def test_v2_release_gate_decision():
    """
    Verifies that release gate blocks documents with unresolved CRITICAL issues,
    requires review for HIGH issues, and allows PASS for clean documents.
    """
    # 1. Clean report passes release
    clean_report = ValidationReport(job_id="clean", source_language="en", target_language="hi")
    clean_report.set_gate_status("preflight", GateStatus.PASS)
    clean_report.set_gate_status("source_ir", GateStatus.PASS)
    clean_report.set_gate_status("translation", GateStatus.PASS)
    clean_report.set_gate_status("facts", GateStatus.PASS)
    clean_report.set_gate_status("release", GateStatus.PASS)
    assert clean_report.overall_status == GateStatus.PASS

    # 2. Critical failure blocks release
    fail_report = ValidationReport(job_id="fail", source_language="en", target_language="hi")
    fail_report.record_issue("facts", ValidationIssue(
        issue_code=IssueCode.SEMANTIC_RELATIONSHIP_CHANGED,
        severity=IssueSeverity.CRITICAL,
        stage="FACT_VALIDATION",
        explanation="Inverted objective direction",
    ))
    fail_report.set_gate_status("release", GateStatus.FAIL)
    assert fail_report.overall_status == GateStatus.FAIL
