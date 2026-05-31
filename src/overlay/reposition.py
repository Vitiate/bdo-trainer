"""Reposition Handler — drag-to-move overlay and position persistence."""

import json
import logging
from pathlib import Path

from src.overlay.renderer import OverlayContext, OverlayRenderer
from src.platform import make_click_through, remove_click_through

logger = logging.getLogger("bdo_trainer")

POSITION_FILE = (
    Path(__file__).resolve().parent.parent.parent / "config" / "overlay_position.json"
)


class RepositionHandler:
    def __init__(
        self,
        ctx: OverlayContext,
        renderer: OverlayRenderer,
        cc_panel=None,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self._cc_panel = cc_panel
        self._active: bool = False
        self._drag_last_x: int = 0
        self._drag_last_y: int = 0
        # Which target the user is currently dragging
        # ("center" — combo overlay anchor, "cc_panel" — CC panel anchor).
        self._drag_target: str = "center"

    @property
    def is_active(self) -> bool:
        return self._active

    def enable(self) -> None:
        if self._active:
            return
        self._active = True
        remove_click_through(self.ctx.root)
        self.ctx.canvas.config(cursor="fleur")
        self.ctx.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.ctx.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self._draw_handle()
        logger.info("Reposition mode enabled")

    def disable(self) -> None:
        if not self._active:
            return
        self._active = False
        self.ctx.canvas.unbind("<ButtonPress-1>")
        self.ctx.canvas.unbind("<B1-Motion>")
        self.ctx.canvas.config(cursor="")
        self.renderer.clear("reposition")
        make_click_through(self.ctx.root)
        self.save_position()
        if self._cc_panel is not None:
            self._cc_panel.end_reposition()
        logger.info("Reposition mode disabled — position saved")

    def toggle(self) -> bool:
        if self._active:
            self.disable()
        else:
            self.enable()
        return self._active

    # ----- visuals -------------------------------------------------------

    def _draw_handle(self) -> None:
        self.renderer.clear("reposition")
        ctx = self.ctx
        # Sample text preview
        self.renderer.draw_outlined_text(
            ctx.cx,
            ctx.cy - 35,
            "Sample Skill Name",
            ctx.skill_font,
            ctx.skill_color,
            tag="reposition",
        )
        self.renderer.draw_outlined_text(
            ctx.cx,
            ctx.cy + 10,
            "Shift + LMB",
            ctx.input_font,
            ctx.input_color,
            tag="reposition",
        )
        # Dashed rectangle
        pad_x, pad_y = 250, 110
        ctx.canvas.create_rectangle(
            ctx.cx - pad_x,
            ctx.cy - pad_y,
            ctx.cx + pad_x,
            ctx.cy + pad_y,
            outline="#FFD700",
            width=2,
            dash=(6, 4),
            tags=("reposition",),
        )
        # Crosshair
        ch = 14
        ctx.canvas.create_line(
            ctx.cx - ch,
            ctx.cy,
            ctx.cx + ch,
            ctx.cy,
            fill="#FFD700",
            width=2,
            tags=("reposition",),
        )
        ctx.canvas.create_line(
            ctx.cx,
            ctx.cy - ch,
            ctx.cx,
            ctx.cy + ch,
            fill="#FFD700",
            width=2,
            tags=("reposition",),
        )
        # Instructions
        self.renderer.draw_outlined_text(
            ctx.cx,
            ctx.cy - pad_y - 25,
            "REPOSITION MODE — Drag to move",
            ctx.note_font,
            "#FFD700",
            tag="reposition",
        )
        self.renderer.draw_outlined_text(
            ctx.cx,
            ctx.cy + pad_y + 25,
            "Deselect 'Reposition' in tray menu to lock",
            ctx.counter_font,
            "#AAAAAA",
            tag="reposition",
        )

    # ----- drag ----------------------------------------------------------

    def _on_drag_start(self, event) -> None:
        self._drag_last_x = event.x
        self._drag_last_y = event.y
        self._drag_target = self._target_for_point(event.x, event.y)
        if self._drag_target == "cc_panel" and self._cc_panel is not None:
            self._cc_panel.begin_reposition()

    def _on_drag_motion(self, event) -> None:
        dx = event.x - self._drag_last_x
        dy = event.y - self._drag_last_y
        if self._drag_target == "cc_panel" and self._cc_panel is not None:
            self._cc_panel.offset(dx, dy)
        else:
            self.ctx.canvas.move("step", dx, dy)
            self.ctx.canvas.move("hold_bar", dx, dy)
            self.ctx.canvas.move("reposition", dx, dy)
            self.ctx.cx += dx
            self.ctx.cy += dy
        self._drag_last_x = event.x
        self._drag_last_y = event.y

    def _target_for_point(self, x: int, y: int) -> str:
        """Decide whether this drag is operating on the CC panel or the
        combo center, based on which is closer to the press point."""
        if self._cc_panel is None or not self._cc_panel.is_active:
            return "center"
        cx, cy = self.ctx.cx, self.ctx.cy
        px, py = self._cc_panel.px, self._cc_panel.py
        d_center = (x - cx) ** 2 + (y - cy) ** 2
        d_panel = (x - px) ** 2 + (y - py) ** 2
        return "cc_panel" if d_panel < d_center else "center"

    # ----- persistence ---------------------------------------------------

    def load_position(self) -> None:
        try:
            with open(POSITION_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            rx = data.get("rx")
            ry = data.get("ry")
            if rx is not None and ry is not None:
                self.ctx.cx = int(float(rx) * self.ctx.screen_w)
                self.ctx.cy = int(float(ry) * self.ctx.screen_h)
                logger.info(f"Loaded overlay position ({self.ctx.cx}, {self.ctx.cy})")
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning(f"Could not load overlay position: {exc}")

    def save_position(self) -> None:
        rx = self.ctx.cx / self.ctx.screen_w
        ry = self.ctx.cy / self.ctx.screen_h
        try:
            POSITION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(POSITION_FILE, "w", encoding="utf-8") as fh:
                json.dump({"rx": round(rx, 6), "ry": round(ry, 6)}, fh)
            logger.info(f"Saved overlay position (rx={rx:.4f}, ry={ry:.4f})")
        except Exception as exc:
            logger.warning(f"Could not save overlay position: {exc}")
