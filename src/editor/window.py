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
# Theme constants (shared with settings_gui)
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
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 9)

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
                self._tab_container, on_change=self._mark_dirty
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
