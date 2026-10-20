import pytest
from packages.translation.cost_guard import CostGuard
from packages.translation.chunker import TranslationChunker
from packages.core.exceptions import CostLimitExceededError


def test_script_aware_token_estimation():
    english_text = "This is a simple revenue analysis document with 10 words total."
    hindi_text = "यह एक साधारण आय विश्लेषण दस्तावेज है जिसमें कुल शब्द हैं।"
    
    latin_tokens = TranslationChunker.estimate_tokens(english_text, "Latin")
    devanagari_tokens = TranslationChunker.estimate_tokens(hindi_text, "Devanagari")
    
    # Devanagari multi-byte tokens should be weighted proportionally higher
    assert devanagari_tokens > latin_tokens


def test_cost_guard_budget_check():
    guard = CostGuard(max_translation_cost_usd=0.01)
    
    # Small text passes
    cost = guard.check_and_estimate_cost("Short paragraph with $5.00 cost.", "hi")
    assert cost > 0.0
    assert cost <= 0.01

    # Oversized text triggers CostLimitExceededError
    huge_text = "Word " * 200000
    with pytest.raises(CostLimitExceededError):
        guard.check_and_estimate_cost(huge_text, "hi")
