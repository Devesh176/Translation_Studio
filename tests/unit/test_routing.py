import pytest
from packages.routing.language import detect_unicode_script, normalize_language_code
from packages.routing.translation_router import TranslationRouter


def test_script_detection():
    hindi_text = "यह एक परीक्षण दस्तावेज है।"
    script, conf = detect_unicode_script(hindi_text)
    assert script == "Devanagari"
    assert conf > 0.8

    tamil_text = "இது ஒரு சோதனை ஆவணம்."
    script_ta, conf_ta = detect_unicode_script(tamil_text)
    assert script_ta == "Tamil"
    assert conf_ta > 0.8


def test_language_normalization():
    assert normalize_language_code("hi-IN") == "hi"
    assert normalize_language_code("Hindi") == "hi"
    assert normalize_language_code("ta") == "ta"
    assert normalize_language_code("en-US") == "en"


def test_deterministic_router():
    router = TranslationRouter()
    
    # Supported Indic pair -> Bodhan
    dec_indic = router.route(source_language="en", target_language="hi")
    assert dec_indic.provider == "bodhan"
    assert dec_indic.reason == "explicit_supported_language_pair"

    # Unsupported / general pair -> OpenRouter
    dec_gen = router.route(source_language="en", target_language="fr")
    assert dec_gen.provider == "openrouter"

    # Circuit breaker fallback -> OpenRouter
    dec_fallback = router.route(source_language="en", target_language="hi", circuit_open_providers={"bodhan"})
    assert dec_fallback.provider == "openrouter"
