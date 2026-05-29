"""
Class & Combo Editor — main window.

Singleton Toplevel that provides a sidebar listing all loaded class/spec
pairs, with a tabbed content area for editing skills and combos.
"""

import copy
import logging
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("bdo_trainer")

# ---------------------------------------------------------------------------
# Theme constants — Solarized Dark (mirrors settings_gui)
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


def _force_dialog_to_front(toplevel: tk.Toplevel) -> None:
    """Keep a modal Toplevel reliably in front for its entire lifetime.

    macOS specifics:
      • A Toplevel created right after a native file picker closes is
        often pushed behind its parent.
      • If the parent window also has ``-topmost True`` set (the editor
        does), the two windows fight for stacking and clicking the
        dialog can hoist the parent's group above it.
      • ``grab_set`` makes the dialog modal but doesn't prevent the
        parent's window manager from being raised on click.

    The fix:
      1. Temporarily turn off ``-topmost`` on the parent so the dialog's
         own ``-topmost`` always wins. Restore the parent's value when
         the dialog is destroyed.
      2. Re-apply ``-topmost True`` + ``lift`` + ``focus_force`` across
         several passes to outlast macOS reordering after a file picker.
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
            # Re-apply on every pass — focus_force / lift can implicitly
            # clear -topmost on macOS, so once is not enough.
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

    # Restore the parent's topmost flag when the dialog is destroyed.
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

# Skill section keys used in class config YAML files
_SKILL_SECTIONS = ("skills", "awakening_skills", "rabam_skills", "preawakening_utility")


class EditorWindow:
    """Class & Combo Editor window (singleton)."""

    _instance: Optional["EditorWindow"] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def open(
        cls,
        root: tk.Tk,
        loader: Any,
        on_save: Optional[Callable] = None,
    ) -> "EditorWindow":
        """Open the editor, or focus the existing one."""
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
        on_save: Optional[Callable] = None,
    ) -> None:
        self.root = root
        self.loader = loader
        self.on_save = on_save

        self._dirty: bool = False
        self._configs: Dict[Tuple[str, str], Dict[str, Any]] = copy.deepcopy(
            loader.class_configs
        )
        self._current_key: Optional[Tuple[str, str]] = None
        self._sidebar_keys: List[Tuple[str, str]] = []

        # ---- Toplevel window ------------------------------------------------
        self.window = tk.Toplevel(root)
        self.window.title("BDO Trainer \u2014 Class & Combo Editor")
        self.window.configure(bg=BG_DARK)
        self.window.attributes("-topmost", True)
        self.window.resizable(True, True)
        self.window.minsize(1000, 650)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

        # Centre on screen
        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        ww = max(self.window.winfo_width(), 1000)
        wh = max(self.window.winfo_height(), 650)
        self.window.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble the full editor layout."""

        # ---- Title bar -----------------------------------------------------
        title_frame = tk.Frame(self.window, bg=BG_DARK)
        title_frame.pack(fill="x", padx=12, pady=(10, 4))

        tk.Label(
            title_frame,
            text="\u2694  Class & Combo Editor",
            font=FONT_TITLE,
            fg=GOLD,
            bg=BG_DARK,
            anchor="w",
        ).pack(side="left")

        # ---- Main PanedWindow (sidebar | content) -------------------------
        self._paned = tk.PanedWindow(
            self.window,
            orient="horizontal",
            bg=BG_DARK,
            sashwidth=4,
            sashrelief="flat",
            bd=0,
        )
        self._paned.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self._build_sidebar()
        self._build_content()

    # ---- Sidebar -----------------------------------------------------------

    def _build_sidebar(self) -> None:
        sidebar = tk.Frame(self._paned, bg=BG_CARD, width=200)
        sidebar.pack_propagate(False)

        # Header
        tk.Label(
            sidebar,
            text="Classes",
            font=FONT_HEADING,
            fg=GOLD,
            bg=BG_CARD,
            anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 4))

        # Separator
        tk.Frame(sidebar, bg=ACCENT, height=1).pack(fill="x", padx=8, pady=(0, 6))

        # Listbox + scrollbar
        lb_frame = tk.Frame(sidebar, bg=BG_CARD)
        lb_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        scrollbar = tk.Scrollbar(lb_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._class_listbox = tk.Listbox(
            lb_frame,
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
        self._class_listbox.pack(fill="both", expand=True)
        scrollbar.configure(command=self._class_listbox.yview)

        self._class_listbox.bind("<<ListboxSelect>>", self._on_class_selected)

        # Button bar
        btn_frame = tk.Frame(sidebar, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=6, pady=(4, 8))

        self._new_btn = tk.Button(
            btn_frame,
            text="+ New Class",
            font=FONT_BOLD,
            bg=GREEN,
            fg="white",
            activebackground="#66BB6A",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._on_new_class,
        )
        self._new_btn.pack(fill="x", pady=(0, 4))

        self._del_btn = tk.Button(
            btn_frame,
            text="Delete",
            font=FONT,
            bg=BG_INPUT,
            fg=RED_SOFT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._on_delete_class,
        )
        self._del_btn.pack(fill="x")

        # Import / Export — two rows below New / Delete.
        io_row1 = tk.Frame(btn_frame, bg=BG_CARD)
        io_row1.pack(fill="x", pady=(6, 0))

        self._export_btn = tk.Button(
            io_row1,
            text="Export",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._on_export_class,
        )
        self._export_btn.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self._import_btn = tk.Button(
            io_row1,
            text="Import",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._on_import_class,
        )
        self._import_btn.pack(side="left", expand=True, fill="x", padx=(2, 0))

        io_row2 = tk.Frame(btn_frame, bg=BG_CARD)
        io_row2.pack(fill="x", pady=(4, 0))

        self._export_all_btn = tk.Button(
            io_row2,
            text="Export All",
            font=FONT_SMALL,
            bg=BG_INPUT,
            fg=FG_DIM,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._on_export_all,
        )
        self._export_all_btn.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self._inspect_btn = tk.Button(
            io_row2,
            text="Inspect",
            font=FONT_SMALL,
            bg=BG_INPUT,
            fg=FG_DIM,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._on_inspect_bundle,
        )
        self._inspect_btn.pack(side="left", expand=True, fill="x", padx=(2, 0))

        self._paned.add(sidebar, minsize=180, width=200)
        self._populate_sidebar()

    # ---- Content area ------------------------------------------------------

    def _build_content(self) -> None:
        content = tk.Frame(self._paned, bg=BG_DARK)

        # ---- Tab bar -------------------------------------------------------
        self._tab_bar = tk.Frame(content, bg=BG_DARK)
        self._tab_bar.pack(fill="x", padx=8, pady=(8, 0))

        self._tab_buttons: Dict[str, tk.Button] = {}
        self._active_tab: Optional[str] = None

        for tab_id, label in [("skills", "  Skills  "), ("combos", "  Combos  ")]:
            btn = tk.Button(
                self._tab_bar,
                text=label,
                font=FONT,
                bg=BG_CARD,
                fg=FG_TEXT,
                activebackground=ACCENT,
                activeforeground="#FFF",
                relief="flat",
                bd=0,
                padx=16,
                pady=6,
                cursor="hand2",
                command=lambda tid=tab_id: self._switch_tab(tid),
            )
            btn.pack(side="left", padx=(0, 2))
            self._tab_buttons[tab_id] = btn

        # Separator under tabs
        tk.Frame(content, bg=ACCENT, height=1).pack(fill="x", padx=8, pady=(4, 0))

        # ---- Tab container --------------------------------------------------
        self._tab_container = tk.Frame(content, bg=BG_DARK)
        self._tab_container.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        # Placeholder (shown when no class selected)
        self._placeholder = tk.Label(
            self._tab_container,
            text="Select a class from the sidebar, or create a new one",
            font=FONT,
            fg=FG_DIM,
            bg=BG_DARK,
            anchor="center",
        )

        # Create sub-editors (lazy import to break circular deps / allow
        # them to be created after this file)
        self._skill_editor: Any = None
        self._combo_editor: Any = None
        self._tabs: Dict[str, Any] = {}

        try:
            from src.editor.skill_editor import SkillEditor  # type: ignore

            self._skill_editor = SkillEditor(
                self._tab_container,
                on_change=self._mark_dirty,
                on_id_renamed=self._on_skill_id_renamed,
            )
            self._tabs["skills"] = self._skill_editor.frame
        except Exception as exc:  # pragma: no cover
            logger.warning("SkillEditor not available yet: %s", exc)
            fallback = tk.Frame(self._tab_container, bg=BG_DARK)
            tk.Label(
                fallback,
                text="(Skill editor not yet implemented)",
                font=FONT,
                fg=FG_DIM,
                bg=BG_DARK,
            ).pack(expand=True)
            self._tabs["skills"] = fallback

        try:
            from src.editor.combo_editor import ComboEditor  # type: ignore

            self._combo_editor = ComboEditor(
                self._tab_container,
                get_skills=lambda: (
                    self._skill_editor.get_skills()
                    if self._skill_editor is not None
                    and hasattr(self._skill_editor, "get_skills")
                    else {}
                ),
                on_change=self._mark_dirty,
            )
            self._tabs["combos"] = self._combo_editor.frame
        except Exception as exc:  # pragma: no cover
            logger.warning("ComboEditor not available yet: %s", exc)
            fallback = tk.Frame(self._tab_container, bg=BG_DARK)
            tk.Label(
                fallback,
                text="(Combo editor not yet implemented)",
                font=FONT,
                fg=FG_DIM,
                bg=BG_DARK,
            ).pack(expand=True)
            self._tabs["combos"] = fallback

        # Show placeholder by default (no class selected)
        self._placeholder.pack(fill="both", expand=True)

        # ---- Bottom bar (status + save) ------------------------------------
        sep = tk.Frame(content, bg=ACCENT, height=1)
        sep.pack(fill="x", padx=8, pady=(6, 0))

        bottom = tk.Frame(content, bg=BG_DARK)
        bottom.pack(fill="x", padx=8, pady=(6, 8))

        self._status_label = tk.Label(
            bottom,
            text="",
            font=FONT_SMALL,
            fg=GOLD,
            bg=BG_DARK,
            anchor="w",
        )
        self._status_label.pack(side="left", padx=(4, 0))

        self._save_btn = tk.Button(
            bottom,
            text="\U0001f4be  Save Class",
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
            command=self._on_save_click,
        )
        self._save_btn.pack(side="right")

        self._paned.add(content, minsize=400)

        # Default tab
        self._switch_tab("skills")

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _switch_tab(self, tab_id: str) -> None:
        if self._active_tab == tab_id:
            return

        # Hide previous tab frame
        if self._active_tab and self._active_tab in self._tabs:
            self._tabs[self._active_tab].pack_forget()
            self._tab_buttons[self._active_tab].configure(bg=BG_CARD, fg=FG_TEXT)

        # Hide placeholder if a class is selected
        if self._current_key is not None:
            self._placeholder.pack_forget()
            self._tabs[tab_id].pack(fill="both", expand=True)
        else:
            # No class selected — keep placeholder visible, still highlight tab
            if self._active_tab and self._active_tab in self._tabs:
                pass  # placeholder already showing
            self._placeholder.pack(fill="both", expand=True)

        self._tab_buttons[tab_id].configure(bg=ACCENT, fg="#FFF")
        self._active_tab = tab_id

    # ------------------------------------------------------------------
    # Sidebar management
    # ------------------------------------------------------------------

    def _populate_sidebar(self) -> None:
        """Rebuild the sidebar listbox from ``self._configs``."""
        self._class_listbox.delete(0, "end")
        self._sidebar_keys = sorted(
            self._configs.keys(), key=lambda k: (k[0].lower(), k[1].lower())
        )

        for class_name, spec_name in self._sidebar_keys:
            self._class_listbox.insert("end", f"{class_name} \u2014 {spec_name}")

        # Restore selection if current key still exists
        if self._current_key and self._current_key in self._sidebar_keys:
            idx = self._sidebar_keys.index(self._current_key)
            self._class_listbox.selection_set(idx)
            self._class_listbox.see(idx)

    def _select_sidebar_key(self, key: Tuple[str, str]) -> None:
        """Programmatically select a sidebar entry by key."""
        if key in self._sidebar_keys:
            idx = self._sidebar_keys.index(key)
            self._class_listbox.selection_clear(0, "end")
            self._class_listbox.selection_set(idx)
            self._class_listbox.see(idx)
            self._current_key = key

    # ------------------------------------------------------------------
    # Class selection
    # ------------------------------------------------------------------

    def _on_class_selected(self, event: tk.Event) -> None:
        sel = self._class_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._sidebar_keys):
            return

        new_key = self._sidebar_keys[idx]

        # Same class already selected — nothing to do
        if new_key == self._current_key:
            return

        # Prompt for unsaved changes
        if self._dirty and self._current_key is not None:
            old_cls, old_spec = self._current_key
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to {old_cls} \u2014 {old_spec}?",
                parent=self.window,
            )
            if answer is True:
                self._on_save_click()
            elif answer is None:
                # Cancel — restore previous selection
                self._select_sidebar_key(self._current_key)
                return
            # answer is False → discard

        self._current_key = new_key
        self._load_current_class()

    def _load_current_class(self) -> None:
        """Load the currently-selected class data into both editors."""
        if self._current_key is None:
            return

        key = self._current_key
        config = copy.deepcopy(self._configs[key])
        class_name, spec_name = key

        # Merge all skill sections into one dict for the skill editor
        skills: Dict[str, Any] = {}
        for section in _SKILL_SECTIONS:
            section_data = config.get(section, {})
            if isinstance(section_data, dict):
                skills.update(section_data)

        # Load into editors
        if self._skill_editor is not None and hasattr(self._skill_editor, "load"):
            try:
                self._skill_editor.load(skills, class_name, spec_name)
            except Exception as exc:
                logger.error("SkillEditor.load failed: %s", exc)

        if self._combo_editor is not None and hasattr(self._combo_editor, "load"):
            try:
                self._combo_editor.load(config, class_name, spec_name)
            except Exception as exc:
                logger.error("ComboEditor.load failed: %s", exc)

        # Reset dirty flag and show content
        self._dirty = False
        self._update_status()

        # Make sure the placeholder is hidden and the active tab is shown
        self._placeholder.pack_forget()
        if self._active_tab and self._active_tab in self._tabs:
            self._tabs[self._active_tab].pack_forget()
            self._tabs[self._active_tab].pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # New class dialog
    # ------------------------------------------------------------------

    def _on_new_class(self) -> None:
        dlg = tk.Toplevel(self.window)
        dlg.title("New Class")
        dlg.configure(bg=BG_DARK)
        dlg.transient(self.window)
        dlg.grab_set()
        dlg.resizable(False, False)

        # Centre on editor window
        dlg.update_idletasks()
        dlg.geometry(
            f"360x220+{self.window.winfo_x() + 200}+{self.window.winfo_y() + 150}"
        )

        tk.Label(
            dlg, text="Create New Class", font=FONT_HEADING, fg=GOLD, bg=BG_DARK
        ).pack(padx=16, pady=(14, 10))

        # Class name
        row1 = tk.Frame(dlg, bg=BG_DARK)
        row1.pack(fill="x", padx=16, pady=(0, 6))

        tk.Label(row1, text="Class Name:", font=FONT, fg=FG_TEXT, bg=BG_DARK).pack(
            side="left"
        )
        name_var = tk.StringVar()
        name_entry = tk.Entry(
            row1,
            textvariable=name_var,
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=0,
        )
        name_entry.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)
        name_entry.focus_set()

        # Spec
        row2 = tk.Frame(dlg, bg=BG_DARK)
        row2.pack(fill="x", padx=16, pady=(0, 10))

        tk.Label(row2, text="Spec:", font=FONT, fg=FG_TEXT, bg=BG_DARK).pack(
            side="left"
        )

        spec_var = tk.StringVar(value="Awakening")
        spec_options = ["Awakening", "Succession"]
        spec_menu = tk.OptionMenu(row2, spec_var, *spec_options)
        spec_menu.configure(
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="white",
            highlightthickness=0,
            relief="flat",
            bd=0,
        )
        spec_menu["menu"].configure(
            font=FONT, bg=BG_INPUT, fg=FG_TEXT, activebackground=ACCENT
        )
        spec_menu.pack(side="left", padx=(8, 0))

        # Error label
        err_label = tk.Label(dlg, text="", font=FONT_SMALL, fg=RED_SOFT, bg=BG_DARK)
        err_label.pack(padx=16)

        # Buttons
        btn_row = tk.Frame(dlg, bg=BG_DARK)
        btn_row.pack(fill="x", padx=16, pady=(4, 14))

        def _do_create() -> None:
            cls_name = name_var.get().strip()
            spc_name = spec_var.get().strip()

            if not cls_name:
                err_label.configure(text="Class name cannot be empty.")
                return

            if (cls_name, spc_name) in self._configs:
                err_label.configure(
                    text=f"{cls_name} \u2014 {spc_name} already exists."
                )
                return

            # Build skeleton config
            data: Dict[str, Any] = {
                "class": cls_name,
                "spec": spc_name,
                "skills": {},
                "pve_combos": {},
                "pvp_combos": {},
                "movement_combos": {},
                "skill_addons": {"pve": []},
                "locked_skills": [],
                "hotbar_skills": [],
                "core_skill": {"recommended": "", "effect": "", "reason": ""},
            }

            # Persist to disk immediately
            try:
                self.loader.save_class_config(cls_name, spc_name, data)
            except Exception as exc:
                logger.error("Failed to save new class: %s", exc)
                err_label.configure(text=f"Save error: {exc}")
                return

            # Update in-memory state
            self._configs[(cls_name, spc_name)] = data
            new_key = (cls_name, spc_name)

            self._populate_sidebar()
            self._select_sidebar_key(new_key)
            self._current_key = new_key
            self._load_current_class()

            dlg.destroy()

            # Notify main app (refresh tray menu, etc.)
            if self.on_save:
                try:
                    self.on_save()
                except Exception as exc:
                    logger.error("on_save callback failed: %s", exc)

        def _do_cancel() -> None:
            dlg.destroy()

        tk.Button(
            btn_row,
            text="Create",
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
            command=_do_create,
        ).pack(side="right", padx=(6, 0))

        tk.Button(
            btn_row,
            text="Cancel",
            font=FONT,
            bg=BG_CARD,
            fg=FG_TEXT,
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=_do_cancel,
        ).pack(side="right")

        # Bind Enter to create
        dlg.bind("<Return>", lambda e: _do_create())
        dlg.bind("<Escape>", lambda e: _do_cancel())

    # ------------------------------------------------------------------
    # Delete class
    # ------------------------------------------------------------------

    def _on_delete_class(self) -> None:
        if self._current_key is None:
            messagebox.showinfo(
                "No Selection",
                "Select a class to delete first.",
                parent=self.window,
            )
            return

        class_name, spec_name = self._current_key
        confirmed = messagebox.askyesno(
            "Delete Class",
            f"Permanently delete {class_name} \u2014 {spec_name}?\n\n"
            "This will remove the YAML file from disk.",
            parent=self.window,
        )
        if not confirmed:
            return

        # Delete on disk
        try:
            self.loader.delete_class_config(class_name, spec_name)
        except Exception as exc:
            logger.error("Failed to delete class config: %s", exc)
            messagebox.showerror(
                "Delete Error", f"Could not delete: {exc}", parent=self.window
            )
            return

        # Remove from in-memory state
        self._configs.pop(self._current_key, None)
        self._current_key = None
        self._dirty = False

        # Refresh sidebar
        self._populate_sidebar()

        # Clear editors
        self._clear_editors()

        # Show placeholder
        if self._active_tab and self._active_tab in self._tabs:
            self._tabs[self._active_tab].pack_forget()
        self._placeholder.pack(fill="both", expand=True)

        self._update_status()

        # Notify main app
        if self.on_save:
            try:
                self.on_save()
            except Exception as exc:
                logger.error("on_save callback failed: %s", exc)

    def _clear_editors(self) -> None:
        """Reset both sub-editors to an empty / unloaded state."""
        if self._skill_editor is not None and hasattr(self._skill_editor, "clear"):
            try:
                self._skill_editor.clear()
            except Exception:
                pass
        if self._combo_editor is not None and hasattr(self._combo_editor, "clear"):
            try:
                self._combo_editor.clear()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def _on_export_class(self) -> None:
        """Export the currently selected class as a .bdt bundle."""
        from tkinter import filedialog
        from src.editor.portability import (
            BDT_EXTENSION,
            write_bundle_to_file,
        )

        if self._current_key is None:
            messagebox.showinfo(
                "Export Class",
                "Select a class to export first.",
                parent=self.window,
            )
            return

        # Make sure the working copy reflects any unsaved edits before we
        # write the bundle out.
        self._collect_current_into_configs()
        class_name, spec_name = self._current_key
        config = self._configs.get(self._current_key, {})

        default_name = (
            f"{class_name}_{spec_name}".lower().replace(" ", "_") + BDT_EXTENSION
        )
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Class",
            defaultextension=BDT_EXTENSION,
            initialfile=default_name,
            filetypes=[("BDO Trainer bundle", f"*{BDT_EXTENSION}"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            written = write_bundle_to_file(path, class_name, spec_name, config)
        except Exception as exc:
            logger.error("Export failed: %s", exc)
            messagebox.showerror(
                "Export Failed", f"Could not export bundle:\n{exc}", parent=self.window,
            )
            return

        messagebox.showinfo(
            "Export Complete",
            f"Exported {class_name} ({spec_name}) to:\n{written}",
            parent=self.window,
        )

    def _collect_current_into_configs(self) -> None:
        """Pull skill + combo edits from the sub-editors into self._configs."""
        if self._current_key is None:
            return
        cfg = self._configs.setdefault(
            self._current_key,
            {
                "class": self._current_key[0],
                "spec": self._current_key[1],
                "skills": {},
                "pve_combos": {},
                "pvp_combos": {},
                "movement_combos": {},
            },
        )
        if self._skill_editor is not None and hasattr(self._skill_editor, "get_skills"):
            try:
                cfg["skills"] = self._skill_editor.get_skills()
            except Exception:
                logger.exception("Could not read skills from editor")
        if self._combo_editor is not None and hasattr(self._combo_editor, "get_combos"):
            try:
                combos = self._combo_editor.get_combos()
                for section, payload in combos.items():
                    cfg[section] = payload
            except Exception:
                logger.exception("Could not read combos from editor")

    def _on_import_class(self) -> None:
        """Open a .bdt file and route the user through the import dialog."""
        from tkinter import filedialog
        from src.editor.portability import (
            BDT_EXTENSION,
            BundleError,
            read_bundle_from_file,
        )

        path = filedialog.askopenfilename(
            parent=self.window,
            title="Import Class Bundle",
            filetypes=[("BDO Trainer bundle", f"*{BDT_EXTENSION}"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            bundle = read_bundle_from_file(path)
        except BundleError as exc:
            messagebox.showerror(
                "Import Failed", str(exc), parent=self.window,
            )
            return
        except Exception as exc:
            logger.exception("Unexpected import error")
            messagebox.showerror(
                "Import Failed",
                f"Could not read bundle:\n{exc}",
                parent=self.window,
            )
            return

        ImportBundleDialog(self.window, self, bundle)

    def _on_export_all(self) -> None:
        """Export every loaded class as a .bdt file into a chosen folder."""
        from tkinter import filedialog
        from src.editor.portability import BDT_EXTENSION, write_bundle_to_file

        # Capture in-memory edits first so the on-disk export reflects them.
        self._collect_current_into_configs()

        keys = sorted(
            self.loader.class_configs.keys(),
            key=lambda k: (k[0].lower(), k[1].lower()),
        )
        if not keys:
            messagebox.showinfo(
                "Export All",
                "No classes are loaded.",
                parent=self.window,
            )
            return

        directory = filedialog.askdirectory(
            parent=self.window,
            title="Export All — Select Output Folder",
            mustexist=True,
        )
        if not directory:
            return

        from pathlib import Path

        out_dir = Path(directory)
        ok_count = 0
        fail_count = 0
        skipped: List[str] = []

        for class_name, spec_name in keys:
            # Use the editor's working copy if it's the active class, else
            # the loader's on-disk copy (which we just refreshed via save).
            if (class_name, spec_name) in self._configs:
                config = self._configs[(class_name, spec_name)]
            else:
                config = self.loader.get_class_config(class_name, spec_name) or {}

            filename = (
                f"{class_name}_{spec_name}".lower().replace(" ", "_") + BDT_EXTENSION
            )
            target = out_dir / filename
            try:
                write_bundle_to_file(target, class_name, spec_name, config)
                ok_count += 1
            except Exception as exc:
                logger.exception("Export failed for %s / %s", class_name, spec_name)
                fail_count += 1
                skipped.append(f"{class_name} ({spec_name}): {exc}")

        msg = f"Exported {ok_count} class(es) to:\n{out_dir}"
        if fail_count:
            msg += f"\n\n{fail_count} skipped:\n" + "\n".join(skipped)
            messagebox.showwarning("Export Partial", msg, parent=self.window)
        else:
            messagebox.showinfo("Export Complete", msg, parent=self.window)

    def _on_inspect_bundle(self) -> None:
        """Open a .bdt file in a read-only inspector — does not import."""
        from tkinter import filedialog
        from src.editor.portability import (
            BDT_EXTENSION,
            BundleError,
            read_bundle_from_file,
        )

        path = filedialog.askopenfilename(
            parent=self.window,
            title="Inspect Class Bundle",
            filetypes=[("BDO Trainer bundle", f"*{BDT_EXTENSION}"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            bundle = read_bundle_from_file(path)
        except BundleError as exc:
            messagebox.showerror("Inspect Failed", str(exc), parent=self.window)
            return
        except Exception as exc:
            logger.exception("Unexpected inspect error")
            messagebox.showerror(
                "Inspect Failed",
                f"Could not read bundle:\n{exc}",
                parent=self.window,
            )
            return

        BundleInspectorDialog(self.window, bundle, source_path=path)

    # ------------------------------------------------------------------
    # Import-apply helpers (called by ImportBundleDialog)
    # ------------------------------------------------------------------

    def apply_imported_class(
        self,
        class_name: str,
        spec_name: str,
        config: Dict[str, Any],
        replace_existing: bool,
    ) -> bool:
        """Persist an imported class to disk and refresh the editor.

        Returns True on success.
        """
        key = (class_name, spec_name)
        existed = key in self.loader.class_configs

        if existed and not replace_existing:
            messagebox.showerror(
                "Import Conflict",
                f"{class_name} ({spec_name}) already exists.",
                parent=self.window,
            )
            return False

        try:
            data = copy.deepcopy(config)
            self.loader.save_class_config(class_name, spec_name, data)
        except Exception as exc:
            logger.exception("Failed to write imported class")
            messagebox.showerror(
                "Import Failed",
                f"Could not write class file:\n{exc}",
                parent=self.window,
            )
            return False

        self._configs[key] = copy.deepcopy(self.loader.get_class_config(class_name, spec_name) or data)
        self._populate_sidebar()
        self._select_sidebar_key(key)
        self._current_key = key
        self._load_current_class()
        self._dirty = False
        self._update_status()

        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed after import")

        return True

    def apply_imported_combos(
        self,
        target_class: str,
        target_spec: str,
        bundle_config: Dict[str, Any],
        selected: List[Tuple[str, str]],
        also_pull_skills: bool,
        rename_conflicts: Dict[Tuple[str, str], str],
    ) -> bool:
        """Merge selected combos (and optionally referenced skills) from a
        bundle into an existing class. ``selected`` is a list of
        ``(section, combo_id)`` pairs from the bundle. ``rename_conflicts``
        provides new combo_ids for combos that would otherwise collide.
        """
        from src.editor.portability import collect_skill_ids_used_by_combo

        target_key = (target_class, target_spec)
        if target_key not in self.loader.class_configs:
            messagebox.showerror(
                "Import Failed",
                f"Target class {target_class} ({target_spec}) is not loaded.",
                parent=self.window,
            )
            return False

        # Take a deep copy of the live class config so partial failure
        # doesn't leave half-merged state on disk.
        target = copy.deepcopy(self.loader.get_class_config(target_class, target_spec) or {})
        target.setdefault("class", target_class)
        target.setdefault("spec", target_spec)

        bundle_skills_section = "skills"
        bundle_skills = (bundle_config.get("skills") or {})
        if not isinstance(bundle_skills, dict):
            bundle_skills = {}

        target_skills = target.setdefault("skills", {})
        if not isinstance(target_skills, dict):
            target_skills = {}
            target["skills"] = target_skills

        added_skills = 0
        added_combos = 0

        for section, combo_id in selected:
            section_data = bundle_config.get(section) or {}
            combo = section_data.get(combo_id)
            if not isinstance(combo, dict):
                continue

            target_section = target.setdefault(section, {})
            if not isinstance(target_section, dict):
                target_section = {}
                target[section] = target_section

            new_id = rename_conflicts.get((section, combo_id), combo_id)
            target_section[new_id] = copy.deepcopy(combo)
            added_combos += 1

            if also_pull_skills:
                for sid in collect_skill_ids_used_by_combo(combo):
                    if sid in target_skills:
                        continue
                    if sid in bundle_skills:
                        target_skills[sid] = copy.deepcopy(bundle_skills[sid])
                        added_skills += 1

        try:
            self.loader.save_class_config(target_class, target_spec, target)
        except Exception as exc:
            logger.exception("Failed to write merged class")
            messagebox.showerror(
                "Import Failed",
                f"Could not write class file:\n{exc}",
                parent=self.window,
            )
            return False

        self._configs[target_key] = copy.deepcopy(target)
        self._current_key = target_key
        self._populate_sidebar()
        self._select_sidebar_key(target_key)
        self._load_current_class()
        self._dirty = False
        self._update_status()

        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed after combo import")

        messagebox.showinfo(
            "Import Complete",
            f"Imported {added_combos} combo(s)"
            + (f" and {added_skills} new skill(s)." if added_skills else "."),
            parent=self.window,
        )
        return True

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save_click(self) -> None:
        if self._current_key is None:
            return

        class_name, spec_name = self._current_key

        # Collect data from editors
        skills: Dict[str, Any] = {}
        if self._skill_editor is not None and hasattr(self._skill_editor, "get_skills"):
            try:
                skills = self._skill_editor.get_skills()
            except Exception as exc:
                logger.error("get_skills failed: %s", exc)

        combos: Dict[str, Any] = {}
        if self._combo_editor is not None and hasattr(self._combo_editor, "get_combos"):
            try:
                combos = self._combo_editor.get_combos()
            except Exception as exc:
                logger.error("get_combos failed: %s", exc)

        # Build config dict
        config = copy.deepcopy(self._configs[self._current_key])

        # Remove old skill section names — we consolidate into "skills"
        for old_section in ("awakening_skills", "rabam_skills", "preawakening_utility"):
            config.pop(old_section, None)

        config["skills"] = skills

        # Merge combo categories (pve_combos, pvp_combos, movement_combos)
        if combos:
            config.update(combos)

        # Persist to disk
        try:
            self.loader.save_class_config(class_name, spec_name, config)
        except Exception as exc:
            logger.error("Failed to save class config: %s", exc)
            messagebox.showerror(
                "Save Error",
                f"Could not save {class_name} \u2014 {spec_name}:\n{exc}",
                parent=self.window,
            )
            return

        # Update in-memory copy
        self._configs[self._current_key] = config

        self._dirty = False
        self._update_status()

        logger.info("Saved class config: %s / %s", class_name, spec_name)

        # Notify main app
        if self.on_save:
            try:
                self.on_save()
            except Exception as exc:
                logger.error("on_save callback failed: %s", exc)

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        """Called by sub-editors when data changes."""
        self._dirty = True
        self._update_status()

    def _on_skill_id_renamed(self, old_id: str, new_id: str) -> None:
        """Propagate a skill ID rename into the combo editor's step references."""
        if self._combo_editor is not None and hasattr(
            self._combo_editor, "rename_skill_reference"
        ):
            try:
                self._combo_editor.rename_skill_reference(old_id, new_id)
            except Exception:
                logger.exception("rename_skill_reference failed")

    def _update_status(self) -> None:
        """Refresh the status label to reflect the current dirty state."""
        if self._dirty:
            self._status_label.configure(text="\u25cf  Unsaved changes", fg=GOLD)
        else:
            self._status_label.configure(text="", fg=GOLD)

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        if self._dirty and self._current_key is not None:
            cls_name, spec_name = self._current_key
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to {cls_name} \u2014 {spec_name} before closing?",
                parent=self.window,
            )
            if answer is True:
                self._on_save_click()
            elif answer is None:
                return  # Cancel — don't close

        self.window.destroy()
        EditorWindow._instance = None


# ===========================================================================
# Import-bundle dialog
# ===========================================================================
class ImportBundleDialog:
    """Modal that walks the user through importing a .bdt bundle.

    Two modes:

    1. **Whole class** — write the bundle as a new class file. If the
       (class, spec) already exists, prompt for replace / rename / cancel.
    2. **Merge combos** — pick specific combos from the bundle and merge
       them into an existing loaded class. The user can also pull in any
       skills referenced by those combos that the target doesn't have yet.
    """

    def __init__(
        self,
        parent: tk.Toplevel,
        editor: "EditorWindow",
        bundle: Dict[str, Any],
    ) -> None:
        from src.editor.portability import (
            collect_skill_ids_used_by_combo,
            list_combos_in_bundle,
        )

        self.editor = editor
        self.bundle = bundle
        self.bundle_class = bundle.get("class_name", "?")
        self.bundle_spec = bundle.get("spec_name", "?")
        self.bundle_config = bundle.get("config") or {}

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Import Class Bundle")
        self.dlg.configure(bg=BG_DARK)
        self.dlg.transient(parent)
        self.dlg.grab_set()
        self.dlg.geometry("520x600")
        _force_dialog_to_front(self.dlg)

        # Header
        tk.Label(
            self.dlg,
            text=f"Importing: {self.bundle_class} ({self.bundle_spec})",
            font=FONT_HEADING,
            fg=GOLD,
            bg=BG_DARK,
        ).pack(anchor="w", padx=14, pady=(14, 2))

        exported_at = bundle.get("exported_at", "")
        tk.Label(
            self.dlg,
            text=f"Exported at: {exported_at}",
            font=FONT_SMALL,
            fg=FG_DIM,
            bg=BG_DARK,
        ).pack(anchor="w", padx=14)

        # Mode picker
        self.mode_var = tk.StringVar(value="whole")

        mode_frame = tk.Frame(self.dlg, bg=BG_DARK)
        mode_frame.pack(fill="x", padx=14, pady=(12, 4))

        tk.Radiobutton(
            mode_frame,
            text="Import whole class (Skills + all combos)",
            variable=self.mode_var,
            value="whole",
            command=self._on_mode_change,
            bg=BG_DARK,
            fg=FG_TEXT,
            activebackground=BG_DARK,
            activeforeground=FG_TEXT,
            selectcolor=BG_CARD,
            font=FONT,
        ).pack(anchor="w")

        tk.Radiobutton(
            mode_frame,
            text="Merge specific combos into an existing class",
            variable=self.mode_var,
            value="merge",
            command=self._on_mode_change,
            bg=BG_DARK,
            fg=FG_TEXT,
            activebackground=BG_DARK,
            activeforeground=FG_TEXT,
            selectcolor=BG_CARD,
            font=FONT,
        ).pack(anchor="w")

        # ---- Section that changes based on mode ----
        self.body = tk.Frame(self.dlg, bg=BG_DARK)
        self.body.pack(fill="both", expand=True, padx=14, pady=(8, 4))

        # Buttons row
        btns = tk.Frame(self.dlg, bg=BG_DARK)
        btns.pack(fill="x", padx=14, pady=(4, 14))

        self.import_btn = tk.Button(
            btns,
            text="Import",
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
            command=self._on_import,
        )
        self.import_btn.pack(side="right")

        tk.Button(
            btns,
            text="Cancel",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        # Diff preview button — packed on the left so it doesn't compete
        # with Cancel/Import.
        self.preview_btn = tk.Button(
            btns,
            text="Preview Changes",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._on_preview_changes,
        )
        self.preview_btn.pack(side="left")

        # Pre-compute combo-list metadata for the merge mode body.
        self._combos: List[Tuple[str, str, Dict[str, Any]]] = list(
            list_combos_in_bundle(bundle)
        )
        self._missing_by_combo: Dict[Tuple[str, str], List[str]] = {}
        for section, cid, combo in self._combos:
            ids = collect_skill_ids_used_by_combo(combo)
            bundle_skills = self.bundle_config.get("skills") or {}
            self._missing_by_combo[(section, cid)] = [
                sid for sid in sorted(ids) if sid not in bundle_skills
            ]

        # Render initial mode
        self._on_mode_change()

    # --- mode bodies ---------------------------------------------------

    def _on_mode_change(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        if self.mode_var.get() == "whole":
            self._render_whole_class_body()
        else:
            self._render_merge_body()

    def _render_whole_class_body(self) -> None:
        existed = (self.bundle_class, self.bundle_spec) in self.editor.loader.class_configs

        info = (
            f"Will create a new class file for "
            f"{self.bundle_class} ({self.bundle_spec})."
        )
        if existed:
            info = (
                f"⚠  {self.bundle_class} ({self.bundle_spec}) already exists. "
                "Choose how to import."
            )

        tk.Label(
            self.body,
            text=info,
            font=FONT,
            fg=FG_TEXT if not existed else "#E0B973",
            bg=BG_DARK,
            anchor="w",
            justify="left",
            wraplength=480,
        ).pack(fill="x", pady=(0, 6))

        self.whole_action_var = tk.StringVar(
            value="rename" if existed else "create"
        )
        self.whole_class_entry: Optional[tk.Entry] = None
        self.whole_spec_var: Optional[tk.StringVar] = None

        if existed:
            tk.Radiobutton(
                self.body,
                text="Replace existing (overwrites the file)",
                variable=self.whole_action_var,
                value="replace",
                bg=BG_DARK,
                fg=FG_TEXT,
                selectcolor=BG_CARD,
                activebackground=BG_DARK,
                activeforeground=FG_TEXT,
                font=FONT,
            ).pack(anchor="w")

            tk.Radiobutton(
                self.body,
                text="Rename and import as a new class",
                variable=self.whole_action_var,
                value="rename",
                bg=BG_DARK,
                fg=FG_TEXT,
                selectcolor=BG_CARD,
                activebackground=BG_DARK,
                activeforeground=FG_TEXT,
                font=FONT,
            ).pack(anchor="w")

        # Rename inputs (always visible — disabled when replacing)
        rename_box = tk.Frame(self.body, bg=BG_DARK)
        rename_box.pack(fill="x", pady=(8, 4))

        tk.Label(
            rename_box, text="Class name:", font=FONT, fg=FG_DIM, bg=BG_DARK,
        ).grid(row=0, column=0, sticky="w", padx=(20, 8), pady=2)
        self.whole_class_entry = tk.Entry(
            rename_box, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
        )
        self.whole_class_entry.insert(0, self.bundle_class)
        self.whole_class_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        rename_box.columnconfigure(1, weight=1)

        tk.Label(
            rename_box, text="Spec:", font=FONT, fg=FG_DIM, bg=BG_DARK,
        ).grid(row=1, column=0, sticky="w", padx=(20, 8), pady=2)
        self.whole_spec_var = tk.StringVar(value=self.bundle_spec)
        spec_dd = tk.OptionMenu(
            rename_box, self.whole_spec_var, "Awakening", "Succession",
        )
        spec_dd.configure(
            bg=BG_INPUT, fg=FG_TEXT, font=FONT, highlightthickness=0,
            relief="flat", activebackground=ACCENT, activeforeground="#FFF",
        )
        spec_dd["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT)
        spec_dd.grid(row=1, column=1, sticky="w", padx=4, pady=2)

    def _render_merge_body(self) -> None:
        # Target-class picker
        targets_frame = tk.Frame(self.body, bg=BG_DARK)
        targets_frame.pack(fill="x", pady=(0, 6))

        tk.Label(
            targets_frame, text="Target class:", font=FONT, fg=FG_DIM, bg=BG_DARK,
        ).pack(side="left")

        self.target_var = tk.StringVar()
        target_keys = sorted(
            self.editor.loader.class_configs.keys(),
            key=lambda k: (k[0].lower(), k[1].lower()),
        )
        target_labels = [f"{c} — {s}" for c, s in target_keys]
        self._target_keys = target_keys

        if not target_labels:
            target_labels = ["(no classes loaded)"]
            self.target_var.set(target_labels[0])
        else:
            # Default to a same-class match if present, else first.
            same = next(
                (k for k in target_keys if k[0] == self.bundle_class),
                target_keys[0],
            )
            self.target_var.set(f"{same[0]} — {same[1]}")

        target_dd = tk.OptionMenu(targets_frame, self.target_var, *target_labels)
        target_dd.configure(
            bg=BG_INPUT, fg=FG_TEXT, font=FONT, highlightthickness=0,
            relief="flat", activebackground=ACCENT, activeforeground="#FFF",
        )
        target_dd["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT)
        target_dd.pack(side="left", padx=8, fill="x", expand=True)

        # Pull-skills checkbox
        self.pull_skills_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.body,
            text="Also import any skills referenced by these combos that the target is missing",
            variable=self.pull_skills_var,
            bg=BG_DARK,
            fg=FG_TEXT,
            selectcolor=BG_CARD,
            activebackground=BG_DARK,
            activeforeground=FG_TEXT,
            font=FONT_SMALL,
            anchor="w",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(2, 6))

        # Combo list with checkboxes
        list_frame = tk.Frame(self.body, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_frame, bg=BG_CARD, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_CARD)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._combo_vars: Dict[Tuple[str, str], tk.BooleanVar] = {}

        cur_section: Optional[str] = None
        for section, cid, combo in self._combos:
            if section != cur_section:
                cur_section = section
                tk.Label(
                    inner,
                    text=section.replace("_", " ").title(),
                    font=FONT_BOLD,
                    fg=GOLD,
                    bg=BG_CARD,
                    anchor="w",
                ).pack(fill="x", padx=8, pady=(8, 2))

            var = tk.BooleanVar(value=False)
            self._combo_vars[(section, cid)] = var

            row = tk.Frame(inner, bg=BG_CARD)
            row.pack(fill="x", padx=14, pady=1)

            cb = tk.Checkbutton(
                row,
                variable=var,
                bg=BG_CARD,
                fg=FG_TEXT,
                selectcolor=BG_DARK,
                activebackground=BG_CARD,
                activeforeground=FG_TEXT,
            )
            cb.pack(side="left")

            name = combo.get("name") or cid
            tk.Label(
                row, text=f"{name}  ({cid})",
                font=FONT, fg=FG_TEXT, bg=BG_CARD, anchor="w",
            ).pack(side="left", fill="x", expand=True)

            missing = self._missing_by_combo.get((section, cid), [])
            if missing:
                hint = f"⚠ {len(missing)} skill(s) missing from bundle"
                color = "#E0B973"
            else:
                hint = "✓ all skills present"
                color = "#9BC79B"
            tk.Label(
                row, text=hint, font=FONT_SMALL, fg=color, bg=BG_CARD, anchor="e",
            ).pack(side="right")

        if not self._combos:
            tk.Label(
                inner,
                text="(this bundle contains no combos)",
                font=FONT, fg=FG_DIM, bg=BG_CARD,
            ).pack(padx=8, pady=12)

    # --- actions -------------------------------------------------------

    def _on_cancel(self) -> None:
        self.dlg.destroy()

    def _on_import(self) -> None:
        if self.mode_var.get() == "whole":
            self._do_whole_import()
        else:
            self._do_merge_import()

    def _on_preview_changes(self) -> None:
        """Show a read-only summary of what the current selection will do."""
        if self.mode_var.get() == "whole":
            lines = self._build_whole_preview_lines()
        else:
            lines = self._build_merge_preview_lines()
        DiffPreviewDialog(self.dlg, lines)

    def _build_whole_preview_lines(self) -> List[Tuple[str, str]]:
        """Return [(category, text)] tuples for the whole-class import preview."""
        from src.editor.portability import COMBO_SECTIONS

        lines: List[Tuple[str, str]] = []
        action = getattr(self, "whole_action_var", tk.StringVar(value="create")).get()
        new_class = self.whole_class_entry.get().strip() if self.whole_class_entry else ""
        new_spec = self.whole_spec_var.get().strip() if self.whole_spec_var else ""

        target_key = (
            (self.bundle_class, self.bundle_spec) if action == "replace"
            else (new_class, new_spec)
        )
        existing = self.editor.loader.get_class_config(*target_key)

        lines.append(("header", f"Target: {target_key[0]} ({target_key[1]})"))
        if existing is None:
            lines.append(("add", "Will create a NEW class file."))
        elif action == "replace":
            lines.append(("warn", "Will REPLACE the existing class file (irreversible)."))
        else:
            lines.append(("warn", "Target name already exists — will overwrite."))

        bundle_skills = self.bundle_config.get("skills") or {}
        lines.append(("info", f"Skills in bundle: {len(bundle_skills)}"))

        for section in COMBO_SECTIONS:
            payload = self.bundle_config.get(section) or {}
            if isinstance(payload, dict) and payload:
                pretty = section.replace("_", " ").title()
                lines.append(("info", f"{pretty}: {len(payload)} combo(s)"))
        return lines

    def _build_merge_preview_lines(self) -> List[Tuple[str, str]]:
        """Return [(category, text)] tuples for the merge-combos preview."""
        from src.editor.portability import collect_skill_ids_used_by_combo

        lines: List[Tuple[str, str]] = []
        if not self._target_keys:
            lines.append(("warn", "No target class loaded — nothing can be merged."))
            return lines

        # Resolve target.
        idx = 0
        label = self.target_var.get()
        for i, (c, s) in enumerate(self._target_keys):
            if f"{c} — {s}" == label:
                idx = i
                break
        target_class, target_spec = self._target_keys[idx]
        target_cfg = self.editor.loader.get_class_config(target_class, target_spec) or {}
        target_skills = target_cfg.get("skills") or {}
        bundle_skills = self.bundle_config.get("skills") or {}

        selected = [k for k, v in self._combo_vars.items() if v.get()]
        lines.append(("header", f"Target: {target_class} ({target_spec})"))
        if not selected:
            lines.append(("warn", "No combos selected."))
            return lines

        # Combos
        combos_to_add: List[str] = []
        combos_to_overwrite: List[str] = []
        for section, cid in selected:
            target_section = target_cfg.get(section) or {}
            pretty = f"{section.replace('_', ' ').title()} → {cid}"
            if cid in target_section:
                combos_to_overwrite.append(pretty)
            else:
                combos_to_add.append(pretty)

        if combos_to_add:
            lines.append(("header", f"Combos to ADD ({len(combos_to_add)})"))
            for c in combos_to_add:
                lines.append(("add", f"  + {c}"))
        if combos_to_overwrite:
            lines.append(("header", f"Combos that would OVERWRITE ({len(combos_to_overwrite)})"))
            lines.append(("warn", "  (you'll be prompted to rename each)"))
            for c in combos_to_overwrite:
                lines.append(("warn", f"  ⚠ {c}"))

        # Skills (only if pull-skills is enabled)
        if self.pull_skills_var.get():
            new_skills: List[str] = []
            missing_from_bundle: List[Tuple[str, str]] = []
            for section, cid in selected:
                payload = self.bundle_config.get(section) or {}
                combo = payload.get(cid)
                if not isinstance(combo, dict):
                    continue
                for sid in sorted(collect_skill_ids_used_by_combo(combo)):
                    if sid in target_skills:
                        continue
                    if sid in bundle_skills and sid not in new_skills:
                        new_skills.append(sid)
                    elif sid not in bundle_skills:
                        missing_from_bundle.append((cid, sid))

            if new_skills:
                lines.append(("header", f"Skills to ADD ({len(new_skills)})"))
                for sid in new_skills:
                    name = bundle_skills.get(sid, {}).get("name", sid)
                    lines.append(("add", f"  + {name}  ({sid})"))
            if missing_from_bundle:
                lines.append(("header",
                              f"⚠ Skill references with no definition in bundle ({len(missing_from_bundle)})"))
                for cid, sid in missing_from_bundle:
                    lines.append(("warn", f"  combo '{cid}' references '{sid}'"))
        else:
            lines.append(("info",
                          "Skill pull-in is disabled — no skill changes will be made."))

        return lines

    def _do_whole_import(self) -> None:
        action = getattr(self, "whole_action_var", tk.StringVar(value="create")).get()
        new_class = (
            self.whole_class_entry.get().strip() if self.whole_class_entry else ""
        )
        new_spec = (
            self.whole_spec_var.get().strip() if self.whole_spec_var else ""
        )
        if not new_class or not new_spec:
            messagebox.showwarning(
                "Missing Info",
                "Class name and spec are required.",
                parent=self.dlg,
            )
            return

        replace_existing = False
        if action == "replace":
            new_class = self.bundle_class
            new_spec = self.bundle_spec
            replace_existing = True
        else:
            # Renaming: if the target also collides, ask before overwriting.
            target_key = (new_class, new_spec)
            if target_key in self.editor.loader.class_configs:
                if not messagebox.askyesno(
                    "Overwrite Existing",
                    f"{new_class} ({new_spec}) already exists. Overwrite it?",
                    parent=self.dlg,
                ):
                    return
                replace_existing = True

        ok = self.editor.apply_imported_class(
            new_class, new_spec, self.bundle_config, replace_existing
        )
        if ok:
            self.dlg.destroy()

    def _do_merge_import(self) -> None:
        if not self._target_keys:
            messagebox.showwarning(
                "No Target",
                "There are no loaded classes to merge into. "
                "Import a class first.",
                parent=self.dlg,
            )
            return

        # Resolve picked target.
        idx = 0
        label = self.target_var.get()
        for i, (c, s) in enumerate(self._target_keys):
            if f"{c} — {s}" == label:
                idx = i
                break
        target_class, target_spec = self._target_keys[idx]

        selected = [k for k, v in self._combo_vars.items() if v.get()]
        if not selected:
            messagebox.showinfo(
                "No Combos Selected",
                "Tick at least one combo to import.",
                parent=self.dlg,
            )
            return

        # Detect combo_id collisions in the target class and ask the user
        # how to resolve each one.
        target_cfg = self.editor.loader.get_class_config(target_class, target_spec) or {}
        rename_conflicts: Dict[Tuple[str, str], str] = {}
        for section, cid in selected:
            existing_section = target_cfg.get(section) or {}
            if cid in existing_section:
                from tkinter import simpledialog
                new_id = simpledialog.askstring(
                    "Combo ID Conflict",
                    f"'{cid}' already exists in {section} of "
                    f"{target_class} ({target_spec}).\n\n"
                    "Enter a new combo ID (or leave blank to overwrite):",
                    parent=self.dlg,
                )
                if new_id is None:
                    return  # user cancelled
                new_id = new_id.strip()
                if new_id and new_id != cid:
                    rename_conflicts[(section, cid)] = new_id

        ok = self.editor.apply_imported_combos(
            target_class,
            target_spec,
            self.bundle_config,
            selected,
            also_pull_skills=self.pull_skills_var.get(),
            rename_conflicts=rename_conflicts,
        )
        if ok:
            self.dlg.destroy()


# ===========================================================================
# Diff preview dialog
# ===========================================================================
class DiffPreviewDialog:
    """Read-only summary of pending import changes.

    ``lines`` is a list of ``(category, text)`` tuples. ``category`` is one
    of: ``header``, ``add``, ``warn``, ``info``.
    """

    _CATEGORY_COLORS: Dict[str, str] = {
        "header": GOLD,
        "add": "#9BC79B",
        "warn": "#E0B973",
        "info": FG_TEXT,
    }
    _CATEGORY_FONTS: Dict[str, Tuple[str, int, str]] = {
        "header": FONT_BOLD,
        "add": FONT,
        "warn": FONT,
        "info": FONT,
    }

    def __init__(self, parent: tk.Toplevel, lines: List[Tuple[str, str]]) -> None:
        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Preview Changes")
        self.dlg.configure(bg=BG_DARK)
        self.dlg.transient(parent)
        self.dlg.grab_set()
        self.dlg.geometry("520x400")
        _force_dialog_to_front(self.dlg)

        outer = tk.Frame(self.dlg, bg=BG_DARK)
        outer.pack(fill="both", expand=True, padx=14, pady=(14, 4))

        canvas = tk.Canvas(outer, bg=BG_CARD, highlightthickness=0)
        scroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_CARD)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        if not lines:
            tk.Label(
                inner,
                text="(no changes detected)",
                font=FONT,
                fg=FG_DIM,
                bg=BG_CARD,
            ).pack(padx=10, pady=20)

        for category, text in lines:
            color = self._CATEGORY_COLORS.get(category, FG_TEXT)
            font = self._CATEGORY_FONTS.get(category, FONT)
            tk.Label(
                inner,
                text=text,
                font=font,
                fg=color,
                bg=BG_CARD,
                anchor="w",
                justify="left",
                wraplength=480,
            ).pack(fill="x", padx=10, pady=1, anchor="w")

        tk.Button(
            self.dlg,
            text="Close",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self.dlg.destroy,
        ).pack(side="right", padx=14, pady=(4, 14))


# ===========================================================================
# Bundle inspector dialog
# ===========================================================================
class BundleInspectorDialog:
    """Read-only viewer for a .bdt file. Shows class metadata, all combos
    with step counts, all skills with key info, and missing-skill warnings.
    """

    def __init__(
        self,
        parent: tk.Toplevel,
        bundle: Dict[str, Any],
        source_path: str = "",
    ) -> None:
        from src.editor.portability import (
            COMBO_SECTIONS,
            collect_skill_ids_used_by_combo,
            list_combos_in_bundle,
        )

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Inspect Bundle")
        self.dlg.configure(bg=BG_DARK)
        self.dlg.transient(parent)
        self.dlg.grab_set()
        self.dlg.geometry("600x600")
        _force_dialog_to_front(self.dlg)

        cfg = bundle.get("config") or {}
        skills = cfg.get("skills") or {}

        # Header block
        header = tk.Frame(self.dlg, bg=BG_DARK)
        header.pack(fill="x", padx=14, pady=(14, 4))

        tk.Label(
            header,
            text=f"{bundle.get('class_name', '?')}  ({bundle.get('spec_name', '?')})",
            font=FONT_HEADING,
            fg=GOLD,
            bg=BG_DARK,
        ).pack(anchor="w")

        meta_lines = []
        if bundle.get("exported_at"):
            meta_lines.append(f"Exported at: {bundle['exported_at']}")
        if bundle.get("format_version") is not None:
            meta_lines.append(f"Format version: {bundle['format_version']}")
        if source_path:
            meta_lines.append(f"File: {source_path}")
        meta_lines.append(f"Skills defined: {len(skills)}")
        for section in COMBO_SECTIONS:
            payload = cfg.get(section) or {}
            if isinstance(payload, dict) and payload:
                pretty = section.replace("_", " ").title()
                meta_lines.append(f"{pretty}: {len(payload)} combo(s)")

        for line in meta_lines:
            tk.Label(
                header,
                text=line,
                font=FONT_SMALL,
                fg=FG_DIM,
                bg=BG_DARK,
                anchor="w",
            ).pack(anchor="w")

        # Tabs: Combos | Skills
        tabbar = tk.Frame(self.dlg, bg=BG_DARK)
        tabbar.pack(fill="x", padx=14, pady=(8, 0))

        self._tab_buttons: Dict[str, tk.Button] = {}
        self._tab_panes: Dict[str, tk.Frame] = {}

        for tab_id, label in [("combos", "Combos"), ("skills", "Skills")]:
            btn = tk.Button(
                tabbar,
                text=label,
                font=FONT_BOLD,
                bg=BG_CARD,
                fg=FG_TEXT,
                activebackground=ACCENT,
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=12,
                pady=4,
                cursor="hand2",
                command=lambda t=tab_id: self._switch_tab(t),
            )
            btn.pack(side="left", padx=(0, 4))
            self._tab_buttons[tab_id] = btn

        body = tk.Frame(self.dlg, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=14, pady=4)

        # ---- Combos tab ----
        combos_pane = tk.Frame(body, bg=BG_CARD)
        canvas = tk.Canvas(combos_pane, bg=BG_CARD, highlightthickness=0)
        scroll = tk.Scrollbar(combos_pane, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_CARD)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        cur_section: Optional[str] = None
        any_combos = False
        for section, cid, combo in list_combos_in_bundle(bundle):
            any_combos = True
            if section != cur_section:
                cur_section = section
                tk.Label(
                    inner,
                    text=section.replace("_", " ").title(),
                    font=FONT_BOLD,
                    fg=GOLD,
                    bg=BG_CARD,
                    anchor="w",
                ).pack(fill="x", padx=8, pady=(8, 2))

            row = tk.Frame(inner, bg=BG_CARD)
            row.pack(fill="x", padx=14, pady=1)

            name = combo.get("name") or cid
            steps = combo.get("steps") or []
            tk.Label(
                row,
                text=f"{name}  ({cid})  — {len(steps)} step(s)",
                font=FONT,
                fg=FG_TEXT,
                bg=BG_CARD,
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

            ids = collect_skill_ids_used_by_combo(combo)
            missing = [sid for sid in ids if sid not in skills]
            if missing:
                tk.Label(
                    row,
                    text=f"⚠ {len(missing)} missing",
                    font=FONT_SMALL,
                    fg="#E0B973",
                    bg=BG_CARD,
                ).pack(side="right", padx=(0, 4))

        if not any_combos:
            tk.Label(
                inner,
                text="(no combos in bundle)",
                font=FONT,
                fg=FG_DIM,
                bg=BG_CARD,
            ).pack(padx=10, pady=12)

        self._tab_panes["combos"] = combos_pane

        # ---- Skills tab ----
        skills_pane = tk.Frame(body, bg=BG_CARD)
        canvas2 = tk.Canvas(skills_pane, bg=BG_CARD, highlightthickness=0)
        scroll2 = tk.Scrollbar(skills_pane, orient="vertical", command=canvas2.yview)
        inner2 = tk.Frame(canvas2, bg=BG_CARD)
        canvas2.create_window((0, 0), window=inner2, anchor="nw")
        inner2.bind(
            "<Configure>",
            lambda _e: canvas2.configure(scrollregion=canvas2.bbox("all")),
        )
        canvas2.configure(yscrollcommand=scroll2.set)
        scroll2.pack(side="right", fill="y")
        canvas2.pack(side="left", fill="both", expand=True)

        if not skills:
            tk.Label(
                inner2,
                text="(no skills in bundle)",
                font=FONT,
                fg=FG_DIM,
                bg=BG_CARD,
            ).pack(padx=10, pady=12)
        else:
            for sid in sorted(skills.keys(), key=lambda x: x.lower()):
                sk = skills[sid]
                if not isinstance(sk, dict):
                    continue
                row = tk.Frame(inner2, bg=BG_CARD)
                row.pack(fill="x", padx=10, pady=1)

                name = sk.get("name") or sid
                input_text = sk.get("input") or ""
                keys_list = sk.get("keys") or []
                input_display = input_text or " + ".join(keys_list).upper() or "—"

                tk.Label(
                    row,
                    text=f"{name}  ({sid})",
                    font=FONT,
                    fg=FG_TEXT,
                    bg=BG_CARD,
                    anchor="w",
                ).pack(side="left", fill="x", expand=True)
                tk.Label(
                    row,
                    text=input_display,
                    font=FONT_SMALL,
                    fg=FG_DIM,
                    bg=BG_CARD,
                ).pack(side="right")

        self._tab_panes["skills"] = skills_pane

        # Activate default tab
        self._switch_tab("combos")

        # Bottom row — Close
        tk.Button(
            self.dlg,
            text="Close",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self.dlg.destroy,
        ).pack(side="right", padx=14, pady=(4, 14))

    def _switch_tab(self, tab_id: str) -> None:
        if tab_id not in self._tab_panes:
            return
        for t_id, pane in self._tab_panes.items():
            pane.pack_forget()
            self._tab_buttons[t_id].configure(bg=BG_CARD, fg=FG_TEXT)
        self._tab_panes[tab_id].pack(fill="both", expand=True)
        self._tab_buttons[tab_id].configure(bg=ACCENT, fg="white")
