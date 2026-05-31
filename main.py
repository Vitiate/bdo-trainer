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
from src.editor import ClassEditorWindow, ComboEditorWindow
from src.overlay import ComboOverlay
from src.settings_gui import SettingsWindow
from src.tray import TRAY_AVAILABLE, TrayManager
from src.updater import check_and_prompt as check_for_updates

# Optional: global hotkeys via the `keyboard` library
_hotkeys_available = False
kb = None
if sys.platform == "darwin" and os.geteuid() != 0:
    # The keyboard library requires root on macOS; importing it is fine but
    # add_hotkey() spawns a listener thread that aborts without root.
    logger.warning(
        "keyboard library requires root on macOS — global hotkeys disabled. "
        "Use the tray menu instead, or run with sudo."
    )
else:
    try:
        import keyboard as kb

        _hotkeys_available = True
    except ImportError:
        logger.warning("keyboard library not installed — global hotkeys disabled")
    except Exception as exc:
        logger.warning(
            f"keyboard library failed to initialise — global hotkeys disabled: {exc}"
        )


# ===========================================================================
# Application controller
# ===========================================================================
class BDOTrainerApp:
    """Wires together the combo loader, overlay, tray icon, and hotkeys."""

    def __init__(self, show_overlay: bool = True):
        logger.info("=== BDO Trainer starting ===")
        self.show_overlay = show_overlay

        # --- One-shot migration (if user is upgrading from 0.4.x) ---------
        try:
            from scripts.migrate_class_yaml import (
                needs_migration as _needs_migration,
                run as _run_migration,
            )

            if _needs_migration():
                logger.info(
                    "Detected legacy class YAML files in config/classes/ — "
                    "running automatic migration to data/classes/ + "
                    "config/combos/<slug>/<bundle>/."
                )
                _run_migration(dry_run=False)
        except Exception:
            logger.exception("Auto-migration failed; continuing with whatever is on disk")

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
            show_window=show_overlay,
        )
        if not show_overlay:
            logger.info(
                "Overlay window disabled — running tray-only "
                "(combos will not be displayed in-game)"
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
                on_cc_panel_toggle=self._on_cc_panel_toggle,
                on_settings=self._on_settings,
                on_combo_editor=self._on_combo_editor,
                on_class_editor=self._on_class_editor,
                on_check_updates=self._on_check_updates,
            )
        else:
            logger.warning("Tray icon unavailable — install pystray + Pillow")

        # --- Register global hotkeys -------------------------------------
        self._hotkey_hooks: list[str] = []
        self._setup_hotkeys()

        # Track current combo for stop / restart
        self._current_class: str = ""
        self._current_spec: str = ""
        self._current_bundle_id: str = ""
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
    def _on_combo_selected(
        self,
        class_name: str,
        spec_name: str,
        bundle_id: str,
        combo_id: str,
    ):
        """Called when the user picks a combo from the tray menu."""
        class_changed = (
            class_name != self._current_class or spec_name != self._current_spec
        )
        self._current_class = class_name
        self._current_spec = spec_name
        self._current_bundle_id = bundle_id
        self._current_combo_id = combo_id
        # Persist active bundle so the setup guide / next-launch flow
        # can pick the right loadout for this class/spec.
        self.loader.settings_loader.set_active_bundle(class_name, spec_name, bundle_id)
        if class_changed and self.overlay.cc_panel_active:
            skills = self.loader.classes.get_skills(class_name, spec_name)
            self.overlay.schedule(lambda: self.overlay.update_cc_panel(skills))
        self.overlay.schedule(
            lambda: self._start_combo(class_name, spec_name, bundle_id, combo_id)
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

    def _on_cc_panel_toggle(self, enabled: bool):
        """Called when user toggles 'Show CC Skills' in the tray."""
        self.loader.set_show_cc_panel(enabled)
        if enabled:
            self.overlay.schedule(self._show_cc_panel)
        else:
            self.overlay.schedule(self.overlay.hide_cc_panel)

    def _show_cc_panel(self):
        """Resolve the active class's skills and display the CC panel."""
        cls, spec = self._current_class, self._current_spec
        if not cls or not spec:
            # Fallback: use the first class/spec we know about so the
            # panel isn't empty if the user opens it before picking a combo.
            keys = self.loader.classes.keys()
            if keys:
                cls, spec = keys[0]
        if not cls or not spec:
            logger.warning("CC panel: no class data available")
            if self.tray:
                self.tray.set_cc_panel_mode(False)
            return
        skills = self.loader.classes.get_skills(cls, spec)
        self.overlay.show_cc_panel(skills)

    def _show_setup_guide(self):
        """Fetch guide data for the current class/spec/bundle and display it."""
        cls, spec, bid = (
            self._current_class, self._current_spec, self._current_bundle_id,
        )
        if not cls or not spec:
            logger.warning("Setup guide: no class/spec selected yet")
            if self.tray:
                self.tray.set_setup_guide_mode(False)
                self.tray.notify(
                    "BDO Trainer", "Select a combo first, then open the Setup Guide."
                )
            return
        guide_data = self.loader.get_setup_guide(cls, spec, bid or None)
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

    def _on_check_updates(self):
        """Called when user clicks 'Check for Updates…' in the tray."""
        check_for_updates(
            schedule=self.overlay.schedule,
            parent_supplier=lambda: self.overlay.root,
            show_no_update_dialog=True,
            show_failure_dialog=True,
        )

    def _check_for_updates_on_startup(self):
        """Silent update check fired once at launch."""
        check_for_updates(
            schedule=self.overlay.schedule,
            parent_supplier=lambda: self.overlay.root,
            show_no_update_dialog=False,
            show_failure_dialog=False,
        )

    def _on_combo_editor(self):
        """Called when user clicks 'Combo Editor' in the tray."""
        self.overlay.schedule(self._open_combo_editor)

    def _open_combo_editor(self):
        ComboEditorWindow.open(
            self.overlay.root,
            self.loader,
            on_save=self._on_editor_saved,
        )

    def _on_class_editor(self):
        """Called when user clicks 'Class Editor' in the tray."""
        self.overlay.schedule(self._open_class_editor)

    def _open_class_editor(self):
        ClassEditorWindow.open(
            self.overlay.root,
            self.loader,
            on_save=self._on_editor_saved,
        )

    def _on_editor_saved(self):
        """Called (on Tk thread) after either editor saves changes."""
        self.loader.reload()
        self.combo_list = self.loader.get_combo_list()
        if self.tray:
            self.tray.refresh_menu(self.loader.get_class_tree())
        logger.info("Reloaded configs after editor save")

    def _hotkey_next_page(self):
        """Advance the setup-guide page (F7) when guide is showing."""
        if self.overlay.setup_guide_active:
            self.overlay.schedule(self.overlay.next_setup_page)

    def _hotkey_restart(self):
        """Re-start (or start) the current combo via hotkey."""
        cls, spec, bid, cid = (
            self._current_class,
            self._current_spec,
            self._current_bundle_id,
            self._current_combo_id,
        )
        if cls and spec and cid:
            self.overlay.schedule(
                lambda: self._start_combo(cls, spec, bid, cid)
            )

    def _hotkey_stop(self):
        self.overlay.schedule(self.overlay.stop_combo)

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------
    def _start_combo(
        self,
        class_name: str,
        spec_name: str,
        bundle_id: str,
        combo_id: str,
    ):
        """Resolve the combo data and hand it to the overlay."""
        if self.overlay.setup_guide_active:
            self.overlay.hide_setup_guide()
            if self.tray:
                self.tray.set_setup_guide_mode(False)

        combo_data = self.loader.get_combo(
            class_name, spec_name, combo_id, bundle_id=bundle_id or None,
        )
        if combo_data is None:
            logger.error(
                f"Combo not found: {class_name}/{spec_name}/{bundle_id}/{combo_id}"
            )
            return

        step_delay = self.loader.get_combo_window_ms(
            class_name, spec_name, combo_id, bundle_id=bundle_id or None,
        )
        combo_name = combo_data.get("name", combo_id)

        self.overlay.get_skill_info = lambda sid: self.loader.get_skill_info(
            sid, class_name, spec_name
        )

        logger.info(
            f"Starting combo: {combo_name} ({step_delay}ms) — "
            f"{class_name}/{spec_name}/{bundle_id}"
        )
        self.overlay.start_combo(
            combo_data=combo_data,
            combo_name=combo_name,
            step_delay_ms=step_delay,
            loop=True,
        )

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
            # Restore the persisted "Show CC Skills" toggle from settings.
            if self.loader.get_show_cc_panel():
                self.tray.set_cc_panel_mode(True)
                self.overlay.schedule(self._show_cc_panel)

        # Check GitHub for a newer release in the background.
        self._check_for_updates_on_startup()

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


def _check_macos_accessibility() -> None:
    """Prompt the user for Accessibility permissions on macOS if not granted."""
    if sys.platform != "darwin":
        return
    try:
        # Use a subprocess to avoid segfaults from ctypes CF object management
        import subprocess

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import objc;"
                "from ApplicationServices import AXIsProcessTrustedWithOptions;"
                "from Foundation import NSDictionary;"
                "opts = NSDictionary.dictionaryWithObject_forKey_(True, 'AXTrustedCheckOptionPrompt');"
                "print(AXIsProcessTrustedWithOptions(opts))",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            trusted = result.stdout.strip() == "True"
            if trusted:
                logger.info("macOS Accessibility permissions: granted")
            else:
                logger.warning(
                    "macOS Accessibility permissions: NOT granted — "
                    "a system prompt has been shown. Grant access and restart."
                )
            return
    except Exception:
        pass

    # Fallback: just check without prompting (no pyobjc available)
    try:
        import subprocess

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import ctypes, ctypes.util;"
                "lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library('ApplicationServices'));"
                "lib.AXIsProcessTrusted.restype = ctypes.c_bool;"
                "print(lib.AXIsProcessTrusted())",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            trusted = result.stdout.strip() == "True"
            if trusted:
                logger.info("macOS Accessibility permissions: granted")
            else:
                logger.warning(
                    "macOS Accessibility permissions: NOT granted. "
                    "Go to System Settings > Privacy & Security > Accessibility "
                    "and grant access to your terminal or Python."
                )
        else:
            logger.warning("macOS Accessibility check: could not determine status")
    except Exception as exc:
        logger.warning(f"macOS Accessibility check failed: {exc}")


def _run_editor_only():
    """Launch the Combo + Class editors in standalone tkinter windows."""
    import tkinter as tk

    logger.info("=== BDO Trainer — Editor-only mode ===")

    # Run migration if necessary so the editor opens against the new layout.
    try:
        from scripts.migrate_class_yaml import (
            needs_migration as _needs_migration,
            run as _run_migration,
        )

        if _needs_migration():
            _run_migration(dry_run=False)
    except Exception:
        logger.exception("Auto-migration failed (editor mode)")

    loader = ComboLoader()
    logger.info(
        f"Loaded {len(loader.get_combo_list())} combos across "
        f"{len(loader.bundles.bundles)} bundles"
    )

    root = tk.Tk()
    root.title("BDO Trainer — Editor")
    root.withdraw()

    def on_editor_saved():
        loader.reload()
        logger.info("Reloaded configs after editor save")

    ComboEditorWindow.open(root, loader, on_save=on_editor_saved)
    ClassEditorWindow.open(root, loader, on_save=on_editor_saved)

    # When the last editor window closes, exit.
    def _check_alive():
        combo_open = (
            ComboEditorWindow._instance is not None
            and ComboEditorWindow._instance.window.winfo_exists()
        )
        class_open = (
            ClassEditorWindow._instance is not None
            and ClassEditorWindow._instance.window.winfo_exists()
        )
        if not combo_open and not class_open:
            root.quit()
            return
        root.after(500, _check_alive)

    root.after(500, _check_alive)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass

    logger.info("=== BDO Trainer — Editor closed ===")


def main():
    if "--editor" in sys.argv:
        _run_editor_only()
        return

    _ensure_admin()
    _check_macos_accessibility()
    # On macOS the overlay isn't useful (BDO doesn't run there), so by
    # default we boot the tray + editor flow without the overlay window.
    # ``--overlay`` forces it on; ``--no-overlay`` forces it off.
    show_overlay = sys.platform != "darwin"
    if "--overlay" in sys.argv:
        show_overlay = True
    if "--no-overlay" in sys.argv:
        show_overlay = False
    app = BDOTrainerApp(show_overlay=show_overlay)
    app.run()


if __name__ == "__main__":
    main()
