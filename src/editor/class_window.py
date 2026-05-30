"""Class Editor — main window.

Edits class definitions: skills only. Locked-skill / hotbar / core /
add-on recommendations live with bundles, not classes, so they're not
part of this editor — see the Combo Editor's loadout panel.

Class definitions are stored at ``data/classes/<slug>.yaml`` and
read/written through :class:`src.combo_loader.ClassLoader`.
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


class ClassEditorWindow:
    """Singleton Toplevel for editing class skill definitions."""

    _instance: Optional["ClassEditorWindow"] = None

    @classmethod
    def open(
        cls,
        root: tk.Tk,
        loader: Any,
        on_save: Optional[Callable] = None,
    ) -> "ClassEditorWindow":
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

        # Per-class skill working copies — the SkillEditor mutates this
        # dict in place. We persist on Save.
        self._skill_copies: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._current_key: Optional[Tuple[str, str]] = None
        self._sidebar_keys: List[Tuple[str, str]] = []
        self._dirty = False

        self.window = tk.Toplevel(root)
        self.window.title("BDO Trainer — Class Editor")
        self.window.configure(bg=BG_DARK)
        self.window.minsize(900, 600)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.window.resizable(True, True)

        self._build_ui()

        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        ww = max(self.window.winfo_width(), 1100)
        wh = max(self.window.winfo_height(), 700)
        self.window.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        title_bar = tk.Frame(self.window, bg=BG_DARK)
        title_bar.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(
            title_bar, text="Class Editor",
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
        sidebar = tk.Frame(self._paned, bg=BG_CARD, width=220)
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="Classes",
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
        self._listbox.bind("<<ListboxSelect>>", self._on_class_selected)

        actions = tk.Frame(sidebar, bg=BG_CARD)
        actions.pack(fill="x", padx=6, pady=(0, 4))
        tk.Button(
            actions, text="+ New Class",
            font=FONT_BOLD, bg=GREEN, fg="white",
            activebackground="#9CA600", activeforeground="white",
            relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
            command=self._on_new_class,
        ).pack(fill="x", pady=(0, 4))
        tk.Button(
            actions, text="Delete Class",
            font=FONT, bg=BG_INPUT, fg=RED_SOFT,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
            command=self._on_delete_class,
        ).pack(fill="x")

        bundle = tk.Frame(sidebar, bg=BG_CARD)
        bundle.pack(fill="x", padx=6, pady=(6, 8))
        for label, cmd in (
            ("Export Class", self._on_export_class),
            ("Import Class", self._on_import_class),
            ("Inspect", self._on_inspect_bundle),
        ):
            tk.Button(
                bundle, text=label, font=FONT,
                bg=BG_INPUT, fg=FG_TEXT,
                activebackground=ACCENT, activeforeground="white",
                relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
                command=cmd,
            ).pack(fill="x", pady=2)

        self._paned.add(sidebar, minsize=200, width=220)
        self._populate_sidebar()

    def _build_content(self) -> None:
        content = tk.Frame(self._paned, bg=BG_DARK)
        self._content = content

        self._placeholder = tk.Label(
            content,
            text="Select a class from the sidebar, or create a new one.",
            font=FONT, fg=FG_DIM, bg=BG_DARK,
            wraplength=480, justify="center",
        )

        self._skill_pane = tk.Frame(content, bg=BG_DARK)
        try:
            from src.editor.skill_editor import SkillEditor

            self._skill_editor = SkillEditor(
                self._skill_pane,
                on_change=self._mark_dirty,
                on_id_renamed=self._on_skill_id_renamed,
            )
            self._skill_editor.frame.pack(fill="both", expand=True)
        except Exception:
            logger.exception("SkillEditor failed to load")
            self._skill_editor = None
            tk.Label(
                self._skill_pane,
                text="(Skill editor failed to load — see logs)",
                font=FONT, fg=FG_DIM, bg=BG_DARK,
            ).pack(expand=True)

        bottom = tk.Frame(content, bg=BG_DARK)
        bottom.pack(side="bottom", fill="x", padx=8, pady=(4, 8))
        self._save_btn = tk.Button(
            bottom,
            text="\U0001F4BE  Save Class",
            font=FONT_BOLD,
            bg=GREEN, fg="white",
            activebackground="#9CA600", activeforeground="white",
            relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
            command=self._on_save_click,
        )
        self._save_btn.pack(side="right")

        self._paned.add(content, minsize=480)

    def _show_placeholder(self) -> None:
        try:
            self._skill_pane.pack_forget()
        except tk.TclError:
            pass
        self._placeholder.pack(fill="both", expand=True, padx=12, pady=12)

    def _show_editor(self) -> None:
        self._placeholder.pack_forget()
        self._skill_pane.pack(fill="both", expand=True, padx=8, pady=8)

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _populate_sidebar(self) -> None:
        self._listbox.delete(0, "end")
        self._sidebar_keys = self.loader.classes.keys()
        for class_name, spec_name in self._sidebar_keys:
            self._listbox.insert("end", f"{class_name} — {spec_name}")
        if self._current_key and self._current_key in self._sidebar_keys:
            idx = self._sidebar_keys.index(self._current_key)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)

    def _select_sidebar_key(self, key: Tuple[str, str]) -> None:
        if key in self._sidebar_keys:
            idx = self._sidebar_keys.index(key)
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
            self._current_key = key

    # ------------------------------------------------------------------
    # Class selection / load
    # ------------------------------------------------------------------
    def _on_class_selected(self, _event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._sidebar_keys):
            return
        new_key = self._sidebar_keys[idx]
        if new_key == self._current_key:
            return
        if self._dirty and self._current_key is not None:
            old_cls, old_spec = self._current_key
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to {old_cls} — {old_spec}?",
                parent=self.window,
            )
            if answer is True:
                self._on_save_click()
            elif answer is None:
                self._select_sidebar_key(self._current_key)
                return
        self._current_key = new_key
        self._load_current()

    def _load_current(self) -> None:
        if self._current_key is None:
            self._show_placeholder()
            return
        class_name, spec_name = self._current_key
        skills_copy = self._skill_copies.get(self._current_key)
        if skills_copy is None:
            skills_copy = copy.deepcopy(
                self.loader.classes.get_skills(class_name, spec_name)
            )
            self._skill_copies[self._current_key] = skills_copy
        if self._skill_editor is not None and hasattr(self._skill_editor, "load"):
            try:
                self._skill_editor.load(skills_copy, class_name, spec_name)
            except Exception:
                logger.exception("SkillEditor.load failed")
        self._show_editor()
        self._dirty = False
        self._update_status()

    # ------------------------------------------------------------------
    # Dirty / status / skill rename propagation
    # ------------------------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_status()

    def _update_status(self) -> None:
        if self._dirty:
            self._status_label.configure(text="●  Unsaved changes", fg=GOLD)
        else:
            self._status_label.configure(text="", fg=GOLD)

    def _on_skill_id_renamed(self, old_id: str, new_id: str) -> None:
        if not old_id or old_id == new_id:
            return
        renames = 0
        for cls, spec, bid, cid, combo in list(
            self.loader.bundles.iter_all_combos()
        ):
            if not isinstance(combo, dict):
                continue
            steps = combo.get("steps") or []
            changed = False
            for step in steps:
                if isinstance(step, dict) and step.get("skill") == old_id:
                    step["skill"] = new_id
                    changed = True
            if changed:
                self.loader.bundles.save_combo(cls, spec, bid, cid, combo)
                renames += 1
        if renames:
            logger.info(f"Skill rename: {old_id} → {new_id} updated {renames} combo(s)")

    # ------------------------------------------------------------------
    # New / Delete class
    # ------------------------------------------------------------------
    def _on_new_class(self) -> None:
        dlg = tk.Toplevel(self.window)
        dlg.title("New Class")
        dlg.configure(bg=BG_DARK)
        dlg.transient(self.window)
        dlg.grab_set()
        dlg.geometry("400x220")
        force_dialog_to_front(dlg)

        tk.Label(
            dlg, text="Create New Class",
            font=FONT_HEADING, fg=GOLD, bg=BG_DARK,
        ).pack(anchor="w", padx=14, pady=(14, 8))

        row1 = tk.Frame(dlg, bg=BG_DARK)
        row1.pack(fill="x", padx=14, pady=4)
        tk.Label(row1, text="Class name:", font=FONT, fg=FG_DIM, bg=BG_DARK,
                 width=12, anchor="w").pack(side="left")
        name_entry = tk.Entry(
            row1, font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BG_CARD,
        )
        name_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        name_entry.focus_set()

        row2 = tk.Frame(dlg, bg=BG_DARK)
        row2.pack(fill="x", padx=14, pady=4)
        tk.Label(row2, text="Spec:", font=FONT, fg=FG_DIM, bg=BG_DARK,
                 width=12, anchor="w").pack(side="left")
        spec_var = tk.StringVar(value="Awakening")
        for s in ("Awakening", "Succession"):
            tk.Radiobutton(
                row2, text=s, variable=spec_var, value=s,
                bg=BG_DARK, fg=FG_TEXT, selectcolor=BG_CARD,
                activebackground=BG_DARK, activeforeground=FG_TEXT, font=FONT,
            ).pack(side="left", padx=(0, 6))

        err_label = tk.Label(dlg, text="", font=FONT_SMALL, fg=RED_SOFT, bg=BG_DARK)
        err_label.pack(anchor="w", padx=14, pady=(4, 0))

        def _create() -> None:
            class_name = name_entry.get().strip()
            spec_name = spec_var.get().strip()
            if not class_name:
                err_label.configure(text="Class name is required.")
                return
            if (class_name, spec_name) in self.loader.class_configs:
                err_label.configure(text=f"{class_name} ({spec_name}) already exists.")
                return
            try:
                self.loader.classes.save(class_name, spec_name, {"skills": {}})
                # Auto-create a default bundle so combos can immediately
                # be added against this class.
                self.loader.bundles.save_bundle(
                    class_name, spec_name, "default",
                    {"name": "Default", "description": ""},
                )
            except Exception as exc:
                err_label.configure(text=f"Save failed: {exc}")
                return
            self._populate_sidebar()
            self._select_sidebar_key((class_name, spec_name))
            self._current_key = (class_name, spec_name)
            self._load_current()
            dlg.destroy()
            if self.on_save:
                try:
                    self.on_save()
                except Exception:
                    logger.exception("on_save callback failed")

        btns = tk.Frame(dlg, bg=BG_DARK)
        btns.pack(fill="x", padx=14, pady=(10, 14))
        tk.Button(
            btns, text="Create",
            font=FONT_BOLD, bg=GREEN, fg="white",
            activebackground="#9CA600", activeforeground="white",
            relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
            command=_create,
        ).pack(side="right")
        tk.Button(
            btns, text="Cancel",
            font=FONT, bg=BG_INPUT, fg=FG_TEXT,
            activebackground=ACCENT, activeforeground="white",
            relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
            command=dlg.destroy,
        ).pack(side="right", padx=(0, 8))

    def _on_delete_class(self) -> None:
        if self._current_key is None:
            messagebox.showinfo(
                "Delete Class", "Select a class to delete first.",
                parent=self.window,
            )
            return
        class_name, spec_name = self._current_key
        if not messagebox.askyesno(
            "Delete Class",
            f"Permanently delete {class_name} — {spec_name}?\n\n"
            "This removes the class definition AND every bundle / combo "
            "associated with it.",
            parent=self.window,
        ):
            return
        try:
            self.loader.delete_class_config(class_name, spec_name)
        except Exception as exc:
            messagebox.showerror(
                "Delete Failed", f"Could not delete: {exc}", parent=self.window,
            )
            return
        self._skill_copies.pop(self._current_key, None)
        self._current_key = None
        self._dirty = False
        self._update_status()
        self._populate_sidebar()
        self._show_placeholder()
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _on_save_click(self) -> None:
        if self._current_key is None:
            return
        class_name, spec_name = self._current_key
        if self._skill_editor is not None and hasattr(self._skill_editor, "get_skills"):
            try:
                self._skill_copies[self._current_key] = self._skill_editor.get_skills()
            except Exception:
                logger.exception("SkillEditor.get_skills failed")
        cfg = copy.deepcopy(self.loader.classes.get(class_name, spec_name) or {})
        cfg["skills"] = copy.deepcopy(self._skill_copies.get(self._current_key, {}))
        for legacy in ("awakening_skills", "rabam_skills", "preawakening_utility"):
            cfg.pop(legacy, None)
        try:
            self.loader.classes.save(class_name, spec_name, cfg)
        except Exception as exc:
            logger.exception("Class save failed")
            messagebox.showerror(
                "Save Failed", f"Could not save class:\n{exc}", parent=self.window,
            )
            return
        self._dirty = False
        self._update_status()
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed")

    # ------------------------------------------------------------------
    # Export / Import / Inspect
    # ------------------------------------------------------------------
    def _on_export_class(self) -> None:
        from src.editor.portability import BDC_EXTENSION, write_class_bundle

        if self._current_key is None:
            messagebox.showinfo(
                "Export Class", "Select a class to export first.",
                parent=self.window,
            )
            return
        if self._dirty:
            self._on_save_click()
        class_name, spec_name = self._current_key
        cfg = self.loader.classes.get(class_name, spec_name) or {}

        default_name = f"{class_name}_{spec_name}".lower().replace(" ", "_") + BDC_EXTENSION
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Class",
            defaultextension=BDC_EXTENSION,
            initialfile=default_name,
            filetypes=[
                ("BDO Trainer class bundle", f"*{BDC_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            written = write_class_bundle(path, class_name, spec_name, cfg)
        except Exception as exc:
            messagebox.showerror(
                "Export Failed", f"Could not export bundle:\n{exc}", parent=self.window,
            )
            return
        messagebox.showinfo(
            "Export Complete",
            f"Exported {class_name} ({spec_name}) to:\n{written}",
            parent=self.window,
        )

    def _on_import_class(self) -> None:
        from src.editor.portability import (
            BDC_EXTENSION, BDT_EXTENSION,
            BundleError, read_bundle_from_file,
        )

        path = filedialog.askopenfilename(
            parent=self.window,
            title="Import Class Bundle",
            filetypes=[
                ("BDO Trainer class bundle", f"*{BDC_EXTENSION}"),
                ("BDO Trainer bundle (any)", f"*{BDC_EXTENSION} *{BDT_EXTENSION}"),
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
        if bundle.get("kind") != "class":
            messagebox.showwarning(
                "Wrong Bundle Type",
                "This file is a combo bundle (.bdt). Use the Combo Editor "
                "to import combos.",
                parent=self.window,
            )
            return

        class_name = bundle.get("class_name", "")
        spec_name = bundle.get("spec_name", "")
        cfg = bundle.get("config") or {}

        if (class_name, spec_name) in self.loader.class_configs:
            choice = messagebox.askyesnocancel(
                "Class Exists",
                f"{class_name} ({spec_name}) already exists.\n\n"
                "Yes → replace existing\n"
                "No  → rename and import as new\n"
                "Cancel → abort",
                parent=self.window,
            )
            if choice is None:
                return
            if choice is False:
                new_name = simpledialog.askstring(
                    "Rename Class", "New class name:",
                    initialvalue=class_name + " (Imported)",
                    parent=self.window,
                )
                if not new_name:
                    return
                class_name = new_name.strip()
                if (class_name, spec_name) in self.loader.class_configs:
                    messagebox.showerror(
                        "Rename Failed",
                        f"{class_name} ({spec_name}) also exists. Aborting.",
                        parent=self.window,
                    )
                    return

        # Strip any legacy combo / loadout sections; this importer is
        # skills-only.
        cfg_clean = {
            k: v for k, v in cfg.items()
            if k not in (
                "pve_combos", "pvp_combos", "movement_combos",
                "locked_skills", "hotbar_skills", "core_skill", "skill_addons",
            )
        }

        try:
            self.loader.classes.save(class_name, spec_name, cfg_clean)
            # Make sure there's at least a default bundle.
            if not self.loader.bundles.bundles_for_class(class_name, spec_name):
                self.loader.bundles.save_bundle(
                    class_name, spec_name, "default",
                    {"name": "Default", "description": ""},
                )
        except Exception as exc:
            logger.exception("Class import failed")
            messagebox.showerror(
                "Import Failed", f"Could not write class file:\n{exc}",
                parent=self.window,
            )
            return

        self._skill_copies.pop((class_name, spec_name), None)
        self._populate_sidebar()
        self._select_sidebar_key((class_name, spec_name))
        self._current_key = (class_name, spec_name)
        self._load_current()
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                logger.exception("on_save callback failed after import")
        messagebox.showinfo(
            "Import Complete",
            f"Imported {class_name} ({spec_name}).",
            parent=self.window,
        )

    def _on_inspect_bundle(self) -> None:
        from src.editor.combo_window import BundleInspectorDialog
        from src.editor.portability import (
            BDC_EXTENSION, BDT_EXTENSION,
            BundleError, read_bundle_from_file,
        )

        path = filedialog.askopenfilename(
            parent=self.window,
            title="Inspect Bundle",
            filetypes=[
                ("BDO Trainer bundles", f"*{BDC_EXTENSION} *{BDT_EXTENSION}"),
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
    # Lifecycle
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        if self._dirty and self._current_key is not None:
            cls_name, spec_name = self._current_key
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to {cls_name} — {spec_name} before closing?",
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
        ClassEditorWindow._instance = None
