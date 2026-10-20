import unicodedata
from typing import List, Tuple, Optional
import fitz


INDIC_UNICODE_RANGES = [
    (0x0900, 0x097F),  # Devanagari
    (0x0980, 0x09FF),  # Bengali
    (0x0A00, 0x0A7F),  # Gurmukhi
    (0x0A80, 0x0AFF),  # Gujarati
    (0x0B00, 0x0B7F),  # Oriya
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
]


def is_indic_codepoint(cp: int) -> bool:
    for start, end in INDIC_UNICODE_RANGES:
        if start <= cp <= end:
            return True
    return False


def get_grapheme_clusters(text: str) -> List[str]:
    """
    Splits text into grapheme clusters, ensuring combining marks (matras, viramas,
    vowel signs, nukta) stay bound to their base consonant/character.
    """
    if not text:
        return []

    clusters: List[str] = []
    current_cluster: List[str] = []

    for char in text:
        category = unicodedata.category(char)
        # Category starting with 'M' (Mn = Nonspacing mark, Mc = Spacing combining mark, Me = Enclosing mark)
        is_mark = category.startswith("M")

        if is_mark and current_cluster:
            # Bind combining mark to current cluster
            current_cluster.append(char)
        else:
            if current_cluster:
                clusters.append("".join(current_cluster))
            current_cluster = [char]

    if current_cluster:
        clusters.append("".join(current_cluster))

    return clusters


def segment_script_runs(
    text: str,
    primary_font: Optional[fitz.Font],
    fallback_font: Optional[fitz.Font],
) -> List[Tuple[str, bool]]:
    """
    Conforms to Section 66.9 (Indic and complex-script shaping):
    Segments text by Unicode script and grapheme-safe boundaries.
    Never splits combining marks or viramas from base consonants.
    
    Returns list of (run_substring, use_primary_font).
    """
    if not text:
        return []
    if not primary_font:
        return [(text, False)]
    if not fallback_font:
        return [(text, True)]

    clusters = get_grapheme_clusters(text)
    if not clusters:
        return []

    runs: List[Tuple[str, bool]] = []
    current_run: List[str] = []
    current_use_primary: Optional[bool] = None

    for cluster in clusters:
        # Determine script of cluster
        first_char = cluster[0]
        code = ord(first_char)

        # Whitespace and neutral punctuation attach to current active run
        is_neutral = first_char in " \t\r\n.,;:!?-()[]{}'\"/\\•"

        if is_neutral and current_use_primary is not None:
            current_run.append(cluster)
            continue

        # Check if Indic codepoint
        is_indic = any(is_indic_codepoint(ord(c)) for c in cluster)

        if is_indic:
            # Use primary font if font has the glyphs or is Indic font
            use_primary = True
        else:
            # Latin / ASCII / Numeral
            has_primary = all(primary_font.has_glyph(ord(c)) > 0 for c in cluster)
            has_fallback = all(fallback_font.has_glyph(ord(c)) > 0 for c in cluster)
            if has_fallback and not has_primary:
                use_primary = False
            elif has_primary and not has_fallback:
                use_primary = True
            else:
                # Default to fallback for pure Latin ASCII words
                use_primary = False if code < 128 and first_char.isalpha() else (current_use_primary if current_use_primary is not None else False)

        if current_use_primary is None:
            current_use_primary = use_primary
            current_run.append(cluster)
        elif use_primary == current_use_primary:
            current_run.append(cluster)
        else:
            runs.append(("".join(current_run), current_use_primary))
            current_run = [cluster]
            current_use_primary = use_primary

    if current_run:
        runs.append(("".join(current_run), current_use_primary if current_use_primary is not None else True))

    return runs
