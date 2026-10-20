import re
from typing import List, Dict, Any, Optional
from packages.translation.facts.fact_extractor import ExpectedFact
from packages.translation.validation.validation_issue import ValidationIssue, IssueCode, IssueSeverity


class ExpectedFactsValidator:
    """
    Validates translated target text against expected technical facts per Section 11 of Modification V2.
    Ensures that values, units, entity-value associations, constraints, and optimization goals are preserved.
    """

    DEVANAGARI_DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")

    @classmethod
    def _to_ascii_digits(cls, text: str) -> str:
        return text.translate(cls.DEVANAGARI_DIGIT_MAP)

    @classmethod
    def validate_facts(
        cls,
        facts: List[ExpectedFact],
        target_text: str,
        page_index: int = 0,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        if not facts or not target_text:
            return issues

        norm_target = cls._to_ascii_digits(target_text)
        lower_target = norm_target.lower()

        for fact in facts:
            # 1. Validate Value Preservation
            if fact.value:
                clean_val = fact.value.rstrip("%")
                # Check direct presence or scale conversion (e.g. 4.2 million -> 42 lakh)
                val_present = clean_val in norm_target
                if not val_present:
                    try:
                        fval = float(clean_val)
                        scaled_lakh = f"{fval * 10:g}"
                        if scaled_lakh in norm_target and ("लाख" in norm_target or "lakh" in lower_target):
                            val_present = True
                    except ValueError:
                        pass

                if not val_present:
                    issues.append(ValidationIssue(
                        issue_code=IssueCode.TECHNICAL_VALUE_CHANGED,
                        severity=IssueSeverity.CRITICAL,
                        stage="FACT_VALIDATION",
                        block_id=fact.source_node_id,
                        page_index=page_index,
                        explanation=f"Technical value '{fact.value}' not found in translated text.",
                        evidence={"fact_id": fact.fact_id, "expected_value": fact.value, "source_evidence": fact.source_evidence},
                    ))

            # 2. Validate Entity-Value Association
            # e.g., If entity is "Type 1" and value is "90%", verify they appear in proximity
            if fact.entity and fact.value:
                # Map entity to Hindi equivalents
                entity_keywords = [fact.entity.lower()]
                if "type" in fact.entity.lower():
                    # e.g. "type 1" -> "टाइप 1"
                    num_match = re.search(r"\d+", fact.entity)
                    if num_match:
                        entity_keywords.extend([
                            f"टाइप {num_match.group(0)}",
                            f"टाइप ${num_match.group(0)}$",
                            f"प्रकार {num_match.group(0)}",
                            f"आउटपुट {num_match.group(0)}",
                        ])

                # Find clauses containing the entity, splitting compound sentences
                target_clauses = re.split(r"[।;\.\n]|(?:\s+और\s+)|\bऔर\b|(?:\s+तथा\s+)|(?:\s+एवं\s+)|(?:\s*,\s*)", norm_target)
                entity_found = False
                association_correct = False

                for clause in target_clauses:
                    clause_lower = clause.lower()
                    if any(ek in clause_lower for ek in entity_keywords):
                        entity_found = True
                        if fact.value in clause or fact.value.rstrip("%") in clause:
                            association_correct = True
                            break

                # If entity was found in the text but nowhere associated with its expected value
                if entity_found and not association_correct:
                    issues.append(ValidationIssue(
                        issue_code=IssueCode.SEMANTIC_RELATIONSHIP_CHANGED,
                        severity=IssueSeverity.CRITICAL,
                        stage="FACT_VALIDATION",
                        block_id=fact.source_node_id,
                        page_index=page_index,
                        explanation=(
                            f"Entity '{fact.entity}' was translated but is not associated with its expected "
                            f"value '{fact.value}'. Possible value swap or association error."
                        ),
                        evidence={"fact_id": fact.fact_id, "entity": fact.entity, "expected_value": fact.value},
                    ))

            # 3. Validate Direction / Optimization Relationship
            if fact.relationship:
                if fact.relationship == "maximize":
                    # Check for maximize equivalent in Hindi ("अधिकतम") or English
                    if "अधिकतम" not in norm_target and "maximize" not in lower_target:
                        if "न्यूनतम" in norm_target or "minimize" in lower_target:
                            issues.append(ValidationIssue(
                                issue_code=IssueCode.SEMANTIC_RELATIONSHIP_CHANGED,
                                severity=IssueSeverity.CRITICAL,
                                stage="FACT_VALIDATION",
                                block_id=fact.source_node_id,
                                page_index=page_index,
                                explanation="Optimization objective inverted: expected 'maximize' but found 'minimize/न्यूनतम'.",
                                evidence={"fact_id": fact.fact_id, "expected": "maximize"},
                            ))
                elif fact.relationship == "minimize":
                    if "न्यूनतम" not in norm_target and "minimize" not in lower_target:
                        if "अधिकतम" in norm_target or "maximize" in lower_target:
                            issues.append(ValidationIssue(
                                issue_code=IssueCode.SEMANTIC_RELATIONSHIP_CHANGED,
                                severity=IssueSeverity.CRITICAL,
                                stage="FACT_VALIDATION",
                                block_id=fact.source_node_id,
                                page_index=page_index,
                                explanation="Optimization objective inverted: expected 'minimize' but found 'maximize/अधिकतम'.",
                                evidence={"fact_id": fact.fact_id, "expected": "minimize"},
                            ))

            # 4. Validate Condition / Negation
            if fact.condition and ("not" in fact.condition.lower() or "never" in fact.condition.lower()):
                # Hindi negation words: नहीं, ना, मत, or isolated word 'न'
                has_negation = bool(
                    re.search(r"\b(?:नहीं|ना|मत)\b", norm_target)
                    or re.search(r"(?:^|\s)न(?:\s|$)", norm_target)
                    or "not" in lower_target
                )
                if not has_negation:
                    issues.append(ValidationIssue(
                        issue_code=IssueCode.SEMANTIC_RELATIONSHIP_CHANGED,
                        severity=IssueSeverity.CRITICAL,
                        stage="FACT_VALIDATION",
                        block_id=fact.source_node_id,
                        page_index=page_index,
                        explanation=f"Negative constraint '{fact.condition}' was omitted or lost in translation.",
                        evidence={"fact_id": fact.fact_id, "condition": fact.condition, "source_evidence": fact.source_evidence},
                    ))

        return issues
