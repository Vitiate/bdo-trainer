"""ChainRenderer — flowchart-style overlay for chain-mode priority combos.

Vertical two-column layout (this is the v1; a true horizontal flowchart
with edges between nodes is the intended end state — see
``docs/priority-combos.md`` chain mode section):

    Cursor (current chain step)        Frontier (legal next casts)
    ──────────────────────────         ─────────────────────────────
    ✓  Charmed                          ▶ Twirling Rhapsody  A+RMB  [ready]
    ✓  Hazy Path                        ▶ Foxflare Fleche     RMB   [ready]
       Twirling Rhapsody  ← cursor      ▶ Foxflare Ambush     F     [3.2s]
                                          Emberclaw Slash    Sh+LMB [ready]
                                          ...

The renderer subscribes to ``PriorityPlayer.on_chain_changed`` for
state updates. Each render produces a snapshot drawn under the
``chain`` canvas tag — fully cleared on every render.

Off-chain reset triggers a brief red overlay flash by checking
``state['reset_flash_at']`` against the current monotonic clock.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.overlay.renderer import (
    OUTLINE_COLOR,
    OUTLINE_OFFSETS,
    OverlayContext,
    OverlayRenderer,
)
from src.utils.keys import format_key_display

logger = logging.getLogger("bdo_trainer")

_TAG = "chain"
# Off-chain red flash fades over this much time after the reset.
_RESET_FLASH_MS = 350
# Frontier flash for the "next best" key chord.
_FLASH_PERIOD_MS = 600

_COL_GAP = 60          # px between cursor column and frontier column
_ROW_HEIGHT = 28       # px per row inside a column
_MAX_HISTORY_ROWS = 6  # cap how many cast-already entries we draw
_MAX_FRONTIER_ROWS = 8 # cap how many legal-next entries we draw

_CURSOR_COLOR = "#FFD700"     # gold — current chain head
_HISTORY_COLOR = "#888888"    # dim — already cast
_FRONTIER_COLOR = "#FFFFFF"   # white — legal next, off-cooldown
_FRONTIER_LOCKED_COLOR = "#666666"  # dim — legal but on cooldown
_KEY_COLOR = "#88DDFF"        # cyan — key chords
_FLASH_COLOR = "#FFFFCC"      # near-white pulse for the next-best skill
_RESET_COLOR = "#CC2030"      # red flash on off-chain reset
_HEADER_COLOR = "#FFD700"


class ChainRenderer:
    """Vertical two-column flowchart for chain-mode priority combos."""

    def __init__(
        self,
        ctx: OverlayContext,
        renderer: OverlayRenderer,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self._state: Optional[Dict[str, Any]] = None
        self._key_remap: Dict[str, str] = {}
        self._is_active: bool = False
        self._tick_after_id: Optional[str] = None
        # Subscribed by PriorityPlayer when chain mode is active.

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def show(self) -> None:
        self._is_active = True
        self._render(self._state)
        self._start_flash_tick()

    def hide(self) -> None:
        was_active = self._is_active
        self._is_active = False
        self._stop_flash_tick()
        self.renderer.clear(_TAG)
        if was_active:
            logger.debug("Chain renderer hidden")

    @property
    def is_active(self) -> bool:
        return self._is_active

    def set_key_remap(self, remap: Dict[str, str]) -> None:
        self._key_remap = remap
        if self._is_active:
            self._render(self._state)

    # ------------------------------------------------------------------
    # Subscription target
    # ------------------------------------------------------------------
    def on_chain_changed(self, state: Dict[str, Any]) -> None:
        """Hook called by PriorityPlayer whenever chain state changes
        (cast, reset, idle tick). Caller is on the Tk thread.
        """
        self._state = state
        if self._is_active:
            self._render(state)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _render(self, state: Optional[Dict[str, Any]]) -> None:
        self.renderer.clear(_TAG)
        if not self._is_active or not state or not state.get("active"):
            return
        ctx = self.ctx
        # Anchor near the regular combo overlay center, but offset
        # downward so the chain panel doesn't fight other overlays.
        cx, cy = ctx.cx, ctx.cy
        # Headers
        header_y = cy - 130
        self.renderer.draw_outlined_text(
            cx - 180, header_y, "CHAIN", ctx.input_font, _HEADER_COLOR,
            anchor="center", tag=_TAG,
        )
        self.renderer.draw_outlined_text(
            cx + 180, header_y, "NEXT", ctx.input_font, _HEADER_COLOR,
            anchor="center", tag=_TAG,
        )

        # Hard-CC budget readout — shown above the columns.
        max_hard = state.get("max_hard_cc", 0)
        hard = state.get("hard_count", 0)
        budget_text = f"Hard-CC: {hard}/{max_hard}"
        budget_color = (
            "#FF7777" if max_hard and hard >= max_hard
            else "#AAAAAA"
        )
        self.renderer.draw_outlined_text(
            cx, header_y - 22, budget_text, ctx.note_font, budget_color,
            anchor="center", tag=_TAG,
        )

        # ---- Left column: cursor + history --------------------------------
        history: List = state.get("history") or []
        rows = state.get("rows") or []
        rows_by_id = {r["id"]: r for r in rows}

        left_x = cx - 180
        y = header_y + 30
        # Show last N entries of history; the most-recent one is
        # the cursor and gets gold.
        recent = history[-_MAX_HISTORY_ROWS:]
        if not recent:
            self.renderer.draw_outlined_text(
                left_x, y, "(open with a Tier-0 skill)",
                ctx.note_font, _HISTORY_COLOR,
                anchor="center", tag=_TAG,
            )
        else:
            for i, (sid, _ts) in enumerate(recent):
                row = rows_by_id.get(sid)
                if not row:
                    continue
                is_cursor = (i == len(recent) - 1)
                color = _CURSOR_COLOR if is_cursor else _HISTORY_COLOR
                prefix = "▶ " if is_cursor else "✓ "
                name = row["name"]
                self.renderer.draw_outlined_text(
                    left_x, y, f"{prefix}{name}",
                    ctx.note_font, color,
                    anchor="center", tag=_TAG,
                )
                y += _ROW_HEIGHT

        # ---- Right column: frontier ---------------------------------------
        frontier_ids = state.get("frontier_ids") or []
        frontier_rows = [rows_by_id[i] for i in frontier_ids if i in rows_by_id]
        # Sort: tier (lower = higher priority) then declaration order
        # already implicit because rows are in tier order.
        frontier_rows = frontier_rows[:_MAX_FRONTIER_ROWS]

        right_x = cx + 180
        y = header_y + 30
        if not frontier_rows:
            self.renderer.draw_outlined_text(
                right_x, y, "(no legal next — all on cooldown / capped)",
                ctx.note_font, _FRONTIER_LOCKED_COLOR,
                anchor="center", tag=_TAG,
            )
        else:
            now_ms = int(time.monotonic() * 1000)
            phase = (now_ms // _FLASH_PERIOD_MS) % 2 == 0
            for i, row in enumerate(frontier_rows):
                # First row is the "best next" — flash its keys.
                is_best = (i == 0)
                key_text = self._format_keys(row["keys"])
                if row["keys_alt"]:
                    alt = self._format_keys(row["keys_alt"])
                    if alt and alt != key_text:
                        key_text = f"{key_text} / {alt}"
                name = row["name"]
                line = f"{name}    {key_text}"
                color = _FRONTIER_COLOR
                if is_best and phase:
                    color = _FLASH_COLOR
                self.renderer.draw_outlined_text(
                    right_x, y, line, ctx.note_font, color,
                    anchor="center", tag=_TAG,
                )
                y += _ROW_HEIGHT

        # ---- Off-chain reset flash overlay --------------------------------
        reset_at = state.get("reset_flash_at") or 0.0
        if reset_at > 0:
            elapsed_ms = (time.monotonic() - reset_at) * 1000.0
            if elapsed_ms < _RESET_FLASH_MS:
                # Draw a single big "OFF-CHAIN" banner at the bottom.
                t = max(0.0, 1.0 - (elapsed_ms / _RESET_FLASH_MS))
                # Fade — we can't change alpha on a Tk text item, but
                # we can short-circuit the draw once t hits zero.
                if t > 0.05:
                    self.renderer.draw_outlined_text(
                        cx, cy + 30,
                        "OFF-CHAIN — RESET",
                        ctx.skill_font,
                        _RESET_COLOR,
                        anchor="center",
                        tag=_TAG,
                    )

    # ------------------------------------------------------------------
    # Flash tick — drives the next-best frontier pulse + reset fade
    # ------------------------------------------------------------------
    def _start_flash_tick(self) -> None:
        if self._tick_after_id is not None:
            return
        self._tick_after_id = self.ctx.root.after(150, self._flash_tick)

    def _stop_flash_tick(self) -> None:
        if self._tick_after_id is not None:
            try:
                self.ctx.root.after_cancel(self._tick_after_id)
            except Exception:
                pass
            self._tick_after_id = None

    def _flash_tick(self) -> None:
        if not self._is_active:
            self._tick_after_id = None
            return
        if self._state and self._state.get("active"):
            self._render(self._state)
        self._tick_after_id = self.ctx.root.after(150, self._flash_tick)

    # ------------------------------------------------------------------
    # Key formatting helper (mirrors the priority player's)
    # ------------------------------------------------------------------
    def _format_keys(self, keys: List[str]) -> str:
        parts: List[str] = []
        for k in keys:
            canonical = str(k).lower()
            if canonical == "hotbar":
                return "Hotbar"
            physical = self._key_remap.get(canonical, canonical)
            parts.append(format_key_display(physical))
        return " + ".join(parts)
