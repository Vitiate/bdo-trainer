"""
Combo Overlay - Transparent overlay with outlined text and key-press advancement.

Displays combo steps as floating outlined text over the game.
Steps advance when the user presses the correct key combination
(detected via pynput keyboard + mouse listeners).
"""

import json
import logging
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("bdo_trainer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRANSPARENT_COLOR = "#010101"
OUTLINE_COLOR = "#000000"
OUTLINE_THICKNESS = 2

DEFAULT_FONT_FAMILY = "Segoe UI"
DEFAULT_SKILL_FONT_SIZE = 32
DEFAULT_INPUT_FONT_SIZE = 22
DEFAULT_NOTE_FONT_SIZE = 14
DEFAULT_SKILL_COLOR = "#FFD700"  # Gold
DEFAULT_INPUT_COLOR = "#FFFFFF"  # White
DEFAULT_NOTE_COLOR = "#AAAAAA"  # Gray
DEFAULT_SUCCESS_COLOR = "#4CAF50"  # Green

PROTECTION_COLORS: Dict[str, str] = {
    "SA": "#4CAF50",  # Green
    "FG": "#2196F3",  # Blue
    "iframe": "#9C27B0",  # Purple
    "none": "#F44336",  # Red
}

POSITION_FILE = (
    Path(__file__).resolve().parent.parent / "config" / "overlay_position.json"
)

# ---------------------------------------------------------------------------
# Try to import pynput for input monitoring
# ---------------------------------------------------------------------------
_pynput_kb = None
_pynput_mouse = None
INPUT_AVAILABLE = False

try:
    from pynput import keyboard as _pynput_kb
    from pynput import mouse as _pynput_mouse

    INPUT_AVAILABLE = True
except ImportError:
    logger.warning(
        "pynput not installed — combo steps will auto-advance on a timer. "
        "Install with: pip install pynput"
    )


# ---------------------------------------------------------------------------
# Win32: make the overlay click-through
# ---------------------------------------------------------------------------
def _make_click_through(root: tk.Tk) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED
        )
        logger.info("Overlay set to click-through (Windows)")
    except Exception as e:
        logger.warning(f"Could not set click-through: {e}")


def _remove_click_through(root: tk.Tk) -> None:
    """Remove the click-through style so the overlay captures mouse events."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT
        )
        logger.info("Overlay click-through removed (Windows)")
    except Exception as e:
        logger.warning(f"Could not remove click-through: {e}")


# =========================================================================
# InputMonitor — tracks keyboard + mouse state via pynput
# =========================================================================
class InputMonitor:
    """
    Watches for a target set of keys/buttons.  When every key in the target
    set is held simultaneously the *on_match* callback fires **once** (edge-
    triggered so holding keys doesn't re-fire).

    Key names use the same strings as ``combos.yaml``:
        shift, space, ctrl, alt, tab, enter, esc   – modifier / special
        a-z, 0-9                                    – character keys
        lmb, rmb, mmb                               – mouse buttons
    """

    def __init__(self) -> None:
        self._pressed: Set[str] = set()
        self._required_sets: List[Set[str]] = []
        self._on_match: Optional[Callable] = None
        self._matched: bool = False
        self._kb_listener = None
        self._mouse_listener = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if not INPUT_AVAILABLE:
            return
        self._kb_listener = _pynput_kb.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._mouse_listener = _pynput_mouse.Listener(
            on_click=self._on_click,
        )
        self._kb_listener.daemon = True
        self._mouse_listener.daemon = True
        self._kb_listener.start()
        self._mouse_listener.start()
        logger.info("Input monitor started (keyboard + mouse)")

    def stop(self) -> None:
        if self._kb_listener:
            try:
                self._kb_listener.stop()
            except Exception:
                pass
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        logger.info("Input monitor stopped")

    # ------------------------------------------------------------------
    # Target management
    # ------------------------------------------------------------------
    def set_target(self, key_sets: List[List[str]], on_match: Callable) -> None:
        """Set one or more key combinations to watch for.

        *key_sets* is a list of key-lists.  The callback fires (once) when
        **any** of the sets is fully held.
        """
        self._required_sets = [
            {k.lower() for k in ks if k.lower() != "hotbar"} for ks in key_sets
        ]
        self._required_sets = [s for s in self._required_sets if s]
        self._on_match = on_match
        self._matched = False

    def clear_target(self) -> None:
        self._required_sets = []
        self._on_match = None
        self._matched = False

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_key(key) -> str:
        """Convert a pynput key object to our canonical lowercase string.

        When a game window (e.g. BDO) has focus, pynput often receives
        KeyCode events with ``char=None`` because the character cannot be
        resolved through the game's keyboard state.  The virtual-key code
        (``vk``) is still present, so we fall back to it for A-Z / 0-9.
        """
        if not INPUT_AVAILABLE:
            return ""
        # Character keys (a-z, 0-9, etc.)
        try:
            if isinstance(key, _pynput_kb.KeyCode):
                if key.char:
                    return key.char.lower()
                # char is None — fall back to the virtual-key code.
                # This happens when a fullscreen / DirectX game has focus.
                vk = getattr(key, "vk", None)
                if vk is not None:
                    # VK_A (0x41) .. VK_Z (0x5A)
                    if 0x41 <= vk <= 0x5A:
                        return chr(vk).lower()
                    # VK_0 (0x30) .. VK_9 (0x39)
                    if 0x30 <= vk <= 0x39:
                        return chr(vk)
                return ""
        except AttributeError:
            pass

        _MAP = {
            _pynput_kb.Key.shift: "shift",
            _pynput_kb.Key.shift_l: "shift",
            _pynput_kb.Key.shift_r: "shift",
            _pynput_kb.Key.space: "space",
            _pynput_kb.Key.ctrl: "ctrl",
            _pynput_kb.Key.ctrl_l: "ctrl",
            _pynput_kb.Key.ctrl_r: "ctrl",
            _pynput_kb.Key.alt: "alt",
            _pynput_kb.Key.alt_l: "alt",
            _pynput_kb.Key.alt_r: "alt",
            _pynput_kb.Key.tab: "tab",
            _pynput_kb.Key.enter: "enter",
            _pynput_kb.Key.esc: "esc",
            _pynput_kb.Key.caps_lock: "capslock",
        }
        return _MAP.get(key, "")

    # ------------------------------------------------------------------
    # Event handlers (called from pynput listener threads)
    # ------------------------------------------------------------------
    def _on_key_press(self, key) -> None:
        name = self._normalize_key(key)
        if name:
            self._pressed.add(name)
            self._check()

    def _on_key_release(self, key) -> None:
        name = self._normalize_key(key)
        if name:
            self._pressed.discard(name)
            # Reset edge trigger when no required set is fully held
            if self._required_sets and not any(
                rs.issubset(self._pressed) for rs in self._required_sets
            ):
                self._matched = False

    def _on_click(self, _x, _y, button, pressed) -> None:
        if not INPUT_AVAILABLE:
            return
        btn_map = {
            _pynput_mouse.Button.left: "lmb",
            _pynput_mouse.Button.right: "rmb",
            _pynput_mouse.Button.middle: "mmb",
        }
        name = btn_map.get(button, "")
        if not name:
            return
        if pressed:
            self._pressed.add(name)
            self._check()
        else:
            self._pressed.discard(name)
            if self._required_sets and not any(
                rs.issubset(self._pressed) for rs in self._required_sets
            ):
                self._matched = False

    def _check(self) -> None:
        """Fire callback if all required keys are currently held (edge-triggered)."""
        if not self._required_sets or self._matched:
            return
        for req_set in self._required_sets:
            if req_set.issubset(self._pressed):
                self._matched = True
                if self._on_match:
                    self._on_match()
                return


# =========================================================================
# ComboOverlay — the transparent window
# =========================================================================
class ComboOverlay:
    """
    Full-screen transparent overlay.

    • Text is drawn on a Canvas with a dark outline so it is readable
      against any game background.
    • Steps wait for the user to press the correct key/mouse combination
      (via ``InputMonitor``).  When matched the step flashes green, then
      the next step appears after a short transition delay.
    • Falls back to timed auto-advance when pynput is unavailable or the
      step uses ``hotbar`` keys that cannot be detected.
    """

    def __init__(
        self,
        font_family: str = DEFAULT_FONT_FAMILY,
        skill_font_size: int = DEFAULT_SKILL_FONT_SIZE,
        input_font_size: int = DEFAULT_INPUT_FONT_SIZE,
        note_font_size: int = DEFAULT_NOTE_FONT_SIZE,
        skill_color: str = DEFAULT_SKILL_COLOR,
        input_color: str = DEFAULT_INPUT_COLOR,
        note_color: str = DEFAULT_NOTE_COLOR,
        show_protection: bool = True,
        show_notes: bool = True,
    ) -> None:
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

        self.screen_w: int = self.root.winfo_screenwidth()
        self.screen_h: int = self.root.winfo_screenheight()
        self.root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")

        _make_click_through(self.root)

        # --- Canvas (covers entire screen) ---------------------------------
        self.canvas = tk.Canvas(
            self.root,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
            width=self.screen_w,
            height=self.screen_h,
        )
        self.canvas.pack()

        # --- Fonts ---------------------------------------------------------
        self.skill_font = tkfont.Font(
            family=font_family, size=skill_font_size, weight="bold"
        )
        self.input_font = tkfont.Font(family=font_family, size=input_font_size)
        self.note_font = tkfont.Font(family=font_family, size=note_font_size)
        self.counter_font = tkfont.Font(family=font_family, size=note_font_size - 2)
        self.header_font = tkfont.Font(
            family=font_family, size=note_font_size, slant="italic"
        )

        # --- Colours -------------------------------------------------------
        self.skill_color: str = skill_color
        self.input_color: str = input_color
        self.note_color: str = note_color
        self.show_protection: bool = show_protection
        self.show_notes: bool = show_notes

        # --- Display anchor (bottom-centre of screen) ----------------------
        self.cx: int = self.screen_w // 2
        self.cy: int = int(self.screen_h * 0.85)
        self._load_position()

        # --- Input monitor -------------------------------------------------
        self.input_monitor = InputMonitor()
        self.input_monitor.start()

        # --- Combo playback state ------------------------------------------
        self._combo_data: Optional[Dict[str, Any]] = None
        self._combo_name: str = ""
        self._steps: List[Dict[str, Any]] = []
        self._current_step: int = 0
        self._transition_ms: int = 200  # pause after key match before next step
        self._is_running: bool = False
        self._loop: bool = True
        self._after_id: Optional[str] = None
        self._idle_reset_ms: int = 0  # 0 = disabled
        self._idle_reset_id: Optional[str] = None

        # --- Reposition mode state -----------------------------------------
        self._reposition_mode: bool = False
        self._drag_last_x: int = 0
        self._drag_last_y: int = 0

        # --- Key remapping (canonical combo key → physical key) ------------
        self._key_remap: Dict[str, str] = {}

        # External hooks (set by main.py)
        self.on_combo_finished: Optional[Callable] = None
        self.get_skill_info: Optional[Callable] = None

        logger.info("Overlay initialised (transparent canvas, key-press mode)")

    # =====================================================================
    # Configuration
    # =====================================================================
    def set_key_remap(self, remap: Dict[str, str]) -> None:
        """Set the key remapping table (canonical combo key → physical key)."""
        self._key_remap = remap
        if remap:
            logger.info(f"Key remap active: {remap}")

    def set_idle_reset_ms(self, ms: int) -> None:
        """Set the idle-reset timeout (ms).  0 = disabled."""
        self._idle_reset_ms = max(int(ms), 0)
        if self._idle_reset_ms:
            logger.info(f"Idle reset timeout: {self._idle_reset_ms}ms")

    # =====================================================================
    # Drawing helpers
    # =====================================================================
    def _draw_outlined_text(
        self,
        x: int,
        y: int,
        text: str,
        font: tkfont.Font,
        color: str,
        anchor: str = "center",
        tag: str = "step",
    ) -> None:
        """Draw *text* with a dark outline for readability over any background."""
        t = OUTLINE_THICKNESS
        for dx in range(-t, t + 1):
            for dy in range(-t, t + 1):
                if dx == 0 and dy == 0:
                    continue
                # Only draw on the "ring" (skip interior for performance)
                if abs(dx) + abs(dy) <= t:
                    continue
                self.canvas.create_text(
                    x + dx,
                    y + dy,
                    text=text,
                    font=font,
                    fill=OUTLINE_COLOR,
                    anchor=anchor,
                    tags=(tag,),
                )
        # Main text on top
        self.canvas.create_text(
            x,
            y,
            text=text,
            font=font,
            fill=color,
            anchor=anchor,
            tags=(tag,),
        )

    def _clear_display(self) -> None:
        """Remove all canvas items tagged 'step'."""
        self.canvas.delete("step")

    # =====================================================================
    # Combo lifecycle
    # =====================================================================
    def start_combo(
        self,
        combo_data: Dict[str, Any],
        combo_name: str = "",
        step_delay_ms: Optional[int] = None,
        loop: bool = True,
    ) -> None:
        """Begin displaying a combo.  Steps wait for user key presses."""
        self.stop_combo()

        self._combo_data = combo_data
        self._combo_name = combo_name or combo_data.get("name", "Combo")
        self._steps = combo_data.get("steps", [])
        self._current_step = 0
        self._loop = loop

        if step_delay_ms is not None:
            self._transition_ms = step_delay_ms
        else:
            self._transition_ms = combo_data.get("combo_window_ms", 200)

        if not self._steps:
            logger.warning(f"Combo '{self._combo_name}' has no steps")
            return

        self._is_running = True
        logger.info(
            f"Starting combo: {self._combo_name} "
            f"({len(self._steps)} steps, {self._transition_ms}ms transition)"
        )
        self._show_intro()

    def stop_combo(self) -> None:
        """Stop playback and clear the display."""
        was_running = self._is_running
        self._is_running = False
        self.input_monitor.clear_target()
        self._cancel_idle_reset()
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._clear_display()
        if was_running:
            logger.info("Combo stopped")

    def is_running(self) -> bool:
        return self._is_running

    # =====================================================================
    # Intro screen
    # =====================================================================
    def _show_intro(self) -> None:
        """Brief splash with the combo name, then show the first step."""
        self._clear_display()
        self._draw_outlined_text(
            self.cx,
            self.cy - 30,
            self._combo_name,
            self.skill_font,
            self.skill_color,
        )
        mode_label = "press keys to advance" if INPUT_AVAILABLE else "timed mode"
        self._draw_outlined_text(
            self.cx,
            self.cy + 20,
            f"{len(self._steps)} steps — {mode_label}",
            self.note_font,
            self.note_color,
        )
        self._after_id = self.root.after(2000, self._show_current_step)

    # =====================================================================
    # Step display
    # =====================================================================
    def _resolve_skill_name(self, skill_id: str) -> str:
        name = skill_id.replace("_", " ").title()
        if self.get_skill_info:
            info = self.get_skill_info(skill_id)
            if info and "name" in info:
                name = info["name"]
        return name

    def _resolve_protection(self, skill_id: str) -> str:
        if not self.show_protection or not self.get_skill_info:
            return ""
        info = self.get_skill_info(skill_id)
        if info:
            return info.get("protection", "")
        return ""

    def _show_current_step(self) -> None:
        if not self._is_running:
            return

        # Wrap around or finish
        if self._current_step >= len(self._steps):
            if self._loop:
                self._current_step = 0
            else:
                self.stop_combo()
                if self.on_combo_finished:
                    self.on_combo_finished()
                return

        step = self._steps[self._current_step]
        self._render_step(step)
        self._arm_input(step)

    def _render_step(self, step: Dict[str, Any]) -> None:
        """Draw the current step's info on the canvas."""
        self._clear_display()

        skill_id: str = step.get("skill", "")
        skill_name = self._resolve_skill_name(skill_id)
        protection = self._resolve_protection(skill_id)
        input_text: str = step.get("input", "")
        note: str = step.get("note", "")
        total = len(self._steps)
        counter = f"Step {self._current_step + 1} / {total}"

        y = self.cy

        # Row 1 — combo name (small italic header)
        self._draw_outlined_text(
            self.cx,
            y - 80,
            self._combo_name,
            self.header_font,
            "#888888",
        )

        # Row 2 — skill name (large gold)
        self._draw_outlined_text(
            self.cx,
            y - 35,
            skill_name,
            self.skill_font,
            self.skill_color,
        )

        # Protection badge beside skill name
        if protection:
            prot_color = PROTECTION_COLORS.get(protection, "#888888")
            half_w = self.skill_font.measure(skill_name) // 2
            self._draw_outlined_text(
                self.cx + half_w + 35,
                y - 35,
                f"[{protection.upper()}]",
                self.note_font,
                prot_color,
            )

        # Row 3 — input keys (white)
        self._draw_outlined_text(
            self.cx,
            y + 10,
            input_text,
            self.input_font,
            self.input_color,
        )

        # Row 4 — note (grey)
        if self.show_notes and note:
            self._draw_outlined_text(
                self.cx,
                y + 48,
                note,
                self.note_font,
                self.note_color,
            )

        # Row 5 — step counter
        counter_y = (y + 78) if (self.show_notes and note) else (y + 48)
        self._draw_outlined_text(
            self.cx,
            counter_y,
            counter,
            self.counter_font,
            "#666666",
        )

    # =====================================================================
    # Input detection
    # =====================================================================
    def _arm_input(self, step: Dict[str, Any]) -> None:
        """
        Configure the InputMonitor to watch for *step*'s keys.
        Supports alt_keys for skills with alternative inputs (e.g. Shift+A / Shift+D).
        Applies key remapping so users with non-default BDO keybinds are detected.
        Falls back to a timed advance for hotbar-only or when pynput is unavailable.
        """
        raw_keys: List[str] = step.get("keys", [])
        alt_keys: List[str] = step.get("alt_keys", [])

        # Fall back to skill definition's keys_alt when the step omits it
        if not alt_keys and self.get_skill_info:
            skill_id = step.get("skill", "")
            if skill_id:
                info = self.get_skill_info(skill_id)
                if info and "keys_alt" in info:
                    alt_keys = info["keys_alt"]

        def _remap_and_filter(keys: List[str]) -> List[str]:
            return [
                self._key_remap.get(k.lower(), k.lower())
                for k in keys
                if k.lower() != "hotbar"
            ]

        primary = _remap_and_filter(raw_keys)
        key_sets: List[List[str]] = []
        if primary:
            key_sets.append(primary)
        if alt_keys:
            alt = _remap_and_filter(alt_keys)
            if alt:
                key_sets.append(alt)

        if not key_sets or not INPUT_AVAILABLE:
            # Cannot detect keys — auto-advance after a generous timeout
            fallback_ms = max(self._transition_ms, 1500)
            self._after_id = self.root.after(fallback_ms, self._advance)
            return

        # pynput will call _on_keys_matched from a listener thread;
        # root.after(0, …) is thread-safe and posts to the Tk event queue.
        self.input_monitor.set_target(
            key_sets,
            on_match=lambda: self.root.after(0, self._on_keys_matched),
        )

        # Start idle-reset timer (resets combo to step 1 if no input)
        self._cancel_idle_reset()
        if self._idle_reset_ms > 0 and self._current_step > 0:
            self._idle_reset_id = self.root.after(self._idle_reset_ms, self._idle_reset)

    def _on_keys_matched(self) -> None:
        """Called (on the Tk thread) when the user presses the correct keys."""
        if not self._is_running:
            return
        self._cancel_idle_reset()

        # --- Brief green "success" flash -----------------------------------
        step = self._steps[self._current_step]
        skill_id: str = step.get("skill", "")
        skill_name = self._resolve_skill_name(skill_id)

        self._clear_display()
        self._draw_outlined_text(
            self.cx,
            self.cy - 35,
            f"✓  {skill_name}",
            self.skill_font,
            DEFAULT_SUCCESS_COLOR,
        )

        # Advance after the transition delay
        self._after_id = self.root.after(self._transition_ms, self._advance)

    def _cancel_idle_reset(self) -> None:
        if self._idle_reset_id is not None:
            self.root.after_cancel(self._idle_reset_id)
            self._idle_reset_id = None

    def _idle_reset(self) -> None:
        """Reset combo back to step 1 after idle timeout."""
        self._idle_reset_id = None
        if not self._is_running:
            return
        logger.info(f"Idle timeout ({self._idle_reset_ms}ms) — resetting to step 1")
        self.input_monitor.clear_target()
        self._current_step = 0
        self._show_current_step()

    def _advance(self) -> None:
        """Move to the next step."""
        if not self._is_running:
            return
        self.input_monitor.clear_target()
        self._current_step += 1
        self._show_current_step()

    # =====================================================================
    # Reposition mode
    # =====================================================================
    def enable_reposition(self) -> None:
        """Enter reposition mode: overlay becomes draggable."""
        if self._reposition_mode:
            return
        self._reposition_mode = True

        # Pause combo input detection so clicks don't advance steps
        self.input_monitor.clear_target()
        self._cancel_idle_reset()
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

        # Remove click-through so the overlay captures mouse events
        _remove_click_through(self.root)

        # Drag cursor and bindings
        self.canvas.config(cursor="fleur")
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)

        # Draw visual handle
        self._draw_reposition_handle()
        logger.info("Reposition mode enabled")

    def disable_reposition(self) -> None:
        """Exit reposition mode: overlay becomes click-through again."""
        if not self._reposition_mode:
            return
        self._reposition_mode = False

        # Remove drag bindings and cursor
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.config(cursor="")

        # Remove reposition visual handle
        self.canvas.delete("reposition")

        # Re-enable click-through
        _make_click_through(self.root)

        # Save position to disk
        self._save_position()

        # Resume combo if a combo is active
        if self._is_running and self._steps:
            self._show_current_step()

        logger.info("Reposition mode disabled — position saved")

    def toggle_reposition(self) -> bool:
        """Toggle reposition mode.  Returns the new state."""
        if self._reposition_mode:
            self.disable_reposition()
        else:
            self.enable_reposition()
        return self._reposition_mode

    # ----- reposition visuals ---------------------------------------------

    def _draw_reposition_handle(self) -> None:
        """Draw a visual indicator showing the text anchor and instructions."""
        self.canvas.delete("reposition")

        # If no combo is running, show sample text so user can preview position
        if not self._is_running:
            self._draw_outlined_text(
                self.cx,
                self.cy - 35,
                "Sample Skill Name",
                self.skill_font,
                self.skill_color,
                tag="reposition",
            )
            self._draw_outlined_text(
                self.cx,
                self.cy + 10,
                "Shift + LMB",
                self.input_font,
                self.input_color,
                tag="reposition",
            )

        # Dashed rectangle around text area
        pad_x, pad_y = 250, 110
        self.canvas.create_rectangle(
            self.cx - pad_x,
            self.cy - pad_y,
            self.cx + pad_x,
            self.cy + pad_y,
            outline="#FFD700",
            width=2,
            dash=(6, 4),
            tags=("reposition",),
        )

        # Crosshair at anchor point
        ch = 14
        self.canvas.create_line(
            self.cx - ch,
            self.cy,
            self.cx + ch,
            self.cy,
            fill="#FFD700",
            width=2,
            tags=("reposition",),
        )
        self.canvas.create_line(
            self.cx,
            self.cy - ch,
            self.cx,
            self.cy + ch,
            fill="#FFD700",
            width=2,
            tags=("reposition",),
        )

        # Instructions
        self._draw_outlined_text(
            self.cx,
            self.cy - pad_y - 25,
            "REPOSITION MODE — Drag to move",
            self.note_font,
            "#FFD700",
            tag="reposition",
        )
        self._draw_outlined_text(
            self.cx,
            self.cy + pad_y + 25,
            "Deselect 'Reposition' in tray menu to lock",
            self.counter_font,
            "#AAAAAA",
            tag="reposition",
        )

    # ----- drag handlers --------------------------------------------------

    def _on_drag_start(self, event: "tk.Event") -> None:
        self._drag_last_x = event.x
        self._drag_last_y = event.y

    def _on_drag_motion(self, event: "tk.Event") -> None:
        dx = event.x - self._drag_last_x
        dy = event.y - self._drag_last_y
        # Shift every canvas item (step text + reposition handle)
        self.canvas.move("all", dx, dy)
        self.cx += dx
        self.cy += dy
        self._drag_last_x = event.x
        self._drag_last_y = event.y

    # ----- position persistence -------------------------------------------

    def _load_position(self) -> None:
        """Load saved anchor position from disk (relative coords)."""
        try:
            with open(POSITION_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            rx = data.get("rx")
            ry = data.get("ry")
            if rx is not None and ry is not None:
                self.cx = int(float(rx) * self.screen_w)
                self.cy = int(float(ry) * self.screen_h)
                logger.info(f"Loaded overlay position ({self.cx}, {self.cy})")
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning(f"Could not load overlay position: {exc}")

    def _save_position(self) -> None:
        """Persist the current anchor as relative coordinates."""
        rx = self.cx / self.screen_w
        ry = self.cy / self.screen_h
        try:
            POSITION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(POSITION_FILE, "w", encoding="utf-8") as fh:
                json.dump({"rx": round(rx, 6), "ry": round(ry, 6)}, fh)
            logger.info(f"Saved overlay position (rx={rx:.4f}, ry={ry:.4f})")
        except Exception as exc:
            logger.warning(f"Could not save overlay position: {exc}")

    # =====================================================================
    # Thread-safe scheduling & main loop
    # =====================================================================
    def schedule(self, func: Callable, delay_ms: int = 0) -> None:
        """Post *func* onto the Tk event loop (safe to call from any thread)."""
        self.root.after(delay_ms, func)

    def run(self) -> None:
        """Enter the Tk main loop (blocks until shutdown)."""
        logger.info("Overlay main loop starting")
        self.root.mainloop()

    def shutdown(self) -> None:
        """Tear down the overlay and input monitor."""
        self.stop_combo()
        self.input_monitor.stop()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
