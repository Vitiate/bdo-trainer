"""BDO Trainer editor windows.

Exposes:
    ComboEditorWindow — edits combo bundles (loadout + combos)
    ClassEditorWindow — edits class skill definitions
"""

from src.editor.combo_window import ComboEditorWindow
from src.editor.class_window import ClassEditorWindow

# Backwards-compat alias for callers that imported the old window name.
EditorWindow = ComboEditorWindow

__all__ = ["ComboEditorWindow", "ClassEditorWindow", "EditorWindow"]
