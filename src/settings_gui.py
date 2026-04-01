"""
Settings GUI — Key bindings, display, hotkeys, and timing configuration.

Opens as a Toplevel window from the overlay's Tk root.  All cross-thread
access is done via ``overlay.schedule()`` before this window is created,
so everything here runs on the Tk main thread.
"""

import logging
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from src.utils.keys import format_key_display

logger = logging.getLogger("bdo_trainer")

# ---------------------------------------------------------------------------
# Theme colours
# ---------------------------------------------------------------------------
BG_DARK = "#1A1A2E"
BG_CARD = "#16213E"
BG_INPUT = "#0F3460"
BG_INPUT_ACTIVE = "#1A4A80"
FG_TEXT = "#E8E8E8"
FG_DIM = "#888888"
ACCENT = "#E94560"
ACCENT_HOVER = "#FF6B81"
GOLD = "#FFD700"
GREEN = "#4CAF50"
GREEN_DARK = "#388E3C"
BLUE = "#2196F3"
RED_SOFT = "#CF6679"

# ---------------------------------------------------------------------------
# BDO key binding definitions:  (bdo_name, section_label, default_value)
# ---------------------------------------------------------------------------
BDO_KEY_BINDINGS: List[Tuple[str, str, str]] = [
    ("Move Forward", "Movement", "w"),
    ("Move Back", "Movement", "s"),
    ("Move Left", "Movement", "a"),
    ("Move Right", "Movement", "d"),
    ("LMB", "Mouse", "lmb"),
    ("RMB", "Mouse", "rmb"),
    ("MMB", "Mouse", "mmb"),
    ("Jump", "Modifiers", "space"),
    ("Sprint", "Modifiers", "shift"),
    ("Q", "Abilities", "q"),
    ("E", "Abilities", "e"),
    ("F", "Abilities", "f"),
    ("X", "Abilities", "x"),
    ("Z", "Abilities", "z"),
]

# Map tkinter keysym → normalised key name used by the trainer
_KEYSYM_MAP: Dict[str, Optional[str]] = {
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Control_L": "ctrl",
    "Control_R": "ctrl",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "space": "space",
    "Return": "enter",
    "Escape": None,  # sentinel — means "cancel"
    "Tab": "tab",
    "BackSpace": "backspace",
    "Delete": "delete",
    "Up": "up",
    "Down": "down",
    "Left": "left",
    "Right": "right",
}

# Default settings (used by "Reset to Defaults")
_DEFAULT_SETTINGS: Dict[str, Any] = {
    "active_combo": "basic_grind",
    "default_combo_window_ms": 250,
    "display": {
        "show_protection_type": True,
        "show_cc_type": True,
        "show_key_overlay": True,
        "highlight_protected_skills": True,
        "highlight_iframes": True,
    },
    "hotkeys": {
        "start_combo": "F5",
        "stop_combo": "F6",
        "next_step": "F7",
        "reset_combo": "F8",
    },
    "key_bindings": {
        "Move Forward": "w",
        "Move Back": "s",
        "Move Left": "a",
        "Move Right": "d",
        "LMB": "lmb",
        "RMB": "rmb",
        "MMB": "mmb",
        "Jump": "space",
        "Sprint": "shift",
        "Q": "q",
        "E": "e",
        "F": "f",
        "X": "x",
        "Z": "z",
    },
    "timing": {
        "step_highlight_duration_ms": 500,
        "transition_delay_ms": 100,
        "auto_advance": False,
        "idle_reset_timeout_ms": 10000,
    },
}


# ===================================================================
# Helpers
# ===================================================================


def _deep_copy(obj: Any) -> Any:
    """Simple deep-copy for JSON-like structures (dicts / lists / scalars)."""
    if isinstance(obj, dict):
        return {k: _deep_copy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_copy(v) for v in obj]
    return obj


def _normalize_keysym(event: tk.Event) -> Optional[str]:
    """Convert a tkinter ``<KeyPress>`` *event* to the key-name string the
    trainer uses, or ``None`` if the key should be ignored / means cancel."""
    keysym: str = event.keysym

    # Function keys (F1–F24)
    if keysym.startswith("F") and keysym[1:].isdigit():
        return keysym  # keep original casing, e.g. "F5"

    # Known special keys
    if keysym in _KEYSYM_MAP:
        return _KEYSYM_MAP[keysym]

    # Single printable character
    if len(keysym) == 1:
        return keysym.lower()

    # Fall back to event.char if printable
    if event.char and len(event.char) == 1 and event.char.isprintable():
        return event.char.lower()

    # Last resort — lowercase keysym
    return keysym.lower()


# ===================================================================
# Widget factory helpers — reduce styling boilerplate for labels
# ===================================================================


def _themed_label(parent: tk.Misc, text: str, **overrides: Any) -> tk.Label:
    """Create a Label with the standard dark theme applied."""
    opts: Dict[str, Any] = dict(
        font=("Segoe UI", 10), fg=FG_TEXT, bg=BG_DARK, anchor="w"
    )
    opts.update(overrides)
    return tk.Label(parent, text=text, **opts)


def _themed_heading(parent: tk.Misc, text: str, **overrides: Any) -> tk.Label:
    """Create a heading Label (bold, gold)."""
    opts: Dict[str, Any] = dict(font=("Segoe UI", 12, "bold"), fg=GOLD, bg=BG_DARK)
    opts.update(overrides)
    return tk.Label(parent, text=text, **opts)


def _themed_hint(parent: tk.Misc, text: str, **overrides: Any) -> tk.Label:
    """Create a hint/description Label (small, dim)."""
    opts: Dict[str, Any] = dict(font=("Segoe UI", 9), fg=FG_DIM, bg=BG_DARK, anchor="w")
    opts.update(overrides)
    return tk.Label(parent, text=text, **opts)


# ===================================================================
# KeyCapturePopup — small modal that grabs the next key / mouse btn
# ===================================================================


class KeyCapturePopup:
    """Modal popup that waits for one keyboard key-press **or** a mouse
    button selection, then calls *on_captured(key_str)*.
    """

    def __init__(
        self,
        parent: tk.Toplevel,
        action_label: str,
        current_value: str,
        on_captured: Callable[[str], None],
        *,
        allow_mouse: bool = True,
    ) -> None:
        self.on_captured = on_captured
        self._done = False

        # --- window --------------------------------------------------------
        self.popup = tk.Toplevel(parent)
        self.popup.title(f"Rebind — {action_label}")
        self.popup.configure(bg=BG_DARK)
        self.popup.resizable(False, False)
        self.popup.attributes("-topmost", True)
        self.popup.overrideredirect(False)
        self.popup.transient(parent)
        self.popup.grab_set()
        self.popup.protocol("WM_DELETE_WINDOW", self._cancel)

        w, h = (340, 230) if allow_mouse else (340, 170)
        self.popup.geometry(f"{w}x{h}")

        # Centre on parent
        parent.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - w) // 2
        py = parent.winfo_y() + (parent.winfo_height() - h) // 2
        self.popup.geometry(f"+{max(px, 0)}+{max(py, 0)}")

        # --- widgets -------------------------------------------------------
        _themed_heading(
            self.popup,
            action_label,
            font=("Segoe UI", 13, "bold"),
        ).pack(pady=(16, 2), padx=16)

        _themed_label(
            self.popup,
            f"Current:  {format_key_display(current_value)}",
            fg=FG_DIM,
        ).pack(padx=16)

        self._status = _themed_label(
            self.popup,
            "Press any keyboard key …",
            font=("Segoe UI", 12),
        )
        self._status.pack(pady=(12, 4), padx=16)

        # Mouse-button helpers (only when relevant)
        if allow_mouse:
            _themed_hint(
                self.popup,
                "Or select a mouse button:",
            ).pack(padx=16)

            mf = tk.Frame(self.popup, bg=BG_DARK)
            mf.pack(pady=4)
            for label, value in [("LMB", "lmb"), ("RMB", "rmb"), ("MMB", "mmb")]:
                tk.Button(
                    mf,
                    text=label,
                    width=6,
                    font=("Segoe UI", 9, "bold"),
                    bg=BG_INPUT,
                    fg=FG_TEXT,
                    activebackground=ACCENT,
                    activeforeground="#FFF",
                    relief="flat",
                    bd=0,
                    cursor="hand2",
                    command=lambda v=value: self._finish(v),
                ).pack(side="left", padx=5)

        # Cancel
        tk.Button(
            self.popup,
            text="Cancel",
            width=10,
            font=("Segoe UI", 9),
            bg=BG_CARD,
            fg=FG_DIM,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
            cursor="hand2",
            command=self._cancel,
        ).pack(pady=(8, 12))

        # --- key binding ---------------------------------------------------
        self.popup.bind("<KeyPress>", self._on_key)
        self.popup.focus_force()

    # ----- internal --------------------------------------------------------

    def _on_key(self, event: tk.Event) -> None:
        key = _normalize_keysym(event)
        if key is None:
            self._cancel()
            return
        self._finish(key)

    def _finish(self, key: str) -> None:
        if self._done:
            return
        self._done = True
        self.on_captured(key)
        self.popup.destroy()

    def _cancel(self) -> None:
        if self._done:
            return
        self._done = True
        self.popup.destroy()


# ===================================================================
# SettingsWindow — main settings / key-remapping GUI
# ===================================================================


class SettingsWindow:
    """Tabbed settings window (singleton — only one may be open at a time)."""

    _instance: Optional["SettingsWindow"] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def open(
        cls,
        root: tk.Tk,
        loader: Any,
        on_save: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "SettingsWindow":
        """Open the settings window, or focus the existing one."""
        if cls._instance is not None:
            try:
                cls._instance.window.lift()
                cls._instance.window.focus_force()
                return cls._instance
            except tk.TclError:
                cls._instance = None

        inst = cls(root, loader, on_save)
        cls._instance = inst
        return inst

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        root: tk.Tk,
        loader: Any,
        on_save: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.root = root
        self.loader = loader
        self.on_save = on_save

        # Working copy of settings (edits happen here; saved on "Save")
        self._settings: Dict[str, Any] = _deep_copy(loader.get_settings())

        # Instance variables populated by _build_ui → _populate_* methods
        self._keybind_buttons: Dict[str, tk.Button] = {}
        self._display_vars: Dict[str, tk.BooleanVar] = {}
        self._hotkey_buttons: Dict[str, tk.Button] = {}
        self._timing_vars: Dict[str, tk.StringVar] = {}
        self._auto_advance_var: tk.BooleanVar = tk.BooleanVar(value=False)

        # ---- Toplevel window ----
        self.window = tk.Toplevel(root)
        self.window.title("BDO Trainer \u2014 Settings")
        self.window.configure(bg=BG_DARK)
        self.window.attributes("-topmost", True)
        self.window.resizable(True, True)
        self.window.minsize(520, 440)
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Build everything
        self._build_ui()

        # Centre on screen
        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        ww = max(self.window.winfo_width(), 560)
        wh = max(self.window.winfo_height(), 540)
        self.window.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ---- title bar ----
        title_frame = tk.Frame(self.window, bg=BG_DARK)
        title_frame.pack(fill="x", padx=12, pady=(10, 0))

        _themed_heading(
            title_frame, "\u2699  Settings", font=("Segoe UI", 16, "bold")
        ).pack(side="left")

        # ---- custom tab bar (we avoid ttk.Notebook for full colour control) ----
        self._tab_bar = tk.Frame(self.window, bg=BG_DARK)
        self._tab_bar.pack(fill="x", padx=12, pady=(10, 0))

        self._tab_container = tk.Frame(self.window, bg=BG_DARK)
        self._tab_container.pack(fill="both", expand=True, padx=12, pady=(0, 0))

        self._tabs: Dict[str, tk.Frame] = {}
        self._tab_buttons: Dict[str, tk.Button] = {}
        self._active_tab: Optional[str] = None

        tab_defs: List[Tuple[str, str, Callable[[tk.Frame], None]]] = [
            ("keybinds", "  Key Bindings  ", self._populate_keybinds),
            ("display", "  Display  ", self._populate_display),
            ("hotkeys", "  Hotkeys  ", self._populate_hotkeys),
            ("timing", "  Timing  ", self._populate_timing),
        ]

        for tab_id, label, populate_fn in tab_defs:
            btn = tk.Button(
                self._tab_bar,
                text=label,
                font=("Segoe UI", 10),
                bg=BG_CARD,
                fg=FG_TEXT,
                activebackground=ACCENT,
                activeforeground="#FFF",
                relief="flat",
                bd=0,
                padx=14,
                pady=6,
                cursor="hand2",
                command=lambda tid=tab_id: self._switch_tab(tid),
            )
            btn.pack(side="left", padx=(0, 2))
            self._tab_buttons[tab_id] = btn

            frame = tk.Frame(self._tab_container, bg=BG_DARK)
            populate_fn(frame)
            self._tabs[tab_id] = frame

        # ---- bottom button bar ----
        sep = tk.Frame(self.window, bg=ACCENT, height=1)
        sep.pack(fill="x", padx=12, pady=(6, 0))

        btn_bar = tk.Frame(self.window, bg=BG_DARK)
        btn_bar.pack(fill="x", padx=12, pady=10)

        self._make_btn(
            btn_bar, "Reset Defaults", self._on_reset, bg=BG_CARD, fg=RED_SOFT
        ).pack(side="left")
        self._make_btn(btn_bar, "Cancel", self._on_cancel, bg=BG_CARD).pack(
            side="right", padx=(6, 0)
        )
        self._make_btn(
            btn_bar, "\u2714  Save", self._on_save_click, bg=GREEN, fg="#FFF"
        ).pack(side="right")

        # Show first tab
        self._switch_tab("keybinds")

    # ---- tab switching -----------------------------------------------------

    def _switch_tab(self, tab_id: str) -> None:
        if self._active_tab == tab_id:
            return
        # hide previous
        if self._active_tab and self._active_tab in self._tabs:
            self._tabs[self._active_tab].pack_forget()
            self._tab_buttons[self._active_tab].configure(bg=BG_CARD, fg=FG_TEXT)
        # show new
        self._tabs[tab_id].pack(fill="both", expand=True, pady=(6, 0))
        self._tab_buttons[tab_id].configure(bg=ACCENT, fg="#FFF")
        self._active_tab = tab_id

    # ---- small widget helpers ---------------------------------------------

    def _make_btn(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable,
        bg: str = BG_INPUT,
        fg: str = FG_TEXT,
        width: int = 0,
    ) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 10),
            bg=bg,
            fg=fg,
            activebackground=ACCENT_HOVER,
            activeforeground="#FFF",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
        )
        if width:
            btn.configure(width=width)
        return btn

    @staticmethod
    def _make_section_header(
        parent: tk.Widget, text: str, row: int, colspan: int = 3
    ) -> int:
        _themed_label(
            parent,
            text,
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT,
        ).grid(row=row, column=0, columnspan=colspan, sticky="w", padx=8, pady=(12, 2))
        return row + 1

    # ==================================================================
    # TAB: Key Bindings
    # ==================================================================

    def _populate_keybinds(self, parent: tk.Frame) -> None:
        # Description
        _themed_hint(
            parent,
            (
                "Map BDO in-game actions to the physical keys you press.  "
                "Click a key button to rebind it."
            ),
            wraplength=500,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(6, 2))

        # Scrollable area
        outer = tk.Frame(parent, bg=BG_DARK)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_DARK)

        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_win = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Make the inner frame stretch to canvas width
        def _resize_inner(event: tk.Event) -> None:
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _resize_inner)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Mouse-wheel scrolling (Windows & macOS)
        def _on_mousewheel(event: tk.Event) -> str:
            delta = event.delta
            if abs(delta) > 10:
                delta = int(delta / 120)
            canvas.yview_scroll(-delta, "units")
            return "break"

        def _bind_wheel(widget: tk.Widget) -> None:
            widget.bind("<MouseWheel>", _on_mousewheel)  # Windows / macOS
            widget.bind("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
            widget.bind("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))

        _bind_wheel(canvas)
        _bind_wheel(inner)

        # Column headers
        inner.columnconfigure(0, weight=0, minsize=160)
        inner.columnconfigure(1, weight=0, minsize=120)
        inner.columnconfigure(2, weight=1)

        hdr_row = 0
        _themed_heading(
            inner,
            "BDO Action",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).grid(row=hdr_row, column=0, sticky="w", padx=(12, 8), pady=(4, 2))
        _themed_heading(
            inner,
            "Bound Key",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).grid(row=hdr_row, column=1, sticky="w", padx=8, pady=(4, 2))

        sep = tk.Frame(inner, bg=ACCENT, height=1)
        sep.grid(row=hdr_row + 1, column=0, columnspan=3, sticky="ew", padx=10, pady=2)

        # Populate rows
        self._keybind_buttons: Dict[str, tk.Button] = {}
        current_bindings: Dict[str, str] = self._settings.get("key_bindings", {})

        cur_section: Optional[str] = None
        row = hdr_row + 2

        for bdo_name, section, default in BDO_KEY_BINDINGS:
            # Section divider
            if section != cur_section:
                cur_section = section
                row = self._make_section_header(inner, f"\u2500  {section}", row)

            # Action label
            _themed_label(inner, bdo_name).grid(
                row=row, column=0, sticky="w", padx=(24, 8), pady=3
            )

            # Key button
            current_val = current_bindings.get(bdo_name, default)
            btn = tk.Button(
                inner,
                text=format_key_display(current_val),
                font=("Segoe UI", 10, "bold"),
                width=10,
                bg=BG_INPUT,
                fg=FG_TEXT,
                activebackground=ACCENT,
                activeforeground="#FFF",
                relief="flat",
                bd=0,
                cursor="hand2",
                command=lambda n=bdo_name: self._capture_keybind(n),
            )
            btn.grid(row=row, column=1, sticky="w", padx=8, pady=3)
            _bind_wheel(btn)
            self._keybind_buttons[bdo_name] = btn

            row += 1

        # pad at bottom so scrolling feels natural
        tk.Frame(inner, bg=BG_DARK, height=12).grid(row=row, column=0, columnspan=3)

    def _capture_keybind(self, bdo_name: str) -> None:
        bindings = self._settings.setdefault("key_bindings", {})
        current_val = bindings.get(bdo_name, "")

        def _on_captured(key: str) -> None:
            bindings[bdo_name] = key
            self._keybind_buttons[bdo_name].configure(text=format_key_display(key))

        KeyCapturePopup(
            self.window,
            bdo_name,
            current_val,
            _on_captured,
            allow_mouse=True,
        )

    # ==================================================================
    # TAB: Display
    # ==================================================================

    def _populate_display(self, parent: tk.Frame) -> None:
        display: Dict[str, Any] = self._settings.setdefault("display", {})

        _themed_heading(parent, "Display Options").pack(
            anchor="w", padx=12, pady=(12, 2)
        )

        _themed_hint(
            parent, "Control what information the overlay shows during combos."
        ).pack(anchor="w", padx=12, pady=(0, 10))

        self._display_vars: Dict[str, tk.BooleanVar] = {}

        options: List[Tuple[str, str, str]] = [
            (
                "show_protection_type",
                "Show protection type",
                "Display SA / FG / iframe badges on each skill step.",
            ),
            (
                "show_cc_type",
                "Show crowd-control type",
                "Display CC labels (bound, knockdown, float, …).",
            ),
            (
                "show_key_overlay",
                "Show key input overlay",
                "Display the key combination you need to press.",
            ),
            (
                "highlight_protected_skills",
                "Highlight protected skills",
                "Colour-code skills that have Super Armor or Forward Guard.",
            ),
            (
                "highlight_iframes",
                "Highlight iframe skills",
                "Colour-code skills with invincibility frames.",
            ),
        ]

        for key, label, description in options:
            var = tk.BooleanVar(value=display.get(key, True))
            self._display_vars[key] = var

            row_frame = tk.Frame(parent, bg=BG_DARK)
            row_frame.pack(anchor="w", fill="x", padx=16, pady=2)

            cb = tk.Checkbutton(
                row_frame,
                text=label,
                variable=var,
                font=("Segoe UI", 10),
                fg=FG_TEXT,
                bg=BG_DARK,
                selectcolor=BG_INPUT,
                activebackground=BG_DARK,
                activeforeground=FG_TEXT,
                highlightthickness=0,
                anchor="w",
                cursor="hand2",
            )
            cb.pack(anchor="w")

            _themed_hint(row_frame, description, font=("Segoe UI", 8)).pack(
                anchor="w", padx=(24, 0)
            )

    # ==================================================================
    # TAB: Hotkeys
    # ==================================================================

    def _populate_hotkeys(self, parent: tk.Frame) -> None:
        hotkeys: Dict[str, str] = self._settings.setdefault(
            "hotkeys",
            _deep_copy(_DEFAULT_SETTINGS["hotkeys"]),
        )

        _themed_heading(parent, "Global Hotkeys").pack(
            anchor="w", padx=12, pady=(12, 2)
        )

        _themed_hint(
            parent,
            "These hotkeys work while the game is focused.  Click a button to rebind.",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        grid = tk.Frame(parent, bg=BG_DARK)
        grid.pack(anchor="w", padx=20, pady=4)

        self._hotkey_buttons: Dict[str, tk.Button] = {}

        hotkey_defs: List[Tuple[str, str, str, str]] = [
            (
                "start_combo",
                "Start / Restart Combo",
                "F5",
                "Begin the selected combo or restart it",
            ),
            ("stop_combo", "Stop Combo", "F6", "Stop the current combo"),
            (
                "next_step",
                "Next Step (Manual)",
                "F7",
                "Manually advance to the next step",
            ),
            ("reset_combo", "Reset Combo", "F8", "Reset combo back to step 1"),
        ]

        for i, (key, label, default, hint) in enumerate(hotkey_defs):
            # Label
            lbl_frame = tk.Frame(grid, bg=BG_DARK)
            lbl_frame.grid(row=i, column=0, sticky="w", pady=6, padx=(0, 16))

            _themed_label(lbl_frame, label).pack(anchor="w")
            _themed_hint(lbl_frame, hint, font=("Segoe UI", 8)).pack(anchor="w")

            # Button
            current = hotkeys.get(key, default)
            btn = tk.Button(
                grid,
                text=format_key_display(current),
                font=("Segoe UI", 10, "bold"),
                width=10,
                bg=BG_INPUT,
                fg=FG_TEXT,
                activebackground=ACCENT,
                activeforeground="#FFF",
                relief="flat",
                bd=0,
                cursor="hand2",
                command=lambda k=key: self._capture_hotkey(k),
            )
            btn.grid(row=i, column=1, sticky="w", padx=8, pady=6)
            self._hotkey_buttons[key] = btn

    def _capture_hotkey(self, hotkey_name: str) -> None:
        hotkeys = self._settings.setdefault("hotkeys", {})
        current = hotkeys.get(hotkey_name, "")

        display_names = {
            "start_combo": "Start / Restart Combo",
            "stop_combo": "Stop Combo",
            "next_step": "Next Step",
            "reset_combo": "Reset Combo",
        }

        def _on_captured(key: str) -> None:
            # Function keys stay uppercase; others lowercase
            if key.startswith("F") and key[1:].isdigit():
                key = key.upper() if len(key) > 1 else key
            hotkeys[hotkey_name] = key
            self._hotkey_buttons[hotkey_name].configure(text=format_key_display(key))

        KeyCapturePopup(
            self.window,
            display_names.get(hotkey_name, hotkey_name),
            current,
            _on_captured,
            allow_mouse=False,
        )

    # ==================================================================
    # TAB: Timing
    # ==================================================================

    def _populate_timing(self, parent: tk.Frame) -> None:
        timing: Dict[str, Any] = self._settings.setdefault(
            "timing",
            _deep_copy(_DEFAULT_SETTINGS["timing"]),
        )

        _themed_heading(parent, "Timing Settings").pack(
            anchor="w", padx=12, pady=(12, 2)
        )

        _themed_hint(parent, "All durations are in milliseconds.").pack(
            anchor="w", padx=12, pady=(0, 10)
        )

        grid = tk.Frame(parent, bg=BG_DARK)
        grid.pack(anchor="w", padx=20, pady=4)

        self._timing_vars: Dict[str, tk.StringVar] = {}

        # Note: default_combo_window_ms lives at the *settings* root level,
        # not under the timing sub-dict.
        timing_fields: List[Tuple[str, str, str, Any, bool]] = [
            # (key, label, hint, value, is_root_key)
            (
                "default_combo_window_ms",
                "Combo Window  (ms)",
                "Delay after a successful key-press before showing the next step.",
                self._settings.get("default_combo_window_ms", 250),
                True,
            ),
            (
                "step_highlight_duration_ms",
                "Success Flash  (ms)",
                "How long the green \u2714 flash is shown.",
                timing.get("step_highlight_duration_ms", 500),
                False,
            ),
            (
                "transition_delay_ms",
                "Transition Delay  (ms)",
                "Short pause between steps.",
                timing.get("transition_delay_ms", 100),
                False,
            ),
            (
                "idle_reset_timeout_ms",
                "Idle Reset Timeout  (ms)",
                "Reset combo to step 1 after this many ms of no input.  0 = disabled.",
                timing.get("idle_reset_timeout_ms", 10000),
                False,
            ),
        ]

        for i, (key, label, hint, default_val, _is_root) in enumerate(timing_fields):
            # Label + hint
            lbl_frame = tk.Frame(grid, bg=BG_DARK)
            lbl_frame.grid(row=i, column=0, sticky="w", pady=6, padx=(0, 16))

            _themed_label(lbl_frame, label).pack(anchor="w")
            _themed_hint(
                lbl_frame, hint, font=("Segoe UI", 8), wraplength=300, justify="left"
            ).pack(anchor="w")

            # Entry
            var = tk.StringVar(value=str(default_val))
            self._timing_vars[key] = var

            entry = tk.Entry(
                grid,
                textvariable=var,
                width=10,
                font=("Segoe UI", 10),
                bg=BG_INPUT,
                fg=FG_TEXT,
                insertbackground=FG_TEXT,
                relief="flat",
                bd=4,
                justify="center",
            )
            entry.grid(row=i, column=1, sticky="w", padx=8, pady=6)

            # Validate: only allow digits
            vcmd = (entry.register(self._validate_int), "%P")
            entry.configure(validate="key", validatecommand=vcmd)

        # Auto-advance checkbox
        self._auto_advance_var = tk.BooleanVar(value=timing.get("auto_advance", False))

        aa_frame = tk.Frame(parent, bg=BG_DARK)
        aa_frame.pack(anchor="w", padx=20, pady=(12, 0))

        tk.Checkbutton(
            aa_frame,
            text="Auto-advance steps (timer-based — ignores input detection)",
            variable=self._auto_advance_var,
            font=("Segoe UI", 10),
            fg=FG_TEXT,
            bg=BG_DARK,
            selectcolor=BG_INPUT,
            activebackground=BG_DARK,
            activeforeground=FG_TEXT,
            highlightthickness=0,
            cursor="hand2",
        ).pack(anchor="w")

        _themed_hint(
            aa_frame,
            "When enabled, steps advance on a timer instead of waiting for key input.",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=(24, 0))

    @staticmethod
    def _validate_int(value: str) -> bool:
        """Tk validation callback — allow empty string or digits only."""
        return value == "" or value.isdigit()

    # ==================================================================
    # Save / Cancel / Reset
    # ==================================================================

    def _collect_all(self) -> Dict[str, Any]:
        """Gather current UI state into the working ``_settings`` dict."""
        # Display
        display = self._settings.setdefault("display", {})
        for key, var in self._display_vars.items():
            display[key] = var.get()

        # Timing
        timing = self._settings.setdefault("timing", {})
        for key, var in self._timing_vars.items():
            try:
                val = int(var.get())
            except (ValueError, TypeError):
                val = 0
            if key == "default_combo_window_ms":
                self._settings["default_combo_window_ms"] = val
            else:
                timing[key] = val
        timing["auto_advance"] = self._auto_advance_var.get()

        # key_bindings and hotkeys are updated in-place by capture callbacks
        return self._settings

    def _on_save_click(self) -> None:
        settings = self._collect_all()
        self._save_to_yaml(settings)

        if self.on_save:
            self.on_save(_deep_copy(settings))

        logger.info("Settings saved via GUI")
        self._close()

    def _on_cancel(self) -> None:
        self._close()

    def _on_reset(self) -> None:
        """Reset everything in the UI back to factory defaults."""
        defaults = _deep_copy(_DEFAULT_SETTINGS)
        self._settings = defaults

        # Update keybind buttons
        bindings = defaults.get("key_bindings", {})
        for bdo_name, btn in self._keybind_buttons.items():
            val = bindings.get(bdo_name, "")
            btn.configure(text=format_key_display(val))

        # Update hotkey buttons
        hotkeys = defaults.get("hotkeys", {})
        for key, btn in self._hotkey_buttons.items():
            val = hotkeys.get(key, "")
            btn.configure(text=format_key_display(val))

        # Update display checkboxes
        display = defaults.get("display", {})
        for key, var in self._display_vars.items():
            var.set(display.get(key, True))

        # Update timing entries
        timing = defaults.get("timing", {})
        for key, var in self._timing_vars.items():
            if key == "default_combo_window_ms":
                var.set(str(defaults.get("default_combo_window_ms", 250)))
            else:
                var.set(str(timing.get(key, 0)))
        self._auto_advance_var.set(timing.get("auto_advance", False))

        logger.info("Settings reset to defaults (not yet saved)")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_to_yaml(self, settings: Dict[str, Any]) -> None:
        """Write the settings dict back to ``combos.yaml``."""
        yaml_path = self.loader.settings_path

        try:
            with open(yaml_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except (FileNotFoundError, yaml.YAMLError):
            data = {}

        data["settings"] = settings

        header = (
            "# ============================================================================\n"
            "# BDO Trainer - Global Settings\n"
            "# ============================================================================\n"
            "# Class-specific data (skills, combos, etc.) is loaded from YAML files in\n"
            "# the config/classes/ directory.  Each file must have top-level `class:` and\n"
            "# `spec:` keys.\n"
            "#\n"
            "# Key Reference (for combo step `keys:` arrays):\n"
            "#   lmb  = Left Mouse Button\n"
            "#   rmb  = Right Mouse Button\n"
            "#   mmb  = Middle Mouse Button\n"
            "#   w/a/s/d = Movement keys\n"
            "#   shift, space, e, f, q, x, z = Ability modifiers\n"
            "# ============================================================================\n\n"
        )

        with open(yaml_path, "w", encoding="utf-8") as fh:
            fh.write(header)
            yaml.dump(
                data,
                fh,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        logger.info(f"Settings written to {yaml_path}")

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def _close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        SettingsWindow._instance = None
