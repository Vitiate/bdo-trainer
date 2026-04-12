"""Combo Overlay — transparent overlay coordinator.

Thin wrapper that creates the Tk window, instantiates all sub-components,
and delegates the public API used by ``main.py``.
"""

import logging
import sys
import tkinter as tk
from typing import Any, Callable, Dict, Optional

from src.input_monitor import InputMonitor
from src.overlay.combo_player import ComboPlayer
from src.overlay.hold_bar import HoldBar
from src.overlay.renderer import TRANSPARENT_COLOR, OverlayContext, OverlayRenderer
from src.overlay.reposition import RepositionHandler
from src.overlay.setup_guide import SetupGuide
from src.platform import default_font_family, make_click_through

logger = logging.getLogger("bdo_trainer")


class ComboOverlay:
    """Full-screen transparent overlay — coordinates all sub-components."""

    def __init__(
        self,
        font_family: str = "",
        skill_font_size: int = 32,
        input_font_size: int = 22,
        note_font_size: int = 14,
        skill_color: str = "#FFD700",
        input_color: str = "#FFFFFF",
        note_color: str = "#AAAAAA",
        show_protection: bool = True,
        show_notes: bool = True,
    ) -> None:
        if not font_family:
            font_family = default_font_family()

        # --- Tk root -------------------------------------------------------
        self.root = tk.Tk()
        self.root.title("BDO Trainer Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_COLOR)

        if sys.platform == "win32":
            self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        else:
            self.root.attributes("-alpha", 0.90)

        screen_w: int = self.root.winfo_screenwidth()
        screen_h: int = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")

        make_click_through(self.root)

        # --- Canvas --------------------------------------------------------
        canvas = tk.Canvas(
            self.root,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
            width=screen_w,
            height=screen_h,
        )
        canvas.pack()

        # --- Shared context & renderer -------------------------------------
        cx = screen_w // 2
        cy = int(screen_h * 0.85)

        self._ctx = OverlayContext(
            root=self.root,
            canvas=canvas,
            screen_w=screen_w,
            screen_h=screen_h,
            cx=cx,
            cy=cy,
            font_family=font_family,
            skill_font_size=skill_font_size,
            input_font_size=input_font_size,
            note_font_size=note_font_size,
            skill_color=skill_color,
            input_color=input_color,
            note_color=note_color,
            show_protection=show_protection,
            show_notes=show_notes,
        )
        self._renderer = OverlayRenderer(self._ctx)

        # --- Components ----------------------------------------------------
        self.input_monitor = InputMonitor()
        self.input_monitor.start()

        self._hold_bar = HoldBar(self._ctx, self._renderer, self.input_monitor)
        self._player = ComboPlayer(
            self._ctx,
            self._renderer,
            self.input_monitor,
            self._hold_bar,
        )
        self._guide = SetupGuide(self._ctx, self._renderer)
        self._reposition = RepositionHandler(self._ctx, self._renderer)

        # Load saved overlay position
        self._reposition.load_position()

        # --- Shutdown guard ------------------------------------------------
        self._destroyed: bool = False

        logger.info("Overlay initialised (transparent canvas, key-press mode)")

    # =================================================================
    # External hooks (forwarded to player)
    # =================================================================
    @property
    def on_combo_finished(self) -> Optional[Callable]:
        return self._player.on_combo_finished

    @on_combo_finished.setter
    def on_combo_finished(self, value: Optional[Callable]) -> None:
        self._player.on_combo_finished = value

    @property
    def get_skill_info(self) -> Optional[Callable]:
        return self._player.get_skill_info

    @get_skill_info.setter
    def get_skill_info(self, value: Optional[Callable]) -> None:
        self._player.get_skill_info = value

    # =================================================================
    # Configuration
    # =================================================================
    def set_key_remap(self, remap: Dict[str, str]) -> None:
        self._player.set_key_remap(remap)

    def set_idle_reset_ms(self, ms: int) -> None:
        self._player.set_idle_reset_ms(ms)

    # =================================================================
    # Combo lifecycle
    # =================================================================
    def start_combo(
        self,
        combo_data: Dict[str, Any],
        combo_name: str = "",
        step_delay_ms: Optional[int] = None,
        loop: bool = True,
    ) -> None:
        self._player.start(combo_data, combo_name, step_delay_ms, loop)

    def stop_combo(self) -> None:
        self._player.stop()

    def is_running(self) -> bool:
        return self._player.is_running

    # =================================================================
    # Setup guide
    # =================================================================
    def show_setup_guide(self, guide_data: Dict[str, Any]) -> None:
        self._player.pause()
        self._guide.show(guide_data)

    def hide_setup_guide(self) -> None:
        was_active = self._guide.is_active
        self._guide.hide()
        if was_active and self._player.is_running:
            self._player.resume()

    def toggle_setup_guide(self, guide_data=None) -> bool:
        if self._guide.is_active:
            self.hide_setup_guide()
            return False
        if guide_data:
            self.show_setup_guide(guide_data)
            return True
        return False

    @property
    def setup_guide_active(self) -> bool:
        return self._guide.is_active

    def next_setup_page(self) -> None:
        self._guide.next_page()

    # =================================================================
    # Reposition
    # =================================================================
    def enable_reposition(self) -> None:
        self._player.pause()
        self._reposition.enable()

    def disable_reposition(self) -> None:
        self._reposition.disable()
        if self._player.is_running:
            self._player.resume()

    def toggle_reposition(self) -> bool:
        if self._reposition.is_active:
            self.disable_reposition()
        else:
            self.enable_reposition()
        return self._reposition.is_active

    # =================================================================
    # Thread-safe scheduling & main loop
    # =================================================================
    def schedule(self, func: Callable, delay_ms: int = 0) -> None:
        if self._destroyed:
            return
        try:
            self.root.after(delay_ms, func)
        except Exception:
            pass

    def run(self) -> None:
        logger.info("Overlay main loop starting")
        self.root.mainloop()

    def shutdown(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._player.stop()
        self.input_monitor.stop()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
