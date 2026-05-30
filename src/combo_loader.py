"""Loaders for class definitions, combos, and global settings.

Layout (post-0.5.0):

    data/classes/<class>_<spec>.yaml          # ships with app — class + skills
        class:, spec:, skills:, locked_skills:, hotbar_skills:,
        core_skill:, skill_addons:

    config/combos/<class>_<spec>/<combo_id>.yaml   # user content — one per combo
        combo_id:, class:, spec:, category: pve|pvp|movement,
        name:, difficulty:, combo_window_ms:, description:, steps:

    config/combos.yaml                        # global settings (key bindings,
                                              # hotkeys, display, timing)

Three loaders live here:

* :class:`ClassLoader`    — reads ``data/classes/``
* :class:`CombosLoader`   — reads ``config/combos/``
* :class:`SettingsLoader` — reads ``config/combos.yaml``

A :class:`AppLoader` facade composes all three and exposes the union of
methods the rest of the app expects (so ``main.py``, the overlay, and the
tray don't need their callsites changed).
"""

from __future__ import annotations

import copy
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

logger = logging.getLogger("bdo_trainer")

# Combo categories live under config/combos/<slug>/<combo_id>.yaml with a
# `category:` field. These are the canonical category values.
COMBO_CATEGORIES: List[str] = ["pve", "pvp", "movement"]

# Sections of a class file that contain skill definitions. The new layout
# normalises everything onto `skills`, but old files (and bundles) may
# still use the legacy three-section split.
SKILL_SECTIONS: List[str] = [
    "skills",
    "awakening_skills",
    "rabam_skills",
    "preawakening_utility",
]

# Maps BDO game-client key-binding names → canonical key names used in
# combo step `keys:` arrays.
_BDO_TO_COMBO_KEY: Dict[str, str] = {
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


def slug_for(class_name: str, spec_name: str) -> str:
    return f"{class_name}_{spec_name}".lower().replace(" ", "_")


# ===========================================================================
# Class loader (ships with app — read-mostly)
# ===========================================================================
class ClassLoader:
    """Loads class definitions from ``data/classes/``.

    Class files contain skills, locked-skill lists, hotbar setup, core
    skill recommendations, and add-ons. They are intended to ship with
    the app and rarely change at runtime.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "classes"
        self.data_dir = Path(data_dir)
        # Keyed by (class_name, spec_name)
        self.class_configs: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        self.class_configs = {}
        if not self.data_dir.is_dir():
            logger.warning(f"Class data directory not found: {self.data_dir}")
            return
        for yaml_file in sorted(self.data_dir.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                logger.error(f"Error parsing {yaml_file.name}: {e}")
                continue
            class_name = data.get("class")
            spec_name = data.get("spec")
            if not class_name or not spec_name:
                logger.warning(
                    f"Skipping {yaml_file.name}: missing 'class' or 'spec' key"
                )
                continue
            self.class_configs[(class_name, spec_name)] = data
            logger.info(
                f"Loaded class definition: {class_name} / {spec_name} from {yaml_file.name}"
            )

    def reload(self) -> None:
        self.load()

    def keys(self) -> List[Tuple[str, str]]:
        """Return all loaded ``(class, spec)`` pairs sorted alphabetically."""
        return sorted(self.class_configs.keys(), key=lambda k: (k[0].lower(), k[1].lower()))

    def get(self, class_name: str, spec_name: str) -> Optional[Dict[str, Any]]:
        return self.class_configs.get((class_name, spec_name))

    def has(self, class_name: str, spec_name: str) -> bool:
        return (class_name, spec_name) in self.class_configs

    # ------------------------------------------------------------------
    # Skill access
    # ------------------------------------------------------------------
    def get_skill_info(
        self, skill_id: str, class_name: str = "", spec_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Look up a skill by ID within a specific class/spec, or across
        all loaded classes if ``class_name``/``spec_name`` are empty."""
        configs_to_search: List[Dict[str, Any]] = []
        if class_name and spec_name:
            cfg = self.get(class_name, spec_name)
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

    def get_skills(self, class_name: str, spec_name: str) -> Dict[str, Any]:
        """Return a flat ``{skill_id: skill_dict}`` for a class/spec.

        Merges all skill sections (``skills``, ``awakening_skills``, etc.)
        into a single dict.
        """
        out: Dict[str, Any] = {}
        cfg = self.get(class_name, spec_name) or {}
        for section in SKILL_SECTIONS:
            skills = cfg.get(section, {})
            if isinstance(skills, dict):
                out.update(skills)
        return out

    # ------------------------------------------------------------------
    # Setup guide accessors
    # ------------------------------------------------------------------
    def _field(
        self, class_name: str, spec_name: str, key: str, default: Any = None
    ) -> Any:
        if default is None:
            default = {}
        return self.class_configs.get((class_name, spec_name), {}).get(key, default)

    def get_locked_skills(self, class_name: str, spec_name: str) -> List[Dict[str, Any]]:
        return self._field(class_name, spec_name, "locked_skills", [])

    def get_hotbar_skills(self, class_name: str, spec_name: str) -> List[str]:
        return self._field(class_name, spec_name, "hotbar_skills", [])

    def get_core_skill(self, class_name: str, spec_name: str) -> Dict[str, Any]:
        return self._field(class_name, spec_name, "core_skill", {})

    def get_skill_addons(self, class_name: str, spec_name: str) -> Dict[str, Any]:
        return self._field(class_name, spec_name, "skill_addons", {})

    # ------------------------------------------------------------------
    # CRUD (used by the Class Editor)
    # ------------------------------------------------------------------
    def save(
        self, class_name: str, spec_name: str, data: Dict[str, Any]
    ) -> Path:
        data = copy.deepcopy(data)
        data["class"] = class_name
        data["spec"] = spec_name

        filepath = self.data_dir / f"{slug_for(class_name, spec_name)}.yaml"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        header = (
            f"# {class_name} — {spec_name}\n"
            f"# Class definition (skills, hotbar, core skill, addons).\n"
            f"# Edit via the Class Editor in BDO Trainer.\n\n"
        )
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(header)
            yaml.dump(
                data, fh,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        self.class_configs[(class_name, spec_name)] = data
        logger.info(f"Saved class definition: {class_name}/{spec_name} → {filepath.name}")
        return filepath

    def delete(self, class_name: str, spec_name: str) -> bool:
        key = (class_name, spec_name)
        if key not in self.class_configs:
            return False
        filepath = self.data_dir / f"{slug_for(class_name, spec_name)}.yaml"
        try:
            if filepath.exists():
                filepath.unlink()
        except OSError as exc:
            logger.error(f"Failed to delete {filepath}: {exc}")
            return False
        del self.class_configs[key]
        logger.info(f"Deleted class definition: {class_name}/{spec_name}")
        return True


# ===========================================================================
# Combo loader (user content — config/combos/)
# ===========================================================================
class CombosLoader:
    """Loads combos from ``config/combos/<slug>/*.yaml``.

    Each combo lives in its own file so combos can be shared, exported,
    imported, or removed individually without rewriting a class file.

    (Class name is :class:`CombosLoader` to avoid colliding with the
    backward-compat ``ComboLoader`` shim at module bottom.)
    """

    def __init__(self, combos_dir: Optional[Path] = None) -> None:
        if combos_dir is None:
            combos_dir = Path(__file__).parent.parent / "config" / "combos"
        self.combos_dir = Path(combos_dir)
        # Keyed by (class_name, spec_name, combo_id)
        self.combos: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        # Original file path on disk for each combo (so save/delete can
        # find it again).
        self._paths: Dict[Tuple[str, str, str], Path] = {}
        self.load()

    def load(self) -> None:
        self.combos = {}
        self._paths = {}
        if not self.combos_dir.is_dir():
            logger.info(f"Combos directory not present: {self.combos_dir}")
            return
        for slug_dir in sorted(self.combos_dir.iterdir()):
            if not slug_dir.is_dir():
                continue
            for combo_file in sorted(slug_dir.glob("*.yaml")):
                try:
                    with open(combo_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                except yaml.YAMLError as e:
                    logger.error(f"Error parsing {combo_file}: {e}")
                    continue
                class_name = data.get("class") or ""
                spec_name = data.get("spec") or ""
                combo_id = data.get("combo_id") or combo_file.stem
                if not class_name or not spec_name:
                    logger.warning(
                        f"Skipping {combo_file}: missing 'class' or 'spec' key"
                    )
                    continue
                key = (class_name, spec_name, combo_id)
                self.combos[key] = data
                self._paths[key] = combo_file
        logger.info(f"Loaded {len(self.combos)} combo(s) from {self.combos_dir}")

    def reload(self) -> None:
        self.load()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------
    def iter_for_class(
        self, class_name: str, spec_name: str
    ) -> Iterable[Tuple[str, Dict[str, Any]]]:
        """Yield ``(combo_id, combo_data)`` for every combo on a class/spec.

        Order: by category (pve → pvp → movement), then alphabetically by
        combo_id within a category.
        """
        cat_index = {cat: i for i, cat in enumerate(COMBO_CATEGORIES)}

        def sort_key(item):
            (cls, spec, cid), data = item
            cat = data.get("category", "pve")
            return (cat_index.get(cat, 99), cid.lower())

        for (cls, spec, cid), data in sorted(self.combos.items(), key=sort_key):
            if cls == class_name and spec == spec_name:
                yield cid, data

    def iter_all(self) -> Iterable[Tuple[str, str, str, Dict[str, Any]]]:
        """Yield ``(class, spec, combo_id, data)`` for every loaded combo."""
        for (cls, spec, cid), data in self.combos.items():
            yield cls, spec, cid, data

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get(
        self, class_name: str, spec_name: str, combo_id: str
    ) -> Optional[Dict[str, Any]]:
        return self.combos.get((class_name, spec_name, combo_id))

    def get_window_ms(
        self, class_name: str, spec_name: str, combo_id: str, default: int
    ) -> int:
        combo = self.get(class_name, spec_name, combo_id)
        if combo and "combo_window_ms" in combo:
            try:
                return int(combo["combo_window_ms"])
            except (TypeError, ValueError):
                pass
        return default

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def save(
        self,
        class_name: str,
        spec_name: str,
        combo_id: str,
        data: Dict[str, Any],
    ) -> Path:
        data = copy.deepcopy(data)
        data["combo_id"] = combo_id
        data["class"] = class_name
        data["spec"] = spec_name
        # Default category to pve if caller didn't supply one.
        data.setdefault("category", "pve")

        slug = slug_for(class_name, spec_name)
        target_dir = self.combos_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / f"{combo_id}.yaml"

        with open(filepath, "w", encoding="utf-8") as fh:
            yaml.dump(
                data, fh,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        key = (class_name, spec_name, combo_id)
        self.combos[key] = data
        self._paths[key] = filepath
        logger.info(f"Saved combo: {class_name}/{spec_name}/{combo_id}")
        return filepath

    def delete(
        self, class_name: str, spec_name: str, combo_id: str
    ) -> bool:
        key = (class_name, spec_name, combo_id)
        path = self._paths.pop(key, None)
        self.combos.pop(key, None)
        if path is not None and path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.error(f"Failed to delete {path}: {exc}")
                return False
        logger.info(f"Deleted combo: {class_name}/{spec_name}/{combo_id}")
        return True

    def delete_for_class(self, class_name: str, spec_name: str) -> int:
        """Delete every combo for a class/spec. Returns count removed."""
        removed = 0
        slug = slug_for(class_name, spec_name)
        for key in list(self.combos.keys()):
            if key[0] == class_name and key[1] == spec_name:
                if self.delete(*key):
                    removed += 1
        # Remove the now-empty slug directory if present.
        target = self.combos_dir / slug
        try:
            if target.exists() and not any(target.iterdir()):
                target.rmdir()
        except OSError:
            pass
        return removed


# ===========================================================================
# Settings loader (config/combos.yaml)
# ===========================================================================
class SettingsLoader:
    """Loads global settings (hotkeys, key bindings, display, timing) from
    ``config/combos.yaml``."""

    def __init__(self, settings_path: Optional[Path] = None) -> None:
        if settings_path is None:
            settings_path = Path(__file__).parent.parent / "config" / "combos.yaml"
        self.settings_path = Path(settings_path)
        self.settings: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
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

    def reload(self) -> None:
        self.load()

    # ------------------------------------------------------------------
    # Accessors
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
        bindings = self.get_key_bindings()
        remap: Dict[str, str] = {}
        for bdo_name, physical_key in bindings.items():
            canonical = _BDO_TO_COMBO_KEY.get(bdo_name)
            if canonical and physical_key:
                phys = str(physical_key).lower().strip()
                if phys != canonical:
                    remap[canonical] = phys

        canonical_set = set(_BDO_TO_COMBO_KEY.values())
        for canonical, phys in remap.items():
            if phys in canonical_set and phys != canonical:
                if remap.get(phys, phys) == phys:
                    logger.warning(
                        "Key remap collision: '%s' is remapped to '%s', but "
                        "'%s' itself is not remapped away. Combos that use "
                        "canonical '%s' will require physical '%s', which is "
                        "the same key as canonical '%s'. Add a matching "
                        "binding for '%s' to swap them properly.",
                        canonical, phys, phys, canonical, phys, phys, phys,
                    )
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


# ===========================================================================
# AppLoader facade
# ===========================================================================
class AppLoader:
    """Composes :class:`ClassLoader`, :class:`CombosLoader`, and
    :class:`SettingsLoader` and exposes the union of methods callers need.

    Most of the existing app code uses this as a drop-in replacement for
    the old monolithic ``ComboLoader``; method names are preserved.
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        combos_dir: Optional[Path] = None,
        settings_path: Optional[Path] = None,
    ) -> None:
        self.classes = ClassLoader(data_dir)
        self.combos_loader = CombosLoader(combos_dir)
        self.settings_loader = SettingsLoader(settings_path)

    # ------------------------------------------------------------------
    # Pass-throughs that look like the old ComboLoader API
    # ------------------------------------------------------------------
    def reload(self) -> None:
        self.classes.reload()
        self.combos_loader.reload()
        self.settings_loader.reload()

    # Settings
    def get_settings(self):       return self.settings_loader.get_settings()
    def get_display_settings(self): return self.settings_loader.get_display_settings()
    def get_hotkeys(self):        return self.settings_loader.get_hotkeys()
    def get_key_bindings(self):   return self.settings_loader.get_key_bindings()
    def get_key_remap(self):      return self.settings_loader.get_key_remap()
    def get_timing_settings(self): return self.settings_loader.get_timing_settings()

    @property
    def settings(self) -> Dict[str, Any]:
        return self.settings_loader.settings

    @settings.setter
    def settings(self, value: Dict[str, Any]) -> None:
        self.settings_loader.settings = value

    # Class enumeration / data
    @property
    def class_configs(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        return self.classes.class_configs

    def get_class_config(self, class_name: str, spec_name: str):
        return self.classes.get(class_name, spec_name)

    def get_skill_info(self, skill_id: str, class_name: str = "", spec_name: str = ""):
        return self.classes.get_skill_info(skill_id, class_name, spec_name)

    # Combo enumeration / data
    def get_combo(self, class_name: str, spec_name: str, combo_id: str):
        return self.combos_loader.get(class_name, spec_name, combo_id)

    def get_combo_window_ms(
        self, class_name: str, spec_name: str, combo_id: str
    ) -> int:
        default = self.settings.get("default_combo_window_ms", 300)
        return self.combos_loader.get_window_ms(class_name, spec_name, combo_id, default)

    def get_class_tree(self) -> Dict[str, Dict[str, List[Tuple[str, str]]]]:
        """Return ``{class: {spec: [(combo_id, display_name), ...]}}``.

        Combos are listed in category order (pve → pvp → movement). Classes
        with no combos still appear in the tree (with an empty list) so the
        tray menu can show them.
        """
        tree: Dict[str, Dict[str, List[Tuple[str, str]]]] = {}
        for class_name, spec_name in self.classes.keys():
            tree.setdefault(class_name, {})[spec_name] = []
        for class_name, spec_name, combo_id, data in self.combos_loader.iter_all():
            display = data.get("name", combo_id)
            tree.setdefault(class_name, {}).setdefault(spec_name, []).append(
                (combo_id, display)
            )
        return tree

    def get_combo_list(self) -> List[Tuple[str, str, str, str]]:
        return [
            (cls, spec, cid, data.get("name", cid))
            for cls, spec, cid, data in self.combos_loader.iter_all()
        ]

    def get_category_display_name(self, category: str) -> str:
        names = {"pve": "PVE Combos", "pvp": "PVP Combos", "movement": "Movement"}
        return names.get(category, category)

    # Setup-guide passthroughs
    def get_locked_skills(self, *args, **kwargs):
        return self.classes.get_locked_skills(*args, **kwargs)

    def get_hotbar_skills(self, *args, **kwargs):
        return self.classes.get_hotbar_skills(*args, **kwargs)

    def get_core_skill(self, *args, **kwargs):
        return self.classes.get_core_skill(*args, **kwargs)

    def get_skill_addons(self, *args, **kwargs):
        return self.classes.get_skill_addons(*args, **kwargs)

    def get_setup_guide(
        self, class_name: str, spec_name: str
    ) -> Optional[Dict[str, Any]]:
        if not self.classes.has(class_name, spec_name):
            return None
        return {
            "class": class_name,
            "spec": spec_name,
            "locked_skills": self.classes.get_locked_skills(class_name, spec_name),
            "hotbar_skills": self.classes.get_hotbar_skills(class_name, spec_name),
            "core_skill": self.classes.get_core_skill(class_name, spec_name),
            "skill_addons": self.classes.get_skill_addons(class_name, spec_name),
        }

    # CRUD passthroughs
    def save_class_config(self, class_name: str, spec_name: str, data: Dict[str, Any]) -> Path:
        return self.classes.save(class_name, spec_name, data)

    def delete_class_config(self, class_name: str, spec_name: str) -> bool:
        # Remove combos when a class is deleted so we don't leave orphans.
        self.combos_loader.delete_for_class(class_name, spec_name)
        return self.classes.delete(class_name, spec_name)


# ---------------------------------------------------------------------------
# Backward-compat shim: keep the old `ComboLoader` import working but make
# it return the AppLoader facade. This lets main.py / tray / overlay keep
# working without churn during the refactor.
# ---------------------------------------------------------------------------
class _LegacyComboLoaderShim(AppLoader):
    """Drop-in for the old monolithic ``ComboLoader``."""

    def __init__(self, config_dir: Optional[str] = None) -> None:
        if config_dir is None:
            project_root = Path(__file__).parent.parent
            data_dir = project_root / "data" / "classes"
            combos_dir = project_root / "config" / "combos"
            settings_path = project_root / "config" / "combos.yaml"
        else:
            base = Path(config_dir)
            project_root = base.parent
            data_dir = project_root / "data" / "classes"
            combos_dir = base / "combos"
            settings_path = base / "combos.yaml"
        super().__init__(data_dir=data_dir, combos_dir=combos_dir, settings_path=settings_path)


# Existing imports (`from src.combo_loader import ComboLoader`) keep working.
ComboLoader = _LegacyComboLoaderShim
