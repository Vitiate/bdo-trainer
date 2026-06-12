"""
BDO Trainer — Transparent overlay combo trainer for Black Desert Online.
"""

__version__ = "0.6.2-beta.2"
__app_name__ = "BDO Trainer"

from .combo_loader import ComboLoader
from .overlay import ComboOverlay
from .settings_gui import SettingsWindow
from .tray import TrayManager

__all__ = ["ComboLoader", "ComboOverlay", "SettingsWindow", "TrayManager"]
