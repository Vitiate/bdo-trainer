"""Loaders for class definitions, combo bundles, and global settings.

Layout (post-0.5.0)::

    data/classes/<slug>.yaml                       # ships with app — skills only
        class:, spec:, skills:

    config/combos/<slug>/<bundle_id>/
        _bundle.yaml                               # bundle metadata + loadout
            class:, spec:, bundle_id:, name:, description:,
            locked_skills:, hotbar_skills:, core_skill:, skill_addons:
        <combo_id>.yaml                            # one file per combo
            combo_id:, class:, spec:, bundle_id:,
            category: pve|pvp|movement,
            name:, difficulty:, combo_window_ms:, description:, steps:

    config/combos.yaml                             # global settings
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

logger = logging.getLogger("bdo_trainer")

COMBO_CATEGORIES: List[str] = ["pve", "pvp", "movement"]
DEFAULT_BUNDLE_ID: str = "default"

SKILL_SECTIONS: List[str] = [
    "skills",
    # legacy fallbacks (read-only) — older class files used these
    "awakening_skills",
    "rabam_skills",
    "preawakening_utility",
]

LOADOUT_KEYS: List[str] = [
    "locked_skills",
    "hotbar_skills",
    "core_skill",
    "skill_addons",
]

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


def _yaml_dump(data: Dict[str, Any], fh) -> None:
    yaml.dump(
        data, fh,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


# ===========================================================================
# Class loader (data/classes/) — skills only
# ===========================================================================
class ClassLoader:
    """Loads class definitions (skills only) from ``data/classes/``."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "classes"
        self.data_dir = Path(data_dir)
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
                logger.warning(f"Skipping {yaml_file.name}: missing 'class' or 'spec'")
                continue
            self.class_configs[(class_name, spec_name)] = data
            logger.info(
                f"Loaded class definition: {class_name} / {spec_name} from {yaml_file.name}"
            )

    def reload(self) -> None:
        self.load()

    def keys(self) -> List[Tuple[str, str]]:
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
        out: Dict[str, Any] = {}
        cfg = self.get(class_name, spec_name) or {}
        for section in SKILL_SECTIONS:
            skills = cfg.get(section, {})
            if isinstance(skills, dict):
                out.update(skills)
        return out

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def save(self, class_name: str, spec_name: str, data: Dict[str, Any]) -> Path:
        data = copy.deepcopy(data)
        data["class"] = class_name
        data["spec"] = spec_name
        # Strip any loadout keys that may have been carried over from the
        # legacy layout — those belong to bundles now.
        for k in LOADOUT_KEYS:
            data.pop(k, None)

        filepath = self.data_dir / f"{slug_for(class_name, spec_name)}.yaml"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        header = (
            f"# {class_name} — {spec_name}\n"
            f"# Class definition (skills only).\n\n"
        )
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(header)
            _yaml_dump(data, fh)
        self.class_configs[(class_name, spec_name)] = data
        logger.info(f"Saved class definition: {class_name}/{spec_name}")
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
# Bundle loader (config/combos/<slug>/<bundle_id>/)
# ===========================================================================
class BundleLoader:
    """Loads bundles (loadout + combos) from ``config/combos/<slug>/<bundle_id>/``.

    A bundle directory contains ``_bundle.yaml`` (metadata + loadout) plus
    one YAML per combo. Multiple bundles per class/spec are supported —
    each ``<bundle_id>`` subdirectory is independent.
    """

    def __init__(self, combos_dir: Optional[Path] = None) -> None:
        if combos_dir is None:
            combos_dir = Path(__file__).parent.parent / "config" / "combos"
        self.combos_dir = Path(combos_dir)

        # Indexed by (class, spec, bundle_id) → bundle metadata dict.
        self.bundles: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        # Indexed by (class, spec, bundle_id, combo_id) → combo dict.
        self.combos: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        # Path tracking for save/delete.
        self._bundle_paths: Dict[Tuple[str, str, str], Path] = {}
        self._combo_paths: Dict[Tuple[str, str, str, str], Path] = {}

        self.load()

    def load(self) -> None:
        self.bundles = {}
        self.combos = {}
        self._bundle_paths = {}
        self._combo_paths = {}
        if not self.combos_dir.is_dir():
            logger.info(f"Combos directory not present: {self.combos_dir}")
            return

        for slug_dir in sorted(self.combos_dir.iterdir()):
            if not slug_dir.is_dir():
                continue
            for bundle_dir in sorted(slug_dir.iterdir()):
                if not bundle_dir.is_dir():
                    continue
                bundle_yaml = bundle_dir / "_bundle.yaml"
                meta: Dict[str, Any] = {}
                if bundle_yaml.exists():
                    try:
                        with open(bundle_yaml, "r", encoding="utf-8") as f:
                            meta = yaml.safe_load(f) or {}
                    except yaml.YAMLError as e:
                        logger.error(f"Error parsing {bundle_yaml}: {e}")
                        meta = {}

                # Fall back to inferring class/spec from the slug folder
                # name if the bundle yaml is missing fields.
                class_name = meta.get("class") or ""
                spec_name = meta.get("spec") or ""
                bundle_id = meta.get("bundle_id") or bundle_dir.name
                if not class_name or not spec_name:
                    logger.warning(
                        f"Skipping bundle {slug_dir.name}/{bundle_dir.name}: "
                        f"missing class/spec in _bundle.yaml"
                    )
                    continue

                key = (class_name, spec_name, bundle_id)
                self.bundles[key] = meta
                self._bundle_paths[key] = bundle_yaml

                for combo_file in sorted(bundle_dir.glob("*.yaml")):
                    if combo_file.name == "_bundle.yaml":
                        continue
                    try:
                        with open(combo_file, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f) or {}
                    except yaml.YAMLError as e:
                        logger.error(f"Error parsing {combo_file}: {e}")
                        continue
                    combo_id = data.get("combo_id") or combo_file.stem
                    ckey = (class_name, spec_name, bundle_id, combo_id)
                    self.combos[ckey] = data
                    self._combo_paths[ckey] = combo_file

        logger.info(
            f"Loaded {len(self.bundles)} bundle(s) and {len(self.combos)} combo(s) "
            f"from {self.combos_dir}"
        )

    def reload(self) -> None:
        self.load()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------
    def bundles_for_class(
        self, class_name: str, spec_name: str
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Return ``[(bundle_id, bundle_meta), ...]`` for a class/spec, sorted."""
        out: List[Tuple[str, Dict[str, Any]]] = []
        for (cls, spec, bid), meta in self.bundles.items():
            if cls == class_name and spec == spec_name:
                out.append((bid, meta))
        out.sort(key=lambda x: (x[0] != DEFAULT_BUNDLE_ID, x[0].lower()))
        return out

    def iter_combos_for_bundle(
        self, class_name: str, spec_name: str, bundle_id: str
    ) -> Iterable[Tuple[str, Dict[str, Any]]]:
        """Yield ``(combo_id, combo_data)`` for one bundle."""
        cat_index = {cat: i for i, cat in enumerate(COMBO_CATEGORIES)}

        def sort_key(item):
            (cls, spec, bid, cid), data = item
            cat = data.get("category", "pve")
            return (cat_index.get(cat, 99), cid.lower())

        for (cls, spec, bid, cid), data in sorted(self.combos.items(), key=sort_key):
            if cls == class_name and spec == spec_name and bid == bundle_id:
                yield cid, data

    def iter_all_bundles(self) -> Iterable[Tuple[str, str, str, Dict[str, Any]]]:
        for (cls, spec, bid), meta in self.bundles.items():
            yield cls, spec, bid, meta

    def iter_all_combos(
        self,
    ) -> Iterable[Tuple[str, str, str, str, Dict[str, Any]]]:
        for (cls, spec, bid, cid), data in self.combos.items():
            yield cls, spec, bid, cid, data

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get_bundle(
        self, class_name: str, spec_name: str, bundle_id: str
    ) -> Optional[Dict[str, Any]]:
        return self.bundles.get((class_name, spec_name, bundle_id))

    def get_combo(
        self, class_name: str, spec_name: str, bundle_id: str, combo_id: str
    ) -> Optional[Dict[str, Any]]:
        return self.combos.get((class_name, spec_name, bundle_id, combo_id))

    def get_window_ms(
        self,
        class_name: str,
        spec_name: str,
        bundle_id: str,
        combo_id: str,
        default: int,
    ) -> int:
        combo = self.get_combo(class_name, spec_name, bundle_id, combo_id)
        if combo and "combo_window_ms" in combo:
            try:
                return int(combo["combo_window_ms"])
            except (TypeError, ValueError):
                pass
        return default

    # ------------------------------------------------------------------
    # CRUD — bundles
    # ------------------------------------------------------------------
    def save_bundle(
        self,
        class_name: str,
        spec_name: str,
        bundle_id: str,
        meta: Dict[str, Any],
    ) -> Path:
        meta = copy.deepcopy(meta)
        meta["class"] = class_name
        meta["spec"] = spec_name
        meta["bundle_id"] = bundle_id
        meta.setdefault("name", bundle_id.replace("_", " ").title())
        meta.setdefault("description", "")

        target_dir = self.combos_dir / slug_for(class_name, spec_name) / bundle_id
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "_bundle.yaml"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                f"# {class_name} — {spec_name} — bundle: {bundle_id}\n"
                f"# Loadout + metadata for this combo bundle.\n\n"
            )
            _yaml_dump(meta, fh)
        key = (class_name, spec_name, bundle_id)
        self.bundles[key] = meta
        self._bundle_paths[key] = path
        return path

    def delete_bundle(
        self, class_name: str, spec_name: str, bundle_id: str
    ) -> bool:
        """Delete one bundle (and every combo inside it)."""
        key = (class_name, spec_name, bundle_id)
        if key not in self.bundles:
            return False

        # Delete every combo first.
        for ckey in list(self.combos.keys()):
            if ckey[:3] == key:
                cpath = self._combo_paths.pop(ckey, None)
                self.combos.pop(ckey, None)
                if cpath is not None and cpath.exists():
                    try:
                        cpath.unlink()
                    except OSError as exc:
                        logger.error(f"Failed to delete combo {cpath}: {exc}")

        # Delete the bundle yaml.
        bpath = self._bundle_paths.pop(key, None)
        self.bundles.pop(key, None)
        if bpath is not None and bpath.exists():
            try:
                bpath.unlink()
            except OSError as exc:
                logger.error(f"Failed to delete bundle yaml {bpath}: {exc}")

        # Remove the now-empty bundle dir.
        bundle_dir = self.combos_dir / slug_for(class_name, spec_name) / bundle_id
        try:
            if bundle_dir.exists() and not any(bundle_dir.iterdir()):
                bundle_dir.rmdir()
        except OSError:
            pass
        return True

    def delete_for_class(self, class_name: str, spec_name: str) -> int:
        """Delete every bundle (and all their combos) for a class/spec.

        Returns the number of bundles removed.
        """
        n = 0
        for key in list(self.bundles.keys()):
            if key[0] == class_name and key[1] == spec_name:
                if self.delete_bundle(*key):
                    n += 1
        slug_dir = self.combos_dir / slug_for(class_name, spec_name)
        try:
            if slug_dir.exists() and not any(slug_dir.iterdir()):
                slug_dir.rmdir()
        except OSError:
            pass
        return n

    def rename_bundle(
        self,
        class_name: str,
        spec_name: str,
        old_id: str,
        new_id: str,
    ) -> bool:
        """Rename a bundle id. Re-keys every combo and the bundle yaml on disk."""
        if old_id == new_id or not new_id:
            return False
        new_key = (class_name, spec_name, new_id)
        old_key = (class_name, spec_name, old_id)
        if old_key not in self.bundles or new_key in self.bundles:
            return False

        meta = copy.deepcopy(self.bundles[old_key])
        # Snapshot the combos so we can rewrite them under the new id.
        combo_snapshots: List[Tuple[str, Dict[str, Any]]] = []
        for cid, combo in list(self.iter_combos_for_bundle(class_name, spec_name, old_id)):
            combo_snapshots.append((cid, copy.deepcopy(combo)))

        # Tear down the old bundle on disk.
        self.delete_bundle(class_name, spec_name, old_id)

        # Recreate under the new id.
        self.save_bundle(class_name, spec_name, new_id, meta)
        for cid, combo in combo_snapshots:
            combo["bundle_id"] = new_id
            self.save_combo(class_name, spec_name, new_id, cid, combo)
        return True

    # ------------------------------------------------------------------
    # CRUD — combos
    # ------------------------------------------------------------------
    def save_combo(
        self,
        class_name: str,
        spec_name: str,
        bundle_id: str,
        combo_id: str,
        data: Dict[str, Any],
    ) -> Path:
        data = copy.deepcopy(data)
        data["combo_id"] = combo_id
        data["class"] = class_name
        data["spec"] = spec_name
        data["bundle_id"] = bundle_id
        data.setdefault("category", "pve")

        # Make sure the bundle exists on disk so the combo has somewhere
        # to live. If it doesn't, auto-create a minimal _bundle.yaml.
        bkey = (class_name, spec_name, bundle_id)
        if bkey not in self.bundles:
            self.save_bundle(class_name, spec_name, bundle_id, {})

        target_dir = self.combos_dir / slug_for(class_name, spec_name) / bundle_id
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{combo_id}.yaml"
        with open(path, "w", encoding="utf-8") as fh:
            _yaml_dump(data, fh)
        ckey = (class_name, spec_name, bundle_id, combo_id)
        self.combos[ckey] = data
        self._combo_paths[ckey] = path
        return path

    def delete_combo(
        self,
        class_name: str,
        spec_name: str,
        bundle_id: str,
        combo_id: str,
    ) -> bool:
        ckey = (class_name, spec_name, bundle_id, combo_id)
        path = self._combo_paths.pop(ckey, None)
        self.combos.pop(ckey, None)
        if path is not None and path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.error(f"Failed to delete combo {path}: {exc}")
                return False
        return True


# ===========================================================================
# Settings loader
# ===========================================================================
class SettingsLoader:
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

    def get_settings(self) -> Dict[str, Any]:                  return self.settings
    def get_display_settings(self) -> Dict[str, Any]:          return self.settings.get("display", {})
    def get_hotkeys(self) -> Dict[str, str]:
        return self.settings.get("hotkeys", {
            "start_combo": "F5", "stop_combo": "F6",
            "next_step": "F7", "reset_combo": "F8",
        })
    def get_key_bindings(self) -> Dict[str, str]:              return self.settings.get("key_bindings", {})

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
                        "'%s' itself is not remapped away.",
                        canonical, phys, phys,
                    )
        return remap

    def get_timing_settings(self) -> Dict[str, Any]:
        return self.settings.get("timing", {
            "step_highlight_duration_ms": 500,
            "transition_delay_ms": 100,
            "auto_advance": False,
            "idle_reset_timeout_ms": 10000,
        })

    # ------------------------------------------------------------------
    # Active-bundle persistence
    # ------------------------------------------------------------------
    def get_active_bundle(self, class_name: str, spec_name: str) -> str:
        """Return the active bundle id for a class/spec, or 'default'."""
        active = self.settings.get("active_bundle_per_class", {}) or {}
        return active.get(f"{class_name}/{spec_name}", DEFAULT_BUNDLE_ID)

    def set_active_bundle(
        self, class_name: str, spec_name: str, bundle_id: str
    ) -> None:
        active = self.settings.setdefault("active_bundle_per_class", {})
        active[f"{class_name}/{spec_name}"] = bundle_id


# ===========================================================================
# AppLoader facade
# ===========================================================================
class AppLoader:
    """Composes class / bundle / settings loaders.

    Most callers are unchanged from 0.4.x — this facade preserves the
    method names ``main.py``, the overlay, and the tray expect.
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        combos_dir: Optional[Path] = None,
        settings_path: Optional[Path] = None,
    ) -> None:
        self.classes = ClassLoader(data_dir)
        self.bundles = BundleLoader(combos_dir)
        self.settings_loader = SettingsLoader(settings_path)

    # ------------------------------------------------------------------
    # Settings passthroughs
    # ------------------------------------------------------------------
    def reload(self) -> None:
        self.classes.reload()
        self.bundles.reload()
        self.settings_loader.reload()

    def get_settings(self):                return self.settings_loader.get_settings()
    def get_display_settings(self):        return self.settings_loader.get_display_settings()
    def get_hotkeys(self):                 return self.settings_loader.get_hotkeys()
    def get_key_bindings(self):            return self.settings_loader.get_key_bindings()
    def get_key_remap(self):               return self.settings_loader.get_key_remap()
    def get_timing_settings(self):         return self.settings_loader.get_timing_settings()

    @property
    def settings(self) -> Dict[str, Any]:
        return self.settings_loader.settings

    @settings.setter
    def settings(self, value: Dict[str, Any]) -> None:
        self.settings_loader.settings = value

    # ------------------------------------------------------------------
    # Class enumeration / data
    # ------------------------------------------------------------------
    @property
    def class_configs(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        return self.classes.class_configs

    def get_class_config(self, class_name: str, spec_name: str):
        return self.classes.get(class_name, spec_name)

    def get_skill_info(
        self, skill_id: str, class_name: str = "", spec_name: str = ""
    ):
        return self.classes.get_skill_info(skill_id, class_name, spec_name)

    # ------------------------------------------------------------------
    # Bundle / combo enumeration
    # ------------------------------------------------------------------
    def get_combo(
        self,
        class_name: str,
        spec_name: str,
        combo_id: str,
        bundle_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if bundle_id is None:
            bundle_id = self.settings_loader.get_active_bundle(class_name, spec_name)
        return self.bundles.get_combo(class_name, spec_name, bundle_id, combo_id)

    def get_combo_window_ms(
        self,
        class_name: str,
        spec_name: str,
        combo_id: str,
        bundle_id: Optional[str] = None,
    ) -> int:
        if bundle_id is None:
            bundle_id = self.settings_loader.get_active_bundle(class_name, spec_name)
        default = self.settings.get("default_combo_window_ms", 300)
        return self.bundles.get_window_ms(
            class_name, spec_name, bundle_id, combo_id, default
        )

    def get_class_tree(
        self,
    ) -> Dict[str, Dict[str, Dict[str, List[Tuple[str, str]]]]]:
        """Return ``{class: {spec: {bundle_id: [(combo_id, name), ...]}}}``.

        Bundles are listed alphabetically with ``default`` first if present.
        Combos are listed by category then alphabetically within a category.
        Classes with no bundles still appear (with an empty bundle dict)
        so they show up in the tray menu.
        """
        tree: Dict[str, Dict[str, Dict[str, List[Tuple[str, str]]]]] = {}
        for class_name, spec_name in self.classes.keys():
            tree.setdefault(class_name, {})[spec_name] = {}

        # Build the bundle list in the right order using bundles_for_class.
        for class_name, spec_name in self.classes.keys():
            for bundle_id, _meta in self.bundles.bundles_for_class(
                class_name, spec_name
            ):
                tree[class_name][spec_name][bundle_id] = []

        for cls, spec, bid, cid, data in self.bundles.iter_all_combos():
            tree.setdefault(cls, {}).setdefault(spec, {}).setdefault(bid, []).append(
                (cid, data.get("name", cid))
            )
        return tree

    def get_combo_list(
        self,
    ) -> List[Tuple[str, str, str, str, str]]:
        """Flat list of ``(class, spec, bundle_id, combo_id, display)``."""
        return [
            (cls, spec, bid, cid, data.get("name", cid))
            for cls, spec, bid, cid, data in self.bundles.iter_all_combos()
        ]

    def get_category_display_name(self, category: str) -> str:
        return {"pve": "PVE Combos", "pvp": "PVP Combos", "movement": "Movement"}.get(
            category, category
        )

    # ------------------------------------------------------------------
    # Loadout / setup-guide passthroughs (now bundle-scoped)
    # ------------------------------------------------------------------
    def _bundle_for_loadout(
        self, class_name: str, spec_name: str, bundle_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if bundle_id is None:
            bundle_id = self.settings_loader.get_active_bundle(class_name, spec_name)
        return self.bundles.get_bundle(class_name, spec_name, bundle_id) or {}

    def get_locked_skills(
        self, class_name: str, spec_name: str, bundle_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self._bundle_for_loadout(class_name, spec_name, bundle_id).get(
            "locked_skills", []
        )

    def get_hotbar_skills(
        self, class_name: str, spec_name: str, bundle_id: Optional[str] = None
    ) -> List[str]:
        return self._bundle_for_loadout(class_name, spec_name, bundle_id).get(
            "hotbar_skills", []
        )

    def get_core_skill(
        self, class_name: str, spec_name: str, bundle_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._bundle_for_loadout(class_name, spec_name, bundle_id).get(
            "core_skill", {}
        )

    def get_skill_addons(
        self, class_name: str, spec_name: str, bundle_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._bundle_for_loadout(class_name, spec_name, bundle_id).get(
            "skill_addons", {}
        )

    def get_setup_guide(
        self, class_name: str, spec_name: str, bundle_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.classes.has(class_name, spec_name):
            return None
        return {
            "class": class_name,
            "spec": spec_name,
            "bundle_id": bundle_id or self.settings_loader.get_active_bundle(
                class_name, spec_name
            ),
            "locked_skills": self.get_locked_skills(class_name, spec_name, bundle_id),
            "hotbar_skills": self.get_hotbar_skills(class_name, spec_name, bundle_id),
            "core_skill": self.get_core_skill(class_name, spec_name, bundle_id),
            "skill_addons": self.get_skill_addons(class_name, spec_name, bundle_id),
        }

    # ------------------------------------------------------------------
    # CRUD passthroughs
    # ------------------------------------------------------------------
    def save_class_config(self, class_name: str, spec_name: str, data: Dict[str, Any]) -> Path:
        return self.classes.save(class_name, spec_name, data)

    def delete_class_config(self, class_name: str, spec_name: str) -> bool:
        # Wipe every bundle before deleting the class file so we don't
        # leave orphan combos.
        self.bundles.delete_for_class(class_name, spec_name)
        return self.classes.delete(class_name, spec_name)


# ---------------------------------------------------------------------------
# Backward-compat shim — keeps the old `ComboLoader` import working.
# ---------------------------------------------------------------------------
class _LegacyComboLoaderShim(AppLoader):
    """Drop-in for the old monolithic ``ComboLoader`` class."""

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
        super().__init__(
            data_dir=data_dir, combos_dir=combos_dir, settings_path=settings_path
        )


ComboLoader = _LegacyComboLoaderShim
