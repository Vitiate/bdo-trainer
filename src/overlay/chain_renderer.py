"""ChainRenderer — vertical-column flowchart with animated priority.

Tier columns laid out left → right. Skills are stacked vertically
within each column, sorted by the player's score-based frontier
priority (CC weight + PvP damage + smash bonus during a smash
window). The highest-priority skill in each column is at the top.

Each skill renders as:
- An icon inside a rounded frame.
- A small CC-type badge in the top-right of the frame (letter on
  a coloured background — 'KD' / 'ST' / 'FL' / 'G' etc).
- Skill name below the frame.
- Key chord below the name.

The single highest-priority skill across the entire combo gets a
gold highlight frame and a clockwise drain ring showing remaining
CC lock time on the target. All other skills get a thin dim frame.

When priority changes (cast goes on cooldown, smash window opens,
chain advances) each card eases toward its new (x, y) target
position over ~6 frames at the 150 ms tick rate, so cards visibly
slide through intermediate slots like a wheel spinning.
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
_NODE_PAD = 8        # px around the icon inside a card frame
_LABEL_GAP = 4
_KEY_GAP = 4
_DEFAULT_COLUMN_GAP = 120
_DEFAULT_NODE_VGAP = 18

# Render tick — 33 ms ≈ 30 fps. Lower than 60 fps to keep CPU
# cost reasonable (each tick rebuilds canvas items), high enough
# that lerp-eased motion looks continuous to the eye.
_TICK_MS = 33

# Per-frame easing fractions tuned for the 30 fps tick. Doubled
# from the original calibration so the next-best skill snaps into
# focus in ~0.4 s instead of ~0.9 s. Still smooth (~12 frames at
# 30 fps) but quick enough to keep up with mid-fight casts.
_SLIDE_LERP = 0.22
_PAN_LERP = 0.18
_SNAP_PX = 0.5

# Highlight box: fixed screen position. The chart pans so the
# column containing the global #1 skill aligns its top-row card
# inside this box. The box itself never moves.
_HIGHLIGHT_PAD = 6

# Dim factors for icon alpha by node priority.
_DIM_TOP = 1.0       # rank 0 in column AND rank 0 overall
_DIM_FRONTIER = 0.85
_DIM_COL_TOP = 0.75  # top of a non-spotlighted column
_DIM_HISTORY = 0.30
_DIM_IDLE = 0.20

# Colours
_FRAME_DIM = "#3A3A3A"
_FRAME_FRONTIER = "#FFFFFF"
_FRAME_HIGHLIGHT = "#FFD700"
_FRAME_HIGHLIGHT_BUFF = "#66E0FF"
_FRAME_HISTORY = "#776A2A"
_DRAIN_DIM = "#3A3A3A"
_LABEL_DIM = "#777777"
_LABEL_LIT = "#FFFFFF"
_LABEL_HIGHLIGHT = "#FFD700"
_KEY_COLOR = "#88DDFF"
_KEY_FLASH = "#FFFFCC"
_HEADER_COLOR = "#FFD700"
_RESET_COLOR = "#CC2030"

# CC badge palette. (label, fill, fg). Picked so the badges stand
# out against a typical BDO icon — saturated CC colours, dark
# letters where the bg is light and white letters where it's dark.
_CC_BADGES: Dict[str, Tuple[str, str, str]] = {
    "grab":         ("G",  "#9C27B0", "#FFFFFF"),
    "knockdown":    ("KD", "#F44336", "#FFFFFF"),
    "stun":         ("ST", "#FF9800", "#000000"),
    "knockback":    ("KB", "#FF5722", "#FFFFFF"),
    "floating":     ("FL", "#FFEB3B", "#000000"),
    "bound":        ("BD", "#CDDC39", "#000000"),
    "stiffness":    ("SF", "#FFF59D", "#000000"),
    "down_smash":   ("DS", "#5D4037", "#FFFFFF"),
    "air_smash":    ("AS", "#795548", "#FFFFFF"),
    "down_attack":  ("DA", "#424242", "#FFFFFF"),
    "air_attack":   ("AA", "#9E9E9E", "#000000"),
}
# Order used to pick a single badge when a skill has multiple CC
# tags — pick the strongest "real" CC first; smash / hit-flag
# tags only badge if the skill has nothing better.
_CC_BADGE_ORDER = (
    "grab", "knockdown", "stun", "knockback", "floating",
    "bound", "stiffness", "down_smash", "air_smash",
    "down_attack", "air_attack",
)

# Rounded-rect perimeter sampling for outline / drain rendering.
_PERIMETER_SAMPLES = 80
_CORNER_RADIUS_FRAC = 0.22


def _rounded_rect_perimeter(
    cx: int, cy: int, half: int, radius: int,
) -> List[Tuple[float, float]]:
    """Walk a rounded square's perimeter clockwise from 12 o'clock.
    Returns ``_PERIMETER_SAMPLES`` evenly-spaced points usable for
    both static outline rendering and partial drain rings.
    """
    side_len = 2 * (half - radius)
    arc_len = (math.pi / 2) * radius
    total_len = 4 * side_len + 4 * arc_len

    left_arc_x = cx - half + radius
    right_arc_x = cx + half - radius
    top_arc_y = cy - half + radius
    bottom_arc_y = cy + half - radius

    out: List[Tuple[float, float]] = []
    half_top = side_len / 2.0
    for i in range(_PERIMETER_SAMPLES):
        s = (i / _PERIMETER_SAMPLES) * total_len
        if s < half_top:
            x = cx + s
            y = cy - half
        elif s < half_top + arc_len:
            a = (s - half_top) / radius
            x = right_arc_x + radius * math.sin(a)
            y = top_arc_y - radius * math.cos(a)
        elif s < half_top + arc_len + side_len:
            x = cx + half
            y = top_arc_y + (s - half_top - arc_len)
        elif s < half_top + arc_len + side_len + arc_len:
            a = (s - half_top - arc_len - side_len) / radius
            x = right_arc_x + radius * math.cos(a)
            y = bottom_arc_y + radius * math.sin(a)
        elif (s
              < half_top + arc_len + side_len + arc_len + side_len):
            x = right_arc_x - (
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
            x = left_arc_x - radius * math.sin(a)
            y = bottom_arc_y + radius * math.cos(a)
        elif (s
              < half_top + arc_len + side_len + arc_len + side_len
              + arc_len + side_len):
            x = cx - half
            y = bottom_arc_y - (
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
            x = left_arc_x - radius * math.cos(a)
            y = top_arc_y - radius * math.sin(a)
        else:
            x = cx - (
                s - half_top - arc_len - side_len - arc_len
                - side_len - arc_len - side_len - arc_len
            )
            y = cy - half
        out.append((x, y))
    return out


class ChainRenderer:
    """Vertical-column flowchart with animated priority reordering."""

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
        self._column_gap_provider = (
            column_gap_provider or (lambda: _DEFAULT_COLUMN_GAP)
        )
        self._icons = IconLoader(size_px=self._icon_size_provider())
        self._state: Optional[Dict[str, Any]] = None
        self._key_remap: Dict[str, str] = {}
        self._is_active: bool = False
        self._tick_after_id: Optional[str] = None
        # Per-skill animated position. Eased toward target each
        # render tick so a rank change slides the card in.
        self._anim_pos: Dict[str, Tuple[float, float]] = {}
        # Animated chart-pan offset (in chart-space pixels). Eases
        # so the global #1's column-top sits inside the fixed
        # highlight box.
        self._anim_pan_x: Optional[float] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def show(self) -> None:
        self._icons.set_size(self._icon_size_provider())
        self._is_active = True
        # Reset animation state so cards drop in at target instead
        # of sweeping in from a stale prior position.
        self._anim_pos.clear()
        self._anim_pan_x = None
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
        rows_by_id: Dict[str, Dict[str, Any]] = {r["id"]: r for r in rows}

        # ---- Layout sizes -------------------------------------------------
        self._icons.set_size(self._icon_size_provider())
        column_gap = max(20, int(self._column_gap_provider()))
        node_size = self._icons.size_px + _NODE_PAD * 2
        col_w = node_size + column_gap
        line_h = ctx.note_font.metrics("linespace")
        # Each card = icon + name line + key line, with gaps.
        card_h = (
            node_size
            + _LABEL_GAP + line_h         # name
            + _KEY_GAP + line_h           # key
        )
        card_step = card_h + _DEFAULT_NODE_VGAP

        # ---- Group rows by tier; sort each column by frontier rank --------
        tier_labels: List[str] = state.get("tier_labels") or []
        tiers: List[List[Dict[str, Any]]] = (
            [[] for _ in tier_labels] or [[]]
        )
        for row in rows:
            t = int(row.get("tier", 0))
            while t >= len(tiers):
                tiers.append([])
            tiers[t].append(row)

        frontier_ids: List[str] = list(state.get("frontier_ids") or [])
        frontier_set = set(frontier_ids)
        rank_map: Dict[str, int] = {
            sid: i for i, sid in enumerate(frontier_ids)
        }
        not_frontier_rank = len(frontier_ids)
        for tier_rows in tiers:
            tier_rows.sort(
                key=lambda r: rank_map.get(r["id"], not_frontier_rank)
            )

        # ---- Chart geometry ----------------------------------------------
        # The highlight box is the fixed reference point: its centre
        # sits at (ctx.cx, ctx.cy + 30 + node_size/2). Each column's
        # *top* card is laid out at the same y as the box, with all
        # subsequent cards stacked below. Columns are then panned in
        # x so the global #1's column lands at ctx.cx.
        # Highlight box icon centre — this is also the y of every
        # column's top-row card.
        highlight_cx = ctx.cx
        highlight_cy = ctx.cy + 30 + node_size // 2

        # Pan: which tier's #1 should sit in the highlight box?
        # Pick the tier whose top-row id has the lowest frontier
        # rank (i.e. contains the global #1). Falls back to tier 0
        # when no frontier exists.
        spotlight_tier_idx = self._spotlight_tier_idx(tiers, rank_map)
        target_pan = float(spotlight_tier_idx * col_w)
        if self._anim_pan_x is None:
            self._anim_pan_x = target_pan
        else:
            d = target_pan - self._anim_pan_x
            self._anim_pan_x = (
                target_pan if abs(d) <= _SNAP_PX
                else self._anim_pan_x + d * _PAN_LERP
            )
        pan_px = int(round(self._anim_pan_x))

        # ---- Compute target (x, y) per skill -----------------------------
        # x = highlight_cx + (tier_idx − spotlight_tier) × col_w,
        #     accounting for the eased pan.
        # y = highlight_cy − row_idx × card_step (top-priority row
        #     sits in the highlight box; lower-priority rows stack
        #     UPWARD above it).
        target_pos: Dict[str, Tuple[float, float]] = {}
        for t_idx, tier_rows in enumerate(tiers):
            col_x = (
                highlight_cx
                + (col_w * t_idx)
                - pan_px
            )
            for r_idx, row in enumerate(tier_rows):
                y = highlight_cy - card_step * r_idx
                target_pos[row["id"]] = (float(col_x), float(y))

        # Bottom of the chart sits below the highlight box (text
        # labels of the row-0 cards extend down past the icon).
        chart_bottom = (
            highlight_cy + node_size // 2
            + _LABEL_GAP + line_h
            + _KEY_GAP + line_h
        )

        # ---- Ease animated positions toward target -----------------------
        for sid, (tx, ty) in target_pos.items():
            cur = self._anim_pos.get(sid)
            if cur is None:
                # First frame for this id — place at target instead
                # of easing in from origin.
                self._anim_pos[sid] = (tx, ty)
                continue
            cx_, cy_ = cur
            dx = tx - cx_
            dy = ty - cy_
            if abs(dx) <= _SNAP_PX and abs(dy) <= _SNAP_PX:
                self._anim_pos[sid] = (tx, ty)
            else:
                self._anim_pos[sid] = (
                    cx_ + dx * _SLIDE_LERP,
                    cy_ + dy * _SLIDE_LERP,
                )
        # Drop entries for ids that aren't in this combo any more.
        for sid in list(self._anim_pos.keys()):
            if sid not in target_pos:
                del self._anim_pos[sid]

        # ---- Header (CC budget, below the chart) -------------------------
        max_hard = state.get("max_hard_cc", 0)
        hard = state.get("hard_count", 0)
        budget_text = f"Hard-CC: {hard}/{max_hard}"
        budget_color = (
            "#FF7777" if max_hard and hard >= max_hard
            else "#AAAAAA"
        )
        self.renderer.draw_outlined_text(
            ctx.cx, chart_bottom + 18,
            budget_text, ctx.note_font, budget_color,
            anchor="center", tag=_TAG,
        )

        # ---- Tier labels (below each column) -----------------------------
        for t_idx, label in enumerate(tier_labels):
            col_centre = (
                highlight_cx + col_w * t_idx - pan_px
            )
            self.renderer.draw_outlined_text(
                col_centre, chart_bottom + 36,
                label, ctx.counter_font, _HEADER_COLOR,
                anchor="center", tag=_TAG,
            )

        # ---- Draw cards --------------------------------------------------
        cls_slug = state.get("class_slug") or ""
        roles: Dict[str, str] = state.get("roles") or {}
        history: List[Tuple[str, float]] = state.get("history") or []
        history_ids = {sid for sid, _ts in history}
        cursor_id = state.get("cursor")
        lock_seconds: Dict[str, float] = state.get("lock_seconds") or {}
        history_ts: Dict[str, float] = {}
        for sid, ts in history:
            history_ts[sid] = ts
        now = time.monotonic()
        now_ms = int(now * 1000)
        flash_phase = (now_ms // _FLASH_PERIOD_MS) % 2 == 0
        # The single highest-priority skill across the whole combo
        # gets the gold highlight + drain ring.
        top_id: Optional[str] = frontier_ids[0] if frontier_ids else None

        # Track per-column rank-0 ids so columns whose top isn't the
        # global top still get a slightly brighter card than a
        # 4th-row idle skill.
        col_top_ids: set = set()
        for tier_rows in tiers:
            if tier_rows:
                col_top_ids.add(tier_rows[0]["id"])

        # ---- Highlight box (static, drawn before cards) ------------------
        # The highlight box always sits at (highlight_cx, highlight_cy).
        # Drain ring uses the cursor's lock — i.e. the most-recent on-
        # chain cast, not the skill that's currently displayed in the
        # box. That way the timer shows when CC will come off the
        # *target*, regardless of what the next skill is.
        box_role = roles.get(top_id or "", "filler")
        box_color = (
            _FRAME_HIGHLIGHT_BUFF
            if box_role == "pre_buff" else _FRAME_HIGHLIGHT
        )
        # Box geometry — just slightly larger than a card frame so
        # the global-top icon sits cleanly inside it.
        box_half = (node_size // 2) + _HIGHLIGHT_PAD
        box_radius = max(6, int(node_size * _CORNER_RADIUS_FRAC))
        box_perim = _rounded_rect_perimeter(
            highlight_cx, highlight_cy, box_half, box_radius,
        )
        # Drain on the cursor's lock — duration of the player's most
        # recent on-chain cast. Cards never carry the drain themselves.
        cursor_lock_remaining = 0.0
        if cursor_id and cursor_id in lock_seconds:
            cursor_cast = history_ts.get(cursor_id)
            if cursor_cast is not None:
                lock_total = lock_seconds[cursor_id]
                if lock_total > 0:
                    elapsed = max(0.0, now - cursor_cast)
                    cursor_lock_remaining = max(
                        0.0, min(1.0, 1.0 - (elapsed / lock_total)),
                    )
        if cursor_lock_remaining > 0:
            self._draw_drain_perim(
                box_perim, cursor_lock_remaining, box_color, 4,
            )
        else:
            self._draw_static_perim(box_perim, box_color, 3)

        for sid, (ax, ay) in self._anim_pos.items():
            row = rows_by_id.get(sid)
            if row is None:
                continue
            is_top = (sid == top_id)
            is_frontier = (sid in frontier_set)
            is_history = (sid in history_ids and sid != cursor_id)
            is_col_top = (sid in col_top_ids)
            dim = self._dim_for(
                is_top=is_top,
                is_frontier=is_frontier,
                is_history=is_history,
                is_col_top=is_col_top,
            )
            self._draw_card(
                cls_slug, row,
                cx=int(round(ax)),
                cy=int(round(ay)),
                node_size=node_size,
                dim_factor=dim,
                is_top=is_top,
                is_frontier=is_frontier,
                is_history=is_history,
                role=roles.get(sid, "filler"),
                cc_tags=tuple(row.get("cc_tags") or ()),
                # lock/drain rendering moved to the static highlight
                # box; cards no longer carry their own drain ring.
                lock_total_s=0.0,
                cast_ts=None,
                now=now,
                flash=flash_phase,
            )

        # ---- Off-chain reset flash -------------------------------------
        reset_at = state.get("reset_flash_at") or 0.0
        if reset_at > 0:
            elapsed_ms = (time.monotonic() - reset_at) * 1000.0
            if elapsed_ms < _RESET_FLASH_MS:
                self.renderer.draw_outlined_text(
                    ctx.cx,
                    chart_bottom + 60,
                    "OFF-CHAIN — RESET",
                    ctx.skill_font, _RESET_COLOR,
                    anchor="center", tag=_TAG,
                )

    # ------------------------------------------------------------------
    # Card draw (icon + frame + CC badge + labels below)
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
        is_frontier: bool,
        is_history: bool,
        role: str,
        cc_tags: Tuple[str, ...],
        lock_total_s: float,
        cast_ts: Optional[float],
        now: float,
        flash: bool,
    ) -> None:
        canvas = self.ctx.canvas
        ctx = self.ctx
        half = node_size // 2
        radius = max(4, int(node_size * _CORNER_RADIUS_FRAC))
        perim = _rounded_rect_perimeter(cx, cy, half, radius)

        # Frame: the global top is framed by the static highlight
        # box drawn in the parent — skip the per-card frame so we
        # don't double-draw on the same pixels. Other cards: white
        # frame on the frontier, dim history frame for past casts,
        # dim grey for everything else.
        if is_top:
            pass  # static highlight box owns this card's frame
        elif is_frontier:
            self._draw_static_perim(perim, _FRAME_FRONTIER, 2)
        elif is_history:
            self._draw_static_perim(perim, _FRAME_HISTORY, 1)
        else:
            self._draw_static_perim(perim, _FRAME_DIM, 1)

        # Icon (with alpha-dim).
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
                _LABEL_LIT if (is_top or is_frontier) else _LABEL_DIM,
                anchor="center", tag=_TAG,
            )

        # CC badge in the top-right of the icon area.
        self._draw_cc_badge(cx, cy, half, cc_tags)

        # Name label + key chord, both below the frame.
        line_h = ctx.note_font.metrics("linespace")
        label_y = cy + half + _LABEL_GAP + line_h // 2
        if is_top:
            name_color = _LABEL_HIGHLIGHT
        elif is_frontier:
            name_color = _LABEL_LIT
        else:
            name_color = _LABEL_DIM
        max_chars = max(8, node_size // 6)
        display_name = row["name"]
        if len(display_name) > max_chars:
            display_name = display_name[: max_chars - 1] + "…"
        # Top card is bigger so the active "press this" text reads
        # at a glance mid-fight; everything else stays small.
        name_font = ctx.input_font if is_top else ctx.note_font
        self.renderer.draw_outlined_text(
            cx, label_y, display_name, name_font, name_color,
            anchor="center", tag=_TAG,
        )

        key_text = self._format_keys(row["keys"])
        if not key_text:
            return
        key_y = label_y + _KEY_GAP + (
            ctx.input_font.metrics("linespace") if is_top else line_h
        )
        if is_top and flash:
            key_color = _KEY_FLASH
        elif is_top or is_frontier:
            key_color = _KEY_COLOR
        else:
            key_color = _LABEL_DIM
        key_font = ctx.input_font if is_top else ctx.note_font
        self.renderer.draw_outlined_text(
            cx, key_y, key_text, key_font, key_color,
            anchor="center", tag=_TAG,
        )

    # ------------------------------------------------------------------
    # CC badge
    # ------------------------------------------------------------------
    def _draw_cc_badge(
        self,
        cx: int,
        cy: int,
        half: int,
        cc_tags: Tuple[str, ...],
    ) -> None:
        if not cc_tags:
            return
        # Pick the strongest "real" CC tag for the badge; smash /
        # hit-flag tags only badge if there's no actual CC.
        tag_set = {str(t).lower() for t in cc_tags}
        chosen: Optional[str] = None
        for cand in _CC_BADGE_ORDER:
            if cand in tag_set:
                chosen = cand
                break
        if chosen is None:
            return
        label, fill, fg = _CC_BADGES[chosen]
        canvas = self.ctx.canvas

        # Badge box: ~28% of node size, top-right inset by 2 px.
        bw = max(14, int(half * 0.55))
        bh = max(11, int(half * 0.42))
        bx_right = cx + half - 3
        by_top = cy - half + 3
        bx_left = bx_right - bw
        by_bottom = by_top + bh

        # Filled rounded rect (Tk has no native rounded fill, so
        # approximate with one big rect plus two side rects to
        # round the corners visually). For a small badge a plain
        # rectangle reads fine.
        canvas.create_rectangle(
            bx_left, by_top, bx_right, by_bottom,
            fill=fill, outline="#000000", width=1,
            tags=(_TAG,),
        )
        # Centre the label inside.
        self.renderer.draw_outlined_text(
            (bx_left + bx_right) // 2,
            (by_top + by_bottom) // 2,
            label,
            self.ctx.counter_font, fg,
            anchor="center", tag=_TAG,
        )

    # ------------------------------------------------------------------
    # Spotlight tier — which column should land in the highlight box
    # ------------------------------------------------------------------
    @staticmethod
    def _spotlight_tier_idx(
        tiers: List[List[Dict[str, Any]]],
        rank_map: Dict[str, int],
    ) -> int:
        """Pick the tier index whose top-row card should sit in the
        highlight box. The "spotlight tier" is the column whose
        top-row id has the lowest frontier rank (closest to the
        global #1). When no frontier row exists in any column, fall
        back to tier 0.
        """
        if not tiers:
            return 0
        best_idx = 0
        best_rank: Optional[int] = None
        big = 10 ** 9
        for idx, tier_rows in enumerate(tiers):
            if not tier_rows:
                continue
            top_id = tier_rows[0]["id"]
            rank = rank_map.get(top_id, big)
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_idx = idx
        return best_idx

    # ------------------------------------------------------------------
    # Dim factor selection
    # ------------------------------------------------------------------
    @staticmethod
    def _dim_for(
        *,
        is_top: bool,
        is_frontier: bool,
        is_history: bool,
        is_col_top: bool,
    ) -> float:
        if is_top:
            return _DIM_TOP
        if is_frontier:
            return _DIM_FRONTIER
        if is_col_top:
            return _DIM_COL_TOP
        if is_history:
            return _DIM_HISTORY
        return _DIM_IDLE

    # ------------------------------------------------------------------
    # Outline / drain helpers
    # ------------------------------------------------------------------
    def _draw_static_perim(
        self,
        perim: List[Tuple[float, float]],
        color: str,
        width: int,
    ) -> None:
        """Draw the rounded outline as a single closed polygon.

        Uses one ``create_polygon`` call instead of N ``create_line``
        calls — much cheaper (one canvas item per outline rather
        than ~80) and the visual is identical. ``fill=""`` keeps
        the centre transparent so the icon shows through.
        """
        if not perim:
            return
        flat: List[float] = []
        for x, y in perim:
            flat.append(x)
            flat.append(y)
        self.ctx.canvas.create_polygon(
            *flat,
            fill="",
            outline=color,
            width=width,
            tags=(_TAG,),
        )

    def _draw_drain_perim(
        self,
        perim: List[Tuple[float, float]],
        remaining_frac: float,
        active_color: str,
        active_width: int,
    ) -> None:
        """Drain ring as two polylines instead of N short lines.

        Tk has no partial-arc primitive that respects custom widths
        cleanly, but a long polyline through every sample is one
        canvas item — vastly cheaper than the old per-segment
        ``create_line`` loop.
        """
        if not perim:
            return
        canvas = self.ctx.canvas
        n = len(perim)
        active_count = int(round(n * max(0.0, min(1.0, remaining_frac))))

        # Active arc: samples 0..active_count, plus the boundary
        # vertex so the colour change happens at the right point.
        if active_count > 0:
            pts: List[float] = []
            for i in range(active_count + 1):
                x, y = perim[i % n]
                pts.append(x)
                pts.append(y)
            canvas.create_line(
                *pts,
                fill=active_color, width=active_width,
                tags=(_TAG,),
            )

        # Dim arc: samples active_count..n, closing back to start.
        if active_count < n:
            pts = []
            # Start from the boundary so we don't overdraw it.
            for i in range(active_count, n + 1):
                x, y = perim[i % n]
                pts.append(x)
                pts.append(y)
            canvas.create_line(
                *pts,
                fill=_DRAIN_DIM, width=1,
                tags=(_TAG,),
            )

    # ------------------------------------------------------------------
    # Flash tick
    # ------------------------------------------------------------------
    def _start_flash_tick(self) -> None:
        if self._tick_after_id is not None:
            return
        self._tick_after_id = self.ctx.root.after(_TICK_MS, self._flash_tick)

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
        self._tick_after_id = self.ctx.root.after(_TICK_MS, self._flash_tick)

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
