"""CC Panel — list of CC skills with cooldown fade tracking.

Renders skills whose ``cc:`` list is non-empty, one row per skill:

    Skill Name      [CC tag, …]      Physical Keys

When the user presses the skill's keys the row dims to grey and the
underlying text "fills" left-to-right back to its original colour over
the skill's ``cooldown_ms`` window — a wipe-style cooldown bar.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.input_monitor import InputMonitor
from src.overlay.renderer import (
    OUTLINE_COLOR,
    OUTLINE_OFFSETS,
    OverlayContext,
    OverlayRenderer,
)
from src.utils.keys import format_key_display

logger = logging.getLogger("bdo_trainer")

POSITION_FILE = (
    Path(__file__).resolve().parent.parent.parent / "config" / "cc_panel_position.json"
)

_TICK_MS = 80    # cooldown wipe refresh rate while a skill is on cooldown
_IDLE_TICK_MS = 500  # tick rate while every CC skill is ready
_DIM_COLOR = "#3A3A3A"  # row colour while on cooldown
_TAG = "cc_panel"

# Strip trailing roman-numeral grade suffix from displayed skill names
# (e.g. "Glorious Advance IV" → "Glorious Advance"). The grade is just
# rank-up information; the panel is meant to be a glanceable list.
_ROMAN_SUFFIX_RE = re.compile(
    r"\s+(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI|XVII|XVIII|XIX|XX|XXI)$"
)


def _strip_grade(name: str) -> str:
    return _ROMAN_SUFFIX_RE.sub("", name).strip()


# CC tag → search keywords used to detect PvE/PvP qualifiers in skill notes.
_CC_KEYWORDS: Dict[str, List[str]] = {
    "stun": ["stun"],
    "stiffness": ["stiffness", "stiffen"],
    "knockdown": ["knockdown", "knock down", "knock-down"],
    "knockback": ["knockback", "knock back", "knock-back"],
    "floating": ["floating", "float "],
    "bound": ["bound"],
    "grab": ["grab", "grapple"],
    "pull": ["pull"],
    "push": ["push"],
    "down_attack": ["down attack", "down-attack"],
    "down_smash": ["down smash", "down-smash"],
    "air_attack": ["air attack", "air-attack"],
    "air_smash": ["air smash", "air-smash"],
    "freeze": ["freeze", "frozen"],
    "spin": ["spin"],
}


_QUALIFIER_RE = re.compile(r"\b(pve|pvp)\s*only\b")


def _classify_cc_modes(cc_tags: List[str], notes: str) -> Dict[str, str]:
    """Classify each CC tag as ``"both"``, ``"pve"`` (PvE-only), or
    ``"pvp"`` (PvP-only) based on phrasing in the skill notes.

    Strategy — find every "pve only" / "pvp only" qualifier in the notes
    and bind it to the nearest preceding CC keyword (within the same
    clause, bounded by the previous punctuation / qualifier). This
    handles patterns like::

        "Knockdown on hits (PvE only) Knockback on hits (PvP only)"

    where simple chunk-splitting wouldn't separate the two clauses.
    """
    out: Dict[str, str] = {tag: "both" for tag in cc_tags}
    if not notes:
        return out
    text = str(notes).lower()
    if "all cc pve only" in text or "all cc are pve only" in text:
        for tag in cc_tags:
            out[tag] = "pve"
        return out
    text = text.replace("(", " ").replace(")", " ")

    # Mark hard boundaries (.,;:- ) so a qualifier doesn't reach across them.
    boundary_positions = [-1] + [
        m.start() for m in re.finditer(r"[\.,;:]| - ", text)
    ]

    last_qualifier_end = 0
    for m in _QUALIFIER_RE.finditer(text):
        qualifier_mode = "pve" if m.group(1) == "pve" else "pvp"
        # Window: from the latest of (last qualifier end, last sentence
        # boundary before m) up to m.start().
        boundary = max(
            (b for b in boundary_positions if b < m.start()), default=-1
        )
        window_start = max(last_qualifier_end, boundary + 1)
        window = text[window_start : m.start()]
        for tag in cc_tags:
            if out[tag] != "both":
                continue
            for kw in _CC_KEYWORDS.get(tag, [tag.replace("_", " ")]):
                if kw in window:
                    out[tag] = qualifier_mode
                    break
        last_qualifier_end = m.end()
    return out

# Only show CC effects that bind / lock the target — knockdowns,
# knockbacks, stuns, stiffens, floats, grabs. Drop damage-only
# modifiers (down attack / down smash / air attack / air smash) and
# secondary tags (push, pull, freeze) — those don't pin a target for
# a follow-up cast and clutter the panel in PvP context.
_PVP_CC_TAGS = frozenset({
    "stun",
    "stiffness",
    "knockdown",
    "knockback",
    "floating",
    "bound",
    "grab",
})


_CC_LABEL = {
    "stun": "Stun",
    "stiffness": "Stiff",
    "knockdown": "KD",
    "knockback": "KB",
    "floating": "Float",
    "bound": "Bound",
    "grab": "Grab",
    "pull": "Pull",
    "push": "Push",
    "down_attack": "DA",
    "down_smash": "DS",
    "air_attack": "AA",
    "air_smash": "AS",
    "freeze": "Freeze",
}

_CC_COLOR = {
    "stun": "#FF8C00",
    "stiffness": "#FFAA66",
    "knockdown": "#FF5555",
    "knockback": "#FF7777",
    "floating": "#88DDFF",
    "bound": "#9966FF",
    "grab": "#FFD700",
    "pull": "#66CCAA",
    "push": "#66AACC",
    "down_attack": "#CCCCCC",
    "down_smash": "#FFFFFF",
    "air_attack": "#CCCCCC",
    "air_smash": "#FFFFFF",
    "freeze": "#AADDFF",
}


def _format_keys(keys: List[str], remap: Dict[str, str]) -> str:
    """Format a key list as ``Shift + LMB`` etc., applying the user's remap."""
    parts: List[str] = []
    for k in keys:
        canonical = str(k).lower()
        if canonical == "hotbar":
            return "Hotbar"
        if canonical == "direction":
            parts.append("Dir")
            continue
        physical = remap.get(canonical, canonical)
        parts.append(format_key_display(physical))
    return " + ".join(parts)


class CCPanel:
    """Side panel listing the active class's CC skills with cooldown fade."""

    def __init__(
        self,
        ctx: OverlayContext,
        renderer: OverlayRenderer,
        input_monitor: InputMonitor,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self.input_monitor = input_monitor

        self._active: bool = False
        self._skills: List[Dict[str, Any]] = []
        self._key_remap: Dict[str, str] = {}
        # skill_id → trigger timestamp (monotonic seconds). 0 = idle.
        self._triggered_at: Dict[str, float] = {}
        # skill_id → cooldown_ms
        self._cooldowns: Dict[str, int] = {}
        # Per-row visual bookkeeping. For each skill_id we store:
        #   "fragments": [
        #       {"text": str, "color": str,
        #        "bright_id": int, "outline_ids": [int, ...]}, ...
        #   ]
        # The bright item shows a leading substring of the fragment's text
        # (matching the wipe progress), the dim text underneath shows the
        # full fragment string in grey while on cooldown. While idle the
        # bright item shows the full text and the dim item is hidden.
        self._row_state: Dict[str, Dict[str, Any]] = {}

        # Anchor (mutable) — top-left of the panel block.
        self.px: int = 60
        self.py: int = 200

        # Reposition / drag
        self._reposition: bool = False
        self._drag_last: Tuple[int, int] = (0, 0)

        # Cooldown wipe ticker
        self._tick_after_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self._active

    def set_key_remap(self, remap: Dict[str, str]) -> None:
        self._key_remap = remap
        if self._active:
            self.refresh()

    def show(
        self,
        skills: Dict[str, Dict[str, Any]],
        spec_skill_ids: Optional[set] = None,
    ) -> None:
        """Display the panel for the given class's skill dict.

        ``spec_skill_ids`` is an optional allowlist of skill ids the
        active spec actually owns — when provided, only those skills
        are shown. Lets us drop the awakening / succession leakage
        that arises when a class's data file carries both kits.
        """
        self._collect_cc_skills(skills, spec_skill_ids)
        self._active = True
        self.load_position()
        self._render()
        self._arm_taps()
        self._start_tick()
        logger.info(f"CC panel shown ({len(self._skills)} skills)")

    def hide(self) -> None:
        was_active = self._active
        self._active = False
        self._stop_tick()
        self._disarm_taps()
        self.renderer.clear(_TAG)
        self._row_state.clear()
        self._triggered_at.clear()
        if was_active:
            logger.info("CC panel hidden")

    def refresh(self) -> None:
        """Re-render the panel using the current skills (e.g. after key remap)."""
        if not self._active:
            return
        self._render()
        self._arm_taps()

    def update_class(
        self,
        skills: Dict[str, Dict[str, Any]],
        spec_skill_ids: Optional[set] = None,
    ) -> None:
        """Swap the displayed class without changing visibility."""
        self._collect_cc_skills(skills, spec_skill_ids)
        self._triggered_at.clear()
        if self._active:
            self._render()
            self._arm_taps()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _collect_cc_skills(
        self,
        skills: Dict[str, Dict[str, Any]],
        spec_skill_ids: Optional[set] = None,
    ) -> None:
        rows: List[Dict[str, Any]] = []
        for skill_id, info in (skills or {}).items():
            if not isinstance(info, dict):
                continue
            # Spec-scope filter — drop skills the active spec doesn't
            # own (Maegu Succession's data file carries the awakening
            # kit too because BDOCodex seeded both).
            if spec_skill_ids is not None and skill_id not in spec_skill_ids:
                continue
            cc = info.get("cc") or []
            if not cc:
                continue
            # PvP / "binds" filter — only show skills with at least one
            # actual binding CC effect. Drop pure damage modifiers
            # (down attack / down smash / air attack / air smash) and
            # secondary tags (push / pull / freeze) that don't lock
            # a target in place.
            cc_tags = [str(c) for c in cc]
            if not any(t in _PVP_CC_TAGS for t in cc_tags):
                continue
            keys = info.get("keys") or []
            keys_alt = info.get("keys_alt") or []
            cooldown_ms = int(info.get("cooldown_ms") or 0)
            raw_name = info.get("name", skill_id.replace("_", " ").title())
            cc_modes = _classify_cc_modes(cc_tags, info.get("notes", ""))
            rows.append({
                "id": skill_id,
                "name": _strip_grade(raw_name),
                "cc": cc_tags,
                "cc_modes": cc_modes,
                "keys": list(keys),
                "keys_alt": list(keys_alt) if keys_alt else [],
                "cooldown_ms": cooldown_ms,
            })
        rows.sort(key=lambda r: (r["cooldown_ms"] == 0, r["name"].lower()))
        self._skills = rows
        self._cooldowns = {r["id"]: r["cooldown_ms"] for r in rows}

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render(self) -> None:
        self.renderer.clear(_TAG)
        self._row_state.clear()

        ctx = self.ctx
        x = self.px
        y = self.py

        # Header — outlined like the rest of the overlay.
        self.renderer.draw_outlined_text(
            x, y, "CC Skills", ctx.input_font, ctx.skill_color,
            anchor="nw", tag=_TAG,
        )
        y += 36

        if not self._skills:
            self.renderer.draw_outlined_text(
                x, y, "(no CC skills for this class)",
                ctx.note_font, ctx.note_color, anchor="nw", tag=_TAG,
            )
            return

        # Compute column widths from actual text so name + cc + keys
        # never overlap regardless of font.
        gap = 24
        name_font = ctx.input_font
        cc_font = ctx.note_font
        keys_font = ctx.input_font

        def _row_strings(row: Dict[str, Any]) -> Tuple[str, str, str]:
            name = row["name"]
            cc_modes: Dict[str, str] = row.get("cc_modes", {})
            tag_strs: List[str] = []
            for c in row["cc"]:
                # Skip non-binding tags in the rendered text — we
                # already filtered the row in by *some* PvP tag
                # being present, but the row may also carry damage
                # modifiers we don't want to clutter the display.
                if c not in _PVP_CC_TAGS:
                    continue
                base = _CC_LABEL.get(c, c.title())
                mode = cc_modes.get(c, "both")
                if mode == "pve":
                    tag_strs.append(f"{base} (PvE)")
                elif mode == "pvp":
                    tag_strs.append(f"{base} (PvP)")
                else:
                    tag_strs.append(base)
            cc_text = "  ".join(tag_strs)
            key_text = _format_keys(row["keys"], self._key_remap)
            if row["keys_alt"]:
                alt = _format_keys(row["keys_alt"], self._key_remap)
                if alt and alt != key_text:
                    key_text = f"{key_text}  /  {alt}"
            return name, cc_text, key_text

        rendered = [(_row_strings(r), r) for r in self._skills]

        name_w = max(name_font.measure(s[0]) for s, _ in rendered)
        cc_w = max(cc_font.measure(s[1]) for s, _ in rendered)
        cc_x = x + name_w + gap
        keys_x = cc_x + cc_w + gap

        # Row height = the tallest font's linespace + a few pixels.
        row_h = max(name_font.metrics("linespace"), keys_font.metrics("linespace")) + 6

        for (name_text, cc_text, key_text), row in rendered:
            skill_id = row["id"]
            primary_cc = row["cc"][0] if row["cc"] else ""
            cc_color = _CC_COLOR.get(primary_cc, ctx.note_color)

            fragments: List[Dict[str, Any]] = [
                self._draw_fragment(x, y, name_text, name_font, ctx.input_color),
                self._draw_fragment(cc_x, y, cc_text, cc_font, cc_color),
                self._draw_fragment(keys_x, y, key_text, keys_font, ctx.input_color),
            ]
            self._row_state[skill_id] = {"fragments": fragments}
            y += row_h

    def _draw_fragment(
        self,
        x: int,
        y: int,
        text: str,
        font,
        color: str,
    ) -> Dict[str, Any]:
        """Draw an outlined-text fragment that supports left-to-right wipe.

        The bright text item starts showing the full string (idle state).
        While on cooldown, ``_apply_progress`` swaps in a dim text item
        underneath and shortens the bright item's text to a leading
        substring proportional to wipe progress.
        """
        canvas = self.ctx.canvas

        outline_ids: List[int] = []
        for dx, dy in OUTLINE_OFFSETS:
            outline_ids.append(canvas.create_text(
                x + dx, y + dy, text=text, font=font,
                fill=OUTLINE_COLOR, anchor="nw", tags=(_TAG,),
            ))

        dim_id = canvas.create_text(
            x, y, text=text, font=font, fill=_DIM_COLOR, anchor="nw",
            tags=(_TAG,), state="hidden",
        )
        bright_id = canvas.create_text(
            x, y, text=text, font=font, fill=color, anchor="nw",
            tags=(_TAG,),
        )
        return {
            "x": x,
            "y": y,
            "text": text,
            "font": font,
            "color": color,
            "bright_id": bright_id,
            "dim_id": dim_id,
            "outline_ids": outline_ids,
        }

    # ------------------------------------------------------------------
    # Cooldown tap + fade
    # ------------------------------------------------------------------
    def _arm_taps(self) -> None:
        self._disarm_taps()
        for row in self._skills:
            keys = row["keys"]
            if not keys or "hotbar" in [str(k).lower() for k in keys]:
                # Hotbar-only skills have no fixed physical key; skip.
                continue
            primary = self._remap_keys(keys)
            key_sets: List[List[str]] = []
            if primary:
                key_sets.append(primary)
            if row["keys_alt"]:
                alt = self._remap_keys(row["keys_alt"])
                if alt:
                    key_sets.append(alt)
            if not key_sets:
                continue
            sid = row["id"]
            tap_name = f"cc_panel:{sid}"
            self.input_monitor.add_tap(
                tap_name,
                key_sets,
                on_match=self._make_trigger(sid),
            )

    def _disarm_taps(self) -> None:
        for row in self._skills:
            self.input_monitor.remove_tap(f"cc_panel:{row['id']}")

    def _remap_keys(self, keys: List[str]) -> List[str]:
        return [
            self._key_remap.get(str(k).lower(), str(k).lower())
            for k in keys
            if str(k).lower() != "hotbar"
        ]

    def _make_trigger(self, skill_id: str) -> Callable[[], None]:
        def _fire() -> None:
            # Marshal back to the Tk thread.
            self.ctx.root.after(0, lambda: self._trigger(skill_id))
        return _fire

    def _trigger(self, skill_id: str) -> None:
        if not self._active:
            return
        self._triggered_at[skill_id] = time.monotonic()
        # Force an immediate redraw — clear last_cut so _apply_progress
        # doesn't short-circuit if the same skill was just on cooldown.
        state = self._row_state.get(skill_id)
        if state:
            for frag in state["fragments"]:
                frag.pop("last_cut", None)
        self._apply_progress(skill_id, 0.0)

    def _apply_progress(self, skill_id: str, progress: float) -> None:
        """Update the row's wipe state. *progress* is 0.0 (just triggered,
        all dim) → 1.0 (fully recovered, all bright). Skips the
        itemconfigure call when the visible cut for a fragment hasn't
        changed since the previous tick — keeps the tick handler cheap
        when the cooldown bar isn't visibly moving."""
        state = self._row_state.get(skill_id)
        if not state:
            return
        canvas = self.ctx.canvas
        progress = max(0.0, min(1.0, progress))
        for frag in state["fragments"]:
            full_text = frag["text"]
            n = len(full_text)
            if progress >= 1.0:
                if frag.get("last_cut") == n:
                    continue
                try:
                    canvas.itemconfigure(frag["dim_id"], state="hidden")
                    canvas.itemconfigure(
                        frag["bright_id"], text=full_text, state="normal",
                    )
                except Exception:
                    pass
                frag["last_cut"] = n
                continue
            cut = int(round(n * progress))
            if frag.get("last_cut") == cut:
                continue
            try:
                canvas.itemconfigure(frag["dim_id"], state="normal")
                if cut <= 0:
                    canvas.itemconfigure(frag["bright_id"], state="hidden")
                else:
                    canvas.itemconfigure(
                        frag["bright_id"],
                        text=full_text[:cut],
                        state="normal",
                    )
            except Exception:
                pass
            frag["last_cut"] = cut

    def _start_tick(self) -> None:
        if self._tick_after_id is not None:
            return
        self._tick_after_id = self.ctx.root.after(_TICK_MS, self._tick)

    def _stop_tick(self) -> None:
        if self._tick_after_id is not None:
            try:
                self.ctx.root.after_cancel(self._tick_after_id)
            except Exception:
                pass
            self._tick_after_id = None

    def _tick(self) -> None:
        if not self._active:
            self._tick_after_id = None
            return
        now = time.monotonic()
        finished: List[str] = []
        for sid, started in self._triggered_at.items():
            cd_ms = self._cooldowns.get(sid, 0)
            if cd_ms <= 0:
                finished.append(sid)
                continue
            elapsed_ms = (now - started) * 1000.0
            if elapsed_ms >= cd_ms:
                finished.append(sid)
                continue
            self._apply_progress(sid, elapsed_ms / float(cd_ms))
        for sid in finished:
            self._apply_progress(sid, 1.0)
            self._triggered_at.pop(sid, None)
        # Adaptive tick rate — the only reason we re-render is to step
        # the cooldown wipe, so when nothing's on cooldown we can drop
        # to a lazy idle interval and still respond to a press fast
        # (a press calls _trigger which immediately resets the cut).
        next_ms = _TICK_MS if self._triggered_at else _IDLE_TICK_MS
        self._tick_after_id = self.ctx.root.after(next_ms, self._tick)

    # ------------------------------------------------------------------
    # Reposition (drag) — driven by RepositionHandler when active
    # ------------------------------------------------------------------
    def begin_reposition(self) -> None:
        self._reposition = True

    def end_reposition(self) -> None:
        if not self._reposition:
            return
        self._reposition = False
        self.save_position()

    def offset(self, dx: int, dy: int) -> None:
        self.px += dx
        self.py += dy
        if self._active:
            try:
                self.ctx.canvas.move(_TAG, dx, dy)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def load_position(self) -> None:
        try:
            with open(POSITION_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            rx = data.get("rx")
            ry = data.get("ry")
            if rx is not None and ry is not None:
                self.px = int(float(rx) * self.ctx.screen_w)
                self.py = int(float(ry) * self.ctx.screen_h)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning(f"Could not load CC panel position: {exc}")

    def save_position(self) -> None:
        rx = self.px / self.ctx.screen_w
        ry = self.py / self.ctx.screen_h
        try:
            POSITION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(POSITION_FILE, "w", encoding="utf-8") as fh:
                json.dump({"rx": round(rx, 6), "ry": round(ry, 6)}, fh)
        except Exception as exc:
            logger.warning(f"Could not save CC panel position: {exc}")
