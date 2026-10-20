import re
from typing import List, Tuple, Dict, Any


class DuplicateContentDetector:
    """
    Implements Duplicate Content Detection per Section 7.2 of Modification V1:
    Detects repeated words, short phrases, and sentences in translated text.
    Specifically calibrated to catch translation stuttering and hallucinations
    (such as the Problem 47 failure case with repeated 'शुद्धता').
    """

    # Common punctuation to clean for token comparison
    CLEAN_PUNCT_REGEX = r"[.,\/#!$%\^&\*;:{}=\-_`~()।\"'«»\?]"

    @classmethod
    def detect_duplicates(cls, text: str) -> List[Dict[str, Any]]:
        """
        Inspects text for:
        1. Consecutive duplicate words (e.g. 'word word' or 'शुद्धता ... शुद्धता।')
        2. Duplicate phrases (2-4 word n-grams repeated within proximity)
        3. Isolated duplicate sentence fragments
        Returns a list of issue dictionaries.
        """
        issues: List[Dict[str, Any]] = []
        if not text or len(text.strip()) < 3:
            return issues

        # 1. Check for immediate consecutive identical words
        # e.g., "है। शुद्धता।" or "शब्द शब्द"
        raw_tokens = [w.strip() for w in text.split() if w.strip()]
        cleaned_tokens = [re.sub(cls.CLEAN_PUNCT_REGEX, "", t) for t in raw_tokens]

        for i in range(len(cleaned_tokens) - 1):
            w1 = cleaned_tokens[i]
            w2 = cleaned_tokens[i + 1]
            if w1 and len(w1) > 2 and w1 == w2:
                issues.append({
                    "type": "DUPLICATE_WORD",
                    "phrase": w1,
                    "evidence": f"Immediate repetition of '{w1}' at token index {i}",
                })

        # 2. Check for duplicate short phrases (2-4 words) repeated immediately or in high-frequency loops
        # Immediate repetition (e.g. "की शुद्धता की शुद्धता") or looping (3+ occurrences in close window)
        for n in range(2, 5):
            if len(cleaned_tokens) < n * 2:
                continue
            seen_ngrams: Dict[Tuple[str, ...], List[int]] = {}
            for i in range(len(cleaned_tokens) - n + 1):
                ngram = tuple(cleaned_tokens[i:i + n])
                if any(len(w) < 2 for w in ngram):
                    continue
                if ngram not in seen_ngrams:
                    seen_ngrams[ngram] = [i]
                else:
                    prev_indices = seen_ngrams[ngram]
                    last_idx = prev_indices[-1]
                    # Check for immediate back-to-back repetition (e.g. [A B] [A B])
                    if i <= last_idx + n:
                        issues.append({
                            "type": "DUPLICATE_PHRASE",
                            "phrase": " ".join(ngram),
                            "evidence": f"Immediate back-to-back repetition of phrase '{' '.join(ngram)}'",
                        })
                    # Check for loop repetition (repeated 3 or more times within 25 tokens)
                    elif len(prev_indices) >= 2 and (i - prev_indices[0]) <= 25:
                        issues.append({
                            "type": "DUPLICATE_PHRASE",
                            "phrase": " ".join(ngram),
                            "evidence": f"Phrase '{' '.join(ngram)}' repeated {len(prev_indices) + 1} times within 25 words (looping defect)",
                        })
                    prev_indices.append(i)

        # 3. Check for isolated single-word or short fragment sentences
        # e.g. "टाइप 2 की शुद्धता 70% है। शुद्धता। कच्चा माल..."
        # Here 'शुद्धता।' is an isolated fragment that duplicates the previous predicate
        sentences = [s.strip() for s in re.split(r"[।\.\?!]", text) if s.strip()]
        for idx in range(len(sentences) - 1):
            s1_words = [re.sub(cls.CLEAN_PUNCT_REGEX, "", w) for w in sentences[idx].split()]
            s2_words = [re.sub(cls.CLEAN_PUNCT_REGEX, "", w) for w in sentences[idx + 1].split()]
            
            # If s2 is a single word or 2 words that already appeared in s1
            if 1 <= len(s2_words) <= 2:
                if all(w in s1_words for w in s2_words if len(w) > 2):
                    fragment = " ".join(s2_words)
                    issues.append({
                        "type": "DUPLICATE_PHRASE",
                        "phrase": fragment,
                        "evidence": f"Isolated sentence fragment '{fragment}' repeats content from previous clause",
                    })

        return issues
