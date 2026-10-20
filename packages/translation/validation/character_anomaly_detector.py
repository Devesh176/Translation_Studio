import re
import unicodedata
from typing import List, Dict, Any


class CharacterAnomalyDetector:
    """
    Implements Character and Script Anomaly Detection per Section 7.2:
    - Unicode replacement characters (U+FFFD).
    - Unexpected control / format characters.
    - Broken combining-mark sequences (e.g. combining mark as initial character).
    - Suspicious repeated punctuation (e.g. '????', '....', ',,,,').
    
    Preserves:
    - Valid Devanagari/Indic combining marks (vowel signs, viramas, anusvara, nukta).
    - Valid ZWJ/ZWNJ where appropriate.
    - Math notation and standard currency symbols.
    - Approved Latin technical terms.
    """

    CONTROL_CHAR_REGEX = r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
    SUSPICIOUS_PUNCT_REGEX = r"([,\.।\?!;:]{4,})"

    @classmethod
    def detect_anomalies(cls, text: str) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        if not text:
            return anomalies

        # 1. Unicode replacement character check
        replacement_char_count = text.count("\ufffd")
        if replacement_char_count > 0:
            anomalies.append({
                "type": "INVALID_UNICODE",
                "evidence": f"Found {replacement_char_count} Unicode replacement character(s) (U+FFFD).",
                "severity": "CRITICAL",
            })

        # 2. Control characters check
        control_matches = re.findall(cls.CONTROL_CHAR_REGEX, text)
        if control_matches:
            anomalies.append({
                "type": "SUSPICIOUS_CHARACTER",
                "evidence": f"Found {len(control_matches)} unexpected control character(s).",
                "severity": "CRITICAL",
            })

        # 3. Suspicious repeated punctuation runs (e.g. ????, ,,,,, ...)
        punct_matches = re.findall(cls.SUSPICIOUS_PUNCT_REGEX, text)
        for m in punct_matches:
            anomalies.append({
                "type": "PUNCTUATION_ANOMALY",
                "evidence": f"Suspicious punctuation run '{m}' detected.",
                "severity": "WARNING",
            })

        # 4. Broken combining mark sequences
        # In Unicode, combining marks (Mn, Mc, Me) must attach to a base character.
        # If the string starts with a combining mark, or a space is followed by a combining mark, it is broken.
        for idx, char in enumerate(text):
            cat = unicodedata.category(char)
            if cat.startswith("M"):
                if idx == 0:
                    anomalies.append({
                        "type": "SUSPICIOUS_CHARACTER",
                        "evidence": f"Detached combining mark '{char}' (U+{ord(char):04X}) at beginning of text.",
                        "severity": "ERROR",
                    })
                    break
                elif text[idx - 1] in " \t\n":
                    anomalies.append({
                        "type": "SUSPICIOUS_CHARACTER",
                        "evidence": f"Detached combining mark '{char}' (U+{ord(char):04X}) following whitespace.",
                        "severity": "ERROR",
                    })
                    break

        return anomalies
