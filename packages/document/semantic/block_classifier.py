import re
from typing import List
from packages.core.domain.node import DocumentNode, NodeType


class SemanticBlockClassifier:
    """
    Classifies nodes into semantic types conforming to Section 66.5:
    TITLE, SECTION_HEADING, SUBHEADING, PARAGRAPH, BULLET_LIST, LIST_ITEM,
    CODE_BLOCK, COMMAND, CONFIG_BLOCK, URL, EMAIL, FILE_PATH.
    """

    COMMAND_PREFIXES = (
        "$ ", "# ", "pip ", "conda ", "git ", "docker ", "python ",
        "python3 ", "npm ", "npx ", "brew ", "apt-get ", "curl ", "wget ", "sudo "
    )

    @classmethod
    def classify_node(cls, node: DocumentNode, body_font_size: float = 11.0) -> NodeType:
        text = node.source_text.strip()
        if not text:
            return NodeType.PARAGRAPH

        # Check for command lines
        if any(text.startswith(prefix) for prefix in cls.COMMAND_PREFIXES) or text.startswith("$"):
            return NodeType.COMMAND

        # Check for Code / Config blocks
        font_family = (node.style.font_family or "").lower()
        if "mono" in font_family or "courier" in font_family or "consolas" in font_family:
            return NodeType.CODE_BLOCK

        # Check for list items
        if re.match(r"^([•\-\*]|\d+\.|\([a-z0-9]+\))\s+", text):
            return NodeType.LIST_ITEM

        # Check for headings based on font size hierarchy
        font_size = node.style.font_size
        if font_size >= body_font_size * 1.5:
            return NodeType.TITLE
        elif font_size >= body_font_size * 1.25:
            return NodeType.SECTION_HEADING
        elif font_size > body_font_size * 1.05 and (node.style.font_weight == "bold" or node.style.is_bold):
            return NodeType.SUBHEADING

        # Check for standalone URLs
        if re.match(r"^https?://[^\s]+$", text):
            return NodeType.URL

        return NodeType.PARAGRAPH

    @classmethod
    def classify_nodes(cls, nodes: List[DocumentNode]) -> None:
        # Determine average body font size
        font_sizes = [n.style.font_size for n in nodes if n.style.font_size > 0]
        avg_body_size = (sum(font_sizes) / max(1, len(font_sizes))) if font_sizes else 11.0

        for node in nodes:
            # Preserve existing explicit tables, footnotes, headers, footers
            if node.type in [
                NodeType.TABLE, NodeType.TABLE_ROW, NodeType.TABLE_CELL,
                NodeType.FOOTNOTE, NodeType.FOOTNOTE_REFERENCE,
                NodeType.HEADER, NodeType.FOOTER, NodeType.FIGURE
            ]:
                continue
            node.type = cls.classify_node(node, body_font_size=avg_body_size)
