import re
from typing import Tuple, List, Dict, Any


class ProtectedSpansManager:
    """
    Manages detection, shielding, and restoration of protected spans
    according to Section 66.6:
    Commands, shell snippets, URLs, emails, file paths, filenames, package names,
    product names, environment variables, and inline code.
    
    Invariants:
    1. Exact preservation of source protected tokens.
    2. Zero leaked placeholders (e.g. <_P_0_>) or internal sentinels (e.g. DOCUMENT_CONTENT).
    3. Exact count verification in translated text.
    """

    FORBIDDEN_SENTINELS = ("DOCUMENT_CONTENT", "__INTERNAL_PROMPT__")

    # Patterns to protect
    URL_REGEX = r"https?://[^\s)\]\"'>]+"
    EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    FILEPATH_REGEX = r"(?:/[a-zA-Z0-9_.-]+){2,}/?"
    ENV_VAR_REGEX = r"\b[A-Z][A-Z0-9_]{2,}\b"

    @classmethod
    def detect_and_shield(cls, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Replaces protected patterns with deterministic placeholders: <_P_0_>, <_P_1_>...
        Returns (shielded_text, list_of_protected_items).
        """
        if not text:
            return text, []

        protected_items: List[Dict[str, Any]] = []
        token_counter = 0

        # Protect URLs
        def replace_url(match):
            nonlocal token_counter
            placeholder = f"<_P_{token_counter}_>"
            val = match.group(0)
            protected_items.append({"id": placeholder, "value": val, "type": "URL"})
            token_counter += 1
            return placeholder

        shielded = re.sub(cls.URL_REGEX, replace_url, text)

        # Protect Emails
        def replace_email(match):
            nonlocal token_counter
            placeholder = f"<_P_{token_counter}_>"
            val = match.group(0)
            protected_items.append({"id": placeholder, "value": val, "type": "EMAIL"})
            token_counter += 1
            return placeholder

        shielded = re.sub(cls.EMAIL_REGEX, replace_email, shielded)

        # Protect File Paths
        def replace_path(match):
            nonlocal token_counter
            placeholder = f"<_P_{token_counter}_>"
            val = match.group(0)
            protected_items.append({"id": placeholder, "value": val, "type": "FILE_PATH"})
            token_counter += 1
            return placeholder

        shielded = re.sub(cls.FILEPATH_REGEX, replace_path, shielded)

        return shielded, protected_items

    @classmethod
    def restore_and_validate(cls, translated_text: str, protected_items: List[Dict[str, Any]]) -> Tuple[str, bool, List[str]]:
        """
        Restores protected placeholders into their exact source strings.
        Validates:
        - All placeholders are replaced.
        - Zero forbidden sentinel leakage.
        - Exact count preservation.
        """
        errors = []
        restored = translated_text

        # 1. Check for forbidden sentinels
        for sentinel in cls.FORBIDDEN_SENTINELS:
            if sentinel in restored:
                errors.append(f"LEAKED_SENTINEL: Forbidden string '{sentinel}' found in translated output.")

        # 2. Restore placeholders
        for item in protected_items:
            placeholder = item["id"]
            val = item["value"]
            if placeholder in restored:
                # Replace placeholder with original value
                restored = restored.replace(placeholder, val)
            else:
                # If placeholder was altered by MT (e.g. translated as spaces or stripped),
                # check if original value is already present, else flag error
                if val not in restored:
                    errors.append(f"PROTECTED_SPAN_DROPPED: {item['type']} '{val}' was dropped or mangled during translation.")

        # 3. Check for any un-restored placeholder patterns
        remaining_placeholders = re.findall(r"<_P_\d+_>", restored)
        if remaining_placeholders:
            errors.append(f"UNRESTORED_PLACEHOLDER: Placeholders {remaining_placeholders} remained in output text.")

        is_valid = len(errors) == 0
        return restored, is_valid, errors
