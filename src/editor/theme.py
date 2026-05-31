"""Shared theme constants and dialog helpers for the editor windows."""

from __future__ import annotations

import tkinter as tk
from typing import Optional

# ---------------------------------------------------------------------------
# Theme constants — Solarized Dark
# ---------------------------------------------------------------------------
BG_DARK = "#002B36"
BG_CARD = "#073642"
BG_INPUT = "#073642"
FG_TEXT = "#93A1A1"
FG_DIM = "#657B83"
ACCENT = "#268BD2"
ACCENT_HOVER = "#2AA198"
GOLD = "#B58900"
GREEN = "#859900"
RED_SOFT = "#DC322F"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_HEADING = ("Segoe UI", 12, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 9)


def force_dialog_to_front(toplevel: tk.Toplevel) -> None:
    """Keep a modal Toplevel reliably in front for its entire lifetime.

    macOS specifics this works around:
      • A Toplevel created right after a native file picker closes is
        often pushed behind its parent.
      • If the parent already has ``-topmost True`` (the editor windows
        do), the two fight for stacking and clicking the dialog can
        hoist the parent above it.
      • ``grab_set`` doesn't prevent macOS from raising the parent on
        click.

    The fix is twofold:

      1. Temporarily turn off ``-topmost`` on the parent so the dialog's
         own topmost flag always wins. Restore the parent's value when
         the dialog is destroyed.
      2. Re-apply ``-topmost True`` + ``lift`` + ``focus_force`` across
         several after-passes to outlast the macOS reordering that
         happens after a file picker closes.
    """
    parent = toplevel.master
    parent_was_topmost = False
    if parent is not None:
        try:
            parent_was_topmost = bool(parent.attributes("-topmost"))
            if parent_was_topmost:
                parent.attributes("-topmost", False)
        except tk.TclError:
            parent_was_topmost = False

    def _bring_up() -> None:
        try:
            toplevel.attributes("-topmost", True)
            toplevel.lift()
            toplevel.focus_force()
        except tk.TclError:
            pass

    _bring_up()
    try:
        toplevel.after_idle(_bring_up)
        toplevel.after(50, _bring_up)
        toplevel.after(150, _bring_up)
        toplevel.after(400, _bring_up)
    except tk.TclError:
        pass

    def _on_destroy(event: Optional[tk.Event] = None) -> None:
        if event is not None and event.widget is not toplevel:
            return
        if parent is not None and parent_was_topmost:
            try:
                if parent.winfo_exists():
                    parent.attributes("-topmost", True)
            except tk.TclError:
                pass

    try:
        toplevel.bind("<Destroy>", _on_destroy, add="+")
    except tk.TclError:
        pass
