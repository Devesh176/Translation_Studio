from packages.core.domain.node import *
from packages.semantic.units import build_units, GroupingConfig, join_text

def N(i, y0, y1, text, size=11, x0=50, x1=500, t=NodeType.PARAGRAPH, order=None):
    return DocumentNode(node_id=i, bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1), source_text=text,
                        type=t, reading_order=order if order is not None else int(y0), style=NodeStyle(font_size=size))

def ir_of(*nodes):
    return DocumentIR(pages=[PageNode(page_number=1, nodes=list(nodes))])

def groups(*nodes):
    return [[n.node_id for n in r] for r in build_units(ir_of(*nodes), GroupingConfig(enabled=True))]

def test_split_paragraph_grouped():
    assert groups(N("a", 100, 124, "The company manufactures two products and both of"),
                  N("b", 126, 150, "which require raw materials. The first is better.")) == [["a", "b"]]

def test_separate_paragraphs_kept():
    assert groups(N("a", 100, 124, "This paragraph is complete."),
                  N("b", 130, 150, "This one starts a new idea.")) == [["a"], ["b"]]

def test_heading_and_list_and_columns_not_merged():
    assert groups(N("h", 100, 115, "Introduction", t=NodeType.HEADING), N("p", 117, 140, "text continues here and")) == [["h"], ["p"]]
    assert groups(N("a", 100, 124, "first item and"), N("b", 126, 150, "- second item")) == [["a"], ["b"]]
    assert groups(N("a", 100, 124, "left column text and", x1=250), N("b", 126, 150, "right column text", x0=300, x1=500)) == [["a"], ["b"]]

def test_short_label_not_merged():
    assert groups(N("a", 100, 112, "Total cost"), N("b", 114, 140, "the amount is paid.")) == [["a"], ["b"]]

def test_join_dehyphenate():
    assert join_text(["manufac-", "turing is"]) == "manufacturing is"

if __name__ == "__main__":
    import sys
    for k, v in list(globals().items()):
        if k.startswith("test_"): v(); print("ok", k)
