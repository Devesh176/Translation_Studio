import re
from typing import List, Tuple, Dict, Any


class InvariantValidator:
    # Regex patterns for deterministic checks
    NUMBER_PATTERN = re.compile(r"\b\d+(?:[\.,]\d+)?%?\b")
    URL_PATTERN = re.compile(r"https?://[^\s]+")
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

    @classmethod
    def validate_numbers(cls, source_text: str, target_text: str) -> Tuple[bool, List[str]]:
        src_numbers = set(cls.NUMBER_PATTERN.findall(source_text))
        tgt_numbers = set(cls.NUMBER_PATTERN.findall(target_text))
        
        # Check if numbers present in source are missing in target
        missing = [num for num in src_numbers if num not in tgt_numbers and not cls._is_transliterated_num(num, target_text)]
        if missing:
            return False, [f"Missing numbers in translation: {missing}"]
        return True, []

    @classmethod
    def validate_urls_and_emails(cls, source_text: str, target_text: str) -> Tuple[bool, List[str]]:
        src_urls = set(cls.URL_PATTERN.findall(source_text))
        tgt_urls = set(cls.URL_PATTERN.findall(target_text))
        
        errors = []
        for url in src_urls:
            if url not in tgt_urls:
                errors.append(f"Missing URL in translation: {url}")
                
        src_emails = set(cls.EMAIL_PATTERN.findall(source_text))
        tgt_emails = set(cls.EMAIL_PATTERN.findall(target_text))
        for email in src_emails:
            if email not in tgt_emails:
                errors.append(f"Missing email in translation: {email}")

        return len(errors) == 0, errors

    @staticmethod
    def _is_transliterated_num(num_str: str, text: str) -> bool:
        # Check for standard Indic script digits
        digit_maps = [
            # Devanagari / Marathi / Hindi
            {"0": "०", "1": "१", "2": "२", "3": "३", "4": "४", "5": "५", "6": "६", "7": "७", "8": "८", "9": "९"},
            # Bengali
            {"0": "০", "1": "১", "2": "২", "3": "৩", "4": "৪", "5": "৫", "6": "৬", "7": "৭", "8": "৮", "9": "৯"},
            # Gurmukhi (Punjabi)
            {"0": "੦", "1": "੧", "2": "੨", "3": "੩", "4": "੪", "5": "੫", "6": "੬", "7": "੭", "8": "੮", "9": "੯"},
            # Gujarati
            {"0": "૦", "1": "૧", "2": "૨", "3": "૩", "4": "૪", "5": "૫", "6": "૬", "7": "૭", "8": "૮", "9": "૯"},
            # Telugu
            {"0": "౦", "1": "౧", "2": "౨", "3": "౩", "4": "౪", "5": "౫", "6": "౬", "7": "౭", "8": "౮", "9": "౯"},
            # Kannada
            {"0": "೦", "1": "೧", "2": "೨", "3": "೩", "4": "೪", "5": "೫", "6": "೬", "7": "೭", "8": "೮", "9": "೯"},
            # Malayalam
            {"0": "൦", "1": "൧", "2": "൨", "3": "൩", "4": "൪", "5": "൫", "6": "൬", "7": "൭", "8": "൮", "9": "൯"},
            # Tamil
            {"0": "0", "1": "௧", "2": "௨", "3": "௩", "4": "௪", "5": "௫", "6": "௬", "7": "௭", "8": "௮", "9": "௯"},
        ]
        for dmap in digit_maps:
            indic_version = "".join(dmap.get(c, c) for c in num_str)
            if indic_version in text:
                return True
        return False

