import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid


class ExpectedFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_node_id: str
    entity: Optional[str] = None
    attribute: Optional[str] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    relationship: Optional[str] = None  # e.g., 'maximize', 'minimize', 'exceeds', 'equals'
    condition: Optional[str] = None     # e.g., 'not exceed', 'up to', 'greater than'
    source_evidence: str
    criticality: str = "HIGH"  # HIGH, MEDIUM, LOW


class ExpectedFactsExtractor:
    """
    Extracts structured technical facts from source text per Section 11 of Modification V2.
    Detects entities, numeric values, units, constraints, and relationships.
    """

    # Units patterns
    UNIT_PATTERN = r"(?:Rs\.?|₹|\$)\s*\d+(?:\.\d+)?(?:/(?:kg|hr|m|sec|year))?|\d+(?:\.\d+)?\s*(?:kg/hr|kg|hr|%|million|billion|thousand)"
    NUMBER_PATTERN = r"\b\d+(?:\.\d+)?%?\b"

    # Relationship keywords
    DIRECTION_KEYWORDS = {
        "maximize": ("maximize", "अधिकतम"),
        "minimize": ("minimize", "न्यूनतम"),
        "increase": ("increase", "बढ़"),
        "decrease": ("decrease", "घट"),
    }

    # Negation keywords
    NEGATION_KEYWORDS = ["must not", "shall not", "cannot", "do not", "never", "not exceed"]

    @classmethod
    def extract_facts(cls, source_node_id: str, text: str) -> List[ExpectedFact]:
        facts: List[ExpectedFact] = []
        if not text:
            return facts

        # 1. Extract directional optimization/relationship facts
        lower_text = text.lower()
        for action, (en_key, hi_key) in cls.DIRECTION_KEYWORDS.items():
            if en_key in lower_text:
                # Find the entity or objective being maximized/minimized
                m = re.search(rf"\b{en_key}\b(?:\s+(?:the\s+)?([a-zA-Z\s]{{2,20}}))?", lower_text)
                target_obj = m.group(1).strip() if m and m.group(1) else "objective"
                facts.append(ExpectedFact(
                    source_node_id=source_node_id,
                    entity=target_obj,
                    attribute="optimization_goal",
                    relationship=action,
                    source_evidence=m.group(0) if m else action,
                    criticality="HIGH",
                ))

        # 2. Extract constraint / condition facts
        for neg in cls.NEGATION_KEYWORDS:
            if neg in lower_text:
                # Find snippet around negation
                m = re.search(rf"([a-zA-Z0-9\s,\$]{{0,30}}{neg}[a-zA-Z0-9\s,\.\$/]{{0,30}})", text, re.IGNORECASE)
                evidence = m.group(1).strip() if m else neg
                # Extract value in constraint if present
                nums = re.findall(cls.NUMBER_PATTERN, evidence)
                val = nums[0] if nums else None
                facts.append(ExpectedFact(
                    source_node_id=source_node_id,
                    condition=neg,
                    value=val,
                    source_evidence=evidence,
                    criticality="HIGH",
                ))

        # 3. Extract Entity-Attribute-Value-Unit associations
        # Patterns like: "Purity of Type 1 is 90%", "Type 1 is 90% pure", "selling price of Type 1 is Rs 200/kg"
        subclauses = re.split(r"[;\.\n]|(?:\s+and\s+)|\band\b|(?:\s*,\s*)", text)
        for clause in subclauses:
            clause = clause.strip()
            if not clause:
                continue

            # Strip leading headers like "Problem 47:"
            cleaned_clause = re.sub(r"^(?:Problem|Chapter|Section|Step)\s+\d+:\s*", "", clause, flags=re.IGNORECASE).strip()

            entities = re.findall(r"\b(type\s+\d+|output\s+\d+|plant|revenue|cost|raw\s+material|packaging|transportation)\b", cleaned_clause, re.IGNORECASE)
            units = re.findall(cls.UNIT_PATTERN, cleaned_clause, re.IGNORECASE)
            nums = re.findall(cls.NUMBER_PATTERN, cleaned_clause)

            if entities and (units or nums):
                primary_entity = entities[0].strip()
                # Find number associated with entity (ignore numbers that are inside entity name like '1' in 'Type 1')
                entity_digit = re.findall(r"\d+", primary_entity)
                candidate_nums = [n for n in nums if n not in entity_digit]
                val = candidate_nums[0] if candidate_nums else (nums[0] if nums else None)
                unit = units[0] if units else None

                # Detect attribute like purity, cost, price, limit
                attr = "value"
                lower_clause = cleaned_clause.lower()
                if "purity" in lower_clause or "pure" in lower_clause:
                    attr = "purity"
                elif "cost" in lower_clause:
                    attr = "cost"
                elif "price" in lower_clause or "selling" in lower_clause:
                    attr = "selling_price"
                elif "capacity" in lower_clause or "handle" in lower_clause:
                    attr = "capacity"

                facts.append(ExpectedFact(
                    source_node_id=source_node_id,
                    entity=primary_entity,
                    attribute=attr,
                    value=val,
                    unit=unit,
                    source_evidence=cleaned_clause,
                    criticality="HIGH",
                ))

        return facts
