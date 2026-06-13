"""ChainRenderer — horizontal flowchart for chain-mode priority combos.

Tier columns laid out left → right. Each tier draws its skills as
icon nodes with a key-chord caption beneath. Faded eligibility edges
connect every node in tier N to every node in tier N+1; cursor →
frontier edges are drawn solid in gold.

Per-node states:
- **idle** — not the cursor, not in the current frontier (faint frame).
- **frontier** — eligible right now (white frame).
- **cursor** — most recent on-chain cast (gold frame).
- **history** — earlier on-chain cast (dim gold frame).
- **reset flash** — briefly drawn after an off-chain press; fades.

Icons come from :mod:`src.overlay.icons`; missing icons fall back to
a text-only node so the renderer still works without the icon repo.
"""

from __future__ import annotations

import logging
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
_NODE_PAD = 8       # extra px around the icon for the node frame
_LABEL_GAP = 4
_KEY_GAP = 4
# Column gap and vertical gap have a sensible default but are
# overridable via providers wired by the settings layer.
_DEFAULT_COLUMN_GAP = 120
_DEFAULT_NODE_VGAP = 18

# Colours
_NODE_FRAME_DIM = "#3A3A3A"
_NODE_FRAME_FRONTIER = "#FFFFFF"
_NODE_FRAME_CURSOR = "#FFD700"
_NODE_FRAME_HISTORY = "#776A2A"
_LABEL_DIM = "#777777"
_LABEL_LIT = "#FFFFFF"
_LABEL_CURSOR = "#FFD700"
_KEY_COLOR = "#88DDFF"
_KEY_FLASH = "#FFFFCC"
_EDGE_DIM = "#2E2E2E"
_EDGE_ACTIVE = "#FFD700"
_HEADER_COLOR = "#FFD700"
_RESET_COLOR = "#CC2030"

# Rounded-rect perimeter sampling — N points around the perimeter
# clockwise from 12 o'clock, used both for drawing the outline and
# for partial-perimeter "drain ring" rendering. Higher = smoother
# curves but more canvas line items per node.
_PERIMETER_SAMPLES = 80
# Radius for the rounded corners as a fraction of node size.
_CORNER_RADIUS_FRAC = 0.22


def _rounded_rect_perimeter(
    cx: int, cy: int, half: int, radius: int,
) -> List[Tuple[float, float]]:
    """Return ``_PERIMETER_SAMPLES`` (x, y) points walking the
    perimeter of a rounded square clockwise, starting at 12 o'clock
    (top-centre) and ending one step before it. Used for drawing
    smooth outlines and partial drain rings.
    """
    import math

    # Centres of the four corner arcs.
    left = cx - half + radius
    right = cx + half - radius
    top = cy - half + radius
    bottom = cy + half - radius

    # Total perimeter = straight sides + four quarter-arcs
    side_len = 2 * (half - radius)
    arc_len = (math.pi / 2) * radius
    total_len = 4 * side_len + 4 * arc_len

    # Walk from 12 o'clock (top centre) clockwise. The "12 o'clock"
    # point sits in the middle of the top straight segment, between
    # the top-left arc end and the top-right arc start.
    out: List[Tuple[float, float]] = []
    half_top = side_len / 2.0
    for i in range(_PERIMETER_SAMPLES):
        t = (i / _PERIMETER_SAMPLES) * total_len
        # Sequence walked clockwise from the top-centre:
        #   1. top straight (right half), length half_top
        #   2. top-right arc, length arc_len
        #   3. right straight, length side_len
        #   4. bottom-right arc, length arc_len
        #   5. bottom straight (right→left), length side_len
        #   6. bottom-left arc, length arc_len
        #   7. left straight (bottom→top), length side_len
        #   8. top-left arc, length arc_len
        #   9. top straight (left half), length half_top
        s = t
        if s < half_top:
            x = cx + s
            y = cy - half
        elif s < half_top + arc_len:
            a = (s - half_top) / radius  # 0 → π/2
            x = right + radius * math.sin(a)
            y = top - radius * math.cos(a)
        elif s < half_top + arc_len + side_len:
            x = cx + half
            y = top + (s - half_top - arc_len)
        elif s < half_top + arc_len + side_len + arc_len:
            a = (s - half_top - arc_len - side_len) / radius
            x = right + radius * math.cos(a)
            y = bottom + radius * math.sin(a)
        elif (s
              < half_top + arc_len + side_len + arc_len + side_len):
            x = right - (
                s - half_top - arc_len - side_len - arc_len
            )
            y = cy + half
        elif (s
              < half_top + arc_len + side_len + arc_len + side_len
              + arc_len):
            a = (
                s - half_top - arc_len - side_len - arc_len
                - side_len
            ) / radius
            x = left - radius * math.sin(a)
            y = bottom + radius * math.cos(a)
        elif (s
              < half_top + arc_len + side_len + arc_len + side_len
              + arc_len + side_len):
            x = cx - half
            y = bottom - (
                s - half_top - arc_len - side_len - arc_len
                - side_len - arc_len
            )
        elif (s
              < half_top + arc_len + side_len + arc_len + side_len
              + arc_len + side_len + arc_len):
            a = (
                s - half_top - arc_len - side_len - arc_len
                - side_len - arc_len - side_len
            ) / radius
            x = left - radius * math.cos(a)
            y = top - radius * math.sin(a)
        else:
            x = cx - (
                s - half_top - arc_len - side_len - arc_len
                - side_len - arc_len - side_len - arc_len
            )
            y = cy - half
        out.append((x, y))
    return out


class ChainRenderer:
    """Horizontal flowchart for chain-mode priority combos."""

    def __init__(
        self,
        ctx: OverlayContext,
        renderer: OverlayRenderer,
        icon_size_provider: Optional[Callable[[], int]] = None,
        column_gap_provider: Optional[Callable[[], int]] = None,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        # All layout knobs are callables so a settings slider drag
        # takes effect on the next render frame (~150 ms).
        self._icon_size_provider = icon_size_provider or (lambda: 36)
        self._column_gap_provider = (
            column_gap_provider or (lambda: _DEFAULT_COLUMN_GAP)
        )
        self._icons = IconLoader(size_px=self._icon_size_provider())
        self._state: Optional[Dict[str, Any]] = None
        self._key_remap: Dict[str, str] = {}
        self._is_active: bool = False
        self._tick_after_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def show(self) -> None:
        # Pick up any size changes since last show.
        self._icons.set_size(self._icon_size_provider())
        self._is_active = True
        self._render(self._state)
        self._start_flash_tick()

    def hide(self) -> None:
        was_active = self._is_active
        self._is_active = False
        self._stop_flash_tick()
        self.renderer.clear(_TAG)
        # Drop pinned icon refs so they can be GC'd / regenerated at
        # the next show.
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
        # Drop the previous frame's icon refs — Tk PhotoImage objects
        # need a live reference but each render re-creates the
        # canvas items, so we can rebuild the ref list per frame.
        canvas = self.ctx.canvas
        canvas._chain_icon_refs = []  # type: ignore[attr-defined]

        if not self._is_active or not state or not state.get("active"):
            return
        ctx = self.ctx
        rows: List[Dict[str, Any]] = state.get("rows") or []
        if not rows:
            return

        # ---- Group rows by tier --------------------------------------------
        tier_labels: List[str] = state.get("tier_labels") or []
        tiers: List[List[Dict[str, Any]]] = (
            [[] for _ in tier_labels] or [[]]
        )
        for row in rows:
            t = int(row.get("tier", 0))
            while t >= len(tiers):
                tiers.append([])
            tiers[t].append(row)

        # ---- Layout sizes --------------------------------------------------
        # Pull layout knobs fresh every render so settings sliders are
        # live (no need to restart the combo).
        self._icons.set_size(self._icon_size_provider())
        column_gap = max(20, int(self._column_gap_provider()))
        node_size = self._icons.size_px + _NODE_PAD * 2
        col_w = node_size + column_gap
        chart_w = (len(tiers) * col_w) - column_gap
        line_h = ctx.note_font.metrics("linespace")
        node_full_h = (
            node_size
            + _LABEL_GAP + line_h         # name label
            + _KEY_GAP + line_h           # key chord
        )
        tallest = max((len(t) for t in tiers), default=1)
        chart_h = (
            tallest * node_full_h
            + max(0, tallest - 1) * _DEFAULT_NODE_VGAP
        )

        chart_left = ctx.cx - (chart_w // 2)
        chart_top = ctx.cy - (chart_h // 2) + 30

        # ---- Header (budget) ----------------------------------------------
        max_hard = state.get("max_hard_cc", 0)
        hard = state.get("hard_count", 0)
        budget_text = f"Hard-CC: {hard}/{max_hard}"
        budget_color = (
            "#FF7777" if max_hard and hard >= max_hard
            else "#AAAAAA"
        )
        self.renderer.draw_outlined_text(
            ctx.cx, chart_top - 36,
            budget_text, ctx.note_font, budget_color,
            anchor="center", tag=_TAG,
        )

        # ---- Tier labels (above each column) ------------------------------
        for t_idx, label in enumerate(tier_labels):
            col_x_centre = (
                chart_left + (col_w * t_idx) + (node_size // 2)
            )
            self.renderer.draw_outlined_text(
                col_x_centre, chart_top - 14,
                label, ctx.counter_font, _HEADER_COLOR,
                anchor="center", tag=_TAG,
            )

        # ---- Compute node centres -----------------------------------------
        node_centres: Dict[str, Tuple[int, int]] = {}
        for t_idx, tier_rows in enumerate(tiers):
            col_x_centre = (
                chart_left + (col_w * t_idx) + (node_size // 2)
            )
            tier_h = (
                len(tier_rows) * node_full_h
                + max(0, len(tier_rows) - 1) * _DEFAULT_NODE_VGAP
            )
            tier_y_top = chart_top + (chart_h - tier_h) // 2
            for n_idx, row in enumerate(tier_rows):
                y_centre = (
                    tier_y_top
                    + (node_full_h + _DEFAULT_NODE_VGAP) * n_idx
                    + (node_size // 2)
                )
                node_centres[row["id"]] = (col_x_centre, y_centre)

        # ---- Eligibility edges (faint) ------------------------------------
        for t_idx in range(len(tiers) - 1):
            for src in tiers[t_idx]:
                for dst in tiers[t_idx + 1]:
                    sx, sy = node_centres.get(src["id"], (0, 0))
                    dx, dy = node_centres.get(dst["id"], (0, 0))
                    canvas.create_line(
                        sx + node_size // 2, sy,
                        dx - node_size // 2, dy,
                        fill=_EDGE_DIM, width=1, tags=(_TAG,),
                    )

        # ---- Active edges: cursor → frontier ------------------------------
        cursor_id = state.get("cursor")
        frontier_ids = set(state.get("frontier_ids") or [])
        if cursor_id and cursor_id in node_centres:
            sx, sy = node_centres[cursor_id]
            for fid in frontier_ids:
                if fid not in node_centres:
                    continue
                dx, dy = node_centres[fid]
                canvas.create_line(
                    sx + node_size // 2, sy,
                    dx - node_size // 2, dy,
                    fill=_EDGE_ACTIVE, width=2, tags=(_TAG,),
                )

        # ---- History trail ------------------------------------------------
        history: List[Tuple[str, float]] = state.get("history") or []
        for i in range(len(history) - 1):
            a = node_centres.get(history[i][0])
            b = node_centres.get(history[i + 1][0])
            if a and b:
                canvas.create_line(
                    a[0], a[1], b[0], b[1],
                    fill=_NODE_FRAME_HISTORY, width=2, tags=(_TAG,),
                )

        # ---- Nodes --------------------------------------------------------
        history_ids = {sid for sid, _ts in history}
        # Map skill_id → most recent cast timestamp from the chain
        # history so the renderer can drain the ring per node.
        history_ts: Dict[str, float] = {}
        for sid, ts in history:
            history_ts[sid] = ts
        lock_seconds: Dict[str, float] = state.get("lock_seconds") or {}
        cls_slug = state.get("class_slug") or ""
        now_ms = int(time.monotonic() * 1000)
        flash_phase = (now_ms // _FLASH_PERIOD_MS) % 2 == 0
        # Best frontier is the first frontier id in tier order — rows
        # are already in priority order.
        best_id: Optional[str] = next(
            (r["id"] for r in rows if r["id"] in frontier_ids), None,
        )

        now = time.monotonic()
        for row in rows:
            sid = row["id"]
            pos = node_centres.get(sid)
            if pos is None:
                continue
            self._draw_node(
                cls_slug, row, pos[0], pos[1], node_size,
                is_cursor=(sid == cursor_id),
                is_history=(sid in history_ids and sid != cursor_id),
                is_frontier=(sid in frontier_ids),
                is_best=(sid == best_id and flash_phase),
                lock_total_s=lock_seconds.get(sid, 0.0),
                cast_ts=history_ts.get(sid),
                now=now,
            )

        # ---- Off-chain reset flash overlay --------------------------------
        reset_at = state.get("reset_flash_at") or 0.0
        if reset_at > 0:
            elapsed_ms = (time.monotonic() - reset_at) * 1000.0
            if elapsed_ms < _RESET_FLASH_MS:
                self.renderer.draw_outlined_text(
                    ctx.cx, chart_top + chart_h + 26,
                    "OFF-CHAIN — RESET",
                    ctx.skill_font, _RESET_COLOR,
                    anchor="center", tag=_TAG,
                )

    # ------------------------------------------------------------------
    # Single-node draw
    # ------------------------------------------------------------------
    def _draw_node(
        self,
        class_slug: str,
        row: Dict[str, Any],
        cx: int,
        cy: int,
        node_size: int,
        *,
        is_cursor: bool,
        is_history: bool,
        is_frontier: bool,
        is_best: bool,
        lock_total_s: float = 0.0,
        cast_ts: Optional[float] = None,
        now: float = 0.0,
    ) -> None:
        canvas = self.ctx.canvas
        ctx = self.ctx
        half = node_size // 2
        radius = max(4, int(node_size * _CORNER_RADIUS_FRAC))

        # ---- Rounded outline (drawn before icon) ---------------------------
        # Cursor + history nodes get a drain ring computed from the
        # cast timestamp + lock duration; frontier and idle nodes
        # get a static thin outline.
        perim = _rounded_rect_perimeter(cx, cy, half, radius)

        if (
            (is_cursor or is_history)
            and cast_ts is not None
            and lock_total_s > 0.0
        ):
            elapsed = max(0.0, now - cast_ts)
            remaining_frac = max(
                0.0, min(1.0, 1.0 - (elapsed / lock_total_s))
            )
            ring_color = (
                _NODE_FRAME_CURSOR if is_cursor else _NODE_FRAME_HISTORY
            )
            ring_width = 3 if is_cursor else 2
            self._draw_drain_ring(
                perim, remaining_frac, ring_color, ring_width,
            )
        else:
            # Static outline for frontier / idle nodes.
            if is_frontier:
                color, width = _NODE_FRAME_FRONTIER, 2
            else:
                color, width = _NODE_FRAME_DIM, 1
            self._draw_static_outline(perim, color, width)

        # ---- Icon ----------------------------------------------------------
        photo = self._icons.get(class_slug, row["name"])
        if photo is not None:
            # Pin a strong reference so Tk doesn't garbage-collect.
            canvas._chain_icon_refs.append(photo)  # type: ignore[attr-defined]
            canvas.create_image(cx, cy, image=photo, tags=(_TAG,))
        else:
            short = row["name"]
            if len(short) > 8:
                short = short[:8] + "…"
            self.renderer.draw_outlined_text(
                cx, cy, short, ctx.note_font,
                _LABEL_LIT if (is_frontier or is_cursor) else _LABEL_DIM,
                anchor="center", tag=_TAG,
            )

        # ---- Name label ----------------------------------------------------
        line_h = ctx.note_font.metrics("linespace")
        label_y = cy + half + _LABEL_GAP + line_h // 2
        if is_cursor:
            name_color = _LABEL_CURSOR
        elif is_frontier:
            name_color = _LABEL_LIT
        else:
            name_color = _LABEL_DIM
        max_chars = max(8, node_size // 6)
        display_name = row["name"]
        if len(display_name) > max_chars:
            display_name = display_name[: max_chars - 1] + "…"
        self.renderer.draw_outlined_text(
            cx, label_y, display_name, ctx.note_font, name_color,
            anchor="center", tag=_TAG,
        )

        # ---- Key chord -----------------------------------------------------
        key_text = self._format_keys(row["keys"])
        if not key_text:
            return
        key_y = label_y + _KEY_GAP + line_h
        if is_best:
            key_color = _KEY_FLASH
        elif is_frontier or is_cursor:
            key_color = _KEY_COLOR
        else:
            key_color = _LABEL_DIM
        self.renderer.draw_outlined_text(
            cx, key_y, key_text, ctx.note_font, key_color,
            anchor="center", tag=_TAG,
        )

    # ------------------------------------------------------------------
    # Flash tick — drives the next-best key flash + reset fade
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Outline helpers
    # ------------------------------------------------------------------
    def _draw_static_outline(
        self,
        perim: List[Tuple[float, float]],
        color: str,
        width: int,
    ) -> None:
        """Draw a closed rounded outline by connecting consecutive
        perimeter samples plus the wrap-around segment."""
        canvas = self.ctx.canvas
        n = len(perim)
        for i in range(n):
            x0, y0 = perim[i]
            x1, y1 = perim[(i + 1) % n]
            canvas.create_line(
                x0, y0, x1, y1,
                fill=color, width=width, tags=(_TAG,),
            )

    def _draw_drain_ring(
        self,
        perim: List[Tuple[float, float]],
        remaining_frac: float,
        active_color: str,
        active_width: int,
    ) -> None:
        """Draw a partial perimeter walking clockwise from 12 o'clock.

        The first ``remaining_frac × N`` samples are drawn in
        ``active_color`` at ``active_width`` (the lock-time ring);
        the rest are drawn faintly so the node still has a visible
        outline.
        """
        canvas = self.ctx.canvas
        n = len(perim)
        active_count = int(round(n * max(0.0, min(1.0, remaining_frac))))
        # When elapsed crosses 100 % we want zero active segments
        # but a still-readable dim outline so the user sees "lock
        # expired".
        for i in range(n):
            x0, y0 = perim[i]
            x1, y1 = perim[(i + 1) % n]
            if i < active_count:
                color, width = active_color, active_width
            else:
                color, width = _NODE_FRAME_DIM, 1
            canvas.create_line(
                x0, y0, x1, y1,
                fill=color, width=width, tags=(_TAG,),
            )

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
    # Key formatting helper
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
