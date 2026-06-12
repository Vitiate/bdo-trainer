"""Priority-mode editor for the Combo Editor.

Self-contained Tk frame that edits a combo's ``priority`` block — a
list of tiers, each with an ordered skill list. Used by
:mod:`src.editor.combo_editor` when the combo's ``mode`` is set to
``priority``.

Schema reference: ``docs/priority-combos.md``.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

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
    GOLD,
    GREEN,
    RED_SOFT,
)

logger = logging.getLogger("bdo_trainer")


class PriorityEditor(tk.Frame):
    """Tier + skill list editor for priority-mode combos."""

    def __init__(
        self,
        parent: tk.Widget,
        get_skills: Callable[[], Dict[str, dict]],
        on_change: Optional[Callable] = None,
    ) -> None:
        super().__init__(parent, bg=BG_DARK)
        self._get_skills = get_skills
        self._on_change = on_change

        # Source of truth — list of tier dicts:
        #   {"tier": "Highest Priority",
        #    "description": "Buffs / debuffs",
        #    "skills": [{"skill": ..., "note": ..., "boost_after": ...}, ...]}
        self._tiers: List[Dict[str, Any]] = []

        # Per-tier widget bookkeeping (rebuilt on every mutation).
        self._tier_widgets: List[Dict[str, Any]] = []

        self.columnconfigure(0, weight=1)
        self._container = tk.Frame(self, bg=BG_DARK)
        self._container.grid(row=0, column=0, sticky="ew", padx=4)
        self._container.columnconfigure(0, weight=1)

        add_tier = tk.Button(
            self,
            text="+ Add Tier",
            font=FONT,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._on_add_tier,
        )
        add_tier.grid(row=1, column=0, sticky="w", padx=8, pady=(8, 12))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self, priority: Optional[List[Any]]) -> None:
        """Replace the editor contents with *priority* (the combo's
        ``priority`` block; a list of tier dicts)."""
        self._tiers = []
        for tier in priority or []:
            if not isinstance(tier, dict):
                continue
            label = str(tier.get("tier", ""))
            desc = str(tier.get("description", ""))
            skills: List[Dict[str, Any]] = []
            for entry in tier.get("skills", []) or []:
                if isinstance(entry, str):
                    skills.append({"skill": entry})
                elif isinstance(entry, dict):
                    skills.append(dict(entry))
            self._tiers.append(
                {"tier": label, "description": desc, "skills": skills}
            )
        if not self._tiers:
            # Seed an empty Tier 1 so the user has a place to start.
            self._tiers.append(
                {"tier": "Highest Priority", "description": "", "skills": []}
            )
        self._rebuild()

    def collect(self) -> List[Dict[str, Any]]:
        """Read current widget state into a clean ``priority`` list
        suitable for writing to YAML."""
        out: List[Dict[str, Any]] = []
        self._sync_from_widgets()
        for tier in self._tiers:
            label = (tier.get("tier") or "").strip()
            description = (tier.get("description") or "").strip()
            skills_clean: List[Dict[str, Any]] = []
            for entry in tier.get("skills") or []:
                sid = (entry.get("skill") or "").strip()
                if not sid:
                    continue
                clean: Dict[str, Any] = {"skill": sid}
                note = (entry.get("note") or "").strip()
                if note:
                    clean["note"] = note
                # boost_after can be a string (single skill) or a list
                # (any-of). The GUI dropdown only edits the single
                # form; if the YAML has a list we preserve it
                # verbatim and skip the dropdown logic.
                raw_booster = entry.get("boost_after")
                if isinstance(raw_booster, list):
                    boosters = [b for b in raw_booster if isinstance(b, str) and b]
                    if boosters:
                        clean["boost_after"] = boosters
                else:
                    booster = (raw_booster or "").strip() if isinstance(raw_booster, str) else ""
                    if booster:
                        clean["boost_after"] = booster
                if "boost_after" in clean:
                    bw = entry.get("boost_window_ms")
                    try:
                        bw_int = int(bw) if bw not in (None, "") else None
                    except (TypeError, ValueError):
                        bw_int = None
                    if bw_int and bw_int > 0:
                        clean["boost_window_ms"] = bw_int
                    bt = entry.get("boost_to_tier")
                    try:
                        bt_int = int(bt) if bt not in (None, "") else None
                    except (TypeError, ValueError):
                        bt_int = None
                    if bt_int is not None:
                        clean["boost_to_tier"] = bt_int
                # Preserve advanced fields (requires_prev / prefers_after
                # families) the GUI doesn't surface, so editing a combo
                # in the UI doesn't strip them out.
                for adv in (
                    "requires_prev", "requires_window_ms",
                    "prefers_after", "prefers_window_ms", "prefers_to_tier",
                ):
                    if entry.get(adv) not in (None, ""):
                        clean[adv] = entry[adv]
                skills_clean.append(clean)
            tier_clean: Dict[str, Any] = {
                "tier": label or f"Tier {len(out) + 1}",
                "skills": skills_clean,
            }
            if description:
                tier_clean["description"] = description
            out.append(tier_clean)
        return out

    def clear(self) -> None:
        self._tiers = []
        self._rebuild()

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------
    def _on_add_tier(self) -> None:
        self._sync_from_widgets()
        self._tiers.append(
            {"tier": f"Tier {len(self._tiers) + 1}", "description": "", "skills": []}
        )
        self._rebuild()
        self._fire_change()

    def _on_remove_tier(self, idx: int) -> None:
        self._sync_from_widgets()
        if 0 <= idx < len(self._tiers):
            self._tiers.pop(idx)
        if not self._tiers:
            self._tiers.append(
                {"tier": "Highest Priority", "description": "", "skills": []}
            )
        self._rebuild()
        self._fire_change()

    def _on_move_tier(self, idx: int, direction: int) -> None:
        self._sync_from_widgets()
        new_idx = idx + direction
        if not (0 <= new_idx < len(self._tiers)):
            return
        self._tiers[idx], self._tiers[new_idx] = (
            self._tiers[new_idx],
            self._tiers[idx],
        )
        self._rebuild()
        self._fire_change()

    def _on_add_skill(self, tier_idx: int) -> None:
        self._sync_from_widgets()
        if 0 <= tier_idx < len(self._tiers):
            self._tiers[tier_idx]["skills"].append({"skill": ""})
        self._rebuild()
        self._fire_change()

    def _on_remove_skill(self, tier_idx: int, skill_idx: int) -> None:
        self._sync_from_widgets()
        if 0 <= tier_idx < len(self._tiers):
            skills = self._tiers[tier_idx]["skills"]
            if 0 <= skill_idx < len(skills):
                skills.pop(skill_idx)
        self._rebuild()
        self._fire_change()

    def _on_move_skill(self, tier_idx: int, skill_idx: int, direction: int) -> None:
        self._sync_from_widgets()
        if not (0 <= tier_idx < len(self._tiers)):
            return
        skills = self._tiers[tier_idx]["skills"]
        new_idx = skill_idx + direction
        if not (0 <= new_idx < len(skills)):
            return
        skills[skill_idx], skills[new_idx] = skills[new_idx], skills[skill_idx]
        self._rebuild()
        self._fire_change()

    # ------------------------------------------------------------------
    # Widget rebuild
    # ------------------------------------------------------------------
    def _sync_from_widgets(self) -> None:
        """Pull values from current widgets back into ``self._tiers``
        so the next rebuild starts from up-to-date state."""
        for tier_idx, w in enumerate(self._tier_widgets):
            if tier_idx >= len(self._tiers):
                continue
            tier = self._tiers[tier_idx]
            tier["tier"] = w["label_var"].get()
            tier["description"] = w["desc_var"].get()
            new_skills: List[Dict[str, Any]] = []
            for sw in w["skill_widgets"]:
                label = sw["skill_var"].get().strip()
                lbl_map = sw.get("skill_label_to_id") or {}
                sid = lbl_map.get(label, label)
                entry: Dict[str, Any] = {"skill": sid}
                note = sw["note_var"].get().strip()
                if note:
                    entry["note"] = note
                # boost_after — read directly from the picker's state.
                boost_state = sw.get("boost_state") or {}
                boost_ids = list(boost_state.get("ids") or [])
                if boost_ids:
                    entry["boost_after"] = (
                        boost_ids if len(boost_ids) > 1 else boost_ids[0]
                    )
                    bw = sw["boost_window_var"].get().strip()
                    if bw:
                        entry["boost_window_ms"] = bw
                # Carry over advanced fields the GUI didn't expose.
                for k, v in (sw.get("advanced") or {}).items():
                    if v not in (None, ""):
                        entry[k] = v
                new_skills.append(entry)
            tier["skills"] = new_skills

    def _rebuild(self) -> None:
        for child in self._container.winfo_children():
            child.destroy()
        self._tier_widgets = []

        skills = self._get_skills() or {}
        sorted_ids = sorted(
            skills.keys(),
            key=lambda sid: (skills[sid].get("name") or sid).lower(),
        )

        def label_for(sid: str) -> str:
            name = (skills.get(sid, {}) or {}).get("name", "").strip()
            return f"{name}  ({sid})" if name else sid

        label_to_id = {label_for(sid): sid for sid in sorted_ids}
        label_to_id[""] = ""  # allow a blank selection
        labels = list(label_to_id.keys())

        for tier_idx, tier in enumerate(self._tiers):
            self._build_tier(tier_idx, tier, labels, label_to_id)

    def _build_tier(
        self,
        tier_idx: int,
        tier: Dict[str, Any],
        labels: List[str],
        label_to_id: Dict[str, str],
    ) -> None:
        outer = tk.Frame(self._container, bg=BG_CARD, padx=8, pady=8)
        outer.grid(row=tier_idx, column=0, sticky="ew", pady=(0, 8))
        outer.columnconfigure(0, weight=1)

        # ---- Tier header --------------------------------------------------
        header = tk.Frame(outer, bg=BG_CARD)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        tk.Label(
            header,
            text=f"Tier {tier_idx + 1}",
            font=FONT_HEADING,
            fg=GOLD,
            bg=BG_CARD,
        ).grid(row=0, column=0, sticky="w")

        label_var = tk.StringVar(value=str(tier.get("tier", "")))
        label_entry = tk.Entry(
            header,
            textvariable=label_var,
            font=FONT_BOLD,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        )
        label_entry.grid(row=0, column=1, sticky="ew", padx=(8, 4))

        btns = tk.Frame(header, bg=BG_CARD)
        btns.grid(row=0, column=2, sticky="e")
        for text, cmd in (
            ("▲", lambda i=tier_idx: self._on_move_tier(i, -1)),
            ("▼", lambda i=tier_idx: self._on_move_tier(i, 1)),
            ("×", lambda i=tier_idx: self._on_remove_tier(i)),
        ):
            tk.Button(
                btns,
                text=text,
                width=2,
                font=FONT_SMALL,
                bg=BG_INPUT,
                fg=RED_SOFT if text == "×" else FG_TEXT,
                relief="flat",
                cursor="hand2",
                activebackground=ACCENT,
                activeforeground="#FFF",
                command=cmd,
            ).pack(side="left", padx=1)

        # ---- Description --------------------------------------------------
        desc_var = tk.StringVar(value=str(tier.get("description", "")))
        desc_row = tk.Frame(outer, bg=BG_CARD)
        desc_row.grid(row=1, column=0, sticky="ew", pady=(4, 4))
        desc_row.columnconfigure(1, weight=1)
        tk.Label(
            desc_row,
            text="Description:",
            font=FONT_SMALL,
            fg=FG_DIM,
            bg=BG_CARD,
        ).grid(row=0, column=0, sticky="w")
        tk.Entry(
            desc_row,
            textvariable=desc_var,
            font=FONT_SMALL,
            bg=BG_INPUT,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        # ---- Skills list --------------------------------------------------
        skills_frame = tk.Frame(outer, bg=BG_CARD)
        skills_frame.grid(row=2, column=0, sticky="ew", pady=(4, 4))

        skill_widgets: List[Dict[str, Any]] = []
        for skill_idx, entry in enumerate(tier.get("skills") or []):
            sw = self._build_skill_row(
                skills_frame,
                tier_idx,
                skill_idx,
                entry,
                labels,
                label_to_id,
            )
            skill_widgets.append(sw)

        tk.Button(
            outer,
            text="+ Add Skill",
            font=FONT_SMALL,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
            bd=0,
            padx=10,
            pady=2,
            cursor="hand2",
            command=lambda i=tier_idx: self._on_add_skill(i),
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))

        self._tier_widgets.append(
            {
                "label_var": label_var,
                "desc_var": desc_var,
                "skill_widgets": skill_widgets,
            }
        )

    def _build_skill_row(
        self,
        parent: tk.Widget,
        tier_idx: int,
        skill_idx: int,
        entry: Dict[str, Any],
        labels: List[str],
        label_to_id: Dict[str, str],
    ) -> Dict[str, Any]:
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=1)

        tk.Label(
            row,
            text=str(skill_idx + 1),
            width=3,
            bg=BG_CARD,
            fg=FG_DIM,
            font=FONT_SMALL,
        ).pack(side="left")

        # Skill dropdown
        current_id = entry.get("skill", "")
        if current_id and current_id not in {label_to_id[lbl] for lbl in labels}:
            stale_label = f"⚠  {current_id}  (missing)"
            labels = [stale_label, *labels]
            label_to_id = {**label_to_id, stale_label: current_id}
            initial = stale_label
        elif current_id:
            initial = next(
                (lbl for lbl, sid in label_to_id.items() if sid == current_id),
                current_id,
            )
        else:
            initial = ""
        skill_var = tk.StringVar(value=initial)
        skill_menu = tk.OptionMenu(row, skill_var, *labels)
        skill_menu.configure(
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT_SMALL,
            highlightthickness=0,
            width=22,
            relief="flat",
            activebackground=ACCENT,
            activeforeground="#FFF",
        )
        skill_menu["menu"].configure(bg=BG_INPUT, fg=FG_TEXT, font=FONT_SMALL)
        skill_menu.pack(side="left", padx=2)

        note_var = tk.StringVar(value=entry.get("note", ""))
        note_entry = tk.Entry(
            row,
            textvariable=note_var,
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT_SMALL,
            width=18,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        )
        note_entry.pack(side="left", padx=2)

        # Boost-after editor. Stores a list of skill ids; the button's
        # label summarises the current selection ("(none)", a single
        # name, or "Foo + N more"). Click opens a checkbox dialog.
        raw_booster = entry.get("boost_after", "")
        if isinstance(raw_booster, list):
            boost_ids: List[str] = [
                b for b in raw_booster if isinstance(b, str) and b
            ]
        elif isinstance(raw_booster, str) and raw_booster:
            boost_ids = [raw_booster]
        else:
            boost_ids = []
        boost_state: Dict[str, Any] = {"ids": boost_ids}

        def _label_for_state() -> str:
            ids = boost_state["ids"]
            if not ids:
                return "(none)"
            id_to_label = {sid: lbl for lbl, sid in label_to_id.items()}
            first = id_to_label.get(ids[0], ids[0])
            # Strip the "  (id)" suffix from the menu label for compactness.
            short = first.split("  (")[0]
            if len(ids) == 1:
                return short
            return f"{short}  +{len(ids) - 1}"

        boost_label_var = tk.StringVar(value=_label_for_state())

        def _open_picker() -> None:
            self._open_boost_picker(
                row,
                boost_state,
                label_to_id,
                boost_label_var,
                _label_for_state,
            )

        boost_menu = tk.Button(
            row,
            textvariable=boost_label_var,
            command=_open_picker,
            font=FONT_SMALL,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
            anchor="w",
            width=20,
            cursor="hand2",
        )
        boost_menu.pack(side="left", padx=(8, 2))

        boost_window_var = tk.StringVar(
            value=str(entry.get("boost_window_ms") or "")
        )
        bw_entry = tk.Entry(
            row,
            textvariable=boost_window_var,
            bg=BG_INPUT,
            fg=FG_TEXT,
            font=FONT_SMALL,
            width=6,
            insertbackground=FG_TEXT,
            relief="flat",
            bd=2,
        )
        bw_entry.pack(side="left", padx=1)
        tk.Label(
            row,
            text="ms",
            font=FONT_SMALL,
            fg=FG_DIM,
            bg=BG_CARD,
        ).pack(side="left", padx=(0, 4))

        # Reorder + delete buttons
        for text, cmd in (
            ("▲", lambda t=tier_idx, s=skill_idx: self._on_move_skill(t, s, -1)),
            ("▼", lambda t=tier_idx, s=skill_idx: self._on_move_skill(t, s, 1)),
            ("×", lambda t=tier_idx, s=skill_idx: self._on_remove_skill(t, s)),
        ):
            tk.Button(
                row,
                text=text,
                width=2,
                font=FONT_SMALL,
                bg=BG_INPUT,
                fg=RED_SOFT if text == "×" else FG_TEXT,
                relief="flat",
                cursor="hand2",
                activebackground=ACCENT,
                activeforeground="#FFF",
                command=cmd,
            ).pack(side="left", padx=1)

        # Stash advanced fields the GUI doesn't surface so a later
        # _sync_from_widgets() can preserve them.
        advanced = {
            k: entry.get(k)
            for k in (
                "requires_prev", "requires_window_ms",
                "prefers_after", "prefers_window_ms", "prefers_to_tier",
                "boost_to_tier",
            )
            if entry.get(k) not in (None, "")
        }
        return {
            "skill_var": skill_var,
            "note_var": note_var,
            "boost_state": boost_state,  # {"ids": [skill_id, ...]}
            "boost_window_var": boost_window_var,
            "skill_label_to_id": label_to_id,
            "advanced": advanced,
        }

    # ------------------------------------------------------------------
    # Notify host
    # ------------------------------------------------------------------
    def _fire_change(self) -> None:
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                logger.exception("PriorityEditor on_change callback failed")

    # ------------------------------------------------------------------
    # Boost-after multi-select picker
    # ------------------------------------------------------------------
    def _open_boost_picker(
        self,
        anchor_widget: tk.Widget,
        boost_state: Dict[str, Any],
        label_to_id: Dict[str, str],
        label_var: tk.StringVar,
        relabel: Callable[[], str],
    ) -> None:
        """Pop a small Toplevel with one checkbox per skill — the user
        ticks any number; on close the selection is written back to
        ``boost_state['ids']`` and the chip label refreshed."""
        win = tk.Toplevel(self.winfo_toplevel())
        win.title("Boost After — pick skills")
        win.transient(self.winfo_toplevel())
        try:
            win.grab_set()
        except tk.TclError:
            pass
        # Position near the button that opened us.
        try:
            x = anchor_widget.winfo_rootx()
            y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
            win.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        win.configure(bg=BG_DARK)

        tk.Label(
            win,
            text="Pick the skills whose cast should boost this row.",
            font=FONT_SMALL,
            fg=FG_DIM,
            bg=BG_DARK,
            anchor="w",
            wraplength=320,
        ).pack(fill="x", padx=10, pady=(8, 4))

        # Scrolling area — a frame inside a Canvas, with a vertical
        # scrollbar. Keeps the dialog compact when the bundle has 50+
        # skills.
        outer = tk.Frame(win, bg=BG_DARK)
        outer.pack(fill="both", expand=True, padx=10, pady=4)
        canvas = tk.Canvas(
            outer,
            bg=BG_DARK,
            highlightthickness=0,
            width=340,
            height=320,
        )
        canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        inner = tk.Frame(canvas, bg=BG_DARK)
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_resize(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_inner_resize)
        # Mouse-wheel scroll within the picker.
        def _on_wheel(event: tk.Event) -> None:
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        win.bind_all("<MouseWheel>", _on_wheel)

        sorted_labels = [lbl for lbl in label_to_id.keys() if lbl]
        sorted_labels.sort(key=str.lower)

        # Live state: skill_id → BooleanVar
        vars_by_id: Dict[str, tk.BooleanVar] = {}
        current = set(boost_state.get("ids") or [])
        for lbl in sorted_labels:
            sid = label_to_id[lbl]
            v = tk.BooleanVar(value=(sid in current))
            vars_by_id[sid] = v
            tk.Checkbutton(
                inner,
                text=lbl,
                variable=v,
                font=FONT_SMALL,
                fg=FG_TEXT,
                bg=BG_DARK,
                selectcolor=BG_INPUT,
                activebackground=BG_DARK,
                activeforeground=FG_TEXT,
                anchor="w",
                highlightthickness=0,
            ).pack(anchor="w", fill="x", padx=2, pady=0)

        # Buttons
        btn_row = tk.Frame(win, bg=BG_DARK)
        btn_row.pack(fill="x", padx=10, pady=(4, 10))

        def _clear_all() -> None:
            for v in vars_by_id.values():
                v.set(False)

        def _commit() -> None:
            boost_state["ids"] = [
                sid for sid, v in vars_by_id.items() if v.get()
            ]
            label_var.set(relabel())
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.unbind_all("<MouseWheel>")
            win.destroy()
            self._fire_change()

        def _cancel() -> None:
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.unbind_all("<MouseWheel>")
            win.destroy()

        tk.Button(
            btn_row,
            text="Clear all",
            command=_clear_all,
            font=FONT_SMALL,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
        ).pack(side="left")
        tk.Button(
            btn_row,
            text="Cancel",
            command=_cancel,
            font=FONT_SMALL,
            bg=BG_INPUT,
            fg=FG_TEXT,
            activebackground=ACCENT,
            activeforeground="#FFF",
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
        ).pack(side="right", padx=(4, 0))
        tk.Button(
            btn_row,
            text="OK",
            command=_commit,
            font=FONT_BOLD,
            bg=GREEN,
            fg="white",
            activebackground="#9CA600",
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=2,
            cursor="hand2",
        ).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", _cancel)
