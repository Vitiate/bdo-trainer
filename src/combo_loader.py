"""
Combo Loader - Loads class/spec configs and global settings
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger("bdo_trainer")

COMBO_CATEGORIES = ["pve_combos", "pvp_combos", "movement_combos"]
SKILL_SECTIONS = ["skills", "awakening_skills", "rabam_skills", "preawakening_utility"]

# Maps BDO game-client key-binding names → canonical key names used in
# combo step `keys:` arrays.
_BDO_TO_COMBO_KEY = {
    "Move Forward": "w",
    "Move Back": "s",
    "Move Left": "a",
    "Move Right": "d",
    "LMB": "lmb",
    "RMB": "rmb",
    "MMB": "mmb",
    "Sprint": "shift",
    "Jump": "space",
    "Q": "q",
    "E": "e",
    "F": "f",
    "X": "x",
    "Z": "z",
}


class ComboLoader:
    """Loads class/spec YAML configs from config/classes/ and global settings from config/combos.yaml."""

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            config_dir = str(Path(__file__).parent.parent / "config")
        self.config_dir = Path(config_dir)
        self.settings_path = self.config_dir / "combos.yaml"
        self.classes_dir = self.config_dir / "classes"

        self.settings: Dict[str, Any] = {}
        # Keyed by (class_name, spec_name) tuple
        self.class_configs: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.load()

    def load(self):
        """Load global settings + all class configs from disk."""
        self._load_settings()
        self._load_class_configs()

    def _load_settings(self):
        """Load global settings from combos.yaml."""
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.settings = data.get("settings", {})
            logger.info(f"Loaded settings from {self.settings_path}")
        except FileNotFoundError:
            logger.warning(f"Settings file not found: {self.settings_path}")
            self.settings = {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing settings YAML: {e}")
            self.settings = {}

    def _load_class_configs(self):
        """Scan config/classes/*.yaml and load each class/spec config."""
        self.class_configs = {}
        if not self.classes_dir.is_dir():
            logger.warning(f"Classes directory not found: {self.classes_dir}")
            return
        for yaml_file in sorted(self.classes_dir.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                class_name = data.get("class")
                spec_name = data.get("spec")
                if not class_name or not spec_name:
                    logger.warning(
                        f"Skipping {yaml_file.name}: missing 'class' or 'spec' key"
                    )
                    continue
                self.class_configs[(class_name, spec_name)] = data
                logger.info(
                    f"Loaded class config: {class_name} / {spec_name} from {yaml_file.name}"
                )
            except yaml.YAMLError as e:
                logger.error(f"Error parsing {yaml_file.name}: {e}")

    def reload(self):
        """Reload all configs from disk."""
        self.load()

    # ------------------------------------------------------------------
    # Combo iteration helper
    # ------------------------------------------------------------------
    def _iter_combos(self):
        """Yield ``(class_name, spec_name, combo_id, combo_data)`` for every combo across all loaded configs."""
        for (class_name, spec_name), data in self.class_configs.items():
            for category in COMBO_CATEGORIES:
                section = data.get(category, {})
                if isinstance(section, dict):
                    for combo_id, combo_data in section.items():
                        if isinstance(combo_data, dict):
                            yield class_name, spec_name, combo_id, combo_data

    # ------------------------------------------------------------------
    # Class / Spec enumeration
    # ------------------------------------------------------------------
    def get_class_tree(self) -> Dict[str, Dict[str, List[Tuple[str, str]]]]:
        """Return a nested dict: {class_name: {spec_name: [(combo_id, display_name), ...]}}.

        This is the structure the tray menu uses to build its submenus.
        Combos from all categories (pve, pvp, movement) are merged into a
        single flat list per spec, preserving their category order.
        """
        tree: Dict[str, Dict[str, List[Tuple[str, str]]]] = {}
        for class_name, spec_name, combo_id, combo_data in self._iter_combos():
            display_name = combo_data.get("name", combo_id)
            tree.setdefault(class_name, {}).setdefault(spec_name, []).append(
                (combo_id, display_name)
            )
        return tree

    def get_combo_list(self) -> List[Tuple[str, str, str, str]]:
        """Return a flat list of (class_name, spec_name, combo_id, display_name)."""
        return [
            (cls, spec, cid, data.get("name", cid))
            for cls, spec, cid, data in self._iter_combos()
        ]

    # ------------------------------------------------------------------
    # Combo access
    # ------------------------------------------------------------------
    def get_combo(
        self, class_name: str, spec_name: str, combo_id: str
    ) -> Optional[Dict[str, Any]]:
        """Look up a combo by class/spec/combo_id (searches across categories)."""
        data = self.class_configs.get((class_name, spec_name))
        if data is None:
            return None
        for category in COMBO_CATEGORIES:
            section = data.get(category, {})
            if isinstance(section, dict) and combo_id in section:
                return section[combo_id]
        return None

    def get_combo_window_ms(
        self, class_name: str, spec_name: str, combo_id: str
    ) -> int:
        """Get the combo_window_ms for a specific combo, falling back to global default."""
        combo = self.get_combo(class_name, spec_name, combo_id)
        if combo and "combo_window_ms" in combo:
            return combo["combo_window_ms"]
        return self.settings.get("default_combo_window_ms", 300)

    # ------------------------------------------------------------------
    # Skill access
    # ------------------------------------------------------------------
    def get_skill_info(
        self, skill_id: str, class_name: str = "", spec_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Look up a skill by ID within a specific class/spec.

        If class_name/spec_name are empty, searches ALL loaded configs (backward compat).
        """
        configs_to_search = []
        if class_name and spec_name:
            cfg = self.class_configs.get((class_name, spec_name))
            if cfg:
                configs_to_search.append(cfg)
        else:
            configs_to_search = list(self.class_configs.values())

        for data in configs_to_search:
            for section in SKILL_SECTIONS:
                skills = data.get(section, {})
                if isinstance(skills, dict) and skill_id in skills:
                    return skills[skill_id]
        return None

    # ------------------------------------------------------------------
    # Settings access (unchanged — reads from global settings)
    # ------------------------------------------------------------------
    def get_settings(self) -> Dict[str, Any]:
        return self.settings

    def get_display_settings(self) -> Dict[str, Any]:
        return self.settings.get("display", {})

    def get_hotkeys(self) -> Dict[str, str]:
        return self.settings.get(
            "hotkeys",
            {
                "start_combo": "F5",
                "stop_combo": "F6",
                "next_step": "F7",
                "reset_combo": "F8",
            },
        )

    def get_key_bindings(self) -> Dict[str, str]:
        return self.settings.get("key_bindings", {})

    def get_key_remap(self) -> Dict[str, str]:
        """Build canonical-combo-key → physical-key mapping from key_bindings config."""
        bindings = self.get_key_bindings()
        remap: Dict[str, str] = {}
        for bdo_name, physical_key in bindings.items():
            canonical = _BDO_TO_COMBO_KEY.get(bdo_name)
            if canonical and physical_key:
                phys = str(physical_key).lower().strip()
                if phys != canonical:
                    remap[canonical] = phys
        return remap

    def get_timing_settings(self) -> Dict[str, Any]:
        return self.settings.get(
            "timing",
            {
                "step_highlight_duration_ms": 500,
                "transition_delay_ms": 100,
                "auto_advance": False,
                "idle_reset_timeout_ms": 10000,
            },
        )

    def get_category_display_name(self, category: str) -> str:
        names = {
            "pve_combos": "PVE Combos",
            "pvp_combos": "PVP Combos",
            "movement_combos": "Movement",
        }
        return names.get(category, category)

    # ------------------------------------------------------------------
    # Setup-guide data (locked skills, hotbar, core, add-ons)
    # ------------------------------------------------------------------
    def _get_class_field(self, class_name: str, spec_name: str, key: str, default=None):
        """Return a field from a class/spec config, or *default* if not found."""
        if default is None:
            default = {}
        return self.class_configs.get((class_name, spec_name), {}).get(key, default)

    def get_locked_skills(
        self, class_name: str, spec_name: str
    ) -> List[Dict[str, Any]]:
        """Return the locked_skills list for a class/spec.

        Each entry is a dict with at least ``name`` and ``reason`` keys.
        """
        return self._get_class_field(class_name, spec_name, "locked_skills", [])

    def get_hotbar_skills(self, class_name: str, spec_name: str) -> List[str]:
        """Return the hotbar_skills list (display names) for a class/spec."""
        return self._get_class_field(class_name, spec_name, "hotbar_skills", [])

    def get_core_skill(self, class_name: str, spec_name: str) -> Dict[str, Any]:
        """Return the core_skill recommendation dict for a class/spec.

        Typically has ``recommended``, ``effect``, and ``reason`` keys.
        """
        return self._get_class_field(class_name, spec_name, "core_skill", {})

    def get_skill_addons(self, class_name: str, spec_name: str) -> Dict[str, Any]:
        """Return the skill_addons dict for a class/spec.

        Usually contains a ``pve`` key with a list of add-on entries.
        """
        return self._get_class_field(class_name, spec_name, "skill_addons", {})

    def get_setup_guide(
        self, class_name: str, spec_name: str
    ) -> Optional[Dict[str, Any]]:
        """Return all setup-guide data for a class/spec in one dict.

        Returns ``None`` if the class/spec is not loaded.  Otherwise
        returns::

            {
                "class": str,
                "spec": str,
                "locked_skills": [...],
                "hotbar_skills": [...],
                "core_skill": {...},
                "skill_addons": {...},
            }
        """
        if (class_name, spec_name) not in self.class_configs:
            return None
        return {
            "class": class_name,
            "spec": spec_name,
            "locked_skills": self._get_class_field(
                class_name, spec_name, "locked_skills", []
            ),
            "hotbar_skills": self._get_class_field(
                class_name, spec_name, "hotbar_skills", []
            ),
            "core_skill": self._get_class_field(
                class_name, spec_name, "core_skill", {}
            ),
            "skill_addons": self._get_class_field(
                class_name, spec_name, "skill_addons", {}
            ),
        }

    # ------------------------------------------------------------------
    # Class config CRUD (used by the Editor GUI)
    # ------------------------------------------------------------------
    def get_class_config(
        self, class_name: str, spec_name: str
    ) -> Optional[Dict[str, Any]]:
        """Return the raw config dict for a class/spec, or None."""
        return self.class_configs.get((class_name, spec_name))

    def save_class_config(
        self, class_name: str, spec_name: str, data: Dict[str, Any]
    ) -> Path:
        """Write *data* to a YAML file for *class_name/spec_name* and update
        the in-memory cache.  Returns the file path written."""
        data["class"] = class_name
        data["spec"] = spec_name

        filename = f"{class_name}_{spec_name}".lower().replace(" ", "_") + ".yaml"
        filepath = self.classes_dir / filename

        header = (
            f"# {class_name} \u2014 {spec_name}\n"
            f"# Generated / updated by BDO Trainer Editor\n\n"
        )

        self.classes_dir.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(header)
            yaml.dump(
                data,
                fh,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        self.class_configs[(class_name, spec_name)] = data
        logger.info(f"Saved class config: {class_name}/{spec_name} → {filepath.name}")
        return filepath

    def delete_class_config(self, class_name: str, spec_name: str) -> bool:
        """Delete the YAML file for a class/spec and remove from cache.
        Returns True on success."""
        if (class_name, spec_name) not in self.class_configs:
            return False

        filename = f"{class_name}_{spec_name}".lower().replace(" ", "_") + ".yaml"
        filepath = self.classes_dir / filename

        try:
            if filepath.exists():
                filepath.unlink()
        except OSError as exc:
            logger.error(f"Failed to delete {filepath}: {exc}")
            return False

        del self.class_configs[(class_name, spec_name)]
        logger.info(f"Deleted class config: {class_name}/{spec_name}")
        return True
