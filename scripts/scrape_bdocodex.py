"""Scrape skill data from BDOCodex into a local cache.

Two-step approach to be polite to the site and to make re-running cheap:

1. Pull the master skills index *once* (~9.6k rows) from
   ``https://bdocodex.com/query.php?a=skills`` and save to
   ``scripts/_cache/skills_index.json``.

2. For every skill belonging to a class we care about, fetch
   ``https://bdocodex.com/us/skill/<id>/`` and save to
   ``scripts/_cache/skills/<id>.html``.

Both phases are idempotent — they skip files that already exist.

The actual YAML construction lives in ``scripts/build_class_yaml.py``;
this script only fills the cache so the parser can be re-run without
hitting the site.

Usage::

    python -m scripts.scrape_bdocodex --index            # fetch index only
    python -m scripts.scrape_bdocodex --classes Striker  # fetch one class
    python -m scripts.scrape_bdocodex --all              # all 27 classes
    python -m scripts.scrape_bdocodex --dry-run --all    # preview
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

logger = logging.getLogger("bdo_trainer.scrape")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "scripts" / "_cache"
INDEX_PATH = CACHE_DIR / "skills_index.json"
SKILLS_DIR = CACHE_DIR / "skills"

INDEX_URL = "https://bdocodex.com/query.php?a=skills"
SKILL_URL_TEMPLATE = "https://bdocodex.com/us/skill/{id}/"

# Match the class roster used elsewhere (seed_class_shells.py). Shai is
# special — Talent + Succession instead of Awakening + Succession.
KNOWN_CLASSES: Set[str] = {
    "Warrior", "Ranger", "Sorceress", "Berserker", "Tamer", "Musa",
    "Maehwa", "Valkyrie", "Kunoichi", "Ninja", "Wizard", "Witch",
    "Dark Knight", "Striker", "Mystic", "Lahn", "Archer", "Shai",
    "Guardian", "Hashashin", "Nova", "Sage", "Corsair", "Drakania",
    "Woosa", "Maegu", "Scholar",
}

USER_AGENT = "bdo-trainer-scraper/0.5 (https://github.com/Vitiate/bdo-trainer)"
REQUEST_TIMEOUT = 30
POLITE_DELAY_S = 1.0
MAX_RETRIES = 2


def _fetch(url: str, *, accept_json: bool = False) -> bytes:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json" if accept_json else "text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = (attempt + 1) * 2
                logger.warning(
                    "Fetch %s failed (%s); retrying in %ds", url, exc, wait
                )
                time.sleep(wait)
            else:
                raise
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Phase 1: skills index
# ---------------------------------------------------------------------------
def fetch_index(dry_run: bool = False, force: bool = False) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_PATH.exists() and not force:
        logger.info("Index cache already present at %s", INDEX_PATH)
        return INDEX_PATH
    if dry_run:
        print(f"DRY RUN: would fetch {INDEX_URL} → {INDEX_PATH}")
        return INDEX_PATH

    logger.info("Fetching skills index from %s", INDEX_URL)
    raw = _fetch(INDEX_URL, accept_json=True)
    INDEX_PATH.write_bytes(raw)
    logger.info("Saved %d bytes to %s", len(raw), INDEX_PATH)
    return INDEX_PATH


def load_index() -> Dict[str, List[List]]:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Index not found at {INDEX_PATH}. Run with --index first."
        )
    with open(INDEX_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def index_rows_for_class(
    class_name: str,
) -> List[Dict[str, object]]:
    """Return ``[{id, name, level}]`` for every skill in ``class_name``.

    The HTML in the second column is stripped to a plain skill name.
    """
    raw = load_index()
    rows: List[Dict[str, object]] = []
    for row in raw.get("aaData", []):
        if len(row) < 5:
            continue
        if row[4] != class_name:
            continue
        skill_id = row[0]
        # Column 2 is HTML containing the skill name inside <b>...</b>.
        name_html = row[2] if isinstance(row[2], str) else ""
        m = re.search(r"<b>\s*(?:<span[^>]*></span>)?\s*([^<]+)</b>", name_html)
        if m:
            name = m.group(1)
        else:
            name = re.sub(r"<[^>]+>", "", name_html).strip()
        # Decode the few HTML entities that show up in skill names.
        name = (
            name.replace("&#39;", "'")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .strip()
        )
        rows.append({"id": skill_id, "name": name, "level": row[3]})
    return rows


# ---------------------------------------------------------------------------
# Phase 2: per-skill pages
# ---------------------------------------------------------------------------
def cached_skill_path(skill_id: int) -> Path:
    return SKILLS_DIR / f"{skill_id}.html"


def fetch_one_skill(skill_id: int, dry_run: bool = False) -> Optional[Path]:
    """Cache a single skill page. Returns the cache path (or None on dry-run)."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target = cached_skill_path(skill_id)
    if target.exists():
        return target
    url = SKILL_URL_TEMPLATE.format(id=skill_id)
    if dry_run:
        print(f"DRY RUN: would fetch {url} → {target}")
        return None
    try:
        raw = _fetch(url)
    except Exception as exc:
        logger.warning("Skipping skill %s — fetch failed: %s", skill_id, exc)
        return None
    target.write_bytes(raw)
    return target


def fetch_class(
    class_name: str, dry_run: bool = False, limit: Optional[int] = None,
) -> int:
    """Cache every skill page for one class. Returns count fetched (skips
    those already in the cache)."""
    if class_name not in KNOWN_CLASSES:
        logger.warning("Unknown class %r — skipping", class_name)
        return 0
    rows = index_rows_for_class(class_name)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        logger.warning("No skills found in index for %r", class_name)
        return 0

    logger.info("Class %s: %d skills indexed", class_name, len(rows))
    fetched = 0
    skipped = 0
    for i, row in enumerate(rows, 1):
        skill_id = row["id"]
        target = cached_skill_path(int(skill_id))
        if target.exists():
            skipped += 1
            continue
        if dry_run:
            print(f"DRY RUN: would fetch skill {skill_id}")
            continue
        if i % 25 == 0:
            logger.info("  %s: %d/%d", class_name, i, len(rows))
        if fetch_one_skill(int(skill_id)) is not None:
            fetched += 1
        time.sleep(POLITE_DELAY_S)
    logger.info(
        "Class %s: fetched %d, skipped %d (already cached)",
        class_name, fetched, skipped,
    )
    return fetched


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index", action="store_true",
        help="Fetch (or refresh) the master skills index and stop.",
    )
    parser.add_argument(
        "--force-index", action="store_true",
        help="Refetch the index even if cached.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Fetch every class in the known roster.",
    )
    parser.add_argument(
        "--classes", nargs="+",
        help="Only fetch the named class(es). Use quotes for multi-word names.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap how many skill pages to fetch per class (smoke testing).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be fetched without writing anything.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Index
    fetch_index(dry_run=args.dry_run, force=args.force_index)
    if args.index:
        return 0

    classes: Iterable[str]
    if args.all:
        classes = sorted(KNOWN_CLASSES)
    elif args.classes:
        classes = args.classes
    else:
        parser.error("Must pass --all or --classes …")
        return 1  # unreachable

    total = 0
    for class_name in classes:
        total += fetch_class(class_name, dry_run=args.dry_run, limit=args.limit)

    logger.info("Done — fetched %d skill page(s) total.", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
