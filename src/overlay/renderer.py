"""
Overlay Renderer — shared context and drawing primitives.

Provides ``OverlayContext`` (mutable shared state for all overlay
components) and ``OverlayRenderer`` (outlined-text drawing, canvas
clearing, and colour utilities).
"""

import logging
import tkinter.font as tkfont
from typing import List, Tuple

logger = logging.getLogger("bdo_trainer")

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
TRANSPARENT_COLOR = "#010101"
OUTLINE_COLOR = "#000000"

DEFAULT_SKILL_FONT_SIZE = 32
DEFAULT_INPUT_FONT_SIZE = 22
DEFAULT_NOTE_FONT_SIZE = 14

DEFAULT_SKILL_COLOR = "#FFD700"  # Gold
DEFAULT_INPUT_COLOR = "#FFFFFF"  # White
DEFAULT_NOTE_COLOR = "#AAAAAA"  # Gray
DEFAULT_SUCCESS_COLOR = "#4CAF50"  # Green

PROTECTION_COLORS = {
    "SA": "#4CAF50",  # Green
    "FG": "#2196F3",  # Blue
    "iframe": "#9C27B0",  # Purple
    "none": "#F44336",  # Red
}

# Pre-computed outline offsets (thickness 2)
_OUTLINE_THICKNESS = 2
OUTLINE_OFFSETS: List[Tuple[int, int]] = [
    (dx, dy)
    for dx in range(-_OUTLINE_THICKNESS, _OUTLINE_THICKNESS + 1)
    for dy in range(-_OUTLINE_THICKNESS, _OUTLINE_THICKNESS + 1)
    if (dx, dy) != (0, 0) and abs(dx) + abs(dy) > _OUTLINE_THICKNESS
]


# =========================================================================
# OverlayContext — mutable shared state for all overlay components
# =========================================================================
class OverlayContext:
    """Mutable shared state passed to every overlay component.

    Attributes that may change at runtime (``cx``, ``cy``) are mutated
    in-place by the owning component (e.g. ``RepositionHandler``), and
    every other component sees the update automatically.
    """

    def __init__(
        self,
        root,
        canvas,
        screen_w: int,
        screen_h: int,
        cx: int,
        cy: int,
        *,
        font_family: str = "Segoe UI",
        skill_font_size: int = DEFAULT_SKILL_FONT_SIZE,
        input_font_size: int = DEFAULT_INPUT_FONT_SIZE,
        note_font_size: int = DEFAULT_NOTE_FONT_SIZE,
        skill_color: str = DEFAULT_SKILL_COLOR,
        input_color: str = DEFAULT_INPUT_COLOR,
        note_color: str = DEFAULT_NOTE_COLOR,
        show_protection: bool = True,
        show_notes: bool = True,
    ) -> None:
        # Tk references
        self.root = root
        self.canvas = canvas

        # Screen geometry
        self.screen_w = screen_w
        self.screen_h = screen_h

        # Anchor point (mutable — changed by reposition)
        self.cx = cx
        self.cy = cy

        # Fonts (require a live Tk root)
        self.skill_font = tkfont.Font(
            family=font_family, size=skill_font_size, weight="bold"
        )
        self.input_font = tkfont.Font(family=font_family, size=input_font_size)
        self.note_font = tkfont.Font(family=font_family, size=note_font_size)
        self.counter_font = tkfont.Font(family=font_family, size=note_font_size - 2)
        self.preview_font = tkfont.Font(
            family=font_family, size=note_font_size - 2, slant="italic"
        )
        self.header_font = tkfont.Font(
            family=font_family, size=note_font_size, slant="italic"
        )

        # Display settings
        self.skill_color = skill_color
        self.input_color = input_color
        self.note_color = note_color
        self.show_protection = show_protection
        self.show_notes = show_notes


# =========================================================================
# OverlayRenderer — drawing primitives and colour utilities
# =========================================================================
class OverlayRenderer:
    """Canvas drawing helpers shared by all overlay components."""

    def __init__(self, ctx: OverlayContext) -> None:
        self.ctx = ctx

    # -----------------------------------------------------------------
    # Text drawing
    # -----------------------------------------------------------------
    def draw_outlined_text(
        self,
        x: int,
        y: int,
        text: str,
        font: tkfont.Font,
        color: str,
        anchor: str = "center",
        tag: str = "step",
    ) -> None:
        """Draw *text* with a dark outline for readability over any background."""
        canvas = self.ctx.canvas
        for dx, dy in OUTLINE_OFFSETS:
            canvas.create_text(
                x + dx,
                y + dy,
                text=text,
                font=font,
                fill=OUTLINE_COLOR,
                anchor=anchor,
                tags=(tag,),
            )
        # Main text on top
        canvas.create_text(
            x,
            y,
            text=text,
            font=font,
            fill=color,
            anchor=anchor,
            tags=(tag,),
        )

    def clear(self, tag: str = "step") -> None:
        """Remove all canvas items with the given *tag*."""
        try:
            self.ctx.canvas.delete(tag)
        except Exception:
            pass

    def clear_step(self) -> None:
        """Remove combo-step and hold-bar canvas items."""
        self.clear("step")
        self.clear("hold_bar")

    # -----------------------------------------------------------------
    # Text wrapping
    # -----------------------------------------------------------------
    @staticmethod
    def wrap_text(text: str, max_chars: int = 65) -> List[str]:
        """Simple word-wrap helper for multi-line outlined text."""
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            if current and len(current) + 1 + len(word) > max_chars:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}" if current else word
        if current:
            lines.append(current)
        return lines

    # -----------------------------------------------------------------
    # Colour utilities
    # -----------------------------------------------------------------
    @staticmethod
    def hold_bar_color(progress: float) -> str:
        """Interpolate bar fill colour: amber → gold → green."""
        if progress < 0.6:
            t = progress / 0.6
            r = int(0xB8 + (0xFF - 0xB8) * t)
            g = int(0x86 + (0xD7 - 0x86) * t)
            b = int(0x0B + (0x00 - 0x0B) * t)
        else:
            t = (progress - 0.6) / 0.4
            r = int(0xFF + (0x4C - 0xFF) * t)
            g = int(0xD7 + (0xAF - 0xD7) * t)
            b = int(0x00 + (0x50 - 0x00) * t)
        return (
            f"#{max(0, min(255, r)):02x}"
            f"{max(0, min(255, g)):02x}"
            f"{max(0, min(255, b)):02x}"
        )

    @staticmethod
    def lighten_color(hex_color: str, amount: float) -> str:
        """Lighten a hex colour by mixing toward white."""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def lerp_color(c1: str, c2: str, t: float) -> str:
        """Linearly interpolate between two hex colours."""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return (
            f"#{max(0, min(255, r)):02x}"
            f"{max(0, min(255, g)):02x}"
            f"{max(0, min(255, b)):02x}"
        )
