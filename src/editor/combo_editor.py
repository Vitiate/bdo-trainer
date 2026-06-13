"""
Combo Editor — list + step editor panel.

Provides a split-view UI: combo list on the left, combo edit form + step
editor on the right.  Used as a tab inside the main EditorWindow.
"""

import copy
import logging
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("bdo_trainer")

# ---------------------------------------------------------------------------
# Theme constants — Solarized Dark (mirrors window.py / settings_gui)
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
FONT_SMALL = ("Segoe UI", 9)

# ---------------------------------------------------------------------------
# Combo category helpers
# ---------------------------------------------------------------------------
COMBO_CATEGORIES = ["pve_combos", "pvp_combos", "movement_combos"]

CATEGORY_DISPLAY: Dict[str, str] = {
    "pve_combos": "PVE",
    "pvp_combos": "PVP",
    "movement_combos": "Movement",
}

CATEGORY_FROM_DISPLAY: Dict[str, str] = {v: k for k, v in CATEGORY_DISPLAY.items()}

DIFFICULTY_OPTIONS = ["beginner", "intermediate", "advanced"]


class ComboEditor(tk.Frame):
    """Combo list + step editor panel."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        parent: tk.Widget,
        get_skills: Callable[[], Dict[str, dict]],
        on_change: Optional[Callable] = None,
    ):
        super().__init__(parent, bg=BG_DARK)
        # Expose self as .frame so the host window can do  editor.frame
        self.frame = self

        self._get_skills = get_skills
        self._on_change = on_change

        # Combo data keyed by category -> combo_id -> combo dict
        self._combos: Dict[str, Dict[str, dict]] = {cat: {} for cat in COMBO_CATEGORIES}
        self._current_combo_id: Optional[str] = None
        self._current_category: Optional[str] = None
        self._class_name: str = ""
        self._spec_name: str = ""

        # Listbox index -> (category, combo_id) or None for separator rows
        self._list_entries: List[Optional[Tuple[str, str]]] = []

        # Steps stored as plain dicts; widgets rebuilt on every mutation
        self._steps_data: List[dict] = []
        self._step_widgets: List[dict] = []

        # Counter for generating unique new-combo IDs
        self._new_combo_counter: int = 0

        # Form widget refs (populated by _build_ui)
        self._id_label: Optional[tk.Label] = None
        self._name_entry: Optional[tk.Entry] = None
        self._category_var: Optional[tk.StringVar] = None
        self._difficulty_var: Optional[tk.StringVar] = None
        self._window_entry: Optional[tk.Entry] = None
        self._desc_text: Optional[tk.Text] = None
        self._steps_container: Optional[tk.Frame] = None
        self._form_frame: Optional[tk.Frame] = None
        self._placeholder_label: Optional[tk.Label] = None
        self._header_label: Optional[tk.Label] = None
        self._save_btn: Optional[tk.Button] = None
        self._delete_btn: Optional[tk.Button] = None
        self._add_step_btn: Optional[tk.Button] = None
        # Mode toggle (sequence | priority)
        self._mode_var: Optional[tk.StringVar] = None
        self._mode_menu: Optional[tk.OptionMenu] = None
        # Sequence-mode container (steps UI). Tracked separately so we
        # can hide/show as the mode changes.
        self._sequence_block: Optional[tk.Frame] = None
        self._sequence_header: Optional[tk.Frame] = None
        # Priority-mode container + editor.
        self._priority_block: Optional[tk.Frame] = None
        self._priority_header: Optional[tk.Frame] = None
        self._priority_editor: Optional[Any] = None
        # Cached mode for the currently-loaded combo so reads / saves
        # know which block to honour even if the dropdown var was
        # cleared by ``_clear_form``.
        self._current_mode: str = "sequence"
        self._window_label: Optional[tk.Label] = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, config_data: Dict[str, Any], class_name: str, spec_name: str):
        """Load combo data from a class config dict."""
        self._class_name = class_name
        self._spec_name = spec_name
        for cat in COMBO_CATEGORIES:
            section = config_data.get(cat, {})
            self._combos[cat] = (
                copy.deepcopy(section) if isinstance(section, dict) else {}
            )
        self._current_combo_id = None
        self._current_category = None
        self._refresh_list()
        self._clear_form()
        if self._header_label is not None:
            self._header_label.configure(text=f"Combos for {class_name} ({spec_name})")

    def get_combos(self) -> Dict[str, dict]:
        """Return dict with pve_combos, pvp_combos, movement_combos."""
        self._save_current_to_memory()
        return copy.deepcopy(self._combos)

    def clear(self):
        """Reset to a blank state."""
        self._combos = {cat: {} for cat in COMBO_CATEGORIES}
        self._current_combo_id = None
        self._current_category = None
        self._class_name = ""
        self._spec_name = ""
        self._refresh_list()
        self._clear_form()
        if self._header_label is not None:
            self._header_label.configure(text="Combos")

    def rename_skill_reference(self, old_id: str, new_id: str) -> None:
        """Update every step that referenced ``old_id`` to point at ``new_id``."""
        if not old_id or old_id == new_id:
            return

        # Update stored combos.
        for cat in COMBO_CATEGORIES:
            for combo in self._combos.get(cat, {}).values():
                steps = combo.get("steps")
                if not isinstance(steps, list):
                    continue
                for step in steps:
                    if isinstance(step, dict) and step.get("skill") == old_id:
                        step["skill"] = new_id

        # Update the in-memory steps for the combo currently being edited.
        for step in self._steps_data:
            if isinstance(step, dict) and step.get("skill") == old_id:
                step["skill"] = new_id

        # Rebuild the step rows so their dropdowns reflect the new ID.
        self._rebuild_steps()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Create the horizontal split: combo list (left) + edit form (right)."""
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ---- Left panel: combo list ----------------------------------------
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
            text="Combos",
            font=FONT_HEADING,
            fg=GOLD,
            bg=BG_DARK,
            anchor="w",
        )
        self._header_label.grid(row=0, column=0, sticky="w")

        add_btn = tk.Button(
            header_row,
            text="+ Add",
            font=FONT_BOLD,
            bg=GREEN,
            fg="white",
            activebackground="#66BB6A",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._on_add_combo,
        )
        add_btn.grid(row=0, column=1, sticky="e", padx=(4, 0))

        # Listbox + scrollbar
        list_frame = tk.Frame(left_panel, bg=BG_DARK)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(2, 4))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._combo_listbox = tk.Listbox(
            list_frame,
            bg=BG_INPUT,
            fg=FG_TEXT,
            selectbackground=ACCENT,
            selectforeground="#FFFFFF",
            font=FONT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            exportselection=False,
            activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        self._combo_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.configure(command=self._combo_listbox.yview)
        self._combo_listbox.bind("<<ListboxSelect>>", self._on_combo_selected)

        # Thin separator between panels
        sep = tk.Frame(self, bg=BG_CARD, width=2)
        sep.grid(row=0, column=0, sticky="nse", padx=(218, 0))

        # ---- Right panel: edit form ----------------------------------------
        right_panel = tk.Frame(self, bg=BG_DARK)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        # Scrollable canvas
        self._canvas = tk.Canvas(
            right_panel,
            bg=BG_DARK,
            highlightthickness=0,
            bd=0,
        )
        canvas_scrollbar = tk.Scrollbar(
            right_panel,
            orient="vertical",
            command=self._canvas.yview,
        )
        self._form_frame = tk.Frame(self._canvas, bg=BG_DARK)

        self._form_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas_window = self._canvas.create_window(
            (0, 0),
            window=self._form_frame,
            anchor="nw",
        )
        self._canvas.configure(yscrollcommand=canvas_scrollbar.set)
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(
                self._canvas_window,
                width=e.width,
            ),
        )

        self._canvas.grid(row=0, column=0, sticky="nsew")
        canvas_scrollbar.grid(row=0, column=1, sticky="ns")

        # Bind mouse-wheel scrolling
        self._form_frame.bind("<Enter>", self._bind_mousewheel)
        self._form_frame.bind("<Leave>", self._unbind_mousewheel)

        # Build the form widgets inside _form_frame
        self._build_form()

        # Placeholder for when no combo is selected
        self._placeholder_label = tk.Label(
            self._form_frame,
            text="Select a combo from the list, or add a new one",
            font=FONT,
            fg=FG_DIM,
            bg=BG_DARK,
            anchor="center",
        )

        # Show placeholder initially
        self._clear_form()

    # ------------------------------------------------------------------
    # Mouse-wheel helpers for the canvas
    # ------------------------------------------------------------------

    def _bind_mousewheel(self, _event=None):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None):
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------
    # Form construction (inside the scrollable frame)
    # ------------------------------------------------------------------

    def _build_form(self):
        """Populate self._form_frame with all editing widgets."""
        ff = self._form_frame
        assert ff is not None
        ff.columnconfigure(1, weight=1)

        row = 0

        # ---- Collapsible metadata header ----------------------------
        # Lets the user hide the Combo ID / Name / Category /
        # Difficulty / Mode / Window / Description block once they're
        # configured, dedicating more visible area to the steps /
        # priority editor below.
        self._metadata_collapsed = False
        self._metadata_toggle_btn = tk.Button(
            ff,
            text="▼  Combo metadata",
            font=FONT_BOLD, fg=GOLD, bg=BG_DARK,
            activebackground=BG_DARK, activeforeground=ACCENT_HOVER,
            relief="flat", bd=0, anchor="w",
            padx=4, pady=2, cursor="hand2",
            command=self._toggle_metadata_collapsed,
        )
        self._metadata_toggle_btn.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 2),
        )
        row += 1

        # All the metadata fields below live inside this child frame
        # so the toggle can grid_remove the whole block at once. We
        # mirror ff's column configuration onto it so the existing
        # per-row .grid(column=0/1, sticky="ew") layout still flows
        # correctly.
        self._metadata_block = tk.Frame(ff, bg=BG_DARK)
        self._metadata_block.grid(
            row=row, column=0, columnspan=2, sticky="ew",
        )
        self._metadata_block.columnconfigure(1, weight=1)
        # Subsequent metadata-row .grid() calls target the child
        # frame by reassigning the local ``ff`` reference. We restore
        # ff at the end of the metadata block so the steps/priority
        # rows below grid into the original parent.
        meta_block_row = self._metadata_block_start_row = row
        row += 1
        ff = self._metadata_block

        # Reset the row counter for the metadata block — it grids
        # into its own child frame starting at row 0.
        row = 0

        # ---- Combo ID (read-only) ----
        tk.Label(
            ff,
            text="Combo ID:",
            font=FONT_BOLD,
            fg=FG_DIM,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=(8, 2))

        # Combo ID — editable. Renaming re-keys the in-memory combos
        # dict so the next save writes a new file (and the old one is
        # diffed away by the host window).
        self._id_entry = tk.Entry(
            ff,
            font=FONT_BOLD,
            fg=ACCENT,
            bg=BG_INPUT,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BG_CARD,
        )
        self._id_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=(8, 2))
        self._id_entry.bind("<FocusOut>", self._on_id_changed)
        self._id_entry.bind("<Return>", self._on_id_changed)
        # Backwards-compat alias for the few sites that still poke
        # ``self._id_label``. The Entry has both ``configure`` and the
        # widget API, so most existing calls work transparently — the
        # ones that read ``cget('text')`` will need a code review.
        self._id_label = self._id_entry
        row += 1

        # ---- Name ----
        tk.Label(
            ff,
            text="Name:",
            font=FONT,
            fg=FG_TEXT,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=2)

        self._name_entry = tk.Entry(
            ff,
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        )
        self._name_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        row += 1

        # ---- Category ----
        tk.Label(
            ff,
            text="Category:",
            font=FONT,
            fg=FG_TEXT,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=2)

        cat_frame = tk.Frame(ff, bg=BG_DARK)
        cat_frame.grid(row=row, column=1, sticky="w", padx=4, pady=2)
        self._category_var = tk.StringVar(value="PVE")
        display_cats = list(CATEGORY_DISPLAY.values())
        self._category_menu = tk.OptionMenu(
            cat_frame, self._category_var, *display_cats
        )
        self._category_menu.configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            highlightthickness=0,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
        )
        self._category_menu["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT)
        self._category_menu.pack(side="left")
        row += 1

        # ---- Difficulty ----
        tk.Label(
            ff,
            text="Difficulty:",
            font=FONT,
            fg=FG_TEXT,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=2)

        diff_frame = tk.Frame(ff, bg=BG_DARK)
        diff_frame.grid(row=row, column=1, sticky="w", padx=4, pady=2)
        self._difficulty_var = tk.StringVar(value="beginner")
        self._difficulty_menu = tk.OptionMenu(
            diff_frame,
            self._difficulty_var,
            *DIFFICULTY_OPTIONS,
        )
        self._difficulty_menu.configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            highlightthickness=0,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
        )
        self._difficulty_menu["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT)
        self._difficulty_menu.pack(side="left")
        row += 1

        # ---- Mode (sequence | priority) ----
        tk.Label(
            ff,
            text="Mode:",
            font=FONT,
            fg=FG_TEXT,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=2)

        mode_frame = tk.Frame(ff, bg=BG_DARK)
        mode_frame.grid(row=row, column=1, sticky="w", padx=4, pady=2)
        self._mode_var = tk.StringVar(value="sequence")
        self._mode_menu = tk.OptionMenu(
            mode_frame,
            self._mode_var,
            "sequence",
            "priority",
            command=self._on_mode_changed,
        )
        self._mode_menu.configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            highlightthickness=0,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
        )
        self._mode_menu["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT)
        self._mode_menu.pack(side="left")
        tk.Label(
            mode_frame,
            text="  (priority = highest off-cooldown skill wins)",
            font=FONT_SMALL,
            fg=FG_DIM,
            bg=BG_DARK,
        ).pack(side="left", padx=(8, 0))
        row += 1

        # ---- Combo Window (ms) — sequence-mode only ----
        self._window_label = tk.Label(
            ff,
            text="Step Window (ms):",
            font=FONT,
            fg=FG_TEXT,
            bg=BG_DARK,
            anchor="w",
        )
        self._window_label.grid(row=row, column=0, sticky="w", padx=(8, 4), pady=2)

        self._window_entry = tk.Entry(
            ff,
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            width=10,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        )
        self._window_entry.grid(row=row, column=1, sticky="w", padx=4, pady=2)
        self._window_row = row
        row += 1

        # ---- Description ----
        tk.Label(
            ff,
            text="Description:",
            font=FONT,
            fg=FG_TEXT,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=row, column=0, sticky="nw", padx=(8, 4), pady=2)

        self._desc_text = tk.Text(
            ff,
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT,
            height=2,
            width=40,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
            wrap="word",
        )
        self._desc_text.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        row += 1

        # End of metadata block — switch back to the outer form
        # frame so the steps / priority sections grid into the
        # parent at row = self._metadata_block_start_row + 1, which
        # was reserved before we redirected ff.
        ff = self._form_frame
        row = self._metadata_block_start_row + 1

        # ---- Sequence-mode block (steps header + container + add btn) ----
        self._sequence_header = tk.Frame(ff, bg=BG_DARK)
        self._sequence_header.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=(12, 2)
        )
        self._sequence_header.columnconfigure(0, weight=1)

        tk.Label(
            self._sequence_header,
            text="Steps",
            font=FONT_BOLD,
            fg=GOLD,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        tk.Frame(self._sequence_header, bg=GOLD, height=1).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(2, 0),
        )
        self._sequence_header_row = row
        row += 1

        # Steps container — bare frame so existing _create_step_row code
        # is unchanged.
        self._steps_container = tk.Frame(ff, bg=BG_DARK)
        self._steps_container.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=2,
        )
        self._steps_container_row = row
        row += 1

        self._add_step_btn = tk.Button(
            ff,
            text="+ Add Step",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._on_add_step,
        )
        self._add_step_btn.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=(4, 8),
        )
        self._add_step_btn_row = row
        row += 1

        # ---- Priority-mode block (header + editor) ----
        # Hidden by default; shown when mode == "priority".
        self._priority_header = tk.Frame(ff, bg=BG_DARK)
        self._priority_header.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=(12, 2)
        )
        self._priority_header.columnconfigure(0, weight=1)
        tk.Label(
            self._priority_header,
            text="Priority Tiers",
            font=FONT_BOLD,
            fg=GOLD,
            bg=BG_DARK,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            self._priority_header,
            text=(
                "Highest tier first. Skills inside each tier are checked "
                "in order. boost_after promotes a skill one tier up while "
                "the named skill is still recently cast."
            ),
            font=FONT_SMALL,
            fg=FG_DIM,
            bg=BG_DARK,
            anchor="w",
            justify="left",
            wraplength=560,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Frame(self._priority_header, bg=GOLD, height=1).grid(
            row=2, column=0, sticky="ew", pady=(2, 0),
        )
        self._priority_header_row = row
        row += 1

        # Imported lazily so the editor still loads if priority_editor.py
        # isn't shipped in some downstream environment.
        from src.editor.priority_editor import PriorityEditor

        self._priority_block = tk.Frame(ff, bg=BG_DARK)
        self._priority_block.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=2,
        )
        self._priority_editor = PriorityEditor(
            self._priority_block,
            get_skills=self._get_skills,
            on_change=self._on_change,
        )
        self._priority_editor.pack(fill="x", expand=True)
        self._priority_block_row = row
        row += 1

        # Default to sequence mode — hide the priority block until the
        # user picks priority mode.
        self._set_mode_visibility("sequence")

        # ---- Button row: Save + Delete ----
        btn_row = tk.Frame(ff, bg=BG_DARK)
        btn_row.grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 16))

        self._save_btn = tk.Button(
            btn_row,
            text="Save Combo",
            font=FONT_BOLD,
            bg=GREEN,
            fg="white",
            activebackground="#66BB6A",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._on_save_combo,
        )
        self._save_btn.pack(side="left", padx=(0, 8))

        self._delete_btn = tk.Button(
            btn_row,
            text="Delete Combo",
            font=FONT,
            bg=BG_INPUT,
            fg=RED_SOFT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._on_delete_combo,
        )
        self._delete_btn.pack(side="left")

        # Keep track of the max form row for toggling visibility
        self._form_widgets_row_count = row + 1

    # ------------------------------------------------------------------
    # Metadata collapse toggle
    # ------------------------------------------------------------------
    def _toggle_metadata_collapsed(self) -> None:
        """Hide / show the combo-metadata block. The toggle button
        always stays visible so the user can re-expand. Steps /
        priority editor below shifts up as the metadata block
        disappears because grid_remove preserves layout slots but
        not space.
        """
        if self._metadata_collapsed:
            self._metadata_block.grid()
            self._metadata_toggle_btn.configure(text="▼  Combo metadata")
            self._metadata_collapsed = False
        else:
            self._metadata_block.grid_remove()
            self._metadata_toggle_btn.configure(text="▶  Combo metadata")
            self._metadata_collapsed = True

    # ------------------------------------------------------------------
    # Mode visibility
    # ------------------------------------------------------------------
    def _set_mode_visibility(self, mode: str) -> None:
        """Show only the widgets relevant to *mode* ("sequence" | "priority")."""
        is_priority = mode == "priority"
        # Sequence widgets
        for w, row_attr in (
            (self._sequence_header, "_sequence_header_row"),
            (self._steps_container, "_steps_container_row"),
            (self._add_step_btn, "_add_step_btn_row"),
        ):
            if w is None:
                continue
            try:
                if is_priority:
                    w.grid_remove()
                else:
                    w.grid()
            except Exception:
                pass
        # Step-window field is sequence-only too.
        if self._window_label is not None and self._window_entry is not None:
            try:
                if is_priority:
                    self._window_label.grid_remove()
                    self._window_entry.grid_remove()
                else:
                    self._window_label.grid()
                    self._window_entry.grid()
            except Exception:
                pass
        # Priority widgets
        for w in (self._priority_header, self._priority_block):
            if w is None:
                continue
            try:
                if is_priority:
                    w.grid()
                else:
                    w.grid_remove()
            except Exception:
                pass

    def _on_mode_changed(self, _value: str = "") -> None:
        """User picked a different combo mode. Persist whatever's in the
        UI right now under the *previous* mode so a flip-flop preserves
        edits, then swap visibility."""
        new_mode = self._mode_var.get() if self._mode_var else "sequence"
        if new_mode == self._current_mode:
            return
        # Capture in-progress edits in the previous mode's data structure
        # before tearing the widgets down.
        self._save_current_to_memory()
        self._current_mode = new_mode
        self._set_mode_visibility(new_mode)
        # Rehydrate the now-visible block from the in-memory combo so
        # any data we already had for that mode shows up.
        if self._current_combo_id and self._current_category:
            combo = self._combos.get(self._current_category, {}).get(
                self._current_combo_id, {}
            )
            if new_mode == "priority":
                if self._priority_editor is not None:
                    self._priority_editor.load(combo.get("priority"))
            else:
                self._steps_data = []
                for step in combo.get("steps", []) or []:
                    if isinstance(step, dict):
                        self._steps_data.append({
                            "skill": step.get("skill", ""),
                            "note": step.get("note", ""),
                            "hold_ms": str(step.get("hold_ms", ""))
                            if step.get("hold_ms") else "",
                        })
                self._rebuild_steps()
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                logger.exception("on_change callback failed (mode change)")

    # ------------------------------------------------------------------
    # Listbox management
    # ------------------------------------------------------------------

    def _refresh_list(self):
        """Rebuild the listbox from current combo data."""
        self._combo_listbox.delete(0, "end")
        self._list_entries = []

        for cat in COMBO_CATEGORIES:
            combos = self._combos.get(cat, {})
            if not combos:
                continue
            # Separator header
            display_name = CATEGORY_DISPLAY.get(cat, cat)
            header_text = f"\u2500\u2500 {display_name} \u2500\u2500"
            idx = self._combo_listbox.size()
            self._combo_listbox.insert("end", header_text)
            self._combo_listbox.itemconfig(idx, fg=GOLD, selectbackground=BG_INPUT)
            self._list_entries.append(None)  # separator marker

            for combo_id in sorted(combos.keys()):
                combo = combos[combo_id]
                display = combo.get("name", combo_id)
                if len(display) > 24:
                    display = display[:22] + "\u2026"
                self._combo_listbox.insert("end", f"  {display}")
                self._list_entries.append((cat, combo_id))

        # Restore selection if the current combo is still present
        if self._current_combo_id and self._current_category:
            for i, entry in enumerate(self._list_entries):
                if entry and entry == (self._current_category, self._current_combo_id):
                    self._combo_listbox.selection_set(i)
                    self._combo_listbox.see(i)
                    break

    def _on_combo_selected(self, _event=None):
        """Handle listbox selection change."""
        sel = self._combo_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._list_entries):
            return

        entry = self._list_entries[idx]
        if entry is None:
            # Clicked a separator — deselect it
            self._combo_listbox.selection_clear(idx)
            # Restore previous selection if any
            if self._current_combo_id and self._current_category:
                for i, e in enumerate(self._list_entries):
                    if e and e == (self._current_category, self._current_combo_id):
                        self._combo_listbox.selection_set(i)
                        break
            return

        cat, combo_id = entry

        # Already selected
        if combo_id == self._current_combo_id and cat == self._current_category:
            return

        # Save previous combo before switching
        self._save_current_to_memory()

        self._current_category = cat
        self._current_combo_id = combo_id
        self._load_combo_to_form(cat, combo_id)

    # ------------------------------------------------------------------
    # Form population / clearing
    # ------------------------------------------------------------------

    def _load_combo_to_form(self, category: str, combo_id: str):
        """Populate the form with data from a specific combo."""
        combo = self._combos.get(category, {}).get(combo_id)
        if combo is None:
            self._clear_form()
            return

        self._show_form(True)

        # Combo ID — populate the Entry without firing dirty.
        assert self._id_entry is not None
        self._id_entry.delete(0, "end")
        self._id_entry.insert(0, combo_id)

        # Name
        assert self._name_entry is not None
        self._name_entry.delete(0, "end")
        self._name_entry.insert(0, combo.get("name", ""))

        # Category
        display_cat = CATEGORY_DISPLAY.get(category, "PVE")
        assert self._category_var is not None
        self._category_var.set(display_cat)

        # Difficulty
        diff = combo.get("difficulty", "beginner")
        if diff not in DIFFICULTY_OPTIONS:
            diff = "beginner"
        assert self._difficulty_var is not None
        self._difficulty_var.set(diff)

        # Combo window
        assert self._window_entry is not None
        self._window_entry.delete(0, "end")
        window_val = combo.get("combo_window_ms", "")
        if window_val != "" and window_val is not None:
            self._window_entry.insert(0, str(window_val))

        # Description
        assert self._desc_text is not None
        self._desc_text.delete("1.0", "end")
        self._desc_text.insert("1.0", combo.get("description", ""))

        # Mode — sequence (default) or priority.
        mode = combo.get("mode", "sequence")
        if mode not in ("sequence", "priority"):
            mode = "sequence"
        self._current_mode = mode
        if self._mode_var is not None:
            self._mode_var.set(mode)
        self._set_mode_visibility(mode)

        # Sequence-mode steps
        self._steps_data = []
        for step in combo.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            self._steps_data.append(
                {
                    "skill": step.get("skill", ""),
                    "note": step.get("note", ""),
                    "hold_ms": str(step.get("hold_ms", ""))
                    if step.get("hold_ms")
                    else "",
                }
            )
        self._rebuild_steps()

        # Priority-mode tiers
        if self._priority_editor is not None:
            self._priority_editor.load(combo.get("priority"))

    def _clear_form(self):
        """Reset all form widgets to empty / default and hide the form."""
        if self._id_entry:
            self._id_entry.delete(0, "end")
        if self._name_entry:
            self._name_entry.delete(0, "end")
        if self._category_var:
            self._category_var.set("PVE")
        if self._difficulty_var:
            self._difficulty_var.set("beginner")
        if self._mode_var:
            self._mode_var.set("sequence")
        self._current_mode = "sequence"
        self._set_mode_visibility("sequence")
        if self._window_entry:
            self._window_entry.delete(0, "end")
        if self._desc_text:
            self._desc_text.delete("1.0", "end")

        self._steps_data = []
        self._rebuild_steps()
        if self._priority_editor is not None:
            self._priority_editor.clear()
        self._show_form(False)

    def _show_form(self, visible: bool):
        """Toggle visibility of the edit form vs. the placeholder."""
        assert self._form_frame is not None
        if visible:
            if self._placeholder_label:
                self._placeholder_label.grid_forget()
            # Make sure form widgets are visible by re-gridding them if needed
            # They should already be gridded from _build_form; just ensure
            # the placeholder is hidden.
            for child in self._form_frame.winfo_children():
                if child is not self._placeholder_label:
                    # Children are already gridded; nothing to do
                    pass
            self._set_form_state("normal")
        else:
            # Hide form contents by disabling interaction; show placeholder
            self._set_form_state("disabled")
            if self._placeholder_label:
                self._placeholder_label.grid(
                    row=0,
                    column=0,
                    columnspan=2,
                    sticky="nsew",
                    padx=20,
                    pady=40,
                )

    def _set_form_state(self, state: str):
        """Enable or disable form entry widgets."""
        # Cast to the literal type expected by tkinter widget .configure()
        entry_state: Any = state
        text_state: Any = state
        btn_state: Any = state

        if self._name_entry:
            self._name_entry.configure(state=entry_state)
        if self._window_entry:
            self._window_entry.configure(state=entry_state)
        if self._desc_text:
            self._desc_text.configure(state=text_state)
        if self._save_btn:
            self._save_btn.configure(state=btn_state)
        if self._delete_btn:
            self._delete_btn.configure(state=btn_state)
        if self._add_step_btn:
            self._add_step_btn.configure(state=btn_state)
        try:
            if self._category_menu:
                self._category_menu.configure(state=btn_state)
        except Exception:
            pass
        try:
            if self._difficulty_menu:
                self._difficulty_menu.configure(state=btn_state)
        except Exception:
            pass
        try:
            if self._mode_menu:
                self._mode_menu.configure(state=btn_state)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    def _rebuild_steps(self):
        """Destroy and recreate all step row widgets from self._steps_data."""
        # Destroy existing step widgets
        for sw in self._step_widgets:
            try:
                sw["frame"].destroy()
            except Exception:
                pass
        self._step_widgets = []

        if self._steps_container is None:
            return

        for i, step_data in enumerate(self._steps_data):
            self._create_step_row(i, step_data)

    def _create_step_row(self, index: int, step_data: dict) -> dict:
        """Create a single step row inside the steps container."""
        row = tk.Frame(self._steps_container, bg=BG_DARK)
        row.pack(fill="x", pady=2)

        # Step number
        num_label = tk.Label(
            row,
            text=str(index + 1),
            width=3,
            bg=BG_DARK,
            fg=FG_DIM,
            font=FONT,
        )
        num_label.pack(side="left")

        # Skill dropdown — labels show the skill name; the underlying value
        # stored in step["skill"] is still the ID.
        skills = self._get_skills() or {}
        # Sort by display label (name fallback to id) for friendlier browsing.
        sorted_ids = sorted(
            skills.keys(),
            key=lambda sid: (skills[sid].get("name") or sid).lower(),
        )

        def _label_for(sid: str) -> str:
            name = skills.get(sid, {}).get("name", "").strip()
            return f"{name}  ({sid})" if name else sid

        label_to_id = {_label_for(sid): sid for sid in sorted_ids}
        labels = list(label_to_id.keys())

        current_id = step_data.get("skill", "")
        # If the step references an unknown skill, surface it so the user
        # can fix it instead of having it silently disappear.
        if current_id and current_id not in skills:
            stale_label = f"⚠  {current_id}  (missing)"
            labels.insert(0, stale_label)
            label_to_id[stale_label] = current_id
            initial_label = stale_label
        elif current_id:
            initial_label = _label_for(current_id)
        else:
            initial_label = ""

        skill_var = tk.StringVar(value=initial_label)

        if labels:
            skill_menu = tk.OptionMenu(row, skill_var, *labels)
        else:
            skill_menu = tk.OptionMenu(row, skill_var, "")
        skill_menu.configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT_SMALL,
            highlightthickness=0,
            width=24,
            relief="flat",
            activebackground=ACCENT,
            activeforeground="#FFF",
        )
        skill_menu["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT_SMALL)
        skill_menu.pack(side="left", padx=2)

        # Note entry
        note_entry = tk.Entry(
            row,
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT_SMALL,
            width=20,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        )
        note_entry.insert(0, step_data.get("note", ""))
        note_entry.pack(side="left", padx=2)

        # Hold ms entry
        hold_frame = tk.Frame(row, bg=BG_DARK)
        hold_frame.pack(side="left", padx=2)

        hold_entry = tk.Entry(
            hold_frame,
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT_SMALL,
            width=6,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        )
        hold_val = step_data.get("hold_ms", "")
        if hold_val:
            hold_entry.insert(0, str(hold_val))
        hold_entry.pack(side="left")

        tk.Label(
            hold_frame,
            text="ms",
            font=FONT_SMALL,
            fg=FG_DIM,
            bg=BG_DARK,
        ).pack(side="left", padx=(1, 0))

        # Move up button
        up_btn = tk.Button(
            row,
            text="\u25b2",
            font=FONT_SMALL,
            width=2,
            bg=BG_INPUT,
            fg=FG_TEXT,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT,
            activeforeground="#FFF",
            command=lambda i=index: self._move_step(i, -1),
        )
        up_btn.pack(side="left", padx=1)

        # Move down button
        down_btn = tk.Button(
            row,
            text="\u25bc",
            font=FONT_SMALL,
            width=2,
            bg=BG_INPUT,
            fg=FG_TEXT,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT,
            activeforeground="#FFF",
            command=lambda i=index: self._move_step(i, 1),
        )
        down_btn.pack(side="left", padx=1)

        # Delete button
        del_btn = tk.Button(
            row,
            text="\u00d7",
            font=FONT_SMALL,
            width=2,
            bg=BG_INPUT,
            fg=RED_SOFT,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT,
            activeforeground="#FFF",
            command=lambda i=index: self._remove_step(i),
        )
        del_btn.pack(side="left", padx=1)

        widget_info = {
            "frame": row,
            "skill_var": skill_var,
            "skill_menu": skill_menu,
            "skill_label_to_id": label_to_id,
            "note_entry": note_entry,
            "hold_entry": hold_entry,
        }
        self._step_widgets.append(widget_info)
        return widget_info

    def _collect_steps_data(self) -> List[dict]:
        """Read the current step widget state into a list of data dicts."""
        steps: List[dict] = []
        for sw in self._step_widgets:
            step: dict = {}
            label = sw["skill_var"].get().strip()
            label_map = sw.get("skill_label_to_id") or {}
            # Translate the user-facing label back to the canonical skill ID;
            # fall back to the raw string for legacy step rows.
            skill = label_map.get(label, label)
            if skill:
                step["skill"] = skill
            note = sw["note_entry"].get().strip()
            if note:
                step["note"] = note
            hold_str = sw["hold_entry"].get().strip()
            if hold_str:
                try:
                    step["hold_ms"] = str(int(hold_str))
                except ValueError:
                    pass
            # Even if step is mostly empty, keep it if it has at least a skill
            # to preserve the row; otherwise include any non-empty step
            if step:
                steps.append(step)
            else:
                # Preserve empty rows to keep numbering stable during editing
                steps.append({"skill": "", "note": "", "hold_ms": ""})
        return steps

    def _on_add_step(self):
        """Add a blank step to the end."""
        self._steps_data = self._collect_steps_data()
        self._steps_data.append({"skill": "", "note": "", "hold_ms": ""})
        self._rebuild_steps()

    def _remove_step(self, index: int):
        """Remove the step at the given index."""
        self._steps_data = self._collect_steps_data()
        if 0 <= index < len(self._steps_data):
            self._steps_data.pop(index)
        self._rebuild_steps()

    def _move_step(self, index: int, direction: int):
        """Move a step up (-1) or down (+1)."""
        self._steps_data = self._collect_steps_data()
        new_index = index + direction
        if new_index < 0 or new_index >= len(self._steps_data):
            return
        # Swap
        self._steps_data[index], self._steps_data[new_index] = (
            self._steps_data[new_index],
            self._steps_data[index],
        )
        self._rebuild_steps()

    # ------------------------------------------------------------------
    # Combo ID rename (live)
    # ------------------------------------------------------------------
    def _on_id_changed(self, _event=None) -> None:
        """User edited the Combo ID Entry. Sanitise + re-key in-memory.

        The actual on-disk move happens at save time — the host window
        diffs the new combo ids against what's currently in the bundle
        and writes/deletes accordingly.
        """
        if self._id_entry is None:
            return
        if self._current_combo_id is None or self._current_category is None:
            return

        raw = self._id_entry.get().strip()
        sanitized = raw.lower().replace(" ", "_")
        sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")

        old_id = self._current_combo_id
        category = self._current_category

        # No-op or empty — revert.
        if not sanitized or sanitized == old_id:
            self._id_entry.delete(0, "end")
            self._id_entry.insert(0, old_id)
            return

        # Collision check — only within the same category.
        if sanitized in self._combos.get(category, {}):
            from tkinter import messagebox
            messagebox.showwarning(
                "Duplicate Combo ID",
                f"A combo with id '{sanitized}' already exists in this "
                "category. Choose a different id.",
                parent=self.winfo_toplevel(),
            )
            self._id_entry.delete(0, "end")
            self._id_entry.insert(0, old_id)
            return

        # Re-key the dict in place. Preserve insertion order by rebuilding.
        new_section: Dict[str, dict] = {}
        for k, v in self._combos.get(category, {}).items():
            if k == old_id:
                # Stamp the new combo_id into the combo dict too so that
                # save_combo() writes the right filename.
                v = dict(v)
                v["combo_id"] = sanitized
                new_section[sanitized] = v
            else:
                new_section[k] = v
        self._combos[category] = new_section

        self._current_combo_id = sanitized
        self._id_entry.delete(0, "end")
        self._id_entry.insert(0, sanitized)
        self._refresh_list()

        # Notify the host window so it knows there's pending work.
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                logger.exception("Error in on_change callback")

    # ------------------------------------------------------------------
    # Save / collect current form data
    # ------------------------------------------------------------------

    def _save_current_to_memory(self):
        """Persist the current form state back into self._combos."""
        if self._current_combo_id is None or self._current_category is None:
            return

        combo_id = self._current_combo_id
        old_cat = self._current_category

        # Collect form values
        name = self._name_entry.get().strip() if self._name_entry else ""
        difficulty = self._difficulty_var.get() if self._difficulty_var else "beginner"
        category_display = self._category_var.get() if self._category_var else "PVE"
        new_cat = CATEGORY_FROM_DISPLAY.get(category_display, old_cat)

        # Combo window ms
        combo_window_ms = 300
        if self._window_entry:
            w_str = self._window_entry.get().strip()
            if w_str:
                try:
                    combo_window_ms = int(w_str)
                except ValueError:
                    combo_window_ms = 300

        # Description
        description = ""
        if self._desc_text:
            description = self._desc_text.get("1.0", "end-1c").strip()

        mode = self._current_mode if self._current_mode in ("sequence", "priority") else "sequence"
        if self._mode_var is not None:
            mv = self._mode_var.get()
            if mv in ("sequence", "priority"):
                mode = mv

        if mode == "priority":
            priority_block: List[dict] = []
            if self._priority_editor is not None:
                priority_block = self._priority_editor.collect()
            combo_dict: dict = {
                "name": name,
                "difficulty": difficulty,
                "description": description,
                "mode": "priority",
                "priority": priority_block,
            }
        else:
            # Sequence mode (default).
            raw_steps = self._collect_steps_data()
            steps: List[dict] = []
            for s in raw_steps:
                clean: dict = {}
                skill = s.get("skill", "")
                if skill:
                    clean["skill"] = skill
                note = s.get("note", "")
                if note:
                    clean["note"] = note
                hold = s.get("hold_ms", "")
                if hold:
                    try:
                        clean["hold_ms"] = int(hold)
                    except ValueError:
                        pass
                if clean:
                    steps.append(clean)

            combo_dict = {
                "name": name,
                "difficulty": difficulty,
                "combo_window_ms": combo_window_ms,
                "description": description,
                "steps": steps,
            }

        # Handle category change
        if new_cat != old_cat:
            # Remove from old category
            old_section = self._combos.get(old_cat, {})
            old_section.pop(combo_id, None)
            # Add to new category
            if new_cat not in self._combos:
                self._combos[new_cat] = {}
            self._combos[new_cat][combo_id] = combo_dict
            self._current_category = new_cat
        else:
            if old_cat not in self._combos:
                self._combos[old_cat] = {}
            self._combos[old_cat][combo_id] = combo_dict

    # ------------------------------------------------------------------
    # Combo-level actions
    # ------------------------------------------------------------------

    def _on_add_combo(self):
        """Create a new combo with a generated ID."""
        self._save_current_to_memory()

        # Generate unique ID
        self._new_combo_counter += 1
        while True:
            new_id = f"new_combo_{self._new_combo_counter}"
            # Ensure uniqueness across all categories
            conflict = False
            for cat in COMBO_CATEGORIES:
                if new_id in self._combos.get(cat, {}):
                    conflict = True
                    break
            if not conflict:
                break
            self._new_combo_counter += 1

        # Default to pve_combos
        default_cat = "pve_combos"
        skeleton: dict = {
            "name": "New Combo",
            "difficulty": "beginner",
            "combo_window_ms": 300,
            "description": "",
            "steps": [],
        }

        if default_cat not in self._combos:
            self._combos[default_cat] = {}
        self._combos[default_cat][new_id] = skeleton

        self._current_category = default_cat
        self._current_combo_id = new_id

        self._refresh_list()
        self._load_combo_to_form(default_cat, new_id)

        if self._on_change:
            try:
                self._on_change()
            except Exception as exc:
                logger.error("on_change callback failed: %s", exc)

    def _on_delete_combo(self):
        """Delete the currently selected combo after confirmation."""
        if self._current_combo_id is None or self._current_category is None:
            return

        combo_id = self._current_combo_id
        cat = self._current_category
        combo = self._combos.get(cat, {}).get(combo_id, {})
        combo_name = combo.get("name", combo_id)

        answer = messagebox.askyesno(
            "Delete Combo",
            f'Delete combo "{combo_name}" ({combo_id})?\n\nThis cannot be undone.',
            parent=self.winfo_toplevel(),
        )
        if not answer:
            return

        # Remove
        section = self._combos.get(cat, {})
        section.pop(combo_id, None)

        self._current_combo_id = None
        self._current_category = None

        self._refresh_list()
        self._clear_form()

        if self._on_change:
            try:
                self._on_change()
            except Exception as exc:
                logger.error("on_change callback failed: %s", exc)

    def _on_save_combo(self):
        """Save the current combo to memory and refresh the list."""
        if self._current_combo_id is None:
            return

        self._save_current_to_memory()
        self._refresh_list()

        if self._on_change:
            try:
                self._on_change()
            except Exception as exc:
                logger.error("on_change callback failed: %s", exc)

        logger.debug(
            "Saved combo %s/%s to memory",
            self._current_category,
            self._current_combo_id,
        )
