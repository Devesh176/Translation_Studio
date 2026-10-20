import re
from typing import List, Dict, Any


class NumericalConsistencyValidator:
    """
    Implements Numerical & Unit Consistency Validation per Section 7.2 of Modification V1:
    - Extracts numbers, decimals, percentages, and units.
    - Maps Devanagari numerals (०-९) to ASCII (0-9) for canonical comparison.
    - Checks that all source numbers exist in target text.
    - Flags NUMERIC_VALUE_MISMATCH or UNIT_ASSOCIATION_MISMATCH.
    """

    DEVANAGARI_DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")

    NUM_REGEX = r"\b\d+(?:\.\d+)?%?\b"
    UNIT_REGEX = r"(?:Rs|₹|\$)\s*\d+(?:\.\d+)?(?:/(?:kg|hr|m|sec|year))?|\d+(?:\.\d+)?\s*(?:kg/hr|kg|hr|%|million|billion|thousand)"

    @classmethod
    def _to_ascii_digits(cls, text: str) -> str:
        return text.translate(cls.DEVANAGARI_DIGIT_MAP)

    @classmethod
    def validate_consistency(cls, source_text: str, target_text: str) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        if not source_text or not target_text:
            return issues

        norm_src = cls._to_ascii_digits(source_text)
        norm_tgt = cls._to_ascii_digits(target_text)

        # 1. Pure numbers comparison
        src_nums = re.findall(cls.NUM_REGEX, norm_src)
        tgt_nums = re.findall(cls.NUM_REGEX, norm_tgt)

        # Count frequencies
        src_counts = {}
        for n in src_nums:
            src_counts[n] = src_counts.get(n, 0) + 1

        tgt_counts = {}
        for n in tgt_nums:
            tgt_counts[n] = tgt_counts.get(n, 0) + 1

        for n, count in src_counts.items():
            actual = tgt_counts.get(n, 0)
            if actual < count:
                # Check for standard million -> lakh (factor of 10) or billion -> crore/arab scale conversions
                is_scale_converted = False
                try:
                    val = float(n.rstrip("%"))
                    # million -> lakh (1 million = 10 lakh, e.g. 4.2 million -> 42 lakh)
                    scaled_lakh = f"{val * 10:g}"
                    if re.search(rf"\b{re.escape(n)}\s+million\b", norm_src, flags=re.IGNORECASE):
                        if re.search(rf"\b{re.escape(scaled_lakh)}\s*(?:लाख|lakh)\b", norm_tgt, flags=re.IGNORECASE):
                            is_scale_converted = True
                    # billion -> crore (1 billion = 100 crore) or arab (1 billion = 1 arab)
                    scaled_crore = f"{val * 100:g}"
                    if re.search(rf"\b{re.escape(n)}\s+billion\b", norm_src, flags=re.IGNORECASE):
                        if re.search(rf"\b{re.escape(scaled_crore)}\s*(?:करोड़|crore)\b", norm_tgt, flags=re.IGNORECASE) or \
                           re.search(rf"\b{re.escape(n)}\s*(?:अरब|arab)\b", norm_tgt, flags=re.IGNORECASE):
                            is_scale_converted = True
                except ValueError:
                    pass

                if not is_scale_converted:
                    issues.append({
                        "type": "NUMERIC_VALUE_MISMATCH",
                        "evidence": f"Number '{n}' appears {count} time(s) in source but only {actual} time(s) in target.",
                        "severity": "CRITICAL",
                    })

        # 2. Key Unit expressions (e.g. Rs 40/kg, 500 kg/hr)
        src_units = [re.sub(r"\s+", "", u.lower()) for u in re.findall(cls.UNIT_REGEX, norm_src, flags=re.IGNORECASE)]
        tgt_units = [re.sub(r"\s+", "", u.lower()) for u in re.findall(cls.UNIT_REGEX, norm_tgt, flags=re.IGNORECASE)]

        for u in src_units:
            # Check if key numbers + units survive
            if u not in tgt_units and not any(u in tu for tu in tgt_units):
                # Only flag warning if numbers were present
                num_in_u = re.findall(r"\d+", u)
                if num_in_u and any(n not in norm_tgt for n in num_in_u):
                    issues.append({
                        "type": "UNIT_ASSOCIATION_MISMATCH",
                        "evidence": f"Unit expression '{u}' not found or modified in target text.",
                        "severity": "WARNING",
                    })

        return issues
