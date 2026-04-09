"""Hold Bar — progress bar for hold-type combo steps."""

import logging
from typing import Callable, List, Optional

from src.input_monitor import InputMonitor
from src.overlay.renderer import OverlayContext, OverlayRenderer

logger = logging.getLogger("bdo_trainer")


class HoldBar:
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
        self._duration_ms: int = 0
        self._elapsed_ms: int = 0
        self._was_held: bool = False
        self._keys_active: bool = False
        self._tick_ms: int = 30  # ~33fps
        self._after_id: Optional[str] = None
        self._on_complete: Optional[Callable] = None
        # Set by the combo player before starting a hold
        self.last_armed_key_sets: List[List[str]] = []

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self, duration_ms: int, on_complete: Callable) -> None:
        """Begin a hold step."""
        self._active = True
        self._duration_ms = max(duration_ms, 100)
        self._elapsed_ms = 0
        self._was_held = False
        self._keys_active = False
        self._on_complete = on_complete
        self.input_monitor.clear_target()
        self._render(0.0)
        self._after_id = self.ctx.root.after(self._tick_ms, self._tick)
        logger.info(f"Hold step started ({duration_ms}ms)")

    def cancel(self) -> None:
        """Cancel an active hold step."""
        self._active = False
        self._elapsed_ms = 0
        if self._after_id is not None:
            self.ctx.root.after_cancel(self._after_id)
            self._after_id = None

    def _tick(self) -> None:
        """Periodic update (~33fps)."""
        if not self._active:
            return
        keys_held = self._check_keys()
        if keys_held:
            self._was_held = True
            self._keys_active = True
        elif self._was_held:
            # Keys were held and then released — advance to next step
            logger.info("Hold released early — advancing to next step")
            self._complete()
            return
        else:
            self._keys_active = False
        # Always increment so hold steps auto-complete after their duration
        self._elapsed_ms += self._tick_ms
        progress = min(self._elapsed_ms / self._duration_ms, 1.0)
        self._render(progress)
        if progress >= 1.0:
            self._complete()
        else:
            self._after_id = self.ctx.root.after(self._tick_ms, self._tick)

    def _check_keys(self) -> bool:
        """Return True if any of the previously-armed key sets are fully held."""
        if not self.last_armed_key_sets:
            return True
        pressed = self.input_monitor._pressed
        return any(set(ks).issubset(pressed) for ks in self.last_armed_key_sets)

    def _complete(self) -> None:
        self._active = False
        self._after_id = None
        if self._on_complete:
            self._on_complete()

    def _render(self, progress: float) -> None:
        """Draw the animated hold progress bar on the canvas."""
        # Clear previous bar
        self.renderer.clear("hold_bar")
        ctx = self.ctx

        bar_w = 320
        bar_h = 22
        x1 = ctx.cx - bar_w // 2
        y1 = ctx.cy + 32
        x2 = x1 + bar_w
        y2 = y1 + bar_h
        inner_pad = 2

        # Outer glow
        if self._keys_active:
            glow_color = OverlayRenderer.lerp_color("#1A1A3E", "#3B2F00", progress)
        else:
            glow_color = OverlayRenderer.lerp_color("#1A1A3E", "#1A2A3E", progress)
        ctx.canvas.create_rectangle(
            x1 - 2,
            y1 - 2,
            x2 + 2,
            y2 + 2,
            fill=glow_color,
            outline="",
            tags=("hold_bar",),
        )

        # Background
        ctx.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill="#0A0A18",
            outline="#8B7530" if self._keys_active else "#506070",
            width=1,
            tags=("hold_bar",),
        )

        # Fill bar
        inner_w = bar_w - inner_pad * 2
        fill_w = int(inner_w * progress)
        if fill_w > 0:
            if self._keys_active:
                fill_color = OverlayRenderer.hold_bar_color(progress)
            else:
                fill_color = OverlayRenderer.hold_bar_timeout_color(progress)
            fx1 = x1 + inner_pad
            fy1 = y1 + inner_pad
            fx2 = fx1 + fill_w
            fy2 = y2 - inner_pad

            # Main fill
            ctx.canvas.create_rectangle(
                fx1,
                fy1,
                fx2,
                fy2,
                fill=fill_color,
                outline="",
                tags=("hold_bar",),
            )
            # Top highlight
            hl_h = max((bar_h - inner_pad * 2) // 4, 2)
            ctx.canvas.create_rectangle(
                fx1,
                fy1,
                fx2,
                fy1 + hl_h,
                fill=OverlayRenderer.lighten_color(fill_color, 0.35),
                outline="",
                tags=("hold_bar",),
            )
            # Leading edge glow
            if fill_w > 4:
                ctx.canvas.create_rectangle(
                    fx2 - 3,
                    fy1 + 1,
                    fx2,
                    fy2 - 1,
                    fill="#FFFFCC" if self._keys_active else "#AABBCC",
                    outline="",
                    tags=("hold_bar",),
                )
            # Bright pixel spark at tip
            if fill_w > 6:
                spark_y = fy1 + (fy2 - fy1) // 2
                ctx.canvas.create_oval(
                    fx2 - 2,
                    spark_y - 2,
                    fx2 + 2,
                    spark_y + 2,
                    fill="#FFFFFF" if self._keys_active else "#CCDDEE",
                    outline="",
                    tags=("hold_bar",),
                )

        # Timer text
        elapsed_s = self._elapsed_ms / 1000.0
        total_s = self._duration_ms / 1000.0
        timer_text = f"HOLD  \u00b7  {elapsed_s:.1f}s / {total_s:.1f}s"
        self.renderer.draw_outlined_text(
            ctx.cx,
            y1 + bar_h // 2,
            timer_text,
            ctx.counter_font,
            "#FFFFFF",
            tag="hold_bar",
        )
