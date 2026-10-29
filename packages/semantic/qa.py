"""Semantic QA: deterministic checks on every unit; optional LLM review of flagged units only."""
import json
import re
from typing import Any, Dict, List, Optional

from packages.semantic.segments import glossary_findings

_LATIN_WORD = re.compile(r"[A-Za-z]{4,}")


def check_unit(source: str, target: str, glossary: Dict[str, str], expected_ids: Optional[List[str]] = None,
               got_ids: Optional[List[str]] = None, src_lang: str = "en", tgt_lang: str = "hi") -> List[Dict[str, Any]]:
    f: List[Dict[str, Any]] = []
    if not (target or "").strip():
        return [{"severity": "high", "category": "empty", "segments": [], "detail": "empty translation"}]
    if expected_ids is not None and got_ids is not None:
        missing = [i for i in expected_ids if i not in got_ids]
        extra = [i for i in got_ids if i not in expected_ids]
        dup = sorted({i for i in got_ids if got_ids.count(i) > 1})
        if missing or extra or dup:
            f.append({"severity": "high", "category": "alignment", "segments": missing + extra + dup,
                      "detail": f"missing={missing} unknown={extra} duplicate={dup}"})
    if src_lang != tgt_lang and tgt_lang != "en":
        src_words = {w.lower() for w in _LATIN_WORD.findall(source)}
        left = [w for w in _LATIN_WORD.findall(target) if w.lower() in src_words]
        n_words = max(1, len(target.split()))
        if len(left) / n_words > 0.4 and len(left) >= 4:
            f.append({"severity": "medium", "category": "untranslated_text", "segments": [],
                      "detail": f"{len(left)} source words remain"})
    ratio = len(target) / max(1, len(source))
    if len(source) > 60 and (ratio < 0.35 or ratio > 4.0):
        f.append({"severity": "medium", "category": "length_anomaly", "segments": [],
                  "detail": f"target/source length ratio {ratio:.2f}"})
    if re.search(r"(.{12,}?)\1{2,}", target):
        f.append({"severity": "medium", "category": "repetition", "segments": [], "detail": "repeated phrase"})
    f.extend(glossary_findings(source, target, glossary))
    return f


async def llm_review(client, source: str, target: str, glossary: Dict[str, str], context: str,
                     src_lang: str, tgt_lang: str, costs=None) -> List[Dict[str, Any]]:
    """Independent reviewer for flagged units. Returns structured findings; never rewrites text."""
    sys = ("You are a bilingual translation reviewer. Compare SOURCE and TRANSLATION. Report only real problems: "
           "missing or added information, reversed relations, altered numbers or instructions, wrong terminology, "
           "dangling fragments. Placeholders like ⟦P1⟧ are protected and must be ignored. Respond with JSON only: "
           '{"findings":[{"severity":"low|medium|high","category":"...","segments":[],"detail":"...","suggestion":"..."}]}')
    user = json.dumps({"source_language": src_lang, "target_language": tgt_lang, "source": source,
                       "translation": target, "context": context[:600], "glossary": glossary}, ensure_ascii=False)
    try:
        resp = await client.chat_completion(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.0, response_format={"type": "json_object"})
        if costs is not None:
            costs.add_llm_response(resp, "semantic_review")
        raw = resp["choices"][0]["message"]["content"]
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip())
        return [dict(x, source="llm") for x in data.get("findings", []) if isinstance(x, dict)]
    except Exception:
        return []
