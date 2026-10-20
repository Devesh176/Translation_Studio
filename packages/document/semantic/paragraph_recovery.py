import re
from typing import List
from packages.core.domain.node import DocumentNode, NodeType, BoundingBox, TextSpan


class ParagraphRecoveryEngine:
    """
    Implements Section 4.1 & 4.3 of Modification V1:
    Distinguishes visual lines from semantic paragraphs.
    Assembles wrapped PDF lines into logical paragraphs based on font/style continuity,
    line spacing, punctuation, and list/heading boundaries.
    """

    LIST_PREFIX_REGEX = r"^([•\-\*]|\d+\.|\([a-z0-9]+\))\s+"
    HEADING_TYPES = (NodeType.TITLE, NodeType.SECTION_HEADING, NodeType.SUBHEADING, NodeType.HEADING)
    SPECIAL_TYPES = (
        NodeType.TABLE, NodeType.TABLE_ROW, NodeType.TABLE_CELL,
        NodeType.CODE_BLOCK, NodeType.COMMAND, NodeType.CONFIG_BLOCK,
        NodeType.FOOTNOTE, NodeType.FOOTNOTE_REFERENCE, NodeType.HEADER, NodeType.FOOTER
    )

    @classmethod
    def recover_paragraphs(cls, nodes: List[DocumentNode], line_spacing_threshold: float = 1.6) -> List[DocumentNode]:
        """
        Takes raw extracted line nodes and merges lines belonging to the same logical
        paragraph while preserving headings, list items, and code blocks.
        """
        if not nodes:
            return []

        # Sort nodes by reading order / geometry
        sorted_nodes = sorted(nodes, key=lambda n: (n.page_number, n.bbox.y0, n.bbox.x0))
        recovered: List[DocumentNode] = []
        current: DocumentNode = None

        for node in sorted_nodes:
            # Special structures are never merged into paragraphs
            if node.type in cls.SPECIAL_TYPES:
                if current:
                    recovered.append(current)
                    current = None
                recovered.append(node)
                continue

            # Check if this node is a heading or start of list item
            is_heading = node.type in cls.HEADING_TYPES
            is_list = re.match(cls.LIST_PREFIX_REGEX, node.source_text.strip()) is not None or node.type in (NodeType.LIST_ITEM, NodeType.BULLET_LIST, NodeType.NUMBERED_LIST)

            if is_heading or is_list:
                if current:
                    recovered.append(current)
                    current = None
                recovered.append(node)
                continue

            if current is None:
                current = node.model_copy(deep=True)
                continue

            # Check if node can be merged with current paragraph
            # 1. Must be on same page
            same_page = (node.page_number == current.page_number)
            # 2. Check font size and style continuity
            style_match = abs(node.style.font_size - current.style.font_size) <= 1.5
            # 3. Check line spacing
            expected_line_height = max(10.0, current.style.line_height or current.style.font_size * 1.3)
            vertical_gap = node.bbox.y0 - current.bbox.y1
            line_spacing_ok = (-2.0 <= vertical_gap <= expected_line_height * line_spacing_threshold)

            # 4. Check if previous line ended with a terminal punctuation (e.g. ., !, ?, ।, :)
            prev_text = current.source_text.strip()
            prev_ended_sentence = bool(re.search(r"[\.!\?।:]$", prev_text))

            # 5. Check if hyphenated at line wrap
            is_hyphenated = prev_text.endswith("-")

            can_merge = same_page and style_match and line_spacing_ok and not (prev_ended_sentence and vertical_gap > expected_line_height * 0.8)

            if can_merge:
                # Merge text
                if is_hyphenated:
                    # Strip trailing hyphen and join directly
                    merged_text = prev_text[:-1] + node.source_text.strip()
                else:
                    merged_text = f"{prev_text} {node.source_text.strip()}"

                current.source_text = merged_text
                # Expand bounding box
                current.bbox = BoundingBox(
                    x0=min(current.bbox.x0, node.bbox.x0),
                    y0=min(current.bbox.y0, node.bbox.y0),
                    x1=max(current.bbox.x1, node.bbox.x1),
                    y1=max(current.bbox.y1, node.bbox.y1),
                )
                # Combine spans
                if node.spans:
                    current.spans.extend(node.spans)
            else:
                recovered.append(current)
                current = node.model_copy(deep=True)

        if current:
            recovered.append(current)

        # Re-assign reading order indices
        for idx, n in enumerate(recovered):
            n.reading_order = idx

        return recovered
