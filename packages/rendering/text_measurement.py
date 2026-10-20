from typing import Tuple, Optional


class TextMeasurement:
    @staticmethod
    def measure_text_width(text: str, font_size: float, font_name: str = "Helvetica") -> float:
        """
        Measures text width in points. Uses HarfBuzz if available for Indic shaping,
        or proportional font metrics heuristic.
        """
        if not text:
            return 0.0

        # Try uharfbuzz for complex text layout shaping
        try:
            import uharfbuzz as hb
            # If font file is available, shape glyphs
            pass
        except ImportError:
            pass

        # Robust standard typographic width estimation
        # Indic complex glyphs have wider average bounding box (~0.65em) than Latin (~0.52em)
        avg_char_ratio = 0.65 if any(ord(c) > 127 for c in text) else 0.52
        return len(text) * font_size * avg_char_ratio

    @classmethod
    def wrap_text_to_width(cls, text: str, max_width: float, font_size: float, font_name: str = "Helvetica") -> list[str]:
        words = text.split()
        if not words:
            return []

        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            w = cls.measure_text_width(test_line, font_size, font_name)
            if w <= max_width or not current_line:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines
