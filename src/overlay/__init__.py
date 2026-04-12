"""
Overlay package — transparent combo overlay for BDO Trainer.

Re-exports the public API so existing ``from src.overlay import …``
imports continue to work after the monolith was split into modules.
"""

from src.input_monitor import INPUT_AVAILABLE
from src.overlay.core import ComboOverlay

__all__ = ["ComboOverlay", "INPUT_AVAILABLE"]
