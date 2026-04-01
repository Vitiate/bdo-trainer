"""
Shared key-display and rendering utilities for BDO Trainer.

This module provides a single source of truth for converting canonical
key names (e.g. ``"shift"``, ``"lmb"``) into user-friendly display
strings (e.g. ``"Shift"``, ``"LMB"``), and pre-computed outline offsets
for the overlay text renderer.
"""

from typing import Dict, List, Tuple

# -----------------------------------------------------------------------
# Canonical key name → display-friendly label
# -----------------------------------------------------------------------
_KEY_DISPLAY_NAMES: Dict[str, str] = {
    "shift": "Shift",
    "ctrl": "Ctrl",
    "alt": "Alt",
    "space": "Space",
    "lmb": "LMB",
    "rmb": "RMB",
    "mmb": "MMB",
    "enter": "Enter",
    "tab": "Tab",
    "backspace": "Back",
    "delete": "Del",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


def format_key_display(key: str) -> str:
    """Turn a canonical key name into a display-friendly string.

    Examples::

        format_key_display("shift")  # → "Shift"
        format_key_display("lmb")    # → "LMB"
        format_key_display("a")      # → "A"
        format_key_display("F5")     # → "F5"
    """
    lower = key.lower()
    if lower in _KEY_DISPLAY_NAMES:
        return _KEY_DISPLAY_NAMES[lower]
    if len(key) == 1:
        return key.upper()
    # F-keys (F1–F24)
    if key.upper().startswith("F") and key[1:].isdigit():
        return key.upper()
    return key.capitalize()


# -----------------------------------------------------------------------
# Pre-computed outline offsets for text rendering
# -----------------------------------------------------------------------
def _build_outline_offsets(thickness: int) -> List[Tuple[int, int]]:
    """Return the list of (dx, dy) offsets that form the outline ring
    around a text element, excluding the centre and interior positions.

    Only positions on the outer edge (Manhattan distance > *thickness*)
    are included, which gives a clean outline without redundant interior
    copies.
    """
    return [
        (dx, dy)
        for dx in range(-thickness, thickness + 1)
        for dy in range(-thickness, thickness + 1)
        if (dx, dy) != (0, 0) and abs(dx) + abs(dy) > thickness
    ]


#: Pre-computed offsets for the default outline thickness of 2.
OUTLINE_OFFSETS: List[Tuple[int, int]] = _build_outline_offsets(2)
