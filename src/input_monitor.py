"""
Input Monitor — tracks keyboard + mouse state via pynput.

Watches for a target set of keys/buttons.  When every key in the target
set is held simultaneously the *on_match* callback fires **once** (edge-
triggered so holding keys doesn't re-fire).

Key names use the same strings as combo YAML files:
    shift, space, ctrl, alt, tab, enter, esc   – modifier / special
    a-z, 0-9                                    – character keys
    lmb, rmb, mmb                               – mouse buttons
"""

import logging
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger("bdo_trainer")

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

    # Special-key mapping (built once; empty if pynput unavailable)
    _SPECIAL_KEY_MAP: dict = {}
    if INPUT_AVAILABLE:
        _SPECIAL_KEY_MAP = {
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

    def __init__(self) -> None:
        self._pressed: Set[str] = set()
        self._required_sets: List[Set[str]] = []
        self._on_match: Optional[Callable] = None
        self._matched: bool = False
        self._kb_listener = None
        self._mouse_listener = None
        # Secondary watchers — fire alongside the main target. Used by
        # the CC panel to track skill activations without disturbing the
        # combo player's exclusive ``set_target`` channel.
        # name → {"sets": [Set[str]], "on_match": Callable, "matched": bool}
        self._taps: Dict[str, Dict[str, object]] = {}

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
        """Stop watching for any keys."""
        self._required_sets = []
        self._on_match = None
        self._matched = False

    def _reset_edge_trigger(self) -> None:
        """Allow the match callback to fire again.

        Called after the user releases keys between steps.
        """
        self._matched = False
        # Snapshot the values — taps may be added/removed by callbacks
        # downstream (priority player re-arms its tap on every press).
        for tap in list(self._taps.values()):
            req_sets: List[Set[str]] = tap["sets"]  # type: ignore[assignment]
            still_held = any(req.issubset(self._pressed) for req in req_sets)
            if not still_held:
                tap["matched"] = False

    # ------------------------------------------------------------------
    # Taps — secondary watchers (e.g. CC panel)
    # ------------------------------------------------------------------
    def add_tap(
        self, name: str, key_sets: List[List[str]], on_match: Callable
    ) -> None:
        """Add a named secondary watcher.

        Independent of ``set_target``; fires once per press whenever any
        of *key_sets* is fully held. Holding the keys does not re-fire;
        the trigger resets when no required set remains held.
        """
        sets = [
            {k.lower() for k in ks if k.lower() != "hotbar"} for ks in key_sets
        ]
        sets = [s for s in sets if s]
        if not sets:
            self._taps.pop(name, None)
            return
        self._taps[name] = {"sets": sets, "on_match": on_match, "matched": False}

    def remove_tap(self, name: str) -> None:
        self._taps.pop(name, None)

    def clear_taps(self) -> None:
        self._taps.clear()

    # ------------------------------------------------------------------
    # Key normalization
    # ------------------------------------------------------------------
    def _normalize_key(self, key) -> Optional[str]:
        """Convert a pynput key object to our canonical string."""
        if not INPUT_AVAILABLE:
            return None

        # Special keys (shift, space, ctrl, …)
        if key in self._SPECIAL_KEY_MAP:
            return self._SPECIAL_KEY_MAP[key]

        # Character keys
        try:
            char = key.char
            if char:
                return char.lower()
        except AttributeError:
            pass

        # Virtual key code fallback (e.g. numpad, media keys)
        try:
            vk = key.vk
            if vk is not None:
                if 65 <= vk <= 90:
                    return chr(vk).lower()
                if 48 <= vk <= 57:
                    return chr(vk)
        except AttributeError:
            pass

        return None

    # ------------------------------------------------------------------
    # pynput callbacks
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
            self._reset_edge_trigger()

    def _on_click(self, x, y, button, pressed) -> None:
        if not INPUT_AVAILABLE:
            return
        btn_map: Dict[str, str] = {
            _pynput_mouse.Button.left.name: "lmb",
            _pynput_mouse.Button.right.name: "rmb",
            _pynput_mouse.Button.middle.name: "mmb",
        }
        name = btn_map.get(button.name)
        if not name:
            return
        if pressed:
            self._pressed.add(name)
            self._check()
        else:
            self._pressed.discard(name)
            self._reset_edge_trigger()

    # ------------------------------------------------------------------
    # Match check
    # ------------------------------------------------------------------
    def _check(self) -> None:
        """Fire callbacks for any matching primary target or tap."""
        # Primary target — single edge-triggered channel
        if not self._matched and self._required_sets:
            for req in self._required_sets:
                if req.issubset(self._pressed):
                    self._matched = True
                    if self._on_match:
                        self._on_match()
                    break
        # Secondary taps — independent of the primary target.
        # Snapshot the dict so a tap's callback can add/remove taps
        # (e.g. PriorityPlayer re-arms a different tap on every press)
        # without "dictionary changed size during iteration".
        for tap in list(self._taps.values()):
            if tap["matched"]:
                continue
            req_sets: List[Set[str]] = tap["sets"]  # type: ignore[assignment]
            for req in req_sets:
                if req.issubset(self._pressed):
                    tap["matched"] = True
                    cb = tap["on_match"]
                    if callable(cb):
                        cb()
                    break
