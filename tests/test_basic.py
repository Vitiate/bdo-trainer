"""
Tests for BDO Trainer
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.combo_loader import ComboLoader


class TestComboLoader(unittest.TestCase):
    """Tests for ComboLoader with the real config files."""

    @classmethod
    def setUpClass(cls):
        cls.loader = ComboLoader()

    def test_settings_loaded(self):
        settings = self.loader.get_settings()
        self.assertIsInstance(settings, dict)
        self.assertIn("default_combo_window_ms", settings)

    def test_class_configs_loaded(self):
        self.assertGreater(len(self.loader.class_configs), 0)

    def test_get_class_tree(self):
        tree = self.loader.get_class_tree()
        self.assertIn("Dark Knight", tree)
        self.assertIn("Awakening", tree["Dark Knight"])
        combos = tree["Dark Knight"]["Awakening"]
        self.assertGreater(len(combos), 0)
        # Each entry is (combo_id, display_name)
        self.assertEqual(len(combos[0]), 2)

    def test_get_combo_list(self):
        cl = self.loader.get_combo_list()
        self.assertGreater(len(cl), 0)
        # Each entry is (class_name, spec_name, combo_id, display_name)
        self.assertEqual(len(cl[0]), 4)

    def test_get_combo_found(self):
        combo = self.loader.get_combo("Dark Knight", "Awakening", "basic_grind")
        self.assertIsNotNone(combo)
        self.assertIn("steps", combo)
        self.assertIn("name", combo)

    def test_get_combo_not_found(self):
        combo = self.loader.get_combo("Dark Knight", "Awakening", "nonexistent")
        self.assertIsNone(combo)

    def test_get_skill_info(self):
        info = self.loader.get_skill_info("spirit_hunt", "Dark Knight", "Awakening")
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "Spirit Hunt")

    def test_get_skill_info_not_found(self):
        info = self.loader.get_skill_info("nonexistent", "Dark Knight", "Awakening")
        self.assertIsNone(info)

    def test_get_key_remap_defaults(self):
        remap = self.loader.get_key_remap()
        # With default key_bindings, remap should be empty (all identity)
        self.assertIsInstance(remap, dict)
        self.assertEqual(len(remap), 0)

    def test_get_timing_settings(self):
        timing = self.loader.get_timing_settings()
        self.assertIn("idle_reset_timeout_ms", timing)

    def test_get_combo_window_ms(self):
        ms = self.loader.get_combo_window_ms("Dark Knight", "Awakening", "basic_grind")
        self.assertIsInstance(ms, int)
        self.assertGreater(ms, 0)

    def test_get_display_settings(self):
        display = self.loader.get_display_settings()
        self.assertIn("show_protection_type", display)

    def test_get_hotkeys(self):
        hk = self.loader.get_hotkeys()
        self.assertIn("start_combo", hk)
        self.assertIn("stop_combo", hk)


if __name__ == "__main__":
    unittest.main()
