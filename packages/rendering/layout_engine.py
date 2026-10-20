from typing import List, Tuple
from packages.core.domain.node import DocumentIR, DocumentNode, PageNode, BoundingBox
from packages.rendering.text_measurement import TextMeasurement


class LayoutEngine:
    def __init__(self, max_shrink_percent: float = 15.0, line_height_multiplier: float = 1.25):
        self.max_shrink_percent = max_shrink_percent
        self.line_height_multiplier = line_height_multiplier

    def compute_layout_for_node(self, node: DocumentNode) -> Tuple[float, List[str], bool]:
        """
        Computes fitted font size, wrapped lines, and whether cascading reflow is needed.
        Returns: (fitted_font_size, lines, needs_reflow)
        """
        text = node.translated_text or node.source_text
        bbox = node.bbox
        available_width = max(10.0, bbox.width)
        available_height = max(10.0, bbox.height)

        initial_font_size = node.style.font_size
        min_font_size = initial_font_size * (1.0 - (self.max_shrink_percent / 100.0))

        font_size = initial_font_size
        step = 0.5

        best_lines = []
        fits = False

        # Tier 1: In-place shrink search
        while font_size >= min_font_size:
            line_height = font_size * self.line_height_multiplier
            lines = TextMeasurement.wrap_text_to_width(text, available_width, font_size)
            required_height = len(lines) * line_height

            if required_height <= available_height:
                best_lines = lines
                fits = True
                break
            font_size -= step

        if not fits:
            # Fallback to min font size lines (Tier 2 triggers cascading reflow)
            font_size = max(6.0, min_font_size)
            best_lines = TextMeasurement.wrap_text_to_width(text, available_width, font_size)
            return (font_size, best_lines, True)

        return (font_size, best_lines, False)
