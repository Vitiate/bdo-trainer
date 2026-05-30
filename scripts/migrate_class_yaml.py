"""Split legacy `config/classes/*.yaml` files into the new layout.

Old layout (everything in one file):
    config/classes/<class>_<spec>.yaml
        class:, spec:, skills:, pve_combos:, pvp_combos:,
        movement_combos:, locked_skills:, hotbar_skills:,
        core_skill:, skill_addons:

New layout:
    data/classes/<class>_<spec>.yaml          (read-only — ships with app)
        class:, spec:, skills:, locked_skills:, hotbar_skills:,
        core_skill:, skill_addons:
    config/combos/<class>_<spec>/<combo_id>.yaml   (one file per combo)
        combo_id:, category: pve|pvp|movement, name:, difficulty:,
        combo_window_ms:, description:, steps:

The legacy file is moved to `config/classes/_legacy/` rather than deleted.

Usage:
    python -m scripts.migrate_class_yaml --dry-run    # preview only
    python -m scripts.migrate_class_yaml              # actually do it

Idempotent: if all six legacy files have already been migrated and moved
to `_legacy/`, this is a no-op.
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

# Sections we strip from the class definition (everything else stays as-is
# under data/classes/). The combo sections explode into per-file YAMLs.
COMBO_SECTIONS: Dict[str, str] = {
    "pve_combos": "pve",
    "pvp_combos": "pvp",
    "movement_combos": "movement",
}

# Keys we keep on the new class-definition file. Order matters — this is
# the order they'll appear in the output YAML.
CLASS_DEF_KEYS: List[str] = [
    "class",
    "spec",
    "skills",
    "awakening_skills",
    "rabam_skills",
    "preawakening_utility",
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


def split_one(legacy_path: Path) -> Tuple[Path, List[Path]]:
    """Split one legacy YAML. Returns (class_def_path, [combo_paths]).

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

    # Class-definition file: keep skill-shaped sections; drop combo sections.
    class_def: Dict = {}
    for key, value in raw.items():
        if key in CLASS_DEF_KEYS:
            class_def[key] = value

    class_def_path = DATA_CLASSES_DIR / f"{slug}.yaml"

    # Per-combo files: explode each combo with category injected.
    combo_dir = COMBO_ROOT / slug
    combo_paths: List[Path] = []

    for section_key, category in COMBO_SECTIONS.items():
        section_data = raw.get(section_key) or {}
        if not isinstance(section_data, dict):
            continue
        for combo_id, combo in section_data.items():
            if not isinstance(combo, dict):
                continue
            entry = {
                "combo_id": combo_id,
                "class": class_name,
                "spec": spec_name,
                "category": category,
            }
            # Preserve combo's own fields (name, difficulty, etc.) without
            # double-writing the keys we just set.
            for k, v in combo.items():
                if k not in entry:
                    entry[k] = v
            combo_paths.append(combo_dir / f"{combo_id}.yaml")

    return class_def_path, combo_paths


def write_split(legacy_path: Path) -> Tuple[Path, List[Path]]:
    """Write the split files to disk. Returns (class_def_path, combo_paths)."""
    with open(legacy_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    class_name = raw["class"]
    spec_name = raw["spec"]
    slug = _slugify(class_name, spec_name)

    DATA_CLASSES_DIR.mkdir(parents=True, exist_ok=True)
    combo_dir = COMBO_ROOT / slug
    combo_dir.mkdir(parents=True, exist_ok=True)

    # Class-def file
    class_def: Dict = {}
    for key in CLASS_DEF_KEYS:
        if key in raw:
            class_def[key] = raw[key]

    class_def_path = DATA_CLASSES_DIR / f"{slug}.yaml"
    with open(class_def_path, "w", encoding="utf-8") as fh:
        fh.write(
            f"# {class_name} — {spec_name}\n"
            f"# Class definition (skills, hotbar, core skill, addons).\n"
            f"# Ships with BDO Trainer; user-edited combos live in "
            f"config/combos/{slug}/.\n\n"
        )
        _yaml_dump(class_def, fh)

    # Per-combo files
    combo_paths: List[Path] = []
    for section_key, category in COMBO_SECTIONS.items():
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
                "category": category,
            }
            for k, v in combo.items():
                if k not in entry:
                    entry[k] = v
            out = combo_dir / f"{combo_id}.yaml"
            with open(out, "w", encoding="utf-8") as fh:
                _yaml_dump(entry, fh)
            combo_paths.append(out)

    return class_def_path, combo_paths


def archive_legacy(legacy_path: Path) -> Path:
    LEGACY_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = LEGACY_BACKUP_DIR / legacy_path.name
    # If target already exists from a prior partial run, suffix it.
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
    """Run the migration. Returns the exit code (0 success, 1 error)."""
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
            class_def_path, combo_paths = split_one(legacy)
        except Exception as exc:
            print(f"  ERROR in {legacy.name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        rel_class = class_def_path.relative_to(PROJECT_ROOT)
        print(f"{legacy.name}")
        print(f"  → {rel_class}")
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
