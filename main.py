"""
BDO Trainer - Main Application Entry Point

A transparent overlay tool that displays BDO class combo sequences
as subtitle-style prompts over the game client.

Usage:
    python main.py
"""

import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make sure the project root is on sys.path so `src` is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging (set up early so every module can use it)
# ---------------------------------------------------------------------------
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-18s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "bdo_trainer.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bdo_trainer")

# ---------------------------------------------------------------------------
# Imports (after path setup)
# ---------------------------------------------------------------------------
from src.combo_loader import ComboLoader
from src.editor import EditorWindow
from src.overlay import ComboOverlay
from src.settings_gui import SettingsWindow
from src.tray import TRAY_AVAILABLE, TrayManager

# Optional: global hotkeys via the `keyboard` library
_hotkeys_available = False
kb = None
try:
    import keyboard as kb

    _hotkeys_available = True
except ImportError:
    logger.warning("keyboard library not installed — global hotkeys disabled")
except Exception as exc:
    # On macOS/Linux the keyboard library may raise OSError or other
    # exceptions when it lacks root privileges or Accessibility permissions.
    logger.warning(
        f"keyboard library failed to initialise — global hotkeys disabled: {exc}"
    )


# ===========================================================================
# Application controller
# ===========================================================================
class BDOTrainerApp:
    """Wires together the combo loader, overlay, tray icon, and hotkeys."""

    def __init__(self):
        logger.info("=== BDO Trainer starting ===")

        # --- Load combos --------------------------------------------------
        self.loader = ComboLoader()
        self.combo_list = self.loader.get_combo_list()
        logger.info(f"Loaded {len(self.combo_list)} combos across classes/specs")

        if not self.combo_list:
            logger.error(
                "No combos found in config/classes/ — "
                "check that the directory exists and contains valid YAML."
            )

        # --- Create overlay -----------------------------------------------
        display = self.loader.get_display_settings()
        self.overlay = ComboOverlay(
            show_protection=display.get("show_protection_type", True),
            show_notes=True,
        )
        # Apply user key remappings (BDO key_bindings → physical keys)
        self.overlay.set_key_remap(self.loader.get_key_remap())

        # Apply idle-reset timeout (return to step 1 after inactivity)
        timing = self.loader.get_timing_settings()
        self.overlay.set_idle_reset_ms(timing.get("idle_reset_timeout_ms", 0))

        # --- Create system-tray icon --------------------------------------
        self.tray: TrayManager | None = None
        if TRAY_AVAILABLE:
            self.tray = TrayManager(
                class_tree=self.loader.get_class_tree(),
                on_combo_selected=self._on_combo_selected,
                on_stop=self._on_stop,
                on_exit=self._on_exit,
                on_reposition_toggle=self._on_reposition_toggle,
                on_setup_guide_toggle=self._on_setup_guide_toggle,
                on_settings=self._on_settings,
                on_editor=self._on_editor,
            )
        else:
            logger.warning("Tray icon unavailable — install pystray + Pillow")

        # --- Register global hotkeys -------------------------------------
        self._hotkey_hooks: list[str] = []
        self._setup_hotkeys()

        # Track current combo for stop / restart
        self._current_class: str = ""
        self._current_spec: str = ""
        self._current_combo_id: str = ""
        self._shutdown_done: bool = False

    # ------------------------------------------------------------------
    # Hotkey helpers
    # ------------------------------------------------------------------
    def _setup_hotkeys(self):
        if not _hotkeys_available or kb is None:
            return

        hk = self.loader.get_hotkeys()
        bindings = {
            hk.get("start_combo", "F5"): self._hotkey_restart,
            hk.get("stop_combo", "F6"): self._hotkey_stop,
            hk.get("next_step", "F7"): self._hotkey_next_page,
            hk.get("reset_combo", "F8"): self._hotkey_restart,
        }

        for key, callback in bindings.items():
            try:
                kb.add_hotkey(key, callback, suppress=False)
                self._hotkey_hooks.append(key)
                logger.info(f"Hotkey registered: {key}")
            except Exception as exc:
                logger.warning(f"Could not register hotkey {key}: {exc}")

    def _remove_hotkeys(self):
        if not _hotkeys_available or kb is None:
            return
        for key in self._hotkey_hooks:
            try:
                kb.remove_hotkey(key)
            except Exception:
                pass
        self._hotkey_hooks.clear()

    # ------------------------------------------------------------------
    # Callbacks (may be called from tray thread — use overlay.schedule)
    # ------------------------------------------------------------------
    def _on_combo_selected(self, class_name: str, spec_name: str, combo_id: str):
        """Called when the user picks a combo from the tray menu."""
        self._current_class = class_name
        self._current_spec = spec_name
        self._current_combo_id = combo_id
        # Schedule on the tkinter thread
        self.overlay.schedule(
            lambda: self._start_combo(class_name, spec_name, combo_id)
        )

    def _on_stop(self):
        """Called when user clicks Stop in the tray."""
        self.overlay.schedule(self.overlay.stop_combo)

    def _on_exit(self):
        """Called when user clicks Exit in the tray."""
        self.overlay.schedule(self._shutdown)

    def _on_reposition_toggle(self, enabled: bool):
        """Called when user toggles Reposition in the tray."""
        if enabled:
            self.overlay.schedule(self.overlay.enable_reposition)
        else:
            self.overlay.schedule(self.overlay.disable_reposition)

    def _on_setup_guide_toggle(self, enabled: bool):
        """Called when user toggles Setup Guide in the tray."""
        if enabled:
            self.overlay.schedule(self._show_setup_guide)
        else:
            self.overlay.schedule(self.overlay.hide_setup_guide)

    def _show_setup_guide(self):
        """Fetch guide data for the current class/spec and display it."""
        cls, spec = self._current_class, self._current_spec
        if not cls or not spec:
            logger.warning("Setup guide: no class/spec selected yet")
            if self.tray:
                self.tray.set_setup_guide_mode(False)
                self.tray.notify(
                    "BDO Trainer", "Select a combo first, then open the Setup Guide."
                )
            return
        guide_data = self.loader.get_setup_guide(cls, spec)
        if guide_data is None:
            logger.warning(f"Setup guide: no data for {cls}/{spec}")
            if self.tray:
                self.tray.set_setup_guide_mode(False)
            return
        self.overlay.show_setup_guide(guide_data)

    def _on_settings(self):
        """Called when user clicks Settings in the tray."""
        self.overlay.schedule(self._open_settings)

    def _open_settings(self):
        """Open the settings window (must run on the Tk thread)."""
        SettingsWindow.open(
            self.overlay.root,
            self.loader,
            on_save=self._on_settings_saved,
        )

    def _on_settings_saved(self, new_settings):
        """Called (on Tk thread) after the user saves settings."""
        # Update the loader's in-memory settings so every getter reflects
        # the new values immediately.
        self.loader.settings = new_settings

        # Re-apply key remapping to the overlay
        self.overlay.set_key_remap(self.loader.get_key_remap())

        # Re-apply idle-reset timeout
        timing = self.loader.get_timing_settings()
        self.overlay.set_idle_reset_ms(timing.get("idle_reset_timeout_ms", 0))

        # Re-register global hotkeys with potentially new keys
        self._remove_hotkeys()
        self._setup_hotkeys()

        logger.info("Live-reloaded settings from GUI")

    def _on_editor(self):
        """Called when user clicks Class & Combo Editor in the tray."""
        self.overlay.schedule(self._open_editor)

    def _open_editor(self):
        """Open the editor window (must run on the Tk thread)."""
        EditorWindow.open(
            self.overlay.root,
            self.loader,
            on_save=self._on_editor_saved,
        )

    def _on_editor_saved(self):
        """Called (on Tk thread) after the editor saves changes."""
        # Reload class configs and update the tray menu
        self.loader.reload()
        self.combo_list = self.loader.get_combo_list()

        if self.tray:
            self.tray.refresh_menu(self.loader.get_class_tree())

        logger.info("Reloaded class configs after editor save")

    def _hotkey_next_page(self):
        """Advance the setup-guide page (F7) when guide is showing."""
        if self.overlay.setup_guide_active:
            self.overlay.schedule(self.overlay.next_setup_page)

    def _hotkey_restart(self):
        """Re-start (or start) the current combo via hotkey."""
        cls, spec, cid = (
            self._current_class,
            self._current_spec,
            self._current_combo_id,
        )
        if cls and spec and cid:
            self.overlay.schedule(lambda: self._start_combo(cls, spec, cid))

    def _hotkey_stop(self):
        self.overlay.schedule(self.overlay.stop_combo)

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------
    def _start_combo(self, class_name: str, spec_name: str, combo_id: str):
        """Resolve the combo data and hand it to the overlay."""
        # Dismiss setup guide if it's showing
        if self.overlay.setup_guide_active:
            self.overlay.hide_setup_guide()
            if self.tray:
                self.tray.set_setup_guide_mode(False)

        combo_data = self.loader.get_combo(class_name, spec_name, combo_id)
        if combo_data is None:
            logger.error(f"Combo not found: {class_name}/{spec_name}/{combo_id}")
            return

        step_delay = self.loader.get_combo_window_ms(class_name, spec_name, combo_id)
        combo_name = combo_data.get("name", combo_id)

        # Bind skill-info lookup to the current class/spec so the overlay
        # resolves skill metadata from the correct context.
        self.overlay.get_skill_info = lambda sid: self.loader.get_skill_info(
            sid, class_name, spec_name
        )

        logger.info(f"Starting combo: {combo_name} ({step_delay}ms)")
        self.overlay.start_combo(
            combo_data=combo_data,
            combo_name=combo_name,
            step_delay_ms=step_delay,
            loop=True,
        )

        # Optional desktop notification
        if self.tray:
            self.tray.notify("BDO Trainer", f"Combo: {combo_name}")

    def _shutdown(self):
        """Gracefully tear everything down (idempotent)."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        logger.info("Shutting down…")
        self._remove_hotkeys()
        if self.tray:
            self.tray.stop()
        self.overlay.shutdown()

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------
    def run(self):
        """Start the tray icon, then enter the overlay main-loop (blocks)."""
        if self.tray:
            self.tray.start()

        logger.info(
            "BDO Trainer is running. Right-click the tray icon to select a combo."
        )

        # Print available hotkeys to console for discoverability
        hk = self.loader.get_hotkeys()
        logger.info(f"  Start / Restart combo : {hk.get('start_combo', 'F5')}")
        logger.info(f"  Stop combo            : {hk.get('stop_combo', 'F6')}")
        logger.info(f"  Reset combo           : {hk.get('reset_combo', 'F8')}")

        try:
            # Blocks until overlay.shutdown() is called
            self.overlay.run()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

        logger.info("=== BDO Trainer exited ===")


# ===========================================================================
# Script entry point
# ===========================================================================
def _ensure_admin() -> None:
    """Re-launch as admin when needed so input hooks work with elevated games."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        if ctypes.windll.shell32.IsUserAnAdmin():
            logger.info("Running with admin privileges")
            return

        logger.warning(
            "Not running as admin — BDO runs elevated, so input hooks "
            "will not work.  Re-launching with admin privileges…"
        )
        # ShellExecuteW returns an HINSTANCE > 32 on success
        script = str(Path(__file__).resolve())
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}'.strip(), None, 1
        )
        if ret > 32:
            sys.exit(0)
        else:
            logger.warning(
                "UAC prompt was declined or elevation failed — "
                "continuing without admin (input hooks may not work)"
            )
    except Exception as exc:
        logger.warning(f"Admin elevation check failed: {exc}")


def main():
    _ensure_admin()
    app = BDOTrainerApp()
    app.run()


if __name__ == "__main__":
    main()
