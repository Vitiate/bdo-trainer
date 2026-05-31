"""Split legacy `config/classes/*.yaml` files into the new layout.

Old layout (everything in one file)::

    config/classes/<class>_<spec>.yaml
        class:, spec:, skills:, pve_combos:, pvp_combos:,
        movement_combos:, locked_skills:, hotbar_skills:,
        core_skill:, skill_addons:

New layout::

    data/classes/<slug>.yaml
        class:, spec:, skills:                        # static class definition

    config/combos/<slug>/<bundle_id>/
        _bundle.yaml                                  # loadout (locked / hotbar /
                                                      # core / skill_addons) +
                                                      # bundle metadata
        <combo_id>.yaml                               # one per combo

The migration writes a single ``default`` bundle per class containing the
loadout from the old file and every combo from every category. Combos
carry a ``category: pve|pvp|movement`` field.

The legacy file is moved to ``config/classes/_legacy/`` rather than
deleted, so the migration is reversible.

Usage::

    python -m scripts.migrate_class_yaml --dry-run    # preview only
    python -m scripts.migrate_class_yaml              # actually do it

Idempotent: if every legacy file has already been migrated, this is a
no-op.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

logger = logging.getLogger("bdo_trainer.migrate")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LEGACY_CLASSES_DIR = PROJECT_ROOT / "config" / "classes"
LEGACY_BACKUP_DIR = LEGACY_CLASSES_DIR / "_legacy"

DATA_CLASSES_DIR = PROJECT_ROOT / "data" / "classes"
COMBO_ROOT = PROJECT_ROOT / "config" / "combos"

DEFAULT_BUNDLE_ID = "default"

# Old combo sections → new category value.
LEGACY_COMBO_SECTIONS: Dict[str, str] = {
    "pve_combos": "pve",
    "pvp_combos": "pvp",
    "movement_combos": "movement",
}

# Sections we keep on the new class-definition file. Order matters — the
# output YAML follows this list.
CLASS_DEF_KEYS: List[str] = [
    "class",
    "spec",
    "skills",
    # Legacy split skill sections are merged into "skills" by the loader,
    # but if a file uses them we preserve them here so nothing is lost.
    "awakening_skills",
    "rabam_skills",
    "preawakening_utility",
]

# Sections that move from the class file into the bundle's loadout.
LOADOUT_KEYS: List[str] = [
    "locked_skills",
    "hotbar_skills",
    "core_skill",
    "skill_addons",
]


def _slugify(class_name: str, spec_name: str) -> str:
    return f"{class_name}_{spec_name}".lower().replace(" ", "_")


def _yaml_dump(data: dict, fh) -> None:
    yaml.dump(
        data, fh,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


def split_one(legacy_path: Path) -> Tuple[Path, Path, List[Path]]:
    """Split one legacy YAML. Returns (class_def_path, bundle_yaml_path, [combo_paths]).

    Does NOT write the files — caller decides whether dry-run."""
    with open(legacy_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    class_name = raw.get("class") or ""
    spec_name = raw.get("spec") or ""
    if not class_name or not spec_name:
        raise ValueError(
            f"{legacy_path.name}: missing 'class' or 'spec' top-level keys"
        )

    slug = _slugify(class_name, spec_name)

    class_def_path = DATA_CLASSES_DIR / f"{slug}.yaml"
    bundle_dir = COMBO_ROOT / slug / DEFAULT_BUNDLE_ID
    bundle_yaml_path = bundle_dir / "_bundle.yaml"

    combo_paths: List[Path] = []
    for section_key, category in LEGACY_COMBO_SECTIONS.items():
        section_data = raw.get(section_key) or {}
        if not isinstance(section_data, dict):
            continue
        for combo_id, combo in section_data.items():
            if not isinstance(combo, dict):
                continue
            combo_paths.append(bundle_dir / f"{combo_id}.yaml")

    return class_def_path, bundle_yaml_path, combo_paths


def write_split(legacy_path: Path) -> Tuple[Path, Path, List[Path]]:
    """Write the split files to disk."""
    with open(legacy_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    class_name = raw["class"]
    spec_name = raw["spec"]
    slug = _slugify(class_name, spec_name)

    DATA_CLASSES_DIR.mkdir(parents=True, exist_ok=True)
    bundle_dir = COMBO_ROOT / slug / DEFAULT_BUNDLE_ID
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Class-def file: skills only, no loadout, no combos.
    class_def: Dict = {}
    for key in CLASS_DEF_KEYS:
        if key in raw:
            class_def[key] = raw[key]

    class_def_path = DATA_CLASSES_DIR / f"{slug}.yaml"
    with open(class_def_path, "w", encoding="utf-8") as fh:
        fh.write(
            f"# {class_name} — {spec_name}\n"
            f"# Class definition (skills only). Ships with BDO Trainer.\n"
            f"# User-edited combos and loadouts live in config/combos/{slug}/.\n\n"
        )
        _yaml_dump(class_def, fh)

    # Bundle yaml: bundle metadata + loadout that came off the legacy file.
    bundle_data: Dict = {
        "class": class_name,
        "spec": spec_name,
        "bundle_id": DEFAULT_BUNDLE_ID,
        "name": "Default",
        "description": "Auto-created default bundle (migrated from legacy class config).",
    }
    for key in LOADOUT_KEYS:
        if key in raw:
            bundle_data[key] = raw[key]
    with open(bundle_yaml_path := bundle_dir / "_bundle.yaml", "w", encoding="utf-8") as fh:
        fh.write(
            f"# {class_name} — {spec_name} — bundle: {DEFAULT_BUNDLE_ID}\n"
            f"# Loadout + metadata for this combo bundle.\n\n"
        )
        _yaml_dump(bundle_data, fh)

    # Per-combo files
    combo_paths: List[Path] = []
    for section_key, category in LEGACY_COMBO_SECTIONS.items():
        section_data = raw.get(section_key) or {}
        if not isinstance(section_data, dict):
            continue
        for combo_id, combo in section_data.items():
            if not isinstance(combo, dict):
                continue
            entry: Dict = {
                "combo_id": combo_id,
                "class": class_name,
                "spec": spec_name,
                "bundle_id": DEFAULT_BUNDLE_ID,
                "category": category,
            }
            for k, v in combo.items():
                if k not in entry:
                    entry[k] = v
            out = bundle_dir / f"{combo_id}.yaml"
            with open(out, "w", encoding="utf-8") as fh:
                _yaml_dump(entry, fh)
            combo_paths.append(out)

    return class_def_path, bundle_yaml_path, combo_paths


def archive_legacy(legacy_path: Path) -> Path:
    LEGACY_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = LEGACY_BACKUP_DIR / legacy_path.name
    n = 1
    final = target
    while final.exists():
        final = target.with_name(f"{target.stem}.{n}{target.suffix}")
        n += 1
    shutil.move(str(legacy_path), str(final))
    return final


def needs_migration() -> bool:
    """True if there are unmigrated class YAMLs in config/classes/."""
    if not LEGACY_CLASSES_DIR.exists():
        return False
    candidates = [
        p for p in LEGACY_CLASSES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".yaml"
    ]
    return bool(candidates)


def run(dry_run: bool = False) -> int:
    if not LEGACY_CLASSES_DIR.exists():
        print(f"No legacy classes directory at {LEGACY_CLASSES_DIR} — nothing to migrate.")
        return 0

    legacy_files = sorted(
        p for p in LEGACY_CLASSES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".yaml"
    )
    if not legacy_files:
        print("No unmigrated *.yaml files found in config/classes/.")
        return 0

    if dry_run:
        print(f"DRY RUN — would migrate {len(legacy_files)} file(s):\n")

    failures = 0
    for legacy in legacy_files:
        try:
            class_def_path, bundle_path, combo_paths = split_one(legacy)
        except Exception as exc:
            print(f"  ERROR in {legacy.name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        print(f"{legacy.name}")
        print(f"  → {class_def_path.relative_to(PROJECT_ROOT)}")
        print(f"  → {bundle_path.relative_to(PROJECT_ROOT)}")
        for cp in combo_paths:
            print(f"  → {cp.relative_to(PROJECT_ROOT)}")
        print(f"  → archive {legacy.relative_to(PROJECT_ROOT)} to "
              f"config/classes/_legacy/{legacy.name}")
        print()

        if not dry_run:
            write_split(legacy)
            archive_legacy(legacy)

    if failures:
        print(f"Migration finished with {failures} error(s).", file=sys.stderr)
        return 1

    if dry_run:
        print("Dry run complete. Re-run without --dry-run to apply.")
    else:
        print(f"Migration complete: {len(legacy_files)} file(s) split.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without writing anything.",
    )
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
