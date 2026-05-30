"""Class & combo bundle formats — `.bdt` (combos) and `.bdc` (class).

Both formats are gzip-compressed JSON with a discriminator ``kind`` field
so a single decoder routes either type. Legacy ``.bdt`` files (whole-class
bundles from 0.4.x) are still readable and treated as class bundles.

Schemas
=======

**Combo bundle** (``.bdt``, ``format_version = 2``, ``kind = "combos"``)::

    {
      "format_version": 2,
      "kind": "combos",
      "exported_at": "...",
      "exporter": "bdo-trainer",
      "class_name": "Dark Knight",
      "spec_name": "Awakening",
      "bundle_id": "grinding",
      "name": "PVE Grinding Setup",
      "description": "Loadout and rotations for endgame grind.",
      "loadout": {
        "locked_skills": [...],
        "hotbar_skills": [...],
        "core_skill": {...},
        "skill_addons": {...}
      },
      "combos": {
        "<combo_id>": {
          "combo_id": "...",
          "class": "Dark Knight",
          "spec": "Awakening",
          "bundle_id": "grinding",
          "category": "pve",
          ...
        },
        ...
      }
    }

**Class bundle** (``.bdc``, ``format_version = 2``, ``kind = "class"``)::

    {
      "format_version": 2,
      "kind": "class",
      "exported_at": "...",
      "exporter": "bdo-trainer",
      "class_name": "Dark Knight",
      "spec_name": "Awakening",
      "config": {
        ... skills only ...
      }
    }

**Legacy combo bundle** (``.bdt``, ``format_version = 1``) — v0.4.x
whole-class bundle. ``kind`` field is absent. Decoded as ``kind = "class"``;
its inner ``config`` carries both class metadata and combos.
"""

from __future__ import annotations

import copy
import datetime as _dt
import gzip
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("bdo_trainer")

FORMAT_VERSION = 2

BDT_EXTENSION = ".bdt"
BDC_EXTENSION = ".bdc"

COMBO_CATEGORIES = ("pve", "pvp", "movement")
LOADOUT_KEYS = ("locked_skills", "hotbar_skills", "core_skill", "skill_addons")
SKILL_SECTIONS = (
    "skills",
    "awakening_skills",
    "rabam_skills",
    "preawakening_utility",
)


class BundleError(ValueError):
    """Raised when a .bdt / .bdc file is malformed or unsupported."""


def _now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _gzip_json(payload: Dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(raw)
    return buf.getvalue()


def _ungzip_json(data: bytes) -> Dict[str, Any]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
            raw = gz.read()
    except OSError as exc:
        raise BundleError(f"file is not a valid gzip archive: {exc}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"file does not contain valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise BundleError("bundle must be a JSON object")
    return decoded


# ---------------------------------------------------------------------------
# Combo bundle (.bdt)
# ---------------------------------------------------------------------------
def pack_combo_bundle(
    class_name: str,
    spec_name: str,
    bundle_id: str,
    name: str,
    description: str,
    loadout: Dict[str, Any],
    combos: Dict[str, Dict[str, Any]],
) -> bytes:
    if not class_name or not spec_name:
        raise BundleError("class_name and spec_name are required")
    if not bundle_id:
        raise BundleError("bundle_id is required")
    bundle = {
        "format_version": FORMAT_VERSION,
        "kind": "combos",
        "exported_at": _now_iso(),
        "exporter": "bdo-trainer",
        "class_name": class_name,
        "spec_name": spec_name,
        "bundle_id": bundle_id,
        "name": name or bundle_id,
        "description": description or "",
        "loadout": copy.deepcopy(loadout) if isinstance(loadout, dict) else {},
        "combos": {cid: copy.deepcopy(combo) for cid, combo in combos.items()},
    }
    return _gzip_json(bundle)


def write_combo_bundle(
    path: str | Path,
    class_name: str,
    spec_name: str,
    bundle_id: str,
    name: str,
    description: str,
    loadout: Dict[str, Any],
    combos: Dict[str, Dict[str, Any]],
) -> Path:
    p = Path(path)
    if p.suffix.lower() != BDT_EXTENSION:
        p = p.with_suffix(BDT_EXTENSION)
    p.write_bytes(
        pack_combo_bundle(
            class_name, spec_name, bundle_id, name, description, loadout, combos
        )
    )
    logger.info(
        "Exported combo bundle: %s/%s/%s -> %s",
        class_name, spec_name, bundle_id, p,
    )
    return p


# ---------------------------------------------------------------------------
# Class bundle (.bdc)
# ---------------------------------------------------------------------------
def pack_class_bundle(
    class_name: str, spec_name: str, config: Dict[str, Any]
) -> bytes:
    if not class_name or not spec_name:
        raise BundleError("class_name and spec_name are required")
    bundle = {
        "format_version": FORMAT_VERSION,
        "kind": "class",
        "exported_at": _now_iso(),
        "exporter": "bdo-trainer",
        "class_name": class_name,
        "spec_name": spec_name,
        "config": copy.deepcopy(config),
    }
    return _gzip_json(bundle)


def write_class_bundle(
    path: str | Path,
    class_name: str,
    spec_name: str,
    config: Dict[str, Any],
) -> Path:
    p = Path(path)
    if p.suffix.lower() != BDC_EXTENSION:
        p = p.with_suffix(BDC_EXTENSION)
    p.write_bytes(pack_class_bundle(class_name, spec_name, config))
    logger.info("Exported class bundle: %s/%s -> %s", class_name, spec_name, p)
    return p


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------
def unpack_bundle(data: bytes) -> Dict[str, Any]:
    """Decode any .bdt / .bdc payload."""
    bundle = _ungzip_json(data)

    fmt = bundle.get("format_version")
    if not isinstance(fmt, int):
        raise BundleError("missing or invalid 'format_version'")
    if fmt > FORMAT_VERSION:
        raise BundleError(
            f"unsupported format_version {fmt} (this build supports up to "
            f"{FORMAT_VERSION}). Update BDO Trainer to import this file."
        )

    # Legacy v1: whole-class bundle. Treat as kind="class".
    if fmt == 1:
        for required in ("class_name", "spec_name", "config"):
            if required not in bundle:
                raise BundleError(f"missing required field '{required}'")
        if not isinstance(bundle["config"], dict):
            raise BundleError("'config' must be an object")
        bundle["kind"] = "class"
        return bundle

    kind = bundle.get("kind")
    if kind not in ("combos", "class"):
        raise BundleError(
            f"unsupported bundle kind {kind!r} (expected 'combos' or 'class')"
        )

    for required in ("class_name", "spec_name"):
        if required not in bundle:
            raise BundleError(f"missing required field '{required}'")
        if not isinstance(bundle[required], str) or not bundle[required].strip():
            raise BundleError(f"'{required}' must be a non-empty string")

    if kind == "combos":
        if not isinstance(bundle.get("combos"), dict):
            raise BundleError("'combos' must be an object keyed by combo_id")
        bundle.setdefault("bundle_id", "default")
        bundle.setdefault("name", bundle["bundle_id"])
        bundle.setdefault("loadout", {})
    else:
        if not isinstance(bundle.get("config"), dict):
            raise BundleError("'config' must be an object")

    return bundle


def read_bundle_from_file(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise BundleError(f"file not found: {p}")
    return unpack_bundle(p.read_bytes())


# ---------------------------------------------------------------------------
# Inspection helpers
# ---------------------------------------------------------------------------
def list_combos_in_bundle(
    bundle: Dict[str, Any],
) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """Yield ``(combo_id, combo_dict)`` for every combo carried by *bundle*.

    Works on v2 combo bundles and on legacy v1 class bundles (which
    carried combos under ``config.pve_combos`` / ``pvp_combos`` /
    ``movement_combos``).
    """
    if bundle.get("kind") == "combos":
        for cid, combo in (bundle.get("combos") or {}).items():
            if isinstance(combo, dict):
                yield cid, combo
        return

    cfg = bundle.get("config") or {}
    for legacy_section in ("pve_combos", "pvp_combos", "movement_combos"):
        section = cfg.get(legacy_section) or {}
        if not isinstance(section, dict):
            continue
        for cid, combo in section.items():
            if not isinstance(combo, dict):
                continue
            entry = dict(combo)
            entry.setdefault("category", legacy_section.removesuffix("_combos"))
            entry.setdefault("combo_id", cid)
            entry.setdefault("class", bundle.get("class_name", ""))
            entry.setdefault("spec", bundle.get("spec_name", ""))
            entry.setdefault("bundle_id", bundle.get("bundle_id", "default"))
            yield cid, entry


def list_skills_in_bundle(bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return ``{skill_id: skill_dict}`` for the bundle, empty for combo bundles."""
    out: Dict[str, Dict[str, Any]] = {}
    if bundle.get("kind") == "combos":
        return out
    cfg = bundle.get("config") or {}
    for section in SKILL_SECTIONS:
        skills = cfg.get(section) or {}
        if isinstance(skills, dict):
            out.update(skills)
    return out


def collect_skill_ids_used_by_combo(combo: Dict[str, Any]) -> set:
    out: set = set()
    for step in combo.get("steps") or []:
        if isinstance(step, dict):
            sid = step.get("skill")
            if isinstance(sid, str) and sid:
                out.add(sid)
    return out


def get_skill(bundle_or_config: Dict[str, Any], skill_id: str):
    if "config" in bundle_or_config and isinstance(bundle_or_config["config"], dict):
        cfg = bundle_or_config["config"]
    else:
        cfg = bundle_or_config
    for section in SKILL_SECTIONS:
        skills = cfg.get(section) or {}
        if isinstance(skills, dict) and skill_id in skills:
            return skills[skill_id]
    return None
