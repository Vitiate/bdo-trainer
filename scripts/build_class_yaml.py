"""Parse cached BDOCodex skill HTML into ``data/classes/<slug>.yaml`` drafts.

Reads:
  - ``scripts/_cache/skills_index.json``  (master skills list)
  - ``scripts/_cache/skills/<id>.html``    (per-skill detail pages)

Writes one or more ``data/classes/<slug>.yaml`` files. Existing entries
are preserved unless ``--overwrite`` is passed; otherwise the new draft is
written to ``data/classes/<slug>.draft.yaml`` for manual review.

Spec routing
------------
Each skill is classified as belonging to a particular spec for the
class:

  * Awakening — names that start with ``"Awakening:"`` *or* are flagged
    by the absence of "Prime:" / "Succession:" / "Black Spirit:" *and*
    appear in the awakening skill list (heuristic — see the source).
  * Succession — names that start with ``"Prime:"`` or
    ``"Succession:"``.
  * Talent (Shai only) — Shai's awakening counterpart.

Skills that don't cleanly route to one spec (passives, base skills shared
by both, "Black Spirit:" variants) are written to *both* specs by default
so they show up in either editor — the user can prune as needed.

Usage::

    python -m scripts.build_class_yaml --classes "Dark Knight"
    python -m scripts.build_class_yaml --all
    python -m scripts.build_class_yaml --all --overwrite
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger("bdo_trainer.build")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "scripts" / "_cache"
INDEX_PATH = CACHE_DIR / "skills_index.json"
SKILLS_DIR = CACHE_DIR / "skills"
DATA_CLASSES_DIR = PROJECT_ROOT / "data" / "classes"

KNOWN_CLASSES: Dict[str, Tuple[str, str]] = {
    # class_name → (awakening_spec_label, succession_spec_label)
    "Warrior": ("Awakening", "Succession"),
    "Ranger": ("Awakening", "Succession"),
    "Sorceress": ("Awakening", "Succession"),
    "Berserker": ("Awakening", "Succession"),
    "Tamer": ("Awakening", "Succession"),
    "Musa": ("Awakening", "Succession"),
    "Maehwa": ("Awakening", "Succession"),
    "Valkyrie": ("Awakening", "Succession"),
    "Kunoichi": ("Awakening", "Succession"),
    "Ninja": ("Awakening", "Succession"),
    "Wizard": ("Awakening", "Succession"),
    "Witch": ("Awakening", "Succession"),
    "Dark Knight": ("Awakening", "Succession"),
    "Striker": ("Awakening", "Succession"),
    "Mystic": ("Awakening", "Succession"),
    "Lahn": ("Awakening", "Succession"),
    "Archer": ("Awakening", "Succession"),
    "Shai": ("Talent", "Succession"),
    "Guardian": ("Awakening", "Succession"),
    "Hashashin": ("Awakening", "Succession"),
    "Nova": ("Awakening", "Succession"),
    "Sage": ("Awakening", "Succession"),
    "Corsair": ("Awakening", "Succession"),
    "Drakania": ("Awakening", "Succession"),
    "Woosa": ("Awakening", "Succession"),
    "Maegu": ("Awakening", "Succession"),
    "Scholar": ("Awakening", "Succession"),
}

# Roman numeral suffix at the end of a skill name (e.g. "Shattering Darkness V")
RANK_SUFFIX_RE = re.compile(r"\s+(I|II|III|IV|V|VI|VII|VIII|IX|X)$")

# Maps human-readable key tokens to canonical combo-step keys.
KEY_ALIASES: Dict[str, str] = {
    "lmb": "lmb",
    "rmb": "rmb",
    "mmb": "mmb",
    "shift": "shift",
    "ctrl": "ctrl",
    "alt": "alt",
    "space": "space",
    "tab": "tab",
    "w": "w", "a": "a", "s": "s", "d": "d",
    "q": "q", "e": "e", "f": "f", "x": "x", "z": "z", "r": "r", "c": "c",
    # Arrow glyphs as they appear on BDOCodex skill pages.
    "↑": "w",
    "↓": "s",
    "←": "a",
    "→": "d",
}

CC_KEYWORDS: Dict[str, str] = {
    # description-text needle  →  canonical CC tag
    "stiffness": "stiffness",
    "knockback": "knockback",
    "knockdown": "knockdown",
    "floating": "floating",
    "bound": "bound",
    "stun": "stun",
    "float": "floating",
    "pull": "pull",
    "grab": "grab",
    "down attack": "down_attack",
    "air attack": "air_attack",
    "spin": "spin",
}

PROTECTION_KEYWORDS: List[Tuple[str, str]] = [
    # phrases checked in order — first match wins
    ("invincible", "iframe"),
    ("invincibility", "iframe"),
    ("forward guard", "FG"),
    ("super armor", "SA"),
    ("swer armor", "SA"),  # typo present in some legacy YAMLs
]


def _slug(class_name: str, spec_name: str) -> str:
    return f"{class_name}_{spec_name}".lower().replace(" ", "_")


def _yaml_dump(data: dict, fh) -> None:
    yaml.dump(
        data, fh,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


# ---------------------------------------------------------------------------
# Cache reading
# ---------------------------------------------------------------------------
def load_index() -> List[dict]:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Index not found at {INDEX_PATH}. "
            "Run `python -m scripts.scrape_bdocodex --index` first."
        )
    with open(INDEX_PATH, encoding="utf-8-sig") as f:
        raw = json.load(f)

    rows: List[dict] = []
    for r in raw.get("aaData", []):
        if len(r) < 5:
            continue
        skill_id = int(r[0])
        cls = r[4]
        # Column 2 is HTML; pull the bold name.
        m = re.search(r"<b>\s*(?:<span[^>]*></span>)?\s*([^<]+)</b>", r[2] or "")
        if m:
            name = unescape(m.group(1)).strip()
        else:
            name = unescape(re.sub(r"<[^>]+>", "", r[2] or "")).strip()
        rows.append({
            "id": skill_id,
            "name": name,
            "level": int(r[3]) if isinstance(r[3], (int, str)) and str(r[3]).isdigit() else 0,
            "class": cls,
        })
    return rows


def load_skill_html(skill_id: int) -> Optional[str]:
    p = SKILLS_DIR / f"{skill_id}.html"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Per-skill HTML parsing
# ---------------------------------------------------------------------------
def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _find(html: str, pat: str) -> Optional[str]:
    m = re.search(pat, html, re.S)
    if not m:
        return None
    return _strip_tags(m.group(1))


def parse_skill_html(html: str) -> dict:
    """Extract a structured skill dict from a cached BDOCodex skill page."""
    # Class
    cls = _find(html, r'class="tag_required_class">([^<]+)<')

    # Short flavor description from the tooltip header.
    desc_html = re.search(r'tag_skill-description">(.*?)</span>', html, re.S)
    flavor = _strip_tags(desc_html.group(1)) if desc_html else ""

    # Control / keybind text. We keep the surrounding text so users can
    # disambiguate "RMB after Spirit Hunt" from a bare "RMB".
    ctrl = re.search(r'tag_control">(.*?)</span>\s*</td>', html, re.S)
    control = _strip_tags(ctrl.group(1)) if ctrl else ""

    # Effects block — this is where Forward Guard / Down Attack /
    # Floating / etc. live. Multiple <div id="description"> blocks may
    # exist (e.g. main + Black Spirit variant); we concatenate them so
    # CC + protection detection sees everything.
    effect_blocks = re.findall(
        r'<div id="description">(.*?)</div>', html, re.S
    )
    effects = " ".join(_strip_tags(b) for b in effect_blocks)

    # The full description we hand to detection heuristics.
    description = (flavor + " " + effects).strip()

    cooldown_text = _find(html, r'tag_cooldown">([^<]+)<') or ""
    mp_text = _find(html, r'tag_required_mp">([^<]+)<') or ""
    level_text = _find(html, r'tag_required_level">([^<]+)<') or ""

    return {
        "class": cls or "",
        "flavor": flavor,
        "description": description,
        "control": control,
        "cooldown_text": cooldown_text,
        "mp_text": mp_text,
        "level_text": level_text,
    }


def parse_cooldown_ms(s: str) -> Optional[int]:
    """`'7s'` → 7000, `'1m 30s'` → 90000, `'None'` → None."""
    if not s or s.lower() in ("none", "passive"):
        return None
    total_ms = 0
    for match in re.finditer(r"(\d+)\s*(ms|s|m|min)", s.lower()):
        n = int(match.group(1))
        unit = match.group(2)
        if unit == "ms":
            total_ms += n
        elif unit == "s":
            total_ms += n * 1000
        elif unit in ("m", "min"):
            total_ms += n * 60_000
    return total_ms or None


def parse_keybind(control_text: str) -> Tuple[str, List[str]]:
    """Return ``(input_display, keys)`` from raw control text.

    ``input_display`` is the raw human-readable string from the page (e.g.
    ``"SHIFT + LMB"``); ``keys`` is a canonical list of combo-step key
    tokens (``["shift", "lmb"]``).
    """
    if not control_text:
        return "", []

    # The control string typically starts with the keybind, then trailing
    # advisories like "Can be added to a Quick Slot". Cut the keybind off
    # at the first sentence boundary.
    primary = re.split(r"(?<=[A-Z])\s{2,}|Can be added|during certain", control_text, maxsplit=1)[0].strip()
    primary = primary.strip(" ,;")

    # Tokenise on `+`, spaces, etc.
    tokens = re.split(r"[+\s,]+", primary.lower())
    keys: List[str] = []
    for t in tokens:
        t = t.strip(" .()")
        if not t:
            continue
        if t in KEY_ALIASES:
            keys.append(KEY_ALIASES[t])
    # Dedup while preserving order
    seen = set()
    deduped: List[str] = []
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        deduped.append(k)
    return primary, deduped


def detect_protection(text: str) -> str:
    lower = text.lower()
    for needle, tag in PROTECTION_KEYWORDS:
        if needle in lower:
            return tag
    return "none"


def detect_cc(text: str) -> List[str]:
    lower = text.lower()
    out: List[str] = []
    for needle, tag in CC_KEYWORDS.items():
        if needle in lower and tag not in out:
            out.append(tag)
    return out


def skill_id_from_name(name: str) -> str:
    """Generate a YAML key from a display name."""
    s = name.lower()
    s = RANK_SUFFIX_RE.sub("", s).strip()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "unnamed_skill"


# ---------------------------------------------------------------------------
# Spec routing heuristics
# ---------------------------------------------------------------------------
def route_to_specs(name: str, awakening_label: str) -> List[str]:
    """Return one or both spec labels this skill belongs to."""
    n = name.strip()
    lower = n.lower()
    if lower.startswith("black spirit:"):
        # Black Spirit ultimates exist in both specs but rarely get used
        # in combos — route to both so the user can decide.
        return [awakening_label, "Succession"]
    if (
        lower.startswith("succession:")
        or lower.startswith("prime:")
        or lower.startswith("absolute:")  # succession-rank evolutions
    ):
        return ["Succession"]
    if lower.startswith(awakening_label.lower() + ":"):
        return [awakening_label]
    if "succession" in lower:
        return ["Succession"]
    if any(kw in lower for kw in ("flow:", "core:")):
        # Flow and Core skills tag onto both specs.
        return [awakening_label, "Succession"]
    # Otherwise it's a base skill — both specs use it.
    return [awakening_label, "Succession"]


# ---------------------------------------------------------------------------
# Build per-class YAML
# ---------------------------------------------------------------------------
def build_class_yaml(
    class_name: str,
    overwrite: bool = False,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Build YAML for a single class. Returns ``{spec: skill_count}``."""
    if class_name not in KNOWN_CLASSES:
        logger.warning("Unknown class %r — skipping", class_name)
        return {}
    awakening_label, succession_label = KNOWN_CLASSES[class_name]

    rows = [r for r in load_index() if r["class"] == class_name]
    if not rows:
        logger.warning("No skills in index for %r", class_name)
        return {}

    # Keep only highest-rank entry per base skill name. (The page links
    # I, II, III, … V to the same description text — we want the highest
    # rank's stats.)
    by_base: Dict[str, dict] = {}
    for r in rows:
        # Skip Black Spirit duplicates of base skills — they're niche.
        if r["name"].lower().startswith("black spirit:"):
            continue
        base = RANK_SUFFIX_RE.sub("", r["name"]).strip()
        existing = by_base.get(base)
        if existing is None or r["level"] > existing["level"]:
            by_base[base] = r

    # Build per-spec skill dicts.
    specs_skills: Dict[str, Dict[str, dict]] = {}
    parsed_count = 0
    skipped_count = 0

    for base, row in sorted(by_base.items(), key=lambda kv: kv[0].lower()):
        html = load_skill_html(row["id"])
        if html is None:
            skipped_count += 1
            continue
        parsed = parse_skill_html(html)
        parsed_count += 1

        sid = skill_id_from_name(base)
        input_display, keys = parse_keybind(parsed["control"])
        cooldown_ms = parse_cooldown_ms(parsed["cooldown_text"])

        # Use the short flavor for `description` and stash the longer
        # effects block under `notes` so the YAML stays readable but
        # power users still have the full text available.
        skill_dict = {
            "name": base,
            "input": input_display or parsed["control"],
            "keys": keys,
            "protection": detect_protection(parsed["description"]),
            "cc": detect_cc(parsed["description"]),
            "cooldown_ms": cooldown_ms or 0,
            "description": parsed["flavor"],
            "notes": parsed["description"] if parsed["description"] != parsed["flavor"] else "",
        }
        # Drop empty fields so the YAML stays scannable.
        if not skill_dict["input"]:
            del skill_dict["input"]
        if not skill_dict["keys"]:
            del skill_dict["keys"]
        if not skill_dict["cc"]:
            del skill_dict["cc"]
        if not skill_dict["cooldown_ms"]:
            del skill_dict["cooldown_ms"]
        if not skill_dict["description"]:
            del skill_dict["description"]
        if not skill_dict["notes"]:
            del skill_dict["notes"]

        for spec_label in route_to_specs(base, awakening_label):
            specs_skills.setdefault(spec_label, {})[sid] = skill_dict

    # Write per-spec YAML files.
    DATA_CLASSES_DIR.mkdir(parents=True, exist_ok=True)
    counts: Dict[str, int] = {}
    for spec_label, skills in specs_skills.items():
        slug = _slug(class_name, spec_label)
        target = DATA_CLASSES_DIR / f"{slug}.yaml"
        suffix = ".yaml" if overwrite else ".draft.yaml"
        out = target if overwrite else target.with_name(target.stem + ".draft.yaml")

        body = {
            "class": class_name,
            "spec": spec_label,
            "skills": skills,
        }
        if dry_run:
            logger.info(
                "DRY RUN: would write %s with %d skills",
                out.relative_to(PROJECT_ROOT), len(skills),
            )
        else:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(
                    f"# {class_name} — {spec_label}\n"
                    f"# Auto-generated from BDOCodex (scripts/build_class_yaml.py).\n"
                    f"# Review keys / protection / cc — they're heuristic guesses.\n\n"
                )
                _yaml_dump(body, fh)
        counts[spec_label] = len(skills)

    logger.info(
        "Class %s: parsed %d, skipped %d (cached page missing); wrote %s",
        class_name, parsed_count, skipped_count,
        ", ".join(f"{k}={v}" for k, v in counts.items()),
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classes", nargs="+",
        help="Build only the named class(es). Use quotes for multi-word names.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Build every class in the known roster.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace existing data/classes/<slug>.yaml in place "
             "(default writes data/classes/<slug>.draft.yaml for review).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be written without changing any files.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.all:
        names = sorted(KNOWN_CLASSES.keys())
    elif args.classes:
        names = args.classes
    else:
        parser.error("Must pass --all or --classes …")
        return 1

    for name in names:
        build_class_yaml(name, overwrite=args.overwrite, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
