"""Merge a JSON patch into a draft skill YAML.

The enrichment subagents emit a patch shaped like::

    {
      "<skill_id>": {
        "keys":       ["shift", "lmb"],   # optional
        "protection": "FG",               # optional
        "cc":         ["stiffness"],      # optional
        "notes_flag": "look at me"        # optional, free-text reason
      },
      ...
    }

Only those four field names are honoured. Anything else is ignored.

Usage::

    python -m scripts.apply_skill_patches \\
        --draft data/classes/striker_awakening.draft.yaml \\
        --patch /tmp/striker_a.patch.json
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger("bdo_trainer.patch")

# Only these fields are accepted from a patch; subagents may write
# whatever they want but we discard everything else to keep the data
# structure tight.
ALLOWED_FIELDS = ("keys", "protection", "cc", "notes_flag")


def _yaml_dump(data: Dict[str, Any], fh) -> None:
    yaml.dump(
        data, fh,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


def apply_patch(draft_path: Path, patch_path: Path, dry_run: bool = False) -> int:
    if not draft_path.exists():
        raise FileNotFoundError(f"draft not found: {draft_path}")
    if not patch_path.exists():
        raise FileNotFoundError(f"patch not found: {patch_path}")

    with open(draft_path, encoding="utf-8") as fh:
        draft = yaml.safe_load(fh) or {}
    with open(patch_path, encoding="utf-8") as fh:
        patch = json.load(fh)

    if not isinstance(patch, dict):
        raise ValueError("patch must be a JSON object keyed by skill id")

    skills = draft.get("skills") or {}
    if not isinstance(skills, dict):
        raise ValueError("draft has no `skills` dict")

    flags: list = []
    changed = 0
    skipped = 0
    new_draft = copy.deepcopy(draft)
    new_skills = new_draft.setdefault("skills", {})

    for skill_id, edits in patch.items():
        if not isinstance(edits, dict):
            skipped += 1
            continue
        target = new_skills.get(skill_id)
        if target is None:
            logger.warning(
                "patch references unknown skill_id %r in %s — ignoring",
                skill_id, draft_path.name,
            )
            skipped += 1
            continue
        # Apply allowed fields.
        any_change = False
        for field in ALLOWED_FIELDS:
            if field not in edits:
                continue
            if field == "notes_flag":
                # Capture flags separately so we can write them under a
                # _flags section rather than polluting the skill dict.
                flags.append({skill_id: edits[field]})
                continue
            new_val = edits[field]
            old_val = target.get(field)
            if new_val == old_val:
                continue
            if new_val in (None, "", [], {}):
                # Treat "blank out" patches conservatively — only honour
                # if the field exists; otherwise leave unset.
                if field in target:
                    del target[field]
                    any_change = True
                continue
            target[field] = new_val
            any_change = True
        if any_change:
            changed += 1
        else:
            skipped += 1

    # Stash flags for human review under a top-level `_flags` map. Easy
    # to spot in git diff and trivially droppable.
    if flags:
        new_draft.setdefault("_flags", []).extend(flags)

    if dry_run:
        print(f"DRY RUN: would update {changed} skill(s), skip {skipped}, "
              f"and add {len(flags)} flag(s) to {draft_path}")
        return 0

    with open(draft_path, "w", encoding="utf-8") as fh:
        # Preserve the existing file header (auto-generated banner).
        with open(draft_path, encoding="utf-8") as orig:
            pass  # We already loaded; just rewrite the file body.
        fh.write(
            f"# {new_draft.get('class', '?')} — {new_draft.get('spec', '?')}\n"
            f"# Auto-generated from BDOCodex (scripts/build_class_yaml.py)\n"
            f"# Enriched by scripts/apply_skill_patches.py.\n\n"
        )
        _yaml_dump(new_draft, fh)

    logger.info(
        "Applied patch to %s — updated=%d, skipped=%d, flags=%d",
        draft_path.name, changed, skipped, len(flags),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--patch", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return apply_patch(args.draft, args.patch, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
