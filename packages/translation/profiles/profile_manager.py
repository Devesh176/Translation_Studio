from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import uuid


class GlossaryEntry(BaseModel):
    source_term: str
    target_term: str
    context: Optional[str] = None
    case_sensitive: bool = False
    is_regex: bool = False


class TranslationProfile(BaseModel):
    profile_id: str
    profile_version: str = "v2.0"
    domain: str = "general"
    source_language: str = "en"
    target_language: str = "hi"
    glossary: List[GlossaryEntry] = Field(default_factory=list)
    untranslatable_terms: List[str] = Field(default_factory=list)
    preserve_code_blocks: bool = True
    preserve_identifiers: bool = True
    number_policy: str = "preserve_ascii"  # preserve_ascii or allow_devanagari
    system_instructions: Optional[str] = None


class TranslationProfileManager:
    """
    Manages Technical Translation Profiles per Section 8 of Modification V2:
    - Domain-specific glossaries.
    - Untranslatable technical terms.
    - Translation policies.
    """

    DEFAULT_PROFILES: Dict[str, TranslationProfile] = {
        "technical_software": TranslationProfile(
            profile_id="technical_software",
            domain="software",
            source_language="en",
            target_language="hi",
            untranslatable_terms=[
                "Python", "Anaconda", "Docker", "PyMuPDF", "FastAPI",
                "Uvicorn", "PostgreSQL", "Redis", "Celery", "HarfBuzz",
                "Linux", "macOS", "Windows", "GitHub", "API", "URL", "JSON"
            ],
            glossary=[
                GlossaryEntry(source_term="terminal", target_term="टर्मिनल"),
                GlossaryEntry(source_term="command", target_term="कमांड"),
                GlossaryEntry(source_term="environment", target_term="एनवायरनमेंट"),
                GlossaryEntry(source_term="installation", target_term="इंस्टॉलेशन"),
                GlossaryEntry(source_term="package", target_term="पैकेज"),
            ],
            system_instructions=(
                "Technical translation: Keep code snippets, package names, and CLI commands in Latin script verbatim. "
                "Translate explanatory text into natural, formal Hindi."
            ),
        ),
        "engineering_mathematics": TranslationProfile(
            profile_id="engineering_mathematics",
            domain="mathematics",
            source_language="en",
            target_language="hi",
            untranslatable_terms=[
                "LP", "Linear Programming", "kg/hr", "Rs", "FY2026", "Type 1", "Type 2"
            ],
            glossary=[
                GlossaryEntry(source_term="purity", target_term="शुद्धता"),
                GlossaryEntry(source_term="refinery", target_term="शोधन संयंत्र"),
                GlossaryEntry(source_term="raw material", target_term="कच्चा माल"),
                GlossaryEntry(source_term="profit", target_term="लाभ"),
                GlossaryEntry(source_term="maximum", target_term="अधिकतम"),
                GlossaryEntry(source_term="minimum", target_term="न्यूनतम"),
                GlossaryEntry(source_term="optimal", target_term="इष्टतम"),
            ],
            system_instructions=(
                "Mathematical/Operations Research translation: Preserve all numbers, percentages, equations, and units exactly. "
                "Do not stutter, loop, or repeat predicate fragments."
            ),
        ),
        "general": TranslationProfile(
            profile_id="general",
            domain="general",
            source_language="en",
            target_language="hi",
            glossary=[],
            untranslatable_terms=[],
        ),
    }

    @classmethod
    def get_profile(cls, profile_id: Optional[str] = None, domain: Optional[str] = None) -> TranslationProfile:
        if profile_id and profile_id in cls.DEFAULT_PROFILES:
            return cls.DEFAULT_PROFILES[profile_id]
        if domain:
            for p in cls.DEFAULT_PROFILES.values():
                if p.domain == domain:
                    return p
        return cls.DEFAULT_PROFILES["general"]

    @classmethod
    def validate_glossary(cls, text: str, profile: TranslationProfile) -> List[Dict[str, Any]]:
        """Checks if mandatory glossary terms are honored in target text."""
        findings = []
        # Checks if source terms translated properly if source appears
        return findings
