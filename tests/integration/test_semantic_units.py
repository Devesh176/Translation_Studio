import asyncio
import json
import os

import pymupdf

from packages.core.domain.node import (BoundingBox, DocumentIR, DocumentNode, NodeStyle, NodeType, PageNode)
from packages.editing.selection import resolve_selection
from packages.providers.base import TranslationRequest
from packages.providers.openrouter.translation import OpenRouterTranslationProvider
from packages.rendering.pdf_renderer import PDFRenderer
from packages.semantic.qa import check_unit
from packages.semantic.segments import split_segments, is_label_like, glossary_findings
from packages.semantic.units import GroupingConfig, build_units, join_text, union_bbox


def N(i, y0, y1, text, size=11, x0=50, x1=500, t=NodeType.PARAGRAPH):
    return DocumentNode(node_id=i, bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1), source_text=text, type=t,
                        reading_order=int(y0), style=NodeStyle(font_size=size))


def groups(*nodes):
    ir = DocumentIR(pages=[PageNode(page_number=1, nodes=list(nodes))])
    return [[n.node_id for n in r] for r in build_units(ir, GroupingConfig(enabled=True))]


# ---------------- grouping ----------------
def test_group_split_paragraph():
    assert groups(N("a", 100, 124, "The company makes two products and both of"),
                  N("b", 126, 150, "which need raw materials. The first is better.")) == [["a", "b"]]


def test_no_group_identical_style_separate_paragraphs():
    assert groups(N("a", 100, 124, "Finished sentence here."), N("b", 130, 150, "Another one starts.")) == [["a"], ["b"]]


def test_no_group_table_like_numeric():
    assert groups(N("a", 100, 112, "Revenue 12.5 14.1 15%"), N("b", 114, 126, "and costs 9.1 8.2 7%")) == [["a"], ["b"]]


def test_no_group_footnote_size_change_and_far_gap():
    assert groups(N("a", 100, 124, "text goes on and"), N("b", 126, 140, "small note", size=8)) == [["a"], ["b"]]
    assert groups(N("a", 100, 124, "text goes on and"), N("b", 200, 224, "later text")) == [["a"], ["b"]]


def test_disabled_flag():
    ir = DocumentIR(pages=[PageNode(page_number=1, nodes=[N("a", 100, 124, "text and"), N("b", 126, 150, "more text")])])
    assert all(len(r) == 1 for r in build_units(ir, GroupingConfig(enabled=False)))


def test_original_nodes_untouched():
    a, b = N("a", 100, 124, "text goes on and"), N("b", 126, 150, "continues here today")
    before = [n.model_dump() for n in (a, b)]
    build_units(DocumentIR(pages=[PageNode(page_number=1, nodes=[a, b])]))
    after = [n.model_dump() for n in (a, b)]
    for x, y in zip(before, after):
        y["metadata"].pop("grouping", None)
        assert x == y


# ---------------- segments / glossary / qa ----------------
def test_segment_split_abbrev_decimals():
    segs = split_segments("The value is 3.5 units, e.g. big ones. Next sentence follows here. Third one is last!")
    assert [s["id"] for s in segs] == ["s1", "s2", "s3"]
    assert "e.g. big" in segs[0]["text"]


def test_label_like_not_echo_failure():
    assert is_label_like("CoT-SC -> ReAct")
    assert not is_label_like("the system is running")


def test_glossary_and_qa():
    f = check_unit("The slack variable is positive.", "सुस्त चर धनात्मक है।", {"slack variable": "ढील चर"})
    assert any(x["category"] == "terminology" for x in f)
    assert not glossary_findings("slack variable", "ढील चर", {"slack variable": "ढील चर"})
    assert check_unit("a", "", {})[0]["category"] == "empty"
    ids = check_unit("x" * 80, "y" * 80, {}, ["s1", "s2"], ["s1", "s1", "s9"])
    assert ids[0]["category"] == "alignment"


# ---------------- segment-ID contract ----------------
class FakeClient:
    default_model = "m"

    def __init__(self, content):
        self.content = content

    async def chat_completion(self, messages, model=None, temperature=0.1, response_format=None):
        return {"choices": [{"message": {"content": self.content}}], "usage": {"prompt_tokens": 10, "completion_tokens": 10}}


def _tr(content):
    prov = OpenRouterTranslationProvider(client=FakeClient(content))
    req = TranslationRequest(node_id="n", source_text="One. Two. Three.", source_language="en", target_language="hi",
                             segments=[{"id": "s1", "text": "One."}, {"id": "s2", "text": "Two."}, {"id": "s3", "text": "Three."}],
                             context={"heading": "H"})
    return asyncio.run(prov._translate_segments(req, "English", "Hindi"))


def test_segment_contract_ok_and_reordered():
    ok = json.dumps({"translations": [{"id": "s3", "text": "C"}, {"id": "s1", "text": "A"}, {"id": "s2", "text": "B"}]})
    r = _tr(ok)
    assert r.translated_text == "A B C" and r.raw_response["alignment"]["segment_ids"]


def test_segment_contract_rejects_bad_ids_and_malformed():
    assert _tr(json.dumps({"translations": [{"id": "s1", "text": "A"}, {"id": "s2", "text": "B"}]})) is None  # missing
    assert _tr(json.dumps({"translations": [{"id": "s1", "text": "A"}, {"id": "s1", "text": "A"}, {"id": "s2", "text": "B"}]})) is None  # dup
    assert _tr(json.dumps({"translations": [{"id": "s1", "text": "A"}, {"id": "s2", "text": "B"}, {"id": "s9", "text": "C"}]})) is None  # unknown
    assert _tr("not json") is None
    assert _tr(json.dumps({"translations": [{"id": "s1", "text": ""}, {"id": "s2", "text": "B"}, {"id": "s3", "text": "C"}]})) is None  # empty


# ---------------- edit resolver + rendering ----------------
def _stu_ir():
    a, b = N("a", 100, 124, "text goes on and"), N("b", 126, 150, "continues here today")
    ir = DocumentIR(target_language="hi", pages=[PageNode(page_number=1, nodes=[a, b])])
    a.translated_text = "यह पाठ आगे चलता है और आज यहाँ जारी रहता है।"
    a.metadata["stu"] = {"unit_id": "u", "role": "lead", "member_ids": ["b"], "union_bbox": union_bbox([a, b])}
    b.translated_text = ""
    b.metadata["stu"] = {"unit_id": "u", "role": "member", "lead_id": "a"}
    return ir


def test_selection_on_member_resolves_to_lead():
    r = resolve_selection(_stu_ir(), {"kind": "box", "page": 1, "rect": [50, 126, 500, 150]})
    assert [n.node_id for n in r.nodes] == ["a"]


def test_render_stu_does_not_draw_member_and_stays_in_page():
    ir = _stu_ir()
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    out = PDFRenderer().render_ir_to_pdf(ir, original_pdf_bytes=doc.tobytes())
    page = pymupdf.open(stream=out, filetype="pdf")[0]
    assert page.get_text().strip()
    assert ir.pages[0].nodes[1].render_status != "OVERFLOW"


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
