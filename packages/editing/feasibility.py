"""Feasibility gate: cheap deterministic pre-checks, then a separate small LLM call."""
import json
import re
from dataclasses import dataclass
from typing import Optional

from packages.costs.ledger import CostCollector
from packages.editing.selection import Resolved
from packages.translation.prompts import PromptManager

MAX_INSTRUCTION_CHARS = 1000
_INJECTION_RE = re.compile(
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)|disregard (the )?(system|previous)|reveal (your|the) (system )?prompt",
    re.I,
)
CATEGORIES = {"ok", "out_of_scope", "locked_content", "layout", "policy", "ambiguous"}


@dataclass
class Feasibility:
    feasible: bool
    category: str = "ok"
    reason: str = ""
    suggestion: str = ""
    checked_by: str = "llm"


def _parse(raw: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def precheck(resolved: Resolved, instruction: str) -> Optional[Feasibility]:
    if not instruction.strip():
        return Feasibility(False, "ambiguous", "Please describe the change you want.", "", "rules")
    if len(instruction) > MAX_INSTRUCTION_CHARS:
        return Feasibility(False, "ambiguous", "The request is too long to act on safely.", "Shorten it to one or two sentences.", "rules")
    if not resolved.nodes:
        cat = "locked_content" if resolved.locked else "out_of_scope"
        return Feasibility(False, cat, resolved.reason or "No editable text was found in the selection.",
                           "Select a region that contains translated text.", "rules")
    if _INJECTION_RE.search(instruction):
        return Feasibility(False, "policy", "This request tries to override the editor's rules, so it was not applied.",
                           "Describe how the selected text itself should change.", "rules")
    return None


async def check_feasibility(resolved: Resolved, instruction: str, tgt_lang: str, client,
                            costs: Optional[CostCollector] = None) -> Feasibility:
    pre = precheck(resolved, instruction)
    if pre:
        return pre
    messages = PromptManager.get_feasibility_messages(
        selected_text=resolved.selected_text[:3000], instruction=instruction,
        kind=resolved.kind, types=resolved.types, tgt_lang=tgt_lang,
    )
    try:
        resp = await client.chat_completion(messages=messages, temperature=0.0,
                                            response_format={"type": "json_object"})
    except Exception:
        return Feasibility(True, "ok", "", "", "rules")  # gate unavailable: later validation still guards the edit
    if costs is not None:
        costs.add_llm_response(resp, "feasibility")
    data = _parse(resp["choices"][0]["message"]["content"])
    if not data or "feasible" not in data:
        return Feasibility(True, "ok", "", "", "rules")
    feasible = bool(data["feasible"])
    cat = data.get("category") if data.get("category") in CATEGORIES else ("ok" if feasible else "out_of_scope")
    return Feasibility(feasible, cat, str(data.get("reason", "")), str(data.get("suggestion", "")), "llm")
