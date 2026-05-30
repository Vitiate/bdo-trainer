"""Generate empty class-definition shells under ``data/classes/``.

A "shell" has just the class+spec metadata and an empty ``skills`` dict.
Existing files are left alone — re-running the script only adds missing
classes/specs.

A matching ``default`` bundle is also created under ``config/combos/<slug>/``
if there isn't one already, so the new class shows up in the tray menu
immediately even before any combos are added.

Usage::

    python -m scripts.seed_class_shells              # create what's missing
    python -m scripts.seed_class_shells --dry-run    # preview only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_CLASSES_DIR = PROJECT_ROOT / "data" / "classes"
COMBO_ROOT = PROJECT_ROOT / "config" / "combos"

# (class_name, spec_name) for every BDO class as of 2026-05.
# Shai has Talent instead of Awakening; Succession is its second spec.
# The rest are Awakening + Succession.
ROSTER: List[Tuple[str, str]] = []
for _class in (
    "Warrior", "Ranger", "Sorceress", "Berserker", "Tamer", "Musa",
    "Maehwa", "Valkyrie", "Kunoichi", "Ninja", "Wizard", "Witch",
    "Dark Knight", "Striker", "Mystic", "Lahn", "Archer", "Guardian",
    "Hashashin", "Nova", "Sage", "Corsair", "Drakania", "Woosa",
    "Maegu", "Scholar",
):
    ROSTER.append((_class, "Awakening"))
    ROSTER.append((_class, "Succession"))
# Shai: Talent + Succession (no Awakening).
ROSTER.append(("Shai", "Talent"))
ROSTER.append(("Shai", "Succession"))


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


def write_class_shell(class_name: str, spec_name: str) -> Path:
    DATA_CLASSES_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_CLASSES_DIR / f"{_slugify(class_name, spec_name)}.yaml"
    body = {
        "class": class_name,
        "spec": spec_name,
        "skills": {},
    }
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            f"# {class_name} — {spec_name}\n"
            f"# Class definition (skills only). Empty shell — populate via "
            f"the Class Editor or import a .bdc.\n\n"
        )
        _yaml_dump(body, fh)
    return path


def write_default_bundle(class_name: str, spec_name: str) -> Path:
    bundle_dir = COMBO_ROOT / _slugify(class_name, spec_name) / "default"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_yaml = bundle_dir / "_bundle.yaml"
    if bundle_yaml.exists():
        return bundle_yaml
    body = {
        "class": class_name,
        "spec": spec_name,
        "bundle_id": "default",
        "name": "Default",
        "description": "",
        "locked_skills": [],
        "hotbar_skills": [],
        "core_skill": {},
        "skill_addons": {"pve": []},
    }
    with open(bundle_yaml, "w", encoding="utf-8") as fh:
        fh.write(
            f"# {class_name} — {spec_name} — bundle: default\n"
            f"# Auto-created by seed_class_shells.\n\n"
        )
        _yaml_dump(body, fh)
    return bundle_yaml


def run(dry_run: bool = False) -> int:
    DATA_CLASSES_DIR.mkdir(parents=True, exist_ok=True)
    existing = {
        p.stem for p in DATA_CLASSES_DIR.glob("*.yaml") if p.is_file()
    }

    to_create: List[Tuple[str, str]] = []
    for class_name, spec_name in ROSTER:
        slug = _slugify(class_name, spec_name)
        if slug in existing:
            continue
        to_create.append((class_name, spec_name))

    if not to_create:
        print(f"All {len(ROSTER)} class shells already exist — nothing to do.")
        return 0

    print(
        f"{'Would create' if dry_run else 'Creating'} "
        f"{len(to_create)} class shell(s) "
        f"(out of {len(ROSTER)} in roster):"
    )
    for class_name, spec_name in to_create:
        slug = _slugify(class_name, spec_name)
        print(f"  - data/classes/{slug}.yaml")
        print(f"    config/combos/{slug}/default/_bundle.yaml")
        if not dry_run:
            write_class_shell(class_name, spec_name)
            write_default_bundle(class_name, spec_name)

    if dry_run:
        print()
        print("Dry run — re-run without --dry-run to apply.")
    else:
        print()
        print(f"Done. {len(to_create)} class shell(s) created.")
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
