"""Combo Editor — main window.

Edits combo bundles (loadout + combos) for classes that already exist.
A class can have multiple bundles; each bundle has its own loadout
(locked / hotbar / core / addons) and combo set.

Sidebar layout::

    Dark Knight — Awakening
        ▸ default            (currently 4 combos)
        ▸ pvp                (currently 2 combos)
        + New Bundle
    Witch — Awakening
        ▸ default
        + New Bundle

Right pane is split: bundle metadata + loadout (top) and the
existing :class:`src.editor.combo_editor.ComboEditor` widget (bottom).
"""

from __future__ import annotations

import copy
import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.editor.theme import (
    ACCENT,
    BG_CARD,
    BG_DARK,
    BG_INPUT,
    FG_DIM,
    FG_TEXT,
    FONT,
    FONT_BOLD,
    FONT_HEADING,
    FONT_SMALL,
    FONT_TITLE,
    GOLD,
    GREEN,
    RED_SOFT,
    force_dialog_to_front,
)

logger = logging.getLogger("bdo_trainer")


SidebarKey = Tuple[str, str, Optional[str]]  # (class, spec, bundle or None)


# ===========================================================================
# Combo Editor window
# ===========================================================================
class ComboEditorWindow:
    """Singleton Toplevel for editing combos (per bundle)."""

    _instance: Optional["ComboEditorWindow"] = None

    @classmethod
    def open(
        cls,
        root: tk.Tk,
        loader: Any,
        on_save: Optional[Callable] = None,
    ) -> "ComboEditorWindow":
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

    def __init__(
        self,
        root: tk.Tk,
        loader: Any,
        on_save: Optional[Callable] = None,
    ) -> None:
        self.root = root
        self.loader = loader
        self.on_save = on_save

        # Currently-selected (class, spec, bundle_id), or None.
        self._current_key: Optional[Tuple[str, str, str]] = None
        # Sidebar entries laid out flat; each entry is one of:
        #   ("header", class, spec)       — non-selectable label
        #   ("bundle", class, spec, bid)  — selectable bundle row
        #   ("new_bundle", class, spec)   — selectable "+ New Bundle" row
        self._sidebar_rows: List[Tuple] = []
        self._dirty = False

        self.window = tk.Toplevel(root)
        self.window.title("BDO Trainer — Combo Editor")
        self.window.configure(bg=BG_DARK)
        self.window.minsize(960, 640)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.window.resizable(True, True)

        self._build_ui()

        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        ww = max(self.window.winfo_width(), 1180)
        wh = max(self.window.winfo_height(), 760)
        self.window.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        title_bar = tk.Frame(self.window, bg=BG_DARK)
        title_bar.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(
            title_bar, text="Combo Editor",
            font=FONT_TITLE, fg=GOLD, bg=BG_DARK,
        ).pack(side="left")
        self._status_label = tk.Label(
            title_bar, text="", font=FONT_SMALL, fg=GOLD, bg=BG_DARK,
        )
        self._status_label.pack(side="right", padx=(0, 8))

        self._paned = tk.PanedWindow(
            self.window, orient="horizontal",
            bg=BG_DARK, sashwidth=2, sashrelief="flat", bd=0,
        )
        self._paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._build_sidebar()
        self._build_content()
        self._show_placeholder()

    def _build_sidebar(self) -> None:
        sidebar = tk.Frame(self._paned, bg=BG_CARD, width=260)
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="Bundles",
            font=FONT_HEADING, fg=GOLD, bg=BG_CARD, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))
        tk.Frame(sidebar, bg=ACCENT, height=1).pack(fill="x", padx=8, pady=(0, 6))

        lb_frame = tk.Frame(sidebar, bg=BG_CARD)
        lb_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        scrollbar = tk.Scrollbar(lb_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self._listbox = tk.Listbox(
            lb_frame,
            bg=BG_INPUT, fg=FG_TEXT, font=FONT,
            selectbackground=ACCENT, selectforeground="white",
            relief="flat", bd=0, highlightthickness=0, activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        self._listbox.pack(fill="both", expand=True)
        scrollbar.configure(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_sidebar_clicked)

        # Bundle action buttons
        actions = tk.Frame(sidebar, bg=BG_CARD)
        actions.pack(fill="x", padx=6, pady=(0, 4))
        for label, cmd in (
            ("Rename Bundle", self._on_rename_bundle),
            ("Delete Bundle", self._on_delete_bundle),
        ):
            tk.Button(
                actions, text=label, font=FONT,
                bg=BG_INPUT, fg=FG_TEXT,
                activebackground=ACCENT, activeforeground="white",
                relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
                command=cmd,
            ).pack(fill="x", pady=2)

        # Bundle import/export/inspect
        bundle = tk.Frame(sidebar, bg=BG_CARD)
        bundle.pack(fill="x", padx=6, pady=(6, 8))
        for label, cmd in (
            ("Export Combo", self._on_export_single_combo),
            ("Export Combos", self._on_export_combos),
            ("Import Combos", self._on_import_combos),
            ("Inspect", self._on_inspect_bundle),
        ):
            tk.Button(
                bundle, text=label, font=FONT,
                bg=BG_INPUT, fg=FG_TEXT,
                activebackground=ACCENT, activeforeground="white",
                relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
                command=cmd,
            ).pack(fill="x", pady=2)

        self._paned.add(sidebar, minsize=240, width=260)
        self._populate_sidebar()

    def _build_content(self) -> None:
        content = tk.Frame(self._paned, bg=BG_DARK)
        self._content = content

        self._placeholder = tk.Label(
            content,
            text="Select a bundle from the sidebar, or click "
                 "“+ New Bundle” under a class.",
            font=FONT, fg=FG_DIM, bg=BG_DARK,
            wraplength=520, justify="center",
        )

        # ---- Top: bundle metadata + loadout ----
        self._meta_pane = tk.Frame(content, bg=BG_CARD)

        meta_inner = tk.Frame(self._meta_pane, bg=BG_CARD)
        meta_inner.pack(fill="x", padx=12, pady=(10, 8))

        # Bundle header (name + description)
        row = tk.Frame(meta_inner, bg=BG_CARD)
        row.pack(fill="x", pady=(0, 4))
        tk.Label(
            row, text="Bundle name:",
            font=FONT, fg=FG_DIM, bg=BG_CARD, width=14, anchor="w",
        ).pack(side="left")
        self._bundle_name_var = tk.StringVar()
        name_entry = tk.Entry(
            row, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
            textvariable=self._bundle_name_var,
        )
        name_entry.pack(side="left", fill="x", expand=True)
        self._bundle_name_var.trace_add("write", lambda *_: self._mark_dirty())

        row2 = tk.Frame(meta_inner, bg=BG_CARD)
        row2.pack(fill="x", pady=(0, 4))
        tk.Label(
            row2, text="Description:",
            font=FONT, fg=FG_DIM, bg=BG_CARD, width=14, anchor="nw",
        ).pack(side="left")
        self._bundle_desc_text = tk.Text(
            row2, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            height=2, wrap="word",
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
        )
        self._bundle_desc_text.pack(side="left", fill="x", expand=True)
        self._bundle_desc_text.bind("<<Modified>>", lambda _e: self._on_desc_modified())

        # Loadout — four mostly-text fields, comma/newline separated.
        load_frame = tk.LabelFrame(
            meta_inner, text=" Loadout ",
            font=FONT_BOLD, fg=GOLD, bg=BG_CARD,
            relief="flat", bd=0, padx=8, pady=4,
        )
        load_frame.pack(fill="x", pady=(6, 0))

        self._loadout_widgets: Dict[str, tk.Text] = {}
        for key, label, hint in (
            ("hotbar_skills", "Hotbar skills", "One per line"),
            ("locked_skills", "Locked skills", "Format: name :: reason (one per line)"),
        ):
            sub = tk.Frame(load_frame, bg=BG_CARD)
            sub.pack(fill="x", pady=2)
            head = tk.Frame(sub, bg=BG_CARD)
            head.pack(fill="x")
            tk.Label(
                head, text=label,
                font=FONT, fg=FG_TEXT, bg=BG_CARD, anchor="w",
            ).pack(side="left")
            tk.Label(
                head, text=hint,
                font=FONT_SMALL, fg=FG_DIM, bg=BG_CARD, anchor="e",
            ).pack(side="right")
            txt = tk.Text(
                sub, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief="flat", bd=0,
                height=3, wrap="word",
                highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
            )
            txt.pack(fill="x")
            txt.bind("<<Modified>>", lambda e, k=key: self._on_loadout_modified(k))
            self._loadout_widgets[key] = txt

        # Core skill — 3 small entries
        core = tk.Frame(load_frame, bg=BG_CARD)
        core.pack(fill="x", pady=(4, 2))
        tk.Label(
            core, text="Core skill",
            font=FONT, fg=FG_TEXT, bg=BG_CARD, width=14, anchor="w",
        ).pack(side="left")
        self._core_recommended_var = tk.StringVar()
        self._core_effect_var = tk.StringVar()
        for label_txt, var in (
            ("Recommended", self._core_recommended_var),
            ("Effect",       self._core_effect_var),
        ):
            sub = tk.Frame(core, bg=BG_CARD)
            sub.pack(side="left", fill="x", expand=True, padx=(2, 2))
            tk.Label(
                sub, text=label_txt,
                font=FONT_SMALL, fg=FG_DIM, bg=BG_CARD, anchor="w",
            ).pack(fill="x")
            tk.Entry(
                sub, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief="flat", bd=0,
                highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
                textvariable=var,
            ).pack(fill="x")
            var.trace_add("write", lambda *_: self._mark_dirty())

        core2 = tk.Frame(load_frame, bg=BG_CARD)
        core2.pack(fill="x", pady=(0, 4))
        tk.Label(
            core2, text="",
            font=FONT, bg=BG_CARD, width=14,
        ).pack(side="left")
        self._core_reason_text = tk.Text(
            core2, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            height=2, wrap="word",
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
        )
        self._core_reason_text.pack(side="left", fill="x", expand=True)
        self._core_reason_text.bind(
            "<<Modified>>", lambda _e: self._on_core_reason_modified()
        )

        # Skill add-ons (PVE) — one entry per line, "skill :: addon_1 :: addon_2"
        addons_frame = tk.Frame(load_frame, bg=BG_CARD)
        addons_frame.pack(fill="x", pady=(2, 4))
        head = tk.Frame(addons_frame, bg=BG_CARD)
        head.pack(fill="x")
        tk.Label(
            head, text="PVE skill add-ons",
            font=FONT, fg=FG_TEXT, bg=BG_CARD, anchor="w",
        ).pack(side="left")
        tk.Label(
            head, text="Format: skill :: addon_1 :: addon_2 (one per line)",
            font=FONT_SMALL, fg=FG_DIM, bg=BG_CARD, anchor="e",
        ).pack(side="right")
        self._addons_text = tk.Text(
            addons_frame, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            height=4, wrap="word",
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
        )
        self._addons_text.pack(fill="x")
        self._addons_text.bind("<<Modified>>", lambda _e: self._on_addons_modified())

        # ---- Bottom: combo editor widget ----
        self._combo_pane = tk.Frame(content, bg=BG_DARK)
        self._combo_editor = None
        try:
            from src.editor.combo_editor import ComboEditor

            self._combo_editor = ComboEditor(
                self._combo_pane,
                get_skills=self._get_skills_for_current_class,
                on_change=self._mark_dirty,
            )
        except Exception:
            logger.exception("ComboEditor failed to load")

        # Bottom: action buttons
        action_row = tk.Frame(content, bg=BG_DARK)

        self._save_btn = tk.Button(
            action_row,
            text="\U0001F4BE  Save Bundle",
            font=FONT_BOLD,
            bg=GREEN, fg="white",
            activebackground="#9CA600", activeforeground="white",
            relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
            command=self._on_save_click,
        )
        self._save_btn.pack(side="right")

        self._new_combo_btn = tk.Button(
            action_row,
            text="+ New Combo",
            font=FONT,
            bg=BG_INPUT, fg=FG_TEXT,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
            command=self._on_new_combo,
        )
        self._new_combo_btn.pack(side="left")

        self._action_row = action_row
        self._content_frame = content
        self._paned.add(content, minsize=560)

    def _show_placeholder(self) -> None:
        for w in (self._meta_pane, self._combo_pane, self._action_row):
            try:
                w.pack_forget()
            except tk.TclError:
                pass
        self._placeholder.pack(fill="both", expand=True, padx=12, pady=12)

    def _show_editor(self) -> None:
        self._placeholder.pack_forget()
        self._meta_pane.pack(fill="x", padx=8, pady=(8, 4))
        self._combo_pane.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._action_row.pack(fill="x", padx=8, pady=(0, 8))
        if self._combo_editor is not None:
            self._combo_editor.frame.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _populate_sidebar(self) -> None:
        self._listbox.delete(0, "end")
        self._sidebar_rows = []

        for class_name, spec_name in self.loader.classes.keys():
            self._sidebar_rows.append(("header", class_name, spec_name))
            self._listbox.insert("end", f"{class_name} — {spec_name}")
            self._listbox.itemconfigure("end", fg=GOLD)

            for bid, meta in self.loader.bundles.bundles_for_class(
                class_name, spec_name
            ):
                count = sum(
                    1 for _ in self.loader.bundles.iter_combos_for_bundle(
                        class_name, spec_name, bid
                    )
                )
                pretty = meta.get("name") or bid
                self._sidebar_rows.append(("bundle", class_name, spec_name, bid))
                self._listbox.insert("end", f"    {pretty}  ({count})")

            self._sidebar_rows.append(("new_bundle", class_name, spec_name))
            self._listbox.insert("end", "    + New Bundle")
            self._listbox.itemconfigure("end", fg=GREEN)

        # Restore selection if possible.
        if self._current_key is not None:
            for idx, row in enumerate(self._sidebar_rows):
                if row[0] == "bundle" and row[1:] == (
                    self._current_key[0], self._current_key[1], self._current_key[2]
                ):
                    self._listbox.selection_set(idx)
                    self._listbox.see(idx)
                    break

    def _on_sidebar_clicked(self, _event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._sidebar_rows):
            return
        row = self._sidebar_rows[idx]
        kind = row[0]

        if kind == "header":
            # Headers are not selectable; restore the last good selection.
            self._listbox.selection_clear(0, "end")
            self._reselect_current()
            return

        if kind == "new_bundle":
            class_name, spec_name = row[1], row[2]
            self._listbox.selection_clear(0, "end")
            self._reselect_current()
            self._on_new_bundle(class_name, spec_name)
            return

        # kind == "bundle"
        class_name, spec_name, bundle_id = row[1], row[2], row[3]
        new_key = (class_name, spec_name, bundle_id)
        if new_key == self._current_key:
            return
        if self._dirty and self._current_key is not None:
            old = self._current_key
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to {old[0]} — {old[1]} / {old[2]}?",
                parent=self.window,
            )
            if answer is True:
                self._on_save_click()
            elif answer is None:
                self._reselect_current()
                return
        self._current_key = new_key
        self._load_current_bundle()

    def _reselect_current(self) -> None:
        if self._current_key is None:
            return
        for idx, row in enumerate(self._sidebar_rows):
            if row[0] == "bundle" and row[1:] == (
                self._current_key[0], self._current_key[1], self._current_key[2]
            ):
                self._listbox.selection_set(idx)
                self._listbox.see(idx)
                break

    # ------------------------------------------------------------------
    # Loading the right pane
    # ------------------------------------------------------------------
    def _load_current_bundle(self) -> None:
        if self._current_key is None:
            self._show_placeholder()
            return

        class_name, spec_name, bundle_id = self._current_key
        meta = self.loader.bundles.get_bundle(class_name, spec_name, bundle_id) or {}

        # --- Bundle metadata fields ---
        self._set_var(self._bundle_name_var, meta.get("name") or bundle_id)
        self._set_text(self._bundle_desc_text, meta.get("description") or "")

        # Loadout fields
        self._set_text(
            self._loadout_widgets["hotbar_skills"],
            "\n".join(meta.get("hotbar_skills") or []),
        )
        locked_lines = []
        for entry in meta.get("locked_skills") or []:
            if isinstance(entry, dict):
                name = entry.get("name", "")
                reason = entry.get("reason", "")
                locked_lines.append(f"{name} :: {reason}" if reason else name)
            else:
                locked_lines.append(str(entry))
        self._set_text(self._loadout_widgets["locked_skills"], "\n".join(locked_lines))

        core = meta.get("core_skill") or {}
        self._set_var(self._core_recommended_var, core.get("recommended", ""))
        self._set_var(self._core_effect_var, core.get("effect", ""))
        self._set_text(self._core_reason_text, core.get("reason", ""))

        addons = (meta.get("skill_addons") or {}).get("pve") or []
        addon_lines = []
        for entry in addons:
            if isinstance(entry, dict):
                addon_lines.append(
                    f"{entry.get('skill', '')} :: {entry.get('addon_1', '')} :: {entry.get('addon_2', '')}"
                )
        self._set_text(self._addons_text, "\n".join(addon_lines))

        # --- Combo editor widget ---
        combos_by_section: Dict[str, Dict[str, Any]] = {
            "pve_combos": {}, "pvp_combos": {}, "movement_combos": {},
        }
        for cid, combo in self.loader.bundles.iter_combos_for_bundle(
            class_name, spec_name, bundle_id
        ):
            section_key = f"{combo.get('category', 'pve')}_combos"
            combos_by_section.setdefault(section_key, {})[cid] = copy.deepcopy(combo)
        cfg_for_widget = {
            "class": class_name,
            "spec": spec_name,
            **combos_by_section,
        }
        if self._combo_editor is not None:
            try:
                self._combo_editor.load(cfg_for_widget, class_name, spec_name)
            except Exception:
                logger.exception("ComboEditor.load failed")

        self._show_editor()
        self._dirty = False
        self._update_status()

    def _get_skills_for_current_class(self) -> Dict[str, Dict[str, Any]]:
        if self._current_key is None:
            return {}
        return self.loader.classes.get_skills(self._current_key[0], self._current_key[1])

    # ------------------------------------------------------------------
    # Helpers — set widget values without firing dirty
    # ------------------------------------------------------------------
    def _set_var(self, var: tk.StringVar, value: str) -> None:
        self._suspend_dirty = True
        try:
            var.set(value)
        finally:
            self._suspend_dirty = False

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.edit_modified(False)
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.edit_modified(False)

    _suspend_dirty: bool = False

    def _on_desc_modified(self) -> None:
        if self._bundle_desc_text.edit_modified():
            self._bundle_desc_text.edit_modified(False)
            if not self._suspend_dirty:
                self._mark_dirty()

    def _on_loadout_modified(self, key: str) -> None:
        widget = self._loadout_widgets[key]
        if widget.edit_modified():
            widget.edit_modified(False)
            if not self._suspend_dirty:
                self._mark_dirty()

    def _on_core_reason_modified(self) -> None:
        if self._core_reason_text.edit_modified():
            self._core_reason_text.edit_modified(False)
            if not self._suspend_dirty:
                self._mark_dirty()

    def _on_addons_modified(self) -> None:
        if self._addons_text.edit_modified():
            self._addons_text.edit_modified(False)
            if not self._suspend_dirty:
                self._mark_dirty()

    # ------------------------------------------------------------------
    # Bundle CRUD
    # ------------------------------------------------------------------
    def _on_new_bundle(self, class_name: str, spec_name: str) -> None:
        new_id = simpledialog.askstring(
            "New Bundle",
            f"Bundle ID for {class_name} ({spec_name}):\n"
            "(lowercase, letters / digits / underscore)",
            parent=self.window,
        )
        if not new_id:
            return
        new_id = new_id.strip().lower().replace(" ", "_")
        new_id = "".join(c for c in new_id if c.isalnum() or c == "_")
        if not new_id:
            messagebox.showwarning(
                "Invalid ID", "Bundle ID is empty after sanitisation.",
                parent=self.window,
            )
            return
        if self.loader.bundles.get_bundle(class_name, spec_name, new_id) is not None:
            messagebox.showwarning(
                "Bundle Exists", f"Bundle '{new_id}' already exists.",
                parent=self.window,
            )
            return
        self.loader.bundles.save_bundle(
            class_name, spec_name, new_id,
            {"name": new_id.replace("_", " ").title(), "description": ""},
        )
        self._populate_sidebar()
        self._current_key = (class_name, spec_name, new_id)
        self._load_current_bundle()
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed")

    def _on_rename_bundle(self) -> None:
        if self._current_key is None:
            messagebox.showinfo(
                "Rename Bundle", "Select a bundle first.", parent=self.window,
            )
            return
        class_name, spec_name, old_id = self._current_key
        new_id = simpledialog.askstring(
            "Rename Bundle",
            f"New bundle ID for {old_id}:",
            initialvalue=old_id,
            parent=self.window,
        )
        if not new_id or new_id == old_id:
            return
        new_id = new_id.strip().lower().replace(" ", "_")
        new_id = "".join(c for c in new_id if c.isalnum() or c == "_")
        if not new_id:
            return
        if not self.loader.bundles.rename_bundle(class_name, spec_name, old_id, new_id):
            messagebox.showerror(
                "Rename Failed",
                f"Could not rename — does '{new_id}' already exist?",
                parent=self.window,
            )
            return
        self._current_key = (class_name, spec_name, new_id)
        self._populate_sidebar()
        self._load_current_bundle()
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed")

    def _on_delete_bundle(self) -> None:
        if self._current_key is None:
            messagebox.showinfo(
                "Delete Bundle", "Select a bundle first.", parent=self.window,
            )
            return
        class_name, spec_name, bid = self._current_key
        if not messagebox.askyesno(
            "Delete Bundle",
            f"Delete bundle '{bid}' (and all its combos) from "
            f"{class_name} ({spec_name})?",
            parent=self.window,
        ):
            return
        self.loader.bundles.delete_bundle(class_name, spec_name, bid)
        self._current_key = None
        self._dirty = False
        self._populate_sidebar()
        self._show_placeholder()
        self._update_status()
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed")

    # ------------------------------------------------------------------
    # Combo CRUD
    # ------------------------------------------------------------------
    def _on_new_combo(self) -> None:
        if self._combo_editor is None:
            return
        try:
            self._combo_editor._on_add_combo()
        except Exception:
            logger.exception("New combo failed")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _gather_loadout_from_widgets(self) -> Dict[str, Any]:
        """Read the loadout panel back into a dict matching the bundle schema."""
        # Hotbar skills: one per non-empty line.
        hotbar_text = self._loadout_widgets["hotbar_skills"].get("1.0", "end-1c")
        hotbar = [line.strip() for line in hotbar_text.splitlines() if line.strip()]

        # Locked skills: "name :: reason" one per line.
        locked_text = self._loadout_widgets["locked_skills"].get("1.0", "end-1c")
        locked: List[Dict[str, str]] = []
        for line in locked_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "::" in line:
                name, reason = line.split("::", 1)
                locked.append({"name": name.strip(), "reason": reason.strip()})
            else:
                locked.append({"name": line, "reason": ""})

        # Core skill
        core: Dict[str, str] = {}
        rec = self._core_recommended_var.get().strip()
        eff = self._core_effect_var.get().strip()
        reason = self._core_reason_text.get("1.0", "end-1c").strip()
        if rec or eff or reason:
            core = {"recommended": rec, "effect": eff, "reason": reason}

        # PVE skill add-ons
        addons_text = self._addons_text.get("1.0", "end-1c")
        pve: List[Dict[str, str]] = []
        for line in addons_text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("::")]
            entry = {
                "skill": parts[0] if len(parts) > 0 else "",
                "addon_1": parts[1] if len(parts) > 1 else "",
                "addon_2": parts[2] if len(parts) > 2 else "",
            }
            pve.append(entry)
        addons = {"pve": pve} if pve else {}

        return {
            "name": self._bundle_name_var.get().strip(),
            "description": self._bundle_desc_text.get("1.0", "end-1c").strip(),
            "hotbar_skills": hotbar,
            "locked_skills": locked,
            "core_skill": core,
            "skill_addons": addons,
        }

    def _on_save_click(self) -> None:
        if self._current_key is None:
            return
        class_name, spec_name, bundle_id = self._current_key

        # 1) Save bundle metadata + loadout.
        meta = self._gather_loadout_from_widgets()
        self.loader.bundles.save_bundle(class_name, spec_name, bundle_id, meta)

        # 2) Save combos: diff against on-disk, persist add/change, delete removals.
        if self._combo_editor is not None:
            try:
                combos = self._combo_editor.get_combos()
            except Exception:
                logger.exception("ComboEditor.get_combos failed")
                combos = {}

            current_ids = {
                cid for cid, _ in self.loader.bundles.iter_combos_for_bundle(
                    class_name, spec_name, bundle_id
                )
            }
            new_ids: set = set()
            for section_key, payload in (combos or {}).items():
                category = section_key.removesuffix("_combos") if section_key.endswith("_combos") else section_key
                if not isinstance(payload, dict):
                    continue
                for cid, combo in payload.items():
                    if not isinstance(combo, dict):
                        continue
                    new_ids.add(cid)
                    data = copy.deepcopy(combo)
                    data["category"] = category
                    self.loader.bundles.save_combo(
                        class_name, spec_name, bundle_id, cid, data
                    )
            for stale in current_ids - new_ids:
                self.loader.bundles.delete_combo(
                    class_name, spec_name, bundle_id, stale
                )

        self._dirty = False
        self._update_status()
        self._populate_sidebar()  # combo counts update
        self._reselect_current()

        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed")

    # ------------------------------------------------------------------
    # Dirty / status
    # ------------------------------------------------------------------
    def _mark_dirty(self) -> None:
        if self._suspend_dirty:
            return
        self._dirty = True
        self._update_status()

    def _update_status(self) -> None:
        if self._dirty:
            self._status_label.configure(text="●  Unsaved changes", fg=GOLD)
        else:
            self._status_label.configure(text="", fg=GOLD)

    # ------------------------------------------------------------------
    # Export / Import / Inspect
    # ------------------------------------------------------------------
    def _on_export_single_combo(self) -> None:
        """Export the currently-selected combo as a single-combo .bdt.

        The bundle still carries its parent's loadout (hotbar / locked /
        core / addons) as context, so when the combo gets uploaded to a
        library the author's setup travels with it. The new bundle's
        metadata (id / name / description) is derived from the combo,
        not from the parent bundle, so two single-combo exports from
        the same parent don't collide.
        """
        from src.editor.portability import BDT_EXTENSION, write_combo_bundle

        if self._current_key is None:
            messagebox.showinfo(
                "Export Combo", "Select a bundle first.",
                parent=self.window,
            )
            return
        if self._combo_editor is None or not getattr(
            self._combo_editor, "_current_combo_id", None,
        ):
            messagebox.showinfo(
                "Export Combo",
                "Select a single combo from the list to export.",
                parent=self.window,
            )
            return

        if self._dirty:
            self._on_save_click()

        class_name, spec_name, parent_bundle_id = self._current_key
        combo_id = self._combo_editor._current_combo_id
        combo = self.loader.bundles.get_combo(
            class_name, spec_name, parent_bundle_id, combo_id,
        )
        if combo is None:
            messagebox.showerror(
                "Export Combo",
                f"Could not find combo '{combo_id}' in bundle "
                f"'{parent_bundle_id}'. Save and try again.",
                parent=self.window,
            )
            return

        # Loadout pulled from the parent bundle so the combo's gameplay
        # context (hotbar, locked, core, addons) travels with it.
        parent_meta = self.loader.bundles.get_bundle(
            class_name, spec_name, parent_bundle_id,
        ) or {}
        loadout = {
            k: parent_meta.get(k)
            for k in ("locked_skills", "hotbar_skills", "core_skill", "skill_addons")
            if k in parent_meta
        }

        # Use the combo's name/description as the bundle metadata so a
        # library upload reads as "this combo" rather than "<parent
        # bundle>".
        bundle_name = combo.get("name") or combo_id
        description = combo.get("description") or ""

        default_name = (
            f"{class_name}_{spec_name}_{combo_id}".lower().replace(" ", "_")
            + BDT_EXTENSION
        )
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Combo",
            defaultextension=BDT_EXTENSION,
            initialfile=default_name,
            filetypes=[
                ("BDO Trainer combo bundle", f"*{BDT_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            written = write_combo_bundle(
                path,
                class_name=class_name,
                spec_name=spec_name,
                # Bundle-id mirrors the combo id so library tooling and
                # diff/inspect dialogs show the right label.
                bundle_id=combo_id,
                name=bundle_name,
                description=description,
                loadout=loadout,
                combos={combo_id: copy.deepcopy(combo)},
            )
        except Exception as exc:
            logger.exception("Export single combo failed")
            messagebox.showerror(
                "Export Failed",
                f"Could not export combo:\n{exc}",
                parent=self.window,
            )
            return

        messagebox.showinfo(
            "Export Complete",
            f"Exported combo '{combo_id}' to:\n{written}",
            parent=self.window,
        )

    def _on_export_combos(self) -> None:
        from src.editor.portability import BDT_EXTENSION, write_combo_bundle

        if self._current_key is None:
            messagebox.showinfo(
                "Export Combos", "Select a bundle to export first.",
                parent=self.window,
            )
            return
        if self._dirty:
            self._on_save_click()

        class_name, spec_name, bundle_id = self._current_key
        meta = self.loader.bundles.get_bundle(class_name, spec_name, bundle_id) or {}
        loadout = {k: meta.get(k) for k in (
            "locked_skills", "hotbar_skills", "core_skill", "skill_addons",
        ) if k in meta}

        combos: Dict[str, Dict[str, Any]] = {}
        for cid, combo in self.loader.bundles.iter_combos_for_bundle(
            class_name, spec_name, bundle_id
        ):
            combos[cid] = copy.deepcopy(combo)

        if not combos and not loadout:
            messagebox.showinfo(
                "Export Combos",
                "Bundle is empty — nothing to export.",
                parent=self.window,
            )
            return

        default_name = (
            f"{class_name}_{spec_name}_{bundle_id}".lower().replace(" ", "_")
            + BDT_EXTENSION
        )
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Bundle",
            defaultextension=BDT_EXTENSION,
            initialfile=default_name,
            filetypes=[("BDO Trainer combo bundle", f"*{BDT_EXTENSION}"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            written = write_combo_bundle(
                path,
                class_name=class_name,
                spec_name=spec_name,
                bundle_id=bundle_id,
                name=meta.get("name", bundle_id),
                description=meta.get("description", ""),
                loadout=loadout,
                combos=combos,
            )
        except Exception as exc:
            logger.exception("Export combo bundle failed")
            messagebox.showerror(
                "Export Failed", f"Could not export bundle:\n{exc}",
                parent=self.window,
            )
            return

        messagebox.showinfo(
            "Export Complete",
            f"Exported bundle '{bundle_id}' ({len(combos)} combo(s)) to:\n{written}",
            parent=self.window,
        )

    def _on_import_combos(self) -> None:
        from src.editor.portability import (
            BDT_EXTENSION, BundleError, read_bundle_from_file,
        )

        path = filedialog.askopenfilename(
            parent=self.window,
            title="Import Combo Bundle",
            filetypes=[
                ("BDO Trainer combo bundle", f"*{BDT_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            bundle = read_bundle_from_file(path)
        except BundleError as exc:
            messagebox.showerror("Import Failed", str(exc), parent=self.window)
            return

        ImportComboBundleDialog(self.window, self, bundle)

    def _on_inspect_bundle(self) -> None:
        from src.editor.portability import (
            BDC_EXTENSION, BDT_EXTENSION,
            BundleError, read_bundle_from_file,
        )

        path = filedialog.askopenfilename(
            parent=self.window,
            title="Inspect Bundle",
            filetypes=[
                ("BDO Trainer bundles", f"*{BDT_EXTENSION} *{BDC_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            bundle = read_bundle_from_file(path)
        except BundleError as exc:
            messagebox.showerror("Inspect Failed", str(exc), parent=self.window)
            return
        BundleInspectorDialog(self.window, bundle, source_path=path)

    # ------------------------------------------------------------------
    # Hooks called by ImportComboBundleDialog
    # ------------------------------------------------------------------
    def apply_imported_combo_bundle(
        self,
        target_class: str,
        target_spec: str,
        target_bundle_id: str,
        bundle: Dict[str, Any],
        selected_ids: List[str],
        rename_conflicts: Dict[str, str],
        merge_loadout: bool,
    ) -> bool:
        """Persist selected combos (and optionally the bundle's loadout)
        from a combo-bundle into the target (class, spec, bundle).
        """
        from src.editor.portability import list_combos_in_bundle

        if not self.loader.classes.has(target_class, target_spec):
            messagebox.showerror(
                "Import Failed",
                f"Target class {target_class} ({target_spec}) is not loaded.",
                parent=self.window,
            )
            return False

        # Make sure the target bundle exists (auto-create if necessary).
        existing = self.loader.bundles.get_bundle(
            target_class, target_spec, target_bundle_id
        )
        if existing is None:
            self.loader.bundles.save_bundle(
                target_class, target_spec, target_bundle_id,
                {"name": target_bundle_id.replace("_", " ").title()},
            )
            existing = self.loader.bundles.get_bundle(
                target_class, target_spec, target_bundle_id
            ) or {}

        # Optionally take the loadout from the bundle file.
        if merge_loadout:
            loadout = bundle.get("loadout") or {}
            if loadout:
                meta = copy.deepcopy(existing)
                for k in ("locked_skills", "hotbar_skills", "core_skill", "skill_addons"):
                    if k in loadout:
                        meta[k] = copy.deepcopy(loadout[k])
                if "name" in bundle:
                    meta["name"] = bundle.get("name")
                if "description" in bundle:
                    meta["description"] = bundle.get("description")
                self.loader.bundles.save_bundle(
                    target_class, target_spec, target_bundle_id, meta,
                )

        # Combos
        bundle_combos = {cid: combo for cid, combo in list_combos_in_bundle(bundle)}
        added = 0
        for cid in selected_ids:
            combo = bundle_combos.get(cid)
            if not isinstance(combo, dict):
                continue
            new_id = rename_conflicts.get(cid, cid)
            data = copy.deepcopy(combo)
            data["combo_id"] = new_id
            data["class"] = target_class
            data["spec"] = target_spec
            data["bundle_id"] = target_bundle_id
            data.setdefault("category", combo.get("category", "pve"))
            self.loader.bundles.save_combo(
                target_class, target_spec, target_bundle_id, new_id, data,
            )
            added += 1

        # Refresh.
        self._populate_sidebar()
        self._current_key = (target_class, target_spec, target_bundle_id)
        self._load_current_bundle()

        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed after import")

        messagebox.showinfo(
            "Import Complete",
            f"Imported {added} combo(s) into {target_class} / {target_spec} / "
            f"{target_bundle_id}.",
            parent=self.window,
        )
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        if self._dirty and self._current_key is not None:
            old = self._current_key
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to {old[0]} — {old[1]} / {old[2]} before closing?",
                parent=self.window,
            )
            if answer is True:
                self._on_save_click()
            elif answer is None:
                return
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        ComboEditorWindow._instance = None


# ===========================================================================
# Combo-bundle import dialog
# ===========================================================================
class ImportComboBundleDialog:
    """Walks the user through importing a combo bundle into a target bundle."""

    def __init__(
        self,
        parent: tk.Toplevel,
        editor: "ComboEditorWindow",
        bundle: Dict[str, Any],
    ) -> None:
        from src.editor.portability import list_combos_in_bundle

        self.editor = editor
        self.bundle = bundle
        self.bundle_class = bundle.get("class_name", "?")
        self.bundle_spec = bundle.get("spec_name", "?")
        self.bundle_id = bundle.get("bundle_id", "default")

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Import Combos")
        self.dlg.configure(bg=BG_DARK)
        self.dlg.transient(parent)
        self.dlg.grab_set()
        self.dlg.geometry("560x600")
        force_dialog_to_front(self.dlg)

        tk.Label(
            self.dlg,
            text=f"Bundle: {self.bundle_class} ({self.bundle_spec}) — "
                 f"{bundle.get('name') or self.bundle_id}",
            font=FONT_HEADING, fg=GOLD, bg=BG_DARK,
        ).pack(anchor="w", padx=14, pady=(14, 2))

        if bundle.get("description"):
            tk.Label(
                self.dlg, text=bundle["description"],
                font=FONT, fg=FG_TEXT, bg=BG_DARK,
                wraplength=520, justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 4))

        # Target class + bundle selection
        target_row = tk.Frame(self.dlg, bg=BG_DARK)
        target_row.pack(fill="x", padx=14, pady=(8, 4))

        tk.Label(target_row, text="Target class:",
                 font=FONT, fg=FG_DIM, bg=BG_DARK, width=14, anchor="w").pack(side="left")

        self._target_keys = editor.loader.classes.keys()
        labels = [f"{c} — {s}" for c, s in self._target_keys] or ["(no classes loaded)"]
        same = next(
            (k for k in self._target_keys if k[0] == self.bundle_class),
            (self._target_keys[0] if self._target_keys else None),
        )
        initial_label = f"{same[0]} — {same[1]}" if same else labels[0]
        self.target_class_var = tk.StringVar(value=initial_label)
        target_dd = tk.OptionMenu(
            target_row, self.target_class_var, *labels,
            command=lambda *_: self._refresh_bundle_options(),
        )
        target_dd.configure(
            bg=BG_INPUT, fg=FG_TEXT, font=FONT, highlightthickness=0,
            relief="flat", activebackground=ACCENT, activeforeground="white",
        )
        target_dd["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT)
        target_dd.pack(side="left", padx=8, fill="x", expand=True)

        bundle_row = tk.Frame(self.dlg, bg=BG_DARK)
        bundle_row.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(bundle_row, text="Target bundle:",
                 font=FONT, fg=FG_DIM, bg=BG_DARK, width=14, anchor="w").pack(side="left")
        self.target_bundle_var = tk.StringVar()
        self._target_bundle_dd = tk.OptionMenu(
            bundle_row, self.target_bundle_var, "(loading...)",
        )
        self._target_bundle_dd.configure(
            bg=BG_INPUT, fg=FG_TEXT, font=FONT, highlightthickness=0,
            relief="flat", activebackground=ACCENT, activeforeground="white",
        )
        self._target_bundle_dd["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT)
        self._target_bundle_dd.pack(side="left", padx=8, fill="x", expand=True)
        self._refresh_bundle_options()

        # Loadout merge option
        self.merge_loadout_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.dlg,
            text="Also import loadout (hotbar / locked / core / addons) into the target bundle",
            variable=self.merge_loadout_var,
            bg=BG_DARK, fg=FG_TEXT, selectcolor=BG_CARD,
            activebackground=BG_DARK, activeforeground=FG_TEXT,
            font=FONT_SMALL, anchor="w", wraplength=520, justify="left",
        ).pack(anchor="w", padx=14, pady=(2, 6))

        # Combo list
        list_box = tk.Frame(self.dlg, bg=BG_CARD)
        list_box.pack(fill="both", expand=True, padx=14, pady=8)
        canvas = tk.Canvas(list_box, bg=BG_CARD, highlightthickness=0)
        scroll = tk.Scrollbar(list_box, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_CARD)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._combo_vars: Dict[str, tk.BooleanVar] = {}
        any_combos = False
        for cid, combo in list_combos_in_bundle(bundle):
            any_combos = True
            var = tk.BooleanVar(value=True)
            self._combo_vars[cid] = var
            row = tk.Frame(inner, bg=BG_CARD)
            row.pack(fill="x", padx=14, pady=1)
            tk.Checkbutton(
                row, variable=var,
                bg=BG_CARD, fg=FG_TEXT, selectcolor=BG_DARK,
                activebackground=BG_CARD, activeforeground=FG_TEXT,
            ).pack(side="left")
            cat = combo.get("category", "pve").upper()
            name = combo.get("name") or cid
            tk.Label(
                row, text=f"[{cat}]  {name}  ({cid})",
                font=FONT, fg=FG_TEXT, bg=BG_CARD, anchor="w",
            ).pack(side="left", fill="x", expand=True)

        if not any_combos:
            tk.Label(
                inner, text="(this bundle contains no combos)",
                font=FONT, fg=FG_DIM, bg=BG_CARD,
            ).pack(padx=8, pady=12)

        # Buttons
        btns = tk.Frame(self.dlg, bg=BG_DARK)
        btns.pack(fill="x", padx=14, pady=(4, 14))
        tk.Button(
            btns, text="Import",
            font=FONT_BOLD, bg=GREEN, fg="white",
            activebackground="#9CA600", activeforeground="white",
            relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
            command=self._on_import,
        ).pack(side="right")
        tk.Button(
            btns, text="Cancel",
            font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
            command=self.dlg.destroy,
        ).pack(side="right", padx=(0, 8))

    def _refresh_bundle_options(self) -> None:
        """Repopulate the target-bundle dropdown for the selected class."""
        target_class, target_spec = self._resolve_target_class()
        bundles = [bid for bid, _ in self.editor.loader.bundles.bundles_for_class(
            target_class, target_spec
        )]
        # Always offer creating a fresh bundle named after the source.
        synthetic = self.bundle_id
        if synthetic not in bundles:
            bundles.append(f"+ {synthetic} (new)")
        else:
            bundles.append(f"+ ___ (new)")  # placeholder for arbitrary new

        menu = self._target_bundle_dd["menu"]
        menu.delete(0, "end")
        for opt in bundles:
            menu.add_command(
                label=opt,
                command=lambda v=opt: self.target_bundle_var.set(v),
            )
        # Default selection: the source's bundle id if it exists, else first.
        if self.bundle_id in bundles:
            self.target_bundle_var.set(self.bundle_id)
        else:
            self.target_bundle_var.set(bundles[0])

    def _resolve_target_class(self) -> Tuple[str, str]:
        label = self.target_class_var.get()
        for c, s in self._target_keys:
            if f"{c} — {s}" == label:
                return c, s
        if self._target_keys:
            return self._target_keys[0]
        return ("", "")

    def _resolve_target_bundle(
        self, target_class: str, target_spec: str,
    ) -> Optional[str]:
        choice = self.target_bundle_var.get()
        if not choice:
            return None
        if choice.startswith("+ "):
            new_id = simpledialog.askstring(
                "New Target Bundle",
                "Bundle ID for the imported combos:",
                initialvalue=self.bundle_id,
                parent=self.dlg,
            )
            if not new_id:
                return None
            new_id = new_id.strip().lower().replace(" ", "_")
            new_id = "".join(c for c in new_id if c.isalnum() or c == "_")
            return new_id or None
        return choice

    def _on_import(self) -> None:
        if not self._target_keys:
            messagebox.showwarning(
                "No Target",
                "There are no loaded classes to import into.",
                parent=self.dlg,
            )
            return

        target_class, target_spec = self._resolve_target_class()
        target_bundle_id = self._resolve_target_bundle(target_class, target_spec)
        if not target_bundle_id:
            return

        selected = [cid for cid, var in self._combo_vars.items() if var.get()]
        if not selected and not self.merge_loadout_var.get():
            messagebox.showinfo(
                "Nothing Selected",
                "Tick at least one combo, or enable loadout import.",
                parent=self.dlg,
            )
            return

        # Combo-id collisions in the target bundle.
        existing_ids = {
            cid for cid, _ in self.editor.loader.bundles.iter_combos_for_bundle(
                target_class, target_spec, target_bundle_id
            )
        }
        rename_conflicts: Dict[str, str] = {}
        for cid in selected:
            if cid in existing_ids:
                new_id = simpledialog.askstring(
                    "Combo ID Conflict",
                    f"'{cid}' already exists in {target_bundle_id}.\n\n"
                    "Enter a new combo ID, or leave blank to overwrite:",
                    parent=self.dlg,
                )
                if new_id is None:
                    return
                new_id = new_id.strip()
                if new_id and new_id != cid:
                    rename_conflicts[cid] = new_id

        if self.editor.apply_imported_combo_bundle(
            target_class,
            target_spec,
            target_bundle_id,
            self.bundle,
            selected,
            rename_conflicts,
            merge_loadout=self.merge_loadout_var.get(),
        ):
            self.dlg.destroy()


# ===========================================================================
# Bundle inspector
# ===========================================================================
class BundleInspectorDialog:
    """Read-only viewer for both .bdt and .bdc bundles."""

    def __init__(
        self,
        parent: tk.Toplevel,
        bundle: Dict[str, Any],
        source_path: str = "",
    ) -> None:
        from src.editor.portability import (
            collect_skill_ids_used_by_combo,
            list_combos_in_bundle,
            list_skills_in_bundle,
        )

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("Inspect Bundle")
        self.dlg.configure(bg=BG_DARK)
        self.dlg.transient(parent)
        self.dlg.grab_set()
        self.dlg.geometry("620x640")
        force_dialog_to_front(self.dlg)

        head = tk.Frame(self.dlg, bg=BG_DARK)
        head.pack(fill="x", padx=14, pady=(14, 4))

        kind = bundle.get("kind", "class")
        bundle_id = bundle.get("bundle_id", "")
        title = (
            f"{bundle.get('class_name', '?')} ({bundle.get('spec_name', '?')}) — "
            f"kind={kind}"
        )
        if bundle_id:
            title += f", bundle={bundle_id}"
        tk.Label(
            head, text=title,
            font=FONT_HEADING, fg=GOLD, bg=BG_DARK,
        ).pack(anchor="w")

        meta_lines: List[str] = []
        if bundle.get("name"):
            meta_lines.append(f"Name: {bundle['name']}")
        if bundle.get("description"):
            meta_lines.append(bundle["description"])
        if bundle.get("exported_at"):
            meta_lines.append(f"Exported at: {bundle['exported_at']}")
        if bundle.get("format_version") is not None:
            meta_lines.append(f"Format version: {bundle['format_version']}")
        if source_path:
            meta_lines.append(f"File: {source_path}")
        for line in meta_lines:
            tk.Label(
                head, text=line, font=FONT_SMALL, fg=FG_DIM, bg=BG_DARK,
                anchor="w", wraplength=580, justify="left",
            ).pack(anchor="w")

        # Tabs
        tabbar = tk.Frame(self.dlg, bg=BG_DARK)
        tabbar.pack(fill="x", padx=14, pady=(8, 0))
        self._tab_buttons: Dict[str, tk.Button] = {}
        self._tab_panes: Dict[str, tk.Frame] = {}
        tabs = [("combos", "Combos")]
        if kind == "class":
            tabs.append(("skills", "Skills"))
        else:
            tabs.append(("loadout", "Loadout"))
        for tab_id, label in tabs:
            btn = tk.Button(
                tabbar, text=label,
                font=FONT_BOLD, bg=BG_CARD, fg=FG_TEXT,
                activebackground=ACCENT, activeforeground="white",
                relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                command=lambda t=tab_id: self._switch_tab(t),
            )
            btn.pack(side="left", padx=(0, 4))
            self._tab_buttons[tab_id] = btn

        body = tk.Frame(self.dlg, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=14, pady=4)

        # Combos tab
        combos_pane = self._scroll_frame(body)
        skills = list_skills_in_bundle(bundle)
        any_combos = False
        for cid, combo in list_combos_in_bundle(bundle):
            any_combos = True
            row = tk.Frame(combos_pane.inner, bg=BG_CARD)
            row.pack(fill="x", padx=10, pady=1)
            steps = combo.get("steps") or []
            tk.Label(
                row,
                text=f"[{combo.get('category', 'pve').upper()}]  "
                     f"{combo.get('name') or cid}  ({cid})  — {len(steps)} step(s)",
                font=FONT, fg=FG_TEXT, bg=BG_CARD, anchor="w",
            ).pack(side="left", fill="x", expand=True)
            ids = collect_skill_ids_used_by_combo(combo)
            missing = [sid for sid in ids if sid not in skills]
            if missing and skills:
                tk.Label(
                    row, text=f"⚠ {len(missing)} missing",
                    font=FONT_SMALL, fg="#E0B973", bg=BG_CARD,
                ).pack(side="right", padx=(0, 4))
        if not any_combos:
            tk.Label(
                combos_pane.inner, text="(no combos in bundle)",
                font=FONT, fg=FG_DIM, bg=BG_CARD,
            ).pack(padx=8, pady=12)
        self._tab_panes["combos"] = combos_pane

        # Skills tab (class bundles)
        if kind == "class":
            skills_pane = self._scroll_frame(body)
            if not skills:
                tk.Label(
                    skills_pane.inner, text="(no skills in bundle)",
                    font=FONT, fg=FG_DIM, bg=BG_CARD,
                ).pack(padx=8, pady=12)
            else:
                for sid in sorted(skills.keys(), key=lambda x: x.lower()):
                    sk = skills[sid] or {}
                    if not isinstance(sk, dict):
                        continue
                    row = tk.Frame(skills_pane.inner, bg=BG_CARD)
                    row.pack(fill="x", padx=10, pady=1)
                    name = sk.get("name") or sid
                    input_text = sk.get("input") or " + ".join(sk.get("keys") or []).upper() or "—"
                    tk.Label(
                        row, text=f"{name}  ({sid})",
                        font=FONT, fg=FG_TEXT, bg=BG_CARD, anchor="w",
                    ).pack(side="left", fill="x", expand=True)
                    tk.Label(
                        row, text=input_text,
                        font=FONT_SMALL, fg=FG_DIM, bg=BG_CARD,
                    ).pack(side="right")
            self._tab_panes["skills"] = skills_pane

        # Loadout tab (combo bundles)
        if kind == "combos":
            loadout_pane = self._scroll_frame(body)
            loadout = bundle.get("loadout") or {}
            if not loadout:
                tk.Label(
                    loadout_pane.inner,
                    text="(no loadout — bundle was exported without one)",
                    font=FONT, fg=FG_DIM, bg=BG_CARD,
                ).pack(padx=8, pady=12)
            else:
                self._render_loadout(loadout_pane.inner, loadout)
            self._tab_panes["loadout"] = loadout_pane

        # Close
        tk.Button(
            self.dlg, text="Close",
            font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
            command=self.dlg.destroy,
        ).pack(side="right", padx=14, pady=(4, 14))

        # Default tab
        self._switch_tab("combos")

    def _scroll_frame(self, parent: tk.Frame) -> Any:
        pane = tk.Frame(parent, bg=BG_CARD)
        canvas = tk.Canvas(pane, bg=BG_CARD, highlightthickness=0)
        scroll = tk.Scrollbar(pane, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_CARD)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        pane.inner = inner  # type: ignore[attr-defined]
        return pane

    def _render_loadout(self, parent: tk.Frame, loadout: Dict[str, Any]) -> None:
        # Hotbar
        hot = loadout.get("hotbar_skills") or []
        tk.Label(parent, text=f"Hotbar skills ({len(hot)})",
                 font=FONT_BOLD, fg=GOLD, bg=BG_CARD, anchor="w",
                 ).pack(fill="x", padx=8, pady=(8, 2))
        for s in hot:
            tk.Label(parent, text=f"  • {s}", font=FONT, fg=FG_TEXT, bg=BG_CARD,
                     anchor="w").pack(fill="x", padx=8)

        # Locked
        locked = loadout.get("locked_skills") or []
        tk.Label(parent, text=f"Locked skills ({len(locked)})",
                 font=FONT_BOLD, fg=GOLD, bg=BG_CARD, anchor="w",
                 ).pack(fill="x", padx=8, pady=(8, 2))
        for entry in locked:
            if isinstance(entry, dict):
                line = f"  🔒 {entry.get('name', '?')}"
                if entry.get("reason"):
                    line += f" — {entry['reason']}"
                tk.Label(parent, text=line, font=FONT, fg=FG_TEXT, bg=BG_CARD,
                         anchor="w", wraplength=540, justify="left").pack(fill="x", padx=8)

        # Core
        core = loadout.get("core_skill") or {}
        tk.Label(parent, text="Core skill",
                 font=FONT_BOLD, fg=GOLD, bg=BG_CARD, anchor="w",
                 ).pack(fill="x", padx=8, pady=(8, 2))
        if core:
            for k in ("recommended", "effect", "reason"):
                if core.get(k):
                    tk.Label(
                        parent,
                        text=f"  {k.title()}: {core[k]}",
                        font=FONT, fg=FG_TEXT, bg=BG_CARD,
                        anchor="w", wraplength=540, justify="left",
                    ).pack(fill="x", padx=8)
        else:
            tk.Label(parent, text="  (none)", font=FONT, fg=FG_DIM, bg=BG_CARD,
                     anchor="w").pack(fill="x", padx=8)

        # Addons
        addons = (loadout.get("skill_addons") or {}).get("pve") or []
        tk.Label(parent, text=f"PVE skill add-ons ({len(addons)})",
                 font=FONT_BOLD, fg=GOLD, bg=BG_CARD, anchor="w",
                 ).pack(fill="x", padx=8, pady=(8, 2))
        for a in addons:
            if isinstance(a, dict):
                line = f"  {a.get('skill', '?')}"
                if a.get("addon_1"):
                    line += f" / {a['addon_1']}"
                if a.get("addon_2"):
                    line += f" / {a['addon_2']}"
                tk.Label(parent, text=line, font=FONT, fg=FG_TEXT, bg=BG_CARD,
                         anchor="w", wraplength=540, justify="left").pack(fill="x", padx=8)

    def _switch_tab(self, tab_id: str) -> None:
        if tab_id not in self._tab_panes:
            return
        for t_id, pane in self._tab_panes.items():
            pane.pack_forget()
            self._tab_buttons[t_id].configure(bg=BG_CARD, fg=FG_TEXT)
        self._tab_panes[tab_id].pack(fill="both", expand=True)
        self._tab_buttons[tab_id].configure(bg=ACCENT, fg="white")
