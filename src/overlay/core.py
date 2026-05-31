"""Combo Overlay — transparent overlay coordinator.

Thin wrapper that creates the Tk window, instantiates all sub-components,
and delegates the public API used by ``main.py``.
"""

import logging
import queue
import sys
import tkinter as tk
from typing import Any, Callable, Dict, Optional

from src.input_monitor import InputMonitor
from src.overlay.cc_panel import CCPanel
from src.overlay.combo_player import ComboPlayer
from src.overlay.hold_bar import HoldBar
from src.overlay.priority_player import PriorityPlayer
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
        show_window: bool = True,
    ) -> None:
        if not font_family:
            font_family = default_font_family()

        self._show_window = show_window

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

        if not self._show_window:
            # Hide the overlay window entirely while keeping the Tk root
            # alive — child windows (settings, editors), the schedule
            # queue, and the input monitor still need it.
            self.root.withdraw()

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
        # Skip starting the pynput listener threads when the overlay
        # window is hidden — there's no in-game UI for them to drive,
        # and on macOS the listener thread can crash on a pyobjc
        # lazy-import bug (KeyError: 'AXIsProcessTrusted'). The
        # editor + tray flows do not depend on input monitoring.
        if self._show_window:
            self.input_monitor.start()

        self._hold_bar = HoldBar(self._ctx, self._renderer, self.input_monitor)
        self._player = ComboPlayer(
            self._ctx,
            self._renderer,
            self.input_monitor,
            self._hold_bar,
        )
        self._priority = PriorityPlayer(
            self._ctx, self._renderer, self.input_monitor,
        )
        # Tracks which player is currently active so stop / pause /
        # resume / external hooks route to the right one.
        self._active_player: Any = self._player
        self._guide = SetupGuide(self._ctx, self._renderer)
        self._cc_panel = CCPanel(self._ctx, self._renderer, self.input_monitor)
        self._reposition = RepositionHandler(
            self._ctx, self._renderer, cc_panel=self._cc_panel,
        )

        # Load saved overlay position
        self._reposition.load_position()

        # --- Shutdown guard ------------------------------------------------
        self._destroyed: bool = False

        # --- Thread-safe scheduling queue ----------------------------------
        self._schedule_queue: queue.Queue = queue.Queue()
        self._poll_queue()

        logger.info("Overlay initialised (transparent canvas, key-press mode)")

    # =================================================================
    # External hooks (forwarded to all players)
    # =================================================================
    @property
    def on_combo_finished(self) -> Optional[Callable]:
        return self._player.on_combo_finished

    @on_combo_finished.setter
    def on_combo_finished(self, value: Optional[Callable]) -> None:
        self._player.on_combo_finished = value
        self._priority.on_combo_finished = value

    @property
    def get_skill_info(self) -> Optional[Callable]:
        return self._player.get_skill_info

    @get_skill_info.setter
    def get_skill_info(self, value: Optional[Callable]) -> None:
        self._player.get_skill_info = value
        self._priority.get_skill_info = value

    # =================================================================
    # Configuration
    # =================================================================
    def set_key_remap(self, remap: Dict[str, str]) -> None:
        self._player.set_key_remap(remap)
        self._priority.set_key_remap(remap)
        self._cc_panel.set_key_remap(remap)

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
        # Stop whichever player is currently active before swapping.
        self._player.stop()
        self._priority.stop()
        mode = (combo_data or {}).get("mode", "sequence")
        if mode == "priority":
            self._active_player = self._priority
            self._priority.start(combo_data, combo_name)
        else:
            self._active_player = self._player
            self._player.start(combo_data, combo_name, step_delay_ms, loop)

    def stop_combo(self) -> None:
        self._player.stop()
        self._priority.stop()

    def is_running(self) -> bool:
        return self._player.is_running or self._priority.is_running

    # =================================================================
    # Setup guide
    # =================================================================
    def show_setup_guide(self, guide_data: Dict[str, Any]) -> None:
        self._active_player.pause()
        self._guide.show(guide_data)

    def hide_setup_guide(self) -> None:
        was_active = self._guide.is_active
        self._guide.hide()
        if was_active and self._active_player.is_running:
            self._active_player.resume()

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
    # CC Skills panel
    # =================================================================
    def show_cc_panel(self, skills: Dict[str, Any]) -> None:
        self._cc_panel.show(skills)

    def hide_cc_panel(self) -> None:
        self._cc_panel.hide()

    def update_cc_panel(self, skills: Dict[str, Any]) -> None:
        self._cc_panel.update_class(skills)

    @property
    def cc_panel_active(self) -> bool:
        return self._cc_panel.is_active

    # =================================================================
    # Reposition
    # =================================================================
    def enable_reposition(self) -> None:
        self._active_player.pause()
        self._reposition.enable()

    def disable_reposition(self) -> None:
        self._reposition.disable()
        if self._active_player.is_running:
            self._active_player.resume()

    def toggle_reposition(self) -> bool:
        if self._reposition.is_active:
            self.disable_reposition()
        else:
            self.enable_reposition()
        return self._reposition.is_active

    # =================================================================
    # Thread-safe scheduling & main loop
    # =================================================================
    def _poll_queue(self) -> None:
        """Drain the schedule queue from the Tk thread (runs every 50ms)."""
        if self._destroyed:
            return
        try:
            while True:
                delay_ms, func = self._schedule_queue.get_nowait()
                self.root.after(delay_ms, func)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def schedule(self, func: Callable, delay_ms: int = 0) -> None:
        """Thread-safe: enqueue work to be picked up by the Tk thread."""
        if self._destroyed:
            return
        self._schedule_queue.put((delay_ms, func))

    def run(self) -> None:
        logger.info("Overlay main loop starting")
        self.root.mainloop()

    def shutdown(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._player.stop()
        self._priority.stop()
        self.input_monitor.stop()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
