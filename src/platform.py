"""
Platform-specific helpers for BDO Trainer.

Provides click-through window management (Windows) and
platform-appropriate font detection.
"""

import logging
import sys
import tkinter as tk

logger = logging.getLogger("bdo_trainer")


# ---------------------------------------------------------------------------
# Platform-appropriate default font
# ---------------------------------------------------------------------------
def default_font_family() -> str:
    """Return a platform-appropriate default font family."""
    if sys.platform == "darwin":
        return "Helvetica Neue"
    elif sys.platform == "win32":
        return "Segoe UI"
    else:
        return "DejaVu Sans"


# ---------------------------------------------------------------------------
# Win32: make the overlay click-through
# ---------------------------------------------------------------------------
def make_click_through(root: tk.Tk) -> None:
    """Set the WS_EX_TRANSPARENT extended style so mouse events pass through."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED
        )
        logger.info("Overlay set to click-through (Windows)")
    except Exception as e:
        logger.warning(f"Could not set click-through: {e}")


def remove_click_through(root: tk.Tk) -> None:
    """Remove the click-through style so the overlay captures mouse events."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT
        )
        logger.info("Overlay click-through removed (Windows)")
    except Exception as e:
        logger.warning(f"Could not remove click-through: {e}")
