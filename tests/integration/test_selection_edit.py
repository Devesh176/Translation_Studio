import json
import fitz
import pytest

from apps.worker.tasks.pipeline import DocumentTranslationPipeline
from apps.worker.tasks.section_edit import SectionEditPipeline
from packages.costs.ledger import CostLedger
from packages.editing.selection import resolve_selection, find_quote
from packages.storage.object_store.local_store import MemoryObjectStore


class FakeLLM:
    def __init__(self, feasible=True, edit="EDITED"):
        self.feasible, self.edit, self.calls = feasible, edit, []

    async def chat_completion(self, messages, model=None, temperature=0.1, response_format=None):
        self.calls.append(response_format)
        if response_format:
            body = json.dumps({"feasible": self.feasible, "category": "ok" if self.feasible else "layout",
                               "reason": "needs image change", "suggestion": "edit text only"})
        else:
            body = self.edit
        return {"choices": [{"message": {"content": body}}], "model": "fake",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}}


def _pdf():
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((50, 70), "Quarterly Financial Overview", fontsize=16)
    p.insert_text((50, 200), "Total revenue increased by 15.5 percent this year.", fontsize=11)
    b = d.tobytes()
    d.close()
    return b


async def _setup():
    storage = MemoryObjectStore()
    await storage.put_object("documents/d1/original.pdf", _pdf(), "application/pdf")
    res = await DocumentTranslationPipeline(storage_store=storage).execute(
        document_id="d1", pdf_bytes=_pdf(), target_language="hi", source_language="en")
    return storage, res


@pytest.mark.asyncio
async def test_box_edit_feasible_and_cost():
    storage, res = await _setup()
    ir = res["ir"]
    n = [x for x in ir.get_all_nodes() if "revenue" in x.source_text][0]
    sel = {"kind": "box", "page": 1, "rect": list(n.bbox.as_tuple())}
    r = resolve_selection(ir, sel)
    assert [x.node_id for x in r.nodes] == [n.node_id]

    pipe = SectionEditPipeline(storage, openrouter_client=FakeLLM(edit="नया पाठ 15.5"))
    out = await pipe.edit_selection("d1", res["version_id"], "make it formal", sel)
    assert out["status"] == "COMPLETED" and out["changed_pages"] == [1]
    assert out["version_id"] != res["version_id"]
    assert await storage.exists(f"documents/d1/versions/{out['version_id']}/output.pdf")
    summary = await CostLedger(storage).summary("d1")
    assert summary["edit_usd"] > 0 and summary["total_usd"] >= summary["edit_usd"]


@pytest.mark.asyncio
async def test_rejected_creates_no_version_and_empty_selection():
    storage, res = await _setup()
    n = [x for x in res["ir"].get_all_nodes() if "revenue" in x.source_text][0]
    sel = {"kind": "box", "page": 1, "rect": list(n.bbox.as_tuple())}
    out = await SectionEditPipeline(storage, FakeLLM(feasible=False)).edit_selection("d1", res["version_id"], "replace the logo", sel)
    assert out["status"] == "REJECTED" and out["category"] == "layout"

    empty = {"kind": "box", "page": 1, "rect": [400, 600, 500, 700]}
    llm = FakeLLM()
    out = await SectionEditPipeline(storage, llm).edit_selection("d1", res["version_id"], "shorten", empty)
    assert out["status"] == "REJECTED" and llm.calls == []  # deterministic pre-check, no LLM call


@pytest.mark.asyncio
async def test_text_span_is_spliced():
    storage, res = await _setup()
    ir = res["ir"]
    n = [x for x in ir.get_all_nodes() if "revenue" in x.source_text][0]
    text = n.translated_text
    quote = text.split()[0]
    sel = {"kind": "text", "page": 1, "quote": quote, "rects": [list(n.bbox.as_tuple())]}
    out = await SectionEditPipeline(storage, FakeLLM(edit="XYZ")).edit_selection("d1", res["version_id"], "replace word", sel)
    assert out["status"] == "COMPLETED"
    assert out["changes"][0]["after"].startswith("XYZ")
    assert out["changes"][0]["after"].endswith(text[len(quote):])


def test_find_quote_whitespace_insensitive():
    assert find_quote("a  b\nc d", "b c") == (3, 6)
