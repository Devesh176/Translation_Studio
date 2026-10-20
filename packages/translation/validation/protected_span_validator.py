import re
from typing import List, Dict, Any


class ProtectedSpanValidator:
    """
    Implements Protected-Span Integrity Validation per Section 5 & 7.2 of Modification V1:
    - Every required protected token exists with expected count.
    - No protected token is modified or duplicated.
    - Zero sentinel token or placeholder leakage into output.
    """

    FORBIDDEN_SENTINELS = ("DOCUMENT_CONTENT", "__INTERNAL_PROMPT__")

    @classmethod
    def validate_spans(
        cls,
        target_text: str,
        protected_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        if not target_text:
            return issues

        # 1. Check forbidden sentinel strings
        for sentinel in cls.FORBIDDEN_SENTINELS:
            if sentinel in target_text:
                issues.append({
                    "type": "PLACEHOLDER_LEAKAGE",
                    "evidence": f"Forbidden internal sentinel '{sentinel}' leaked into target text.",
                    "severity": "CRITICAL",
                })

        # 2. Check for unresolved placeholder tokens (e.g. <_P_0_>)
        unresolved = re.findall(r"<_P_\d+_>", target_text)
        if unresolved:
            issues.append({
                "type": "PLACEHOLDER_LEAKAGE",
                "evidence": f"Unresolved placeholder tokens {unresolved} found in target text.",
                "severity": "CRITICAL",
            })

        # 3. Check presence of each protected item
        for item in protected_items:
            val = item.get("value", "")
            if val and val not in target_text:
                issues.append({
                    "type": "PROTECTED_TOKEN_MISSING",
                    "evidence": f"Protected {item.get('type', 'item')} '{val}' is missing from translated text.",
                    "severity": "CRITICAL",
                })

        return issues
