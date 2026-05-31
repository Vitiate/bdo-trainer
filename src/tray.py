"""
Tray Manager - System tray icon with combo selection menu
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("bdo_trainer")

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont

    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    logger.warning("pystray or Pillow not installed — tray icon disabled")


def _create_icon_image(size: int = 64) -> "Image.Image":
    """Generate a simple tray icon using Pillow (Solarized Dark palette)."""
    img = Image.new("RGB", (size, size), color="#002B36")  # base03
    draw = ImageDraw.Draw(img)

    # Draw a border
    draw.rectangle([1, 1, size - 2, size - 2], outline="#268BD2", width=2)  # blue

    # Draw "DK" text
    try:
        font = ImageFont.truetype("arial.ttf", size // 3)
    except (OSError, IOError):
        font = ImageFont.load_default()

    text = "DK"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2
    y = (size - text_h) // 2
    draw.text((x, y), text, fill="#B58900", font=font)  # yellow

    return img


class TrayManager:
    """System tray icon with combo selection menu"""

    def __init__(
        self,
        class_tree: Dict[str, Dict[str, Dict[str, List[Tuple[str, str]]]]],
        on_combo_selected: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
        on_reposition_toggle: Optional[Callable] = None,
        on_setup_guide_toggle: Optional[Callable] = None,
        on_cc_panel_toggle: Optional[Callable] = None,
        on_settings: Optional[Callable] = None,
        on_combo_editor: Optional[Callable] = None,
        on_class_editor: Optional[Callable] = None,
        on_check_updates: Optional[Callable] = None,
        on_exit: Optional[Callable] = None,
    ):
        """
        Args:
            class_tree: {class: {spec: {bundle_id: [(combo_id, display_name), ...]}}}
            on_combo_selected: Callback(class, spec, bundle_id, combo_id)
                when a combo is picked
            on_stop: Callback when "Stop" is selected
            on_reposition_toggle: Callback(enabled: bool)
            on_setup_guide_toggle: Callback(enabled: bool)
            on_cc_panel_toggle: Callback(enabled: bool)
            on_settings: Callback when "Settings" is selected
            on_combo_editor: Callback when "Combo Editor" is selected
            on_class_editor: Callback when "Class Editor" is selected
            on_check_updates: Callback when "Check for Updates…" is selected
            on_exit: Callback when "Exit" is selected
        """
        if not TRAY_AVAILABLE:
            raise RuntimeError("pystray/Pillow not installed")

        self.class_tree = class_tree
        self.on_combo_selected = on_combo_selected
        self.on_stop = on_stop
        self.on_reposition_toggle = on_reposition_toggle
        self.on_setup_guide_toggle = on_setup_guide_toggle
        self.on_cc_panel_toggle = on_cc_panel_toggle
        self.on_settings = on_settings
        self.on_combo_editor = on_combo_editor
        self.on_class_editor = on_class_editor
        self.on_check_updates = on_check_updates
        self.on_exit = on_exit

        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self._reposition_mode: bool = False
        self._setup_guide_mode: bool = False
        self._cc_panel_mode: bool = False

    def _build_menu(self) -> pystray.Menu:
        """Build the tray context menu with Class > Spec > Combo submenus"""
        menu_items = []

        # Title (non-clickable)
        menu_items.append(pystray.MenuItem("BDO Trainer", None, enabled=False))
        menu_items.append(pystray.Menu.SEPARATOR)

        # Build Class > Spec > Bundle > Combo hierarchy.
        class_sub_items = []
        for class_name, specs in self.class_tree.items():
            spec_sub_items = []
            for spec_name, bundles in specs.items():
                bundle_sub_items = []
                for bundle_id, combos in bundles.items():
                    combo_items = []
                    for combo_id, display_name in combos:
                        action = self._make_combo_action(
                            class_name, spec_name, bundle_id, combo_id,
                        )
                        combo_items.append(pystray.MenuItem(display_name, action))
                    if combo_items:
                        bundle_sub_items.append(
                            pystray.MenuItem(bundle_id, pystray.Menu(*combo_items))
                        )
                if bundle_sub_items:
                    spec_sub_items.append(
                        pystray.MenuItem(spec_name, pystray.Menu(*bundle_sub_items))
                    )
            if spec_sub_items:
                class_sub_items.append(
                    pystray.MenuItem(class_name, pystray.Menu(*spec_sub_items))
                )

        if class_sub_items:
            menu_items.append(pystray.MenuItem("Class", pystray.Menu(*class_sub_items)))

        menu_items.append(pystray.Menu.SEPARATOR)

        # Stop
        menu_items.append(pystray.MenuItem("Stop Combo", self._on_stop_clicked))

        # Reposition (checkable toggle)
        menu_items.append(
            pystray.MenuItem(
                "Reposition Overlay",
                self._on_reposition_clicked,
                checked=lambda item: self._reposition_mode,
            )
        )

        # Setup Guide (checkable toggle)
        menu_items.append(
            pystray.MenuItem(
                "Setup Guide",
                self._on_setup_guide_clicked,
                checked=lambda item: self._setup_guide_mode,
            )
        )

        # CC Skills panel (checkable toggle)
        menu_items.append(
            pystray.MenuItem(
                "Show CC Skills",
                self._on_cc_panel_clicked,
                checked=lambda item: self._cc_panel_mode,
            )
        )

        menu_items.append(pystray.Menu.SEPARATOR)

        # Settings + editors
        menu_items.append(pystray.MenuItem("Settings", self._on_settings_clicked))
        menu_items.append(
            pystray.MenuItem("Combo Editor", self._on_combo_editor_clicked)
        )
        menu_items.append(
            pystray.MenuItem("Class Editor", self._on_class_editor_clicked)
        )

        menu_items.append(
            pystray.MenuItem("Check for Updates…", self._on_check_updates_clicked)
        )

        menu_items.append(pystray.Menu.SEPARATOR)

        # Exit
        menu_items.append(pystray.MenuItem("Exit", self._on_exit_clicked))

        return pystray.Menu(*menu_items)

    def _make_combo_action(
        self, class_name: str, spec_name: str, bundle_id: str, combo_id: str,
    ):
        """Create a callback closure for a specific combo."""

        def action(icon, item):
            logger.info(
                f"Tray: combo selected — {class_name}/{spec_name}/{bundle_id}/{combo_id}"
            )
            if self.on_combo_selected:
                self.on_combo_selected(class_name, spec_name, bundle_id, combo_id)

        return action

    def _on_stop_clicked(self, icon, item):
        logger.info("Tray: stop clicked")
        if self.on_stop:
            self.on_stop()

    def _on_settings_clicked(self, icon, item):
        logger.info("Tray: settings clicked")
        if self.on_settings:
            self.on_settings()

    def _on_combo_editor_clicked(self, icon, item):
        logger.info("Tray: combo editor clicked")
        if self.on_combo_editor:
            self.on_combo_editor()

    def _on_class_editor_clicked(self, icon, item):
        logger.info("Tray: class editor clicked")
        if self.on_class_editor:
            self.on_class_editor()

    def _on_check_updates_clicked(self, icon, item):
        logger.info("Tray: check for updates clicked")
        if self.on_check_updates:
            self.on_check_updates()

    def _on_reposition_clicked(self, icon, item):
        self._reposition_mode = not self._reposition_mode
        logger.info(
            f"Tray: reposition toggled — {'ON' if self._reposition_mode else 'OFF'}"
        )
        if self.on_reposition_toggle:
            self.on_reposition_toggle(self._reposition_mode)

    def _on_setup_guide_clicked(self, icon, item):
        self._setup_guide_mode = not self._setup_guide_mode
        logger.info(
            f"Tray: setup guide toggled — {'ON' if self._setup_guide_mode else 'OFF'}"
        )
        if self.on_setup_guide_toggle:
            self.on_setup_guide_toggle(self._setup_guide_mode)

    def _on_cc_panel_clicked(self, icon, item):
        self._cc_panel_mode = not self._cc_panel_mode
        logger.info(
            f"Tray: CC panel toggled — {'ON' if self._cc_panel_mode else 'OFF'}"
        )
        if self.on_cc_panel_toggle:
            self.on_cc_panel_toggle(self._cc_panel_mode)

    def set_setup_guide_mode(self, enabled: bool):
        """Allow external code to sync the checkmark state (e.g. when
        dismissed via hotkey rather than the tray menu)."""
        self._setup_guide_mode = enabled

    def set_cc_panel_mode(self, enabled: bool):
        """Sync the CC panel checkmark with externally-driven state
        (e.g. the persisted setting on startup)."""
        self._cc_panel_mode = enabled

    def _on_exit_clicked(self, icon, item):
        logger.info("Tray: exit clicked")
        if self.on_exit:
            self.on_exit()
        if self._icon:
            self._icon.stop()

    def start(self):
        """Start the tray icon in a daemon thread"""
        icon_image = _create_icon_image()
        menu = self._build_menu()

        self._icon = pystray.Icon(
            name="bdo_trainer",
            icon=icon_image,
            title="BDO Trainer",
            menu=menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("Tray icon started")

    def refresh_menu(self, class_tree=None):
        """Rebuild the tray menu (e.g. after editor changes)."""
        if class_tree is not None:
            self.class_tree = class_tree
        if self._icon:
            self._icon.menu = self._build_menu()

    def stop(self):
        """Stop the tray icon"""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
        logger.info("Tray icon stopped")

    def notify(self, title: str, message: str):
        """Show a system notification"""
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception as e:
                logger.warning(f"Tray notification failed: {e}")
