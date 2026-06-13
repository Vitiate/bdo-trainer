"""ChainRenderer — horizontal "priority reel" for chain-mode combos.

All skills in the combo are laid out in a single horizontal row.
The leftmost slot is a fixed **highlight box** at the overlay
centre — whichever skill currently ranks #1 by the player's
frontier sort (CC weight + PvP damage + smash bonus) lives there.
Everything else trails off to the right.

When the priority order changes (a cast goes on cooldown, a smash
window opens, a chain advances), each card eases toward its new
slot. The cumulative motion looks like a wheel spinning — cards
slide through intermediate slots over ~5 frames at the 150 ms
tick rate.

Visual layers, drawn back-to-front:
- Reel cards (icon + name + key chord), each with its own animated x.
- Highlight box (rounded outline at slot 0, always at ctx.cx).
- Drain ring around the highlight box for the most-recently-cast
  skill — visualises remaining CC lock time on the target.
- Off-chain reset banner (briefly drawn after a wrong key).

Icons come from :mod:`src.overlay.icons`; missing icons fall back
to a text-only card so the renderer still works without the icon
repo.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.overlay.icons import IconLoader
from src.overlay.renderer import OverlayContext, OverlayRenderer
from src.utils.keys import format_key_display

logger = logging.getLogger("bdo_trainer")

_TAG = "chain"
_RESET_FLASH_MS = 350
_FLASH_PERIOD_MS = 600

# Layout — pixel constants (most scale implicitly with icon size).
_NODE_PAD = 8         # px around the icon inside a card
_LABEL_GAP = 4
_KEY_GAP = 4
# Default per-card spacing along the reel (renderer override
# wired through the existing column_gap setting).
_DEFAULT_SLOT_GAP = 28
# Maximum number of cards drawn to the left/right of the
# highlight slot. Cards past this fade out + clip; keeps the reel
# from running off-screen on very long chains.
_VISIBLE_RIGHT = 8
_VISIBLE_LEFT = 4

# Highlight-box padding around a card — its rounded outline sits
# this many extra pixels out from the card art on every side.
_HIGHLIGHT_PAD = 6

# Per-frame easing fraction for the slide animation. 0.30 lands in
# ~6 frames at the 150 ms tick rate.
_SLIDE_LERP = 0.30
# Below this px-distance from target we snap, otherwise tiny
# residuals never settle.
_SNAP_PX = 0.5

# Dim factors for icon alpha by reel position / state.
_DIM_HIGHLIGHT = 1.0    # in the highlight box
_DIM_NEAR = 0.85        # one or two slots away
_DIM_MID = 0.55         # mid reel
_DIM_FAR = 0.25         # far edges
_DIM_HISTORY = 0.20     # off-cooldown but recently cast → drifts right

# Colours
_HIGHLIGHT_FRAME = "#FFD700"     # highlight box outline (gold)
_HIGHLIGHT_FRAME_BUFF = "#66E0FF"  # cyan when the #1 is a buff
_DRAIN_DIM = "#3A3A3A"
_LABEL_DIM = "#777777"
_LABEL_LIT = "#FFFFFF"
_LABEL_HIGHLIGHT = "#FFD700"
_KEY_COLOR = "#88DDFF"
_KEY_FLASH = "#FFFFCC"
_HEADER_COLOR = "#FFD700"
_RESET_COLOR = "#CC2030"

# Rounded-rect perimeter sampling for the highlight box.
_PERIMETER_SAMPLES = 80
_CORNER_RADIUS_FRAC = 0.22


def _rounded_rect_perimeter(
    cx: int, cy: int, half_w: int, half_h: int, radius: int,
) -> List[Tuple[float, float]]:
    """Return ``_PERIMETER_SAMPLES`` (x, y) points walking the
    perimeter of a rounded rectangle clockwise, starting at 12
    o'clock. Supports asymmetric width / height so the highlight
    box can be wider than tall.
    """
    left = cx - half_w + radius
    right = cx + half_w - radius
    top = cy - half_h + radius
    bottom = cy + half_h - radius

    side_h = 2 * (half_w - radius)
    side_v = 2 * (half_h - radius)
    arc_len = (math.pi / 2) * radius
    total_len = 2 * side_h + 2 * side_v + 4 * arc_len

    out: List[Tuple[float, float]] = []
    half_top = side_h / 2.0
    for i in range(_PERIMETER_SAMPLES):
        s = (i / _PERIMETER_SAMPLES) * total_len
        if s < half_top:
            x = cx + s
            y = cy - half_h
        elif s < half_top + arc_len:
            a = (s - half_top) / radius
            x = right + radius * math.sin(a)
            y = top - radius * math.cos(a)
        elif s < half_top + arc_len + side_v:
            x = cx + half_w
            y = top + (s - half_top - arc_len)
        elif s < half_top + arc_len + side_v + arc_len:
            a = (s - half_top - arc_len - side_v) / radius
            x = right + radius * math.cos(a)
            y = bottom + radius * math.sin(a)
        elif s < half_top + arc_len + side_v + arc_len + side_h:
            x = right - (
                s - half_top - arc_len - side_v - arc_len
            )
            y = cy + half_h
        elif (s
              < half_top + arc_len + side_v + arc_len + side_h
              + arc_len):
            a = (
                s - half_top - arc_len - side_v - arc_len - side_h
            ) / radius
            x = left - radius * math.sin(a)
            y = bottom + radius * math.cos(a)
        elif (s
              < half_top + arc_len + side_v + arc_len + side_h
              + arc_len + side_v):
            x = cx - half_w
            y = bottom - (
                s - half_top - arc_len - side_v - arc_len
                - side_h - arc_len
            )
        elif (s
              < half_top + arc_len + side_v + arc_len + side_h
              + arc_len + side_v + arc_len):
            a = (
                s - half_top - arc_len - side_v - arc_len
                - side_h - arc_len - side_v
            ) / radius
            x = left - radius * math.cos(a)
            y = top - radius * math.sin(a)
        else:
            x = cx - (
                s - half_top - arc_len - side_v - arc_len
                - side_h - arc_len - side_v - arc_len
            )
            y = cy - half_h
        out.append((x, y))
    return out


class ChainRenderer:
    """Horizontal priority reel for chain-mode combos."""

    def __init__(
        self,
        ctx: OverlayContext,
        renderer: OverlayRenderer,
        icon_size_provider: Optional[Callable[[], int]] = None,
        column_gap_provider: Optional[Callable[[], int]] = None,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self._icon_size_provider = icon_size_provider or (lambda: 36)
        # Reuse the existing "column gap" slider for slot spacing —
        # users already have it wired and the semantics are similar
        # enough (horizontal padding between cards).
        self._column_gap_provider = (
            column_gap_provider or (lambda: _DEFAULT_SLOT_GAP)
        )
        self._icons = IconLoader(size_px=self._icon_size_provider())
        self._state: Optional[Dict[str, Any]] = None
        self._key_remap: Dict[str, str] = {}
        self._is_active: bool = False
        self._tick_after_id: Optional[str] = None
        # Per-skill animated x position. Eases toward the target
        # slot position each render tick.
        self._anim_x: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def show(self) -> None:
        self._icons.set_size(self._icon_size_provider())
        self._is_active = True
        # Reset animation state so cards don't ease in from
        # wherever they happened to be last hide.
        self._anim_x.clear()
        self._render(self._state)
        self._start_flash_tick()

    def hide(self) -> None:
        was_active = self._is_active
        self._is_active = False
        self._stop_flash_tick()
        self.renderer.clear(_TAG)
        canvas = self.ctx.canvas
        if hasattr(canvas, "_chain_icon_refs"):
            canvas._chain_icon_refs = []  # type: ignore[attr-defined]
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
        self._state = state
        if self._is_active:
            self._render(state)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _render(self, state: Optional[Dict[str, Any]]) -> None:
        self.renderer.clear(_TAG)
        canvas = self.ctx.canvas
        canvas._chain_icon_refs = []  # type: ignore[attr-defined]

        if not self._is_active or not state or not state.get("active"):
            return
        ctx = self.ctx
        rows: List[Dict[str, Any]] = state.get("rows") or []
        if not rows:
            return

        # ---- Layout sizes --------------------------------------------------
        self._icons.set_size(self._icon_size_provider())
        slot_gap = max(8, int(self._column_gap_provider()) // 4)
        node_size = self._icons.size_px + _NODE_PAD * 2
        slot_w = node_size + slot_gap
        line_h = ctx.note_font.metrics("linespace")
        card_h = (
            node_size
            + _LABEL_GAP + line_h         # name label
            + _KEY_GAP + line_h           # key chord
        )

        highlight_x = ctx.cx
        highlight_y = ctx.cy + 30 + node_size // 2

        # ---- Build the priority order list --------------------------------
        # Ordered list: frontier_ids first (already score-sorted by
        # the player), then everything else (cooldown / blocked) in
        # declaration order so the eye has a stable reference point.
        rows_by_id: Dict[str, Dict[str, Any]] = {r["id"]: r for r in rows}
        frontier_ids: List[str] = list(state.get("frontier_ids") or [])
        ordered_ids: List[str] = []
        seen: set = set()
        for sid in frontier_ids:
            if sid in rows_by_id and sid not in seen:
                ordered_ids.append(sid)
                seen.add(sid)
        for row in rows:
            if row["id"] not in seen:
                ordered_ids.append(row["id"])
                seen.add(row["id"])

        # ---- Compute target x per skill -----------------------------------
        target_x: Dict[str, float] = {}
        for slot_idx, sid in enumerate(ordered_ids):
            target_x[sid] = float(highlight_x + slot_idx * slot_w)

        # ---- Ease animated x toward target --------------------------------
        for sid, tx in target_x.items():
            cur = self._anim_x.get(sid)
            if cur is None:
                # First time we've seen this id — drop in at target
                # so a fresh combo doesn't sweep all icons across
                # the screen.
                self._anim_x[sid] = tx
                continue
            delta = tx - cur
            if abs(delta) <= _SNAP_PX:
                self._anim_x[sid] = tx
            else:
                self._anim_x[sid] = cur + delta * _SLIDE_LERP
        # Drop anim entries for skills that aren't in the row set
        # any more (combo swap).
        for sid in list(self._anim_x.keys()):
            if sid not in target_x:
                del self._anim_x[sid]

        # ---- Header (CC budget) -------------------------------------------
        max_hard = state.get("max_hard_cc", 0)
        hard = state.get("hard_count", 0)
        budget_text = f"Hard-CC: {hard}/{max_hard}"
        budget_color = (
            "#FF7777" if max_hard and hard >= max_hard
            else "#AAAAAA"
        )
        self.renderer.draw_outlined_text(
            ctx.cx, highlight_y - node_size // 2 - line_h - 18,
            budget_text, ctx.note_font, budget_color,
            anchor="center", tag=_TAG,
        )

        # ---- Highlight box -------------------------------------------------
        # Drawn before the cards so it sits behind whichever card is
        # currently in slot 0.
        cls_slug = state.get("class_slug") or ""
        roles: Dict[str, str] = state.get("roles") or {}
        history: List[Tuple[str, float]] = state.get("history") or []
        history_ids = {sid for sid, _ts in history}
        cursor_id = state.get("cursor")
        lock_seconds: Dict[str, float] = state.get("lock_seconds") or {}

        top_id = ordered_ids[0] if ordered_ids else None
        top_role = roles.get(top_id or "", "filler")

        # Highlight box geometry: enough room around a card (icon
        # plus the two text lines) so a fully-rendered card fits
        # cleanly inside.
        box_half_w = (node_size // 2) + _HIGHLIGHT_PAD
        box_half_h = (card_h // 2) + _HIGHLIGHT_PAD
        # Centre vertically on the card centre (which is offset from
        # icon centre by half the text block).
        text_block_h = (_LABEL_GAP + line_h) + (_KEY_GAP + line_h)
        box_cy = highlight_y + text_block_h // 2

        radius = max(6, int(node_size * _CORNER_RADIUS_FRAC))
        perim = _rounded_rect_perimeter(
            highlight_x, box_cy, box_half_w, box_half_h, radius,
        )
        frame_color = (
            _HIGHLIGHT_FRAME_BUFF
            if top_role == "pre_buff"
            else _HIGHLIGHT_FRAME
        )

        # Drain ring on the highlight box if the cursor is currently
        # locking the target. Visualises remaining CC duration
        # clockwise from 12 o'clock; falls back to a static frame
        # when no cast is active.
        now = time.monotonic()
        cursor_lock_remaining = 0.0
        if cursor_id and cursor_id in lock_seconds:
            cast_ts = next(
                (ts for sid, ts in reversed(history) if sid == cursor_id),
                None,
            )
            if cast_ts is not None:
                lock_total = lock_seconds[cursor_id]
                if lock_total > 0:
                    elapsed = max(0.0, now - cast_ts)
                    cursor_lock_remaining = max(
                        0.0, min(1.0, 1.0 - (elapsed / lock_total)),
                    )
        if cursor_lock_remaining > 0:
            self._draw_drain_perim(
                perim, cursor_lock_remaining, frame_color, 4,
            )
        else:
            self._draw_static_perim(perim, frame_color, 3)

        # ---- Draw cards in z-order: far → near so the highlight
        # ----  card sits on top if any visual overlap occurs. -------------
        now_ms = int(time.monotonic() * 1000)
        flash_phase = (now_ms // _FLASH_PERIOD_MS) % 2 == 0

        # Reverse so slot 0 (highlight) draws last → on top.
        for slot_idx in range(len(ordered_ids) - 1, -1, -1):
            sid = ordered_ids[slot_idx]
            row = rows_by_id[sid]
            x = self._anim_x[sid]
            # Off-screen / far-edge clipping — we still update anim
            # but skip the draw past the visibility window.
            if slot_idx > _VISIBLE_RIGHT:
                continue
            dim = self._dim_for_slot(
                slot_idx,
                is_history=(sid in history_ids and sid != cursor_id),
            )
            is_top = (slot_idx == 0)
            self._draw_card(
                cls_slug, row,
                cx=int(round(x)),
                cy=highlight_y,
                node_size=node_size,
                dim_factor=dim,
                is_top=is_top,
                flash=flash_phase,
                role=roles.get(sid, "filler"),
            )

        # ---- Off-chain reset flash ----------------------------------------
        reset_at = state.get("reset_flash_at") or 0.0
        if reset_at > 0:
            elapsed_ms = (time.monotonic() - reset_at) * 1000.0
            if elapsed_ms < _RESET_FLASH_MS:
                self.renderer.draw_outlined_text(
                    ctx.cx,
                    box_cy + box_half_h + 26,
                    "OFF-CHAIN — RESET",
                    ctx.skill_font, _RESET_COLOR,
                    anchor="center", tag=_TAG,
                )

    # ------------------------------------------------------------------
    # Card draw
    # ------------------------------------------------------------------
    def _draw_card(
        self,
        class_slug: str,
        row: Dict[str, Any],
        *,
        cx: int,
        cy: int,
        node_size: int,
        dim_factor: float,
        is_top: bool,
        flash: bool,
        role: str,
    ) -> None:
        canvas = self.ctx.canvas
        ctx = self.ctx
        half = node_size // 2

        # ---- Icon ---------------------------------------------------------
        photo = self._icons.get(
            class_slug, row["name"], dim_factor=dim_factor,
        )
        if photo is not None:
            canvas._chain_icon_refs.append(photo)  # type: ignore[attr-defined]
            canvas.create_image(cx, cy, image=photo, tags=(_TAG,))
        else:
            short = row["name"]
            if len(short) > 8:
                short = short[:8] + "…"
            self.renderer.draw_outlined_text(
                cx, cy, short, ctx.note_font,
                _LABEL_LIT if is_top else _LABEL_DIM,
                anchor="center", tag=_TAG,
            )

        # ---- Name label ---------------------------------------------------
        line_h = ctx.note_font.metrics("linespace")
        label_y = cy + half + _LABEL_GAP + line_h // 2
        if is_top:
            name_color = _LABEL_HIGHLIGHT
        elif dim_factor >= _DIM_NEAR:
            name_color = _LABEL_LIT
        else:
            name_color = _LABEL_DIM
        max_chars = max(8, node_size // 6)
        display_name = row["name"]
        if len(display_name) > max_chars:
            display_name = display_name[: max_chars - 1] + "…"
        font = ctx.skill_font if is_top else ctx.note_font
        self.renderer.draw_outlined_text(
            cx, label_y, display_name, font, name_color,
            anchor="center", tag=_TAG,
        )

        # ---- Key chord ----------------------------------------------------
        key_text = self._format_keys(row["keys"])
        if not key_text:
            return
        # When is_top we use the larger skill_font for the name;
        # bump the key chord y so it doesn't overlap.
        key_y = label_y + _KEY_GAP + (
            ctx.skill_font.metrics("linespace") if is_top else line_h
        )
        if is_top and flash:
            key_color = _KEY_FLASH
        elif is_top or dim_factor >= _DIM_NEAR:
            key_color = _KEY_COLOR
        else:
            key_color = _LABEL_DIM
        key_font = ctx.input_font if is_top else ctx.note_font
        self.renderer.draw_outlined_text(
            cx, key_y, key_text, key_font, key_color,
            anchor="center", tag=_TAG,
        )

    # ------------------------------------------------------------------
    # Slot → dim factor
    # ------------------------------------------------------------------
    @staticmethod
    def _dim_for_slot(slot_idx: int, *, is_history: bool) -> float:
        if is_history:
            return _DIM_HISTORY
        if slot_idx == 0:
            return _DIM_HIGHLIGHT
        if slot_idx <= 1:
            return _DIM_NEAR
        if slot_idx <= 3:
            return _DIM_MID
        return _DIM_FAR

    # ------------------------------------------------------------------
    # Outline / drain helpers
    # ------------------------------------------------------------------
    def _draw_static_perim(
        self,
        perim: List[Tuple[float, float]],
        color: str,
        width: int,
    ) -> None:
        canvas = self.ctx.canvas
        n = len(perim)
        for i in range(n):
            x0, y0 = perim[i]
            x1, y1 = perim[(i + 1) % n]
            canvas.create_line(
                x0, y0, x1, y1,
                fill=color, width=width, tags=(_TAG,),
            )

    def _draw_drain_perim(
        self,
        perim: List[Tuple[float, float]],
        remaining_frac: float,
        active_color: str,
        active_width: int,
    ) -> None:
        canvas = self.ctx.canvas
        n = len(perim)
        active_count = int(round(n * max(0.0, min(1.0, remaining_frac))))
        for i in range(n):
            x0, y0 = perim[i]
            x1, y1 = perim[(i + 1) % n]
            if i < active_count:
                color, width = active_color, active_width
            else:
                color, width = _DRAIN_DIM, 1
            canvas.create_line(
                x0, y0, x1, y1,
                fill=color, width=width, tags=(_TAG,),
            )

    # ------------------------------------------------------------------
    # Flash tick
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
    # Key formatting
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
