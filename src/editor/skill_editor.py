"""
Skill Editor — skill list + edit form panel for the BDO Trainer class/combo editor.

Provides a split-view interface: skill list on the left, full edit form on the right.
"""

import logging
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("bdo_trainer")

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
BG_DARK = "#1A1A2E"
BG_CARD = "#16213E"
BG_INPUT = "#0F3460"
FG_TEXT = "#E8E8E8"
FG_DIM = "#888888"
ACCENT = "#E94560"
ACCENT_HOVER = "#FF6B81"
GOLD = "#FFD700"
GREEN = "#4CAF50"
RED_SOFT = "#CF6679"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_HEADING = ("Segoe UI", 12, "bold")
FONT_SMALL = ("Segoe UI", 9)

# ---------------------------------------------------------------------------
# Key definitions
# ---------------------------------------------------------------------------
ALL_KEYS: List[str] = [
    "w",
    "a",
    "s",
    "d",
    "shift",
    "space",
    "lmb",
    "rmb",
    "mmb",
    "q",
    "e",
    "f",
    "x",
    "z",
    "hotbar",
    "hold",
    "down",
]

KEY_DISPLAY: Dict[str, str] = {
    "w": "W",
    "a": "A",
    "s": "S",
    "d": "D",
    "shift": "Shift",
    "space": "Space",
    "lmb": "LMB",
    "rmb": "RMB",
    "mmb": "MMB",
    "q": "Q",
    "e": "E",
    "f": "F",
    "x": "X",
    "z": "Z",
    "hotbar": "Hotbar",
    "hold": "Hold",
    "down": "\u2193Down",
}

# Grid layout for key toggle buttons: list of rows, each row is a list of keys
KEY_GRID = [
    ["w", "a", "s", "d"],
    ["shift", "space"],
    ["lmb", "rmb", "mmb"],
    ["q", "e", "f", "x", "z"],
    ["hotbar", "hold", "down"],
]

CC_TYPES: List[str] = [
    "stiffness",
    "knockdown",
    "knockback",
    "floating",
    "bound",
    "stun",
    "float",
    "pull",
    "grab",
    "down_attack",
    "spin",
]

CC_DISPLAY: Dict[str, str] = {
    "stiffness": "Stiffness",
    "knockdown": "Knockdown",
    "knockback": "Knockback",
    "floating": "Floating",
    "bound": "Bound",
    "stun": "Stun",
    "float": "Float",
    "pull": "Pull",
    "grab": "Grab",
    "down_attack": "Down Atk",
    "spin": "Spin",
}

PROTECTION_VALUES = ["SA", "FG", "iframe", "none"]
DAMAGE_VALUES = ["none", "low", "medium", "high", "very_high"]


class SkillEditor(tk.Frame):
    """Skill list + edit form panel."""

    def __init__(self, parent: tk.Widget, on_change: Optional[Callable] = None):
        super().__init__(parent, bg=BG_DARK)
        # Expose self as .frame so the host window can do  editor.frame
        self.frame = self
        self._on_change = on_change
        self._skills: Dict[str, dict] = {}  # skill_id -> skill_data
        self._current_skill_id: Optional[str] = None
        self._class_name = ""
        self._spec_name = ""

        # Widget references populated by _build_ui
        self._listbox: Optional[tk.Listbox] = None
        self._header_label: Optional[tk.Label] = None

        # Form widgets
        self._id_label: Optional[tk.Label] = None
        self._id_entry: Optional[tk.Entry] = None
        self._id_is_new = False
        self._name_entry: Optional[tk.Entry] = None
        self._input_entry: Optional[tk.Entry] = None
        self._key_vars: Dict[str, tk.BooleanVar] = {}
        self._key_buttons: Dict[str, tk.Button] = {}
        self._alt_key_vars: Dict[str, tk.BooleanVar] = {}
        self._alt_key_buttons: Dict[str, tk.Button] = {}
        self._alt_keys_frame: Optional[tk.Frame] = None
        self._alt_keys_visible = False
        self._alt_keys_toggle_label: Optional[tk.Label] = None
        self._protection_var: Optional[tk.StringVar] = None
        self._damage_var: Optional[tk.StringVar] = None
        self._cooldown_entry: Optional[tk.Entry] = None
        self._level_entry: Optional[tk.Entry] = None
        self._cc_vars: Dict[str, tk.BooleanVar] = {}
        self._desc_text: Optional[tk.Text] = None
        self._notes_text: Optional[tk.Text] = None
        self._flows_entry: Optional[tk.Entry] = None
        self._core_entry: Optional[tk.Entry] = None
        self._form_frame: Optional[tk.Frame] = None
        self._placeholder_label: Optional[tk.Label] = None
        self._save_btn: Optional[tk.Button] = None
        self._delete_btn: Optional[tk.Button] = None

        # Track new-skill counter for unique IDs
        self._new_skill_counter = 0

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, skills: Dict[str, dict], class_name: str, spec_name: str) -> None:
        """Load skills from a class config."""
        self._skills = skills  # already a deep copy from window.py
        self._class_name = class_name
        self._spec_name = spec_name
        self._current_skill_id = None
        self._new_skill_counter = 0
        self._refresh_list()
        self._clear_form()
        self._update_header()

    def get_skills(self) -> Dict[str, dict]:
        """Return the current skills dict with all edits applied."""
        self._save_current_to_memory()
        return self._skills

    def clear(self) -> None:
        """Reset when no class is selected."""
        self._skills = {}
        self._current_skill_id = None
        self._class_name = ""
        self._spec_name = ""
        self._new_skill_counter = 0
        self._refresh_list()
        self._clear_form()
        self._update_header()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the horizontal split: skill list (left) + edit form (right)."""
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ---- Left panel: skill list ----
        left_panel = tk.Frame(self, bg=BG_DARK, width=220)
        left_panel.grid(row=0, column=0, sticky="ns", padx=(0, 2))
        left_panel.grid_propagate(False)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)

        # Header row
        header_row = tk.Frame(left_panel, bg=BG_DARK)
        header_row.grid(row=0, column=0, sticky="ew", padx=4, pady=(6, 2))
        header_row.columnconfigure(0, weight=1)

        self._header_label = tk.Label(
            header_row,
            text="Skills",
            font=FONT_HEADING,
            bg=BG_DARK,
            fg=GOLD,
            anchor="w",
        )
        self._header_label.grid(row=0, column=0, sticky="w")

        add_btn = tk.Button(
            header_row,
            text="+ Add",
            font=FONT_SMALL,
            bg=GREEN,
            fg="white",
            activebackground="#66BB6A",
            activeforeground="white",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._on_add_skill,
        )
        add_btn.grid(row=0, column=1, sticky="e", padx=(4, 0))

        # Listbox
        list_frame = tk.Frame(left_panel, bg=BG_DARK)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(2, 4))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            list_frame,
            bg=BG_INPUT,
            fg=FG_TEXT,
            selectbackground=ACCENT,
            selectforeground="white",
            font=FONT,
            exportselection=False,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
            activestyle="none",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")

        list_sb = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self._listbox.yview,
        )
        list_sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=list_sb.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_skill_selected)

        # Mouse wheel for listbox
        self._listbox.bind(
            "<MouseWheel>",
            lambda e: self._listbox.yview_scroll(
                -int(e.delta / 120) if abs(e.delta) > 10 else -e.delta,
                "units",
            ),
        )

        # Separator
        sep = tk.Frame(self, bg=BG_CARD, width=2)
        sep.grid(row=0, column=0, sticky="nse", padx=(218, 0))

        # ---- Right panel: edit form ----
        right_panel = tk.Frame(self, bg=BG_DARK)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        # Scrollable canvas
        self._canvas = tk.Canvas(right_panel, bg=BG_DARK, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(
            right_panel, orient="vertical", command=self._canvas.yview
        )
        self._form_frame = tk.Frame(self._canvas, bg=BG_DARK)

        self._form_frame.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas_win = self._canvas.create_window(
            (0, 0),
            window=self._form_frame,
            anchor="nw",
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._canvas_win, width=e.width),
        )
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Mouse wheel scrolling on canvas
        self._bind_mousewheel(self._canvas)
        self._bind_mousewheel(self._form_frame)

        # Placeholder for when no skill is selected
        self._placeholder_label = tk.Label(
            self._form_frame,
            text="Select a skill from the list or click '+ Add' to create one.",
            font=FONT,
            bg=BG_DARK,
            fg=FG_DIM,
            wraplength=400,
            justify="center",
        )
        self._placeholder_label.grid(row=0, column=0, columnspan=4, pady=60, padx=40)

        # Build the actual form widgets (initially hidden)
        self._build_form()

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        """Bind mouse wheel scrolling to the canvas."""

        def _on_mousewheel(event: tk.Event) -> str:
            delta = event.delta
            if abs(delta) > 10:
                delta = int(delta / 120)
            self._canvas.yview_scroll(-delta, "units")
            return "break"

        widget.bind("<MouseWheel>", _on_mousewheel)
        widget.bind("<Button-4>", lambda e: self._canvas.yview_scroll(-3, "units"))
        widget.bind("<Button-5>", lambda e: self._canvas.yview_scroll(3, "units"))

    def _build_form(self) -> None:
        """Build all form fields inside self._form_frame using grid layout."""
        f = self._form_frame
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)

        row = 1  # Row 0 is reserved for the placeholder

        # --- Skill ID ---
        tk.Label(
            f,
            text="Skill ID:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_DIM,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(12, 6), pady=(12, 4))

        id_frame = tk.Frame(f, bg=BG_DARK)
        id_frame.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=(12, 4)
        )

        self._id_label = tk.Label(
            id_frame,
            text="",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=ACCENT,
            anchor="w",
        )
        self._id_label.pack(side="left", fill="x", expand=True)

        self._id_entry = tk.Entry(
            id_frame,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
        )
        # id_entry is only shown for new skills
        row += 1

        # --- Name ---
        tk.Label(
            f,
            text="Name:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(12, 6), pady=4)

        self._name_entry = tk.Entry(
            f,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
        )
        self._name_entry.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4
        )
        row += 1

        # --- Input ---
        tk.Label(
            f,
            text="Input:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(12, 6), pady=4)

        self._input_entry = tk.Entry(
            f,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
        )
        self._input_entry.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4
        )
        row += 1

        # --- Keys ---
        tk.Label(
            f,
            text="Keys:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="nw",
        ).grid(row=row, column=0, sticky="nw", padx=(12, 6), pady=4)

        keys_frame = tk.Frame(f, bg=BG_DARK)
        keys_frame.grid(
            row=row, column=1, columnspan=3, sticky="w", padx=(0, 12), pady=4
        )
        self._build_key_grid(keys_frame, is_alt=False)
        row += 1

        # --- Alt Keys ---
        tk.Label(
            f,
            text="Alt Keys:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="nw",
        ).grid(row=row, column=0, sticky="nw", padx=(12, 6), pady=4)

        alt_outer = tk.Frame(f, bg=BG_DARK)
        alt_outer.grid(
            row=row, column=1, columnspan=3, sticky="w", padx=(0, 12), pady=4
        )

        self._alt_keys_toggle_label = tk.Label(
            alt_outer,
            text="\u25b6 Show Alt Keys",
            font=FONT_SMALL,
            bg=BG_DARK,
            fg=ACCENT,
            cursor="hand2",
        )
        self._alt_keys_toggle_label.pack(anchor="w")
        self._alt_keys_toggle_label.bind("<Button-1>", self._toggle_alt_keys_visibility)

        self._alt_keys_frame = tk.Frame(alt_outer, bg=BG_DARK)
        # Initially hidden
        self._build_key_grid(self._alt_keys_frame, is_alt=True)
        row += 1

        # --- Protection + Damage (same row) ---
        prot_damage_frame = tk.Frame(f, bg=BG_DARK)
        prot_damage_frame.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=(12, 12), pady=4
        )

        tk.Label(
            prot_damage_frame,
            text="Protection:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
        ).pack(side="left")

        self._protection_var = tk.StringVar(value="none")
        prot_menu = tk.OptionMenu(
            prot_damage_frame, self._protection_var, *PROTECTION_VALUES
        )
        prot_menu.configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            activebackground=ACCENT,
            activeforeground="white",
            highlightthickness=0,
            bd=0,
            width=8,
        )
        prot_menu["menu"].configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            activebackground=ACCENT,
            activeforeground="white",
        )
        prot_menu.pack(side="left", padx=(4, 20))

        tk.Label(
            prot_damage_frame,
            text="Damage:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
        ).pack(side="left")

        self._damage_var = tk.StringVar(value="none")
        dmg_menu = tk.OptionMenu(prot_damage_frame, self._damage_var, *DAMAGE_VALUES)
        dmg_menu.configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            activebackground=ACCENT,
            activeforeground="white",
            highlightthickness=0,
            bd=0,
            width=10,
        )
        dmg_menu["menu"].configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            activebackground=ACCENT,
            activeforeground="white",
        )
        dmg_menu.pack(side="left", padx=(4, 0))
        row += 1

        # --- Cooldown + Level (same row) ---
        cd_level_frame = tk.Frame(f, bg=BG_DARK)
        cd_level_frame.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=(12, 12), pady=4
        )

        tk.Label(
            cd_level_frame,
            text="Cooldown:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
        ).pack(side="left")

        self._cooldown_entry = tk.Entry(
            cd_level_frame,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
            width=8,
        )
        self._cooldown_entry.pack(side="left", padx=(4, 2))

        tk.Label(
            cd_level_frame,
            text="ms",
            font=FONT,
            bg=BG_DARK,
            fg=FG_DIM,
        ).pack(side="left", padx=(0, 20))

        tk.Label(
            cd_level_frame,
            text="Level:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
        ).pack(side="left")

        self._level_entry = tk.Entry(
            cd_level_frame,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
            width=6,
        )
        self._level_entry.pack(side="left", padx=(4, 0))
        row += 1

        # --- CC Types ---
        tk.Label(
            f,
            text="CC:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="nw",
        ).grid(row=row, column=0, sticky="nw", padx=(12, 6), pady=4)

        cc_frame = tk.Frame(f, bg=BG_DARK)
        cc_frame.grid(row=row, column=1, columnspan=3, sticky="w", padx=(0, 12), pady=4)

        cc_grid = [
            ["stiffness", "knockdown", "knockback", "floating"],
            ["bound", "stun", "float", "pull"],
            ["grab", "down_attack", "spin"],
        ]
        for r_idx, cc_row in enumerate(cc_grid):
            for c_idx, cc_type in enumerate(cc_row):
                var = tk.BooleanVar(value=False)
                self._cc_vars[cc_type] = var
                cb = tk.Checkbutton(
                    cc_frame,
                    text=CC_DISPLAY.get(cc_type, cc_type),
                    variable=var,
                    font=FONT_SMALL,
                    bg=BG_DARK,
                    fg=FG_TEXT,
                    selectcolor=BG_INPUT,
                    activebackground=BG_DARK,
                    activeforeground=FG_TEXT,
                    highlightthickness=0,
                    bd=0,
                )
                cb.grid(row=r_idx, column=c_idx, sticky="w", padx=(0, 10), pady=1)
                self._bind_mousewheel(cb)
        row += 1

        # --- Description ---
        tk.Label(
            f,
            text="Description:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="nw",
        ).grid(row=row, column=0, sticky="nw", padx=(12, 6), pady=4)

        self._desc_text = tk.Text(
            f,
            height=3,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
            wrap="word",
        )
        self._desc_text.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4
        )
        self._bind_mousewheel(self._desc_text)
        row += 1

        # --- Notes ---
        tk.Label(
            f,
            text="Notes:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="nw",
        ).grid(row=row, column=0, sticky="nw", padx=(12, 6), pady=4)

        self._notes_text = tk.Text(
            f,
            height=2,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
            wrap="word",
        )
        self._notes_text.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4
        )
        self._bind_mousewheel(self._notes_text)
        row += 1

        # --- Flows Into ---
        tk.Label(
            f,
            text="Flows Into:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(12, 6), pady=4)

        self._flows_entry = tk.Entry(
            f,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
        )
        self._flows_entry.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4
        )
        row += 1

        # --- Core Effect ---
        tk.Label(
            f,
            text="Core Effect:",
            font=FONT_BOLD,
            bg=BG_DARK,
            fg=FG_TEXT,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(12, 6), pady=4)

        self._core_entry = tk.Entry(
            f,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
        )
        self._core_entry.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=4
        )
        row += 1

        # --- Buttons ---
        btn_frame = tk.Frame(f, bg=BG_DARK)
        btn_frame.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=12, pady=(16, 20)
        )

        self._save_btn = tk.Button(
            btn_frame,
            text="Save Skill",
            font=FONT_BOLD,
            bg=GREEN,
            fg="white",
            activebackground="#66BB6A",
            activeforeground="white",
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            command=self._on_save_skill,
        )
        self._save_btn.pack(side="left", padx=(0, 10))

        self._delete_btn = tk.Button(
            btn_frame,
            text="Delete Skill",
            font=FONT_BOLD,
            bg=BG_INPUT,
            fg=RED_SOFT,
            activebackground="#1A1A3E",
            activeforeground=RED_SOFT,
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            command=self._on_delete_skill,
        )
        self._delete_btn.pack(side="left")

        # Store the row references for showing/hiding form vs placeholder
        self._form_widgets: List[tk.Widget] = []
        for child in f.grid_slaves():
            if child is not self._placeholder_label:
                self._form_widgets.append(child)

        # Initially hide form, show placeholder
        self._set_form_visible(False)

    def _build_key_grid(self, parent: tk.Frame, is_alt: bool) -> None:
        """Build a toggle-button grid for key selection."""
        vars_dict = self._alt_key_vars if is_alt else self._key_vars
        btns_dict = self._alt_key_buttons if is_alt else self._key_buttons

        for r_idx, key_row in enumerate(KEY_GRID):
            for c_idx, key in enumerate(key_row):
                var = tk.BooleanVar(value=False)
                vars_dict[key] = var

                btn = tk.Button(
                    parent,
                    text=KEY_DISPLAY.get(key, key),
                    font=FONT_SMALL,
                    bg=BG_INPUT,
                    fg=FG_DIM,
                    activebackground=ACCENT_HOVER,
                    activeforeground="white",
                    bd=0,
                    width=6,
                    height=1,
                    cursor="hand2",
                    command=lambda k=key, a=is_alt: self._toggle_key(k, a),
                )
                btn.grid(row=r_idx, column=c_idx, padx=2, pady=2, sticky="w")
                btns_dict[key] = btn
                self._bind_mousewheel(btn)

    # ------------------------------------------------------------------
    # Key toggle
    # ------------------------------------------------------------------

    def _toggle_key(self, key: str, is_alt: bool = False) -> None:
        """Toggle a key button on/off."""
        vars_dict = self._alt_key_vars if is_alt else self._key_vars
        btns_dict = self._alt_key_buttons if is_alt else self._key_buttons
        var = vars_dict[key]
        var.set(not var.get())
        btn = btns_dict[key]
        if var.get():
            btn.configure(bg=ACCENT, fg="white")
        else:
            btn.configure(bg=BG_INPUT, fg=FG_DIM)

    def _set_key_state(self, key: str, active: bool, is_alt: bool = False) -> None:
        """Set a specific key toggle to active or inactive."""
        vars_dict = self._alt_key_vars if is_alt else self._key_vars
        btns_dict = self._alt_key_buttons if is_alt else self._key_buttons
        if key not in vars_dict:
            return
        vars_dict[key].set(active)
        btn = btns_dict[key]
        if active:
            btn.configure(bg=ACCENT, fg="white")
        else:
            btn.configure(bg=BG_INPUT, fg=FG_DIM)

    def _reset_all_keys(self, is_alt: bool = False) -> None:
        """Reset all key toggles to off."""
        vars_dict = self._alt_key_vars if is_alt else self._key_vars
        for key in vars_dict:
            self._set_key_state(key, False, is_alt)

    # ------------------------------------------------------------------
    # Alt keys visibility
    # ------------------------------------------------------------------

    def _toggle_alt_keys_visibility(self, _event: Any = None) -> None:
        """Toggle the alt keys grid visibility."""
        self._alt_keys_visible = not self._alt_keys_visible
        if self._alt_keys_visible:
            self._alt_keys_frame.pack(anchor="w", pady=(4, 0))
            self._alt_keys_toggle_label.configure(text="\u25bc Hide Alt Keys")
        else:
            self._alt_keys_frame.pack_forget()
            self._alt_keys_toggle_label.configure(text="\u25b6 Show Alt Keys")

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _update_header(self) -> None:
        """Update the header label with class/spec info."""
        if self._class_name and self._spec_name:
            text = f"Skills \u2014 {self._class_name} ({self._spec_name})"
        else:
            text = "Skills"
        if self._header_label:
            self._header_label.configure(text=text)

    # ------------------------------------------------------------------
    # Form show / hide
    # ------------------------------------------------------------------

    def _set_form_visible(self, visible: bool) -> None:
        """Show or hide form widgets vs placeholder."""
        if visible:
            self._placeholder_label.grid_remove()
            for w in self._form_widgets:
                w.grid()
        else:
            for w in self._form_widgets:
                w.grid_remove()
            self._placeholder_label.grid()

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        """Clear and repopulate the listbox from self._skills."""
        if not self._listbox:
            return
        self._listbox.delete(0, tk.END)
        for skill_id in sorted(self._skills.keys()):
            skill_data = self._skills[skill_id]
            name = skill_data.get("name", "")
            if name:
                display = f"{skill_id} \u2014 {name}"
            else:
                display = skill_id
            self._listbox.insert(tk.END, display)

        # Re-select current skill if still present
        if self._current_skill_id and self._current_skill_id in self._skills:
            sorted_ids = sorted(self._skills.keys())
            try:
                idx = sorted_ids.index(self._current_skill_id)
                self._listbox.selection_set(idx)
                self._listbox.see(idx)
            except ValueError:
                pass

    def _on_skill_selected(self, event: tk.Event) -> None:
        """Handle listbox selection change."""
        if not self._listbox:
            return
        selection = self._listbox.curselection()
        if not selection:
            return

        # Save current form state before switching
        self._save_current_to_memory()

        # Get the new skill ID
        idx = selection[0]
        sorted_ids = sorted(self._skills.keys())
        if idx >= len(sorted_ids):
            return

        skill_id = sorted_ids[idx]
        self._load_skill_to_form(skill_id)

    # ------------------------------------------------------------------
    # Form <-> Data
    # ------------------------------------------------------------------

    def _save_current_to_memory(self) -> None:
        """Collect all form field values and store in self._skills."""
        if self._current_skill_id is None:
            return
        if self._current_skill_id not in self._skills:
            return

        skill = {}

        # Name
        name = self._name_entry.get().strip() if self._name_entry else ""
        skill["name"] = name

        # Input
        inp = self._input_entry.get().strip() if self._input_entry else ""
        skill["input"] = inp

        # Keys
        keys = [k for k, v in self._key_vars.items() if v.get()]
        skill["keys"] = keys

        # Alt keys (only include if non-empty)
        alt_keys = [k for k, v in self._alt_key_vars.items() if v.get()]
        if alt_keys:
            skill["keys_alt"] = alt_keys

        # Protection
        prot = self._protection_var.get() if self._protection_var else "none"
        skill["protection"] = prot if prot else "none"

        # Damage
        dmg = self._damage_var.get() if self._damage_var else "none"
        skill["damage"] = dmg if dmg else "none"

        # Cooldown
        cd_text = self._cooldown_entry.get().strip() if self._cooldown_entry else "0"
        try:
            skill["cooldown_ms"] = int(cd_text) if cd_text else 0
        except ValueError:
            skill["cooldown_ms"] = 0

        # Level (optional)
        lvl_text = self._level_entry.get().strip() if self._level_entry else ""
        if lvl_text:
            try:
                skill["level"] = int(lvl_text)
            except ValueError:
                pass

        # CC
        cc = [cc_type for cc_type, var in self._cc_vars.items() if var.get()]
        skill["cc"] = cc

        # Description
        desc = self._desc_text.get("1.0", "end-1c").strip() if self._desc_text else ""
        if desc:
            skill["description"] = desc

        # Notes
        notes = (
            self._notes_text.get("1.0", "end-1c").strip() if self._notes_text else ""
        )
        if notes:
            skill["notes"] = notes

        # Flows into
        flows_text = self._flows_entry.get().strip() if self._flows_entry else ""
        if flows_text:
            flows = [s.strip() for s in flows_text.split(",") if s.strip()]
            if flows:
                skill["flows_into"] = flows

        # Core effect
        core = self._core_entry.get().strip() if self._core_entry else ""
        if core:
            skill["core_effect"] = core

        self._skills[self._current_skill_id] = skill

    def _load_skill_to_form(self, skill_id: str) -> None:
        """Load a skill's data into the form widgets."""
        self._current_skill_id = skill_id
        skill_data = self._skills.get(skill_id, {})

        self._set_form_visible(True)

        # Skill ID display
        self._id_label.configure(text=skill_id)
        self._id_label.pack(side="left", fill="x", expand=True)
        self._id_entry.pack_forget()
        self._id_is_new = False

        # Name
        self._set_entry(self._name_entry, skill_data.get("name", ""))

        # Input
        self._set_entry(self._input_entry, skill_data.get("input", ""))

        # Keys
        self._reset_all_keys(is_alt=False)
        for key in skill_data.get("keys", []):
            self._set_key_state(key, True, is_alt=False)

        # Alt keys
        self._reset_all_keys(is_alt=True)
        alt_keys = skill_data.get("keys_alt", [])
        for key in alt_keys:
            self._set_key_state(key, True, is_alt=True)

        # Show alt keys section if there are alt keys
        if alt_keys and not self._alt_keys_visible:
            self._toggle_alt_keys_visibility()
        elif not alt_keys and self._alt_keys_visible:
            self._toggle_alt_keys_visibility()

        # Protection
        prot = skill_data.get("protection", "none")
        if not prot or prot is None:
            prot = "none"
        self._protection_var.set(prot)

        # Damage
        dmg = skill_data.get("damage", "none")
        if not dmg or dmg is None:
            dmg = "none"
        self._damage_var.set(dmg)

        # Cooldown
        self._set_entry(self._cooldown_entry, str(skill_data.get("cooldown_ms", 0)))

        # Level
        level = skill_data.get("level", "")
        self._set_entry(self._level_entry, str(level) if level else "")

        # CC checkboxes
        cc_list = skill_data.get("cc", [])
        for cc_type, var in self._cc_vars.items():
            var.set(cc_type in cc_list)

        # Description
        self._set_text(self._desc_text, skill_data.get("description", ""))

        # Notes
        self._set_text(self._notes_text, skill_data.get("notes", ""))

        # Flows into
        flows = skill_data.get("flows_into", [])
        flows_str = ", ".join(flows) if isinstance(flows, list) else str(flows)
        self._set_entry(self._flows_entry, flows_str)

        # Core effect
        self._set_entry(self._core_entry, skill_data.get("core_effect", ""))

        # Scroll to top
        self._canvas.yview_moveto(0)

    def _clear_form(self) -> None:
        """Reset all form widgets to empty/default state."""
        self._current_skill_id = None
        self._id_is_new = False

        self._set_form_visible(False)

        # Reset field values anyway
        if self._id_label:
            self._id_label.configure(text="")
        if self._id_entry:
            self._id_entry.delete(0, tk.END)
            self._id_entry.pack_forget()
            self._id_label.pack(side="left", fill="x", expand=True)

        self._set_entry(self._name_entry, "")
        self._set_entry(self._input_entry, "")

        self._reset_all_keys(is_alt=False)
        self._reset_all_keys(is_alt=True)

        if self._alt_keys_visible:
            self._toggle_alt_keys_visibility()

        if self._protection_var:
            self._protection_var.set("none")
        if self._damage_var:
            self._damage_var.set("none")

        self._set_entry(self._cooldown_entry, "0")
        self._set_entry(self._level_entry, "")

        for var in self._cc_vars.values():
            var.set(False)

        self._set_text(self._desc_text, "")
        self._set_text(self._notes_text, "")
        self._set_entry(self._flows_entry, "")
        self._set_entry(self._core_entry, "")

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _set_entry(entry: Optional[tk.Entry], value: str) -> None:
        """Set an Entry widget's content."""
        if entry is None:
            return
        entry.delete(0, tk.END)
        entry.insert(0, value)

    @staticmethod
    def _set_text(text_widget: Optional[tk.Text], value: str) -> None:
        """Set a Text widget's content."""
        if text_widget is None:
            return
        text_widget.delete("1.0", tk.END)
        if value:
            text_widget.insert("1.0", value)

    # ------------------------------------------------------------------
    # Skill actions
    # ------------------------------------------------------------------

    def _generate_skill_id(self, name: str) -> str:
        """Generate a unique skill ID from a name."""
        base = name.lower().strip().replace(" ", "_")
        base = "".join(c for c in base if c.isalnum() or c == "_")
        if not base:
            base = "new_skill"

        skill_id = base
        counter = 2
        while skill_id in self._skills:
            skill_id = f"{base}_{counter}"
            counter += 1
        return skill_id

    def _on_add_skill(self) -> None:
        """Add a new skill to the list."""
        # Save current form first
        self._save_current_to_memory()

        self._new_skill_counter += 1
        default_name = f"New Skill {self._new_skill_counter}"
        skill_id = self._generate_skill_id(default_name)

        self._skills[skill_id] = {
            "name": default_name,
            "input": "",
            "keys": [],
            "protection": "none",
            "damage": "none",
            "cooldown_ms": 0,
            "cc": [],
            "description": "",
        }

        self._refresh_list()
        self._load_skill_to_form(skill_id)

        # Show the ID entry for new skills so user can customize
        self._id_label.pack_forget()
        self._id_entry.pack(side="left", fill="x", expand=True)
        self._id_entry.delete(0, tk.END)
        self._id_entry.insert(0, skill_id)
        self._id_is_new = True

        # Select in listbox
        sorted_ids = sorted(self._skills.keys())
        try:
            idx = sorted_ids.index(skill_id)
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
        except ValueError:
            pass

        # Focus the name entry for quick editing
        self._name_entry.focus_set()
        self._name_entry.select_range(0, tk.END)

        if self._on_change:
            try:
                self._on_change()
            except Exception:
                logger.exception("Error in on_change callback")

    def _on_delete_skill(self) -> None:
        """Delete the currently selected skill."""
        if self._current_skill_id is None:
            return
        if self._current_skill_id not in self._skills:
            return

        skill_name = self._skills[self._current_skill_id].get(
            "name", self._current_skill_id
        )
        confirm = messagebox.askyesno(
            "Delete Skill",
            f"Delete skill '{skill_name}' ({self._current_skill_id})?\n\n"
            "This cannot be undone.",
            icon="warning",
        )
        if not confirm:
            return

        del self._skills[self._current_skill_id]
        self._current_skill_id = None
        self._refresh_list()
        self._clear_form()

        if self._on_change:
            try:
                self._on_change()
            except Exception:
                logger.exception("Error in on_change callback")

    def _on_save_skill(self) -> None:
        """Save the current skill form to memory."""
        if self._current_skill_id is None:
            return

        # Handle ID rename for new skills
        if self._id_is_new and self._id_entry.winfo_ismapped():
            new_id = self._id_entry.get().strip()
            new_id = new_id.lower().replace(" ", "_")
            new_id = "".join(c for c in new_id if c.isalnum() or c == "_")

            if not new_id:
                new_id = self._current_skill_id

            if new_id != self._current_skill_id:
                # Check for conflicts
                if new_id in self._skills:
                    messagebox.showwarning(
                        "ID Conflict",
                        f"Skill ID '{new_id}' already exists. Please choose a different ID.",
                    )
                    return

                # Rename: move data from old key to new key
                self._skills[new_id] = self._skills.pop(self._current_skill_id)
                self._current_skill_id = new_id

            # Switch to label display
            self._id_entry.pack_forget()
            self._id_label.configure(text=self._current_skill_id)
            self._id_label.pack(side="left", fill="x", expand=True)
            self._id_is_new = False

        # Validate required fields
        name = self._name_entry.get().strip() if self._name_entry else ""
        if not name:
            messagebox.showwarning("Validation", "Skill name is required.")
            self._name_entry.focus_set()
            return

        self._save_current_to_memory()
        self._refresh_list()

        logger.info(f"Saved skill: {self._current_skill_id}")

        if self._on_change:
            try:
                self._on_change()
            except Exception:
                logger.exception("Error in on_change callback")
