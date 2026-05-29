"""Class export / import — `.bdt` (BDO Trainer) file format.

A `.bdt` file is gzip-compressed JSON containing a single class config
plus a small header. The format is intentionally minimal so that the
loader can detect bad files early and migrate cleanly across versions.

Schema (format_version = 1):

    {
      "format_version": 1,
      "exported_at": "2026-05-28T18:54:00Z",
      "exporter": "bdo-trainer",
      "class_name": "Dark Knight",
      "spec_name": "Awakening",
      "config": { ... full class YAML config dict ... }
    }

Public API:
    pack_class_bundle(class_name, spec_name, config)  -> bytes
    unpack_class_bundle(data: bytes)                  -> dict (validated)
    write_bundle_to_file(path, class_name, spec, config)
    read_bundle_from_file(path)                       -> dict
"""

from __future__ import annotations

import copy
import datetime as _dt
import gzip
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("bdo_trainer")

BDT_FORMAT_VERSION = 1
BDT_EXTENSION = ".bdt"


class BundleError(ValueError):
    """Raised when a .bdt file is malformed or unsupported."""


def pack_class_bundle(
    class_name: str, spec_name: str, config: Dict[str, Any]
) -> bytes:
    """Serialize a class config into a gzipped-JSON .bdt payload."""
    bundle = {
        "format_version": BDT_FORMAT_VERSION,
        "exported_at": _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "exporter": "bdo-trainer",
        "class_name": class_name,
        "spec_name": spec_name,
        "config": copy.deepcopy(config),
    }
    raw = json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(raw)
    return buf.getvalue()


def unpack_class_bundle(data: bytes) -> Dict[str, Any]:
    """Decode a .bdt payload. Returns the validated bundle dict."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
            raw = gz.read()
    except OSError as exc:
        raise BundleError(f"file is not a valid gzip archive: {exc}") from exc

    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"file does not contain valid JSON: {exc}") from exc

    if not isinstance(bundle, dict):
        raise BundleError("bundle must be a JSON object")

    fmt = bundle.get("format_version")
    if not isinstance(fmt, int):
        raise BundleError("missing or invalid 'format_version'")
    if fmt > BDT_FORMAT_VERSION:
        raise BundleError(
            f"unsupported format_version {fmt} (this build supports up to "
            f"{BDT_FORMAT_VERSION}). Update BDO Trainer to import this file."
        )

    for required in ("class_name", "spec_name", "config"):
        if required not in bundle:
            raise BundleError(f"missing required field '{required}'")

    if not isinstance(bundle["class_name"], str) or not bundle["class_name"].strip():
        raise BundleError("'class_name' must be a non-empty string")
    if not isinstance(bundle["spec_name"], str) or not bundle["spec_name"].strip():
        raise BundleError("'spec_name' must be a non-empty string")
    if not isinstance(bundle["config"], dict):
        raise BundleError("'config' must be an object")

    return bundle


def write_bundle_to_file(
    path: str | Path,
    class_name: str,
    spec_name: str,
    config: Dict[str, Any],
) -> Path:
    p = Path(path)
    if p.suffix.lower() != BDT_EXTENSION:
        p = p.with_suffix(BDT_EXTENSION)
    p.write_bytes(pack_class_bundle(class_name, spec_name, config))
    logger.info("Exported class bundle: %s -> %s", class_name, p)
    return p


def read_bundle_from_file(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise BundleError(f"file not found: {p}")
    return unpack_class_bundle(p.read_bytes())


# ---------------------------------------------------------------------------
# Combo-extraction helpers used by the import dialog
# ---------------------------------------------------------------------------

COMBO_SECTIONS = ("pve_combos", "pvp_combos", "movement_combos")


def list_combos_in_bundle(bundle: Dict[str, Any]):
    """Yield ``(section, combo_id, combo_dict)`` for every combo in the bundle."""
    cfg = bundle.get("config") or {}
    for section in COMBO_SECTIONS:
        section_data = cfg.get(section) or {}
        if not isinstance(section_data, dict):
            continue
        for combo_id, combo in section_data.items():
            if isinstance(combo, dict):
                yield section, combo_id, combo


def collect_skill_ids_used_by_combo(combo: Dict[str, Any]):
    """Return the set of skill IDs referenced by a combo's steps."""
    out = set()
    for step in combo.get("steps") or []:
        if isinstance(step, dict):
            sid = step.get("skill")
            if isinstance(sid, str) and sid:
                out.add(sid)
    return out


def get_skill(bundle_or_config: Dict[str, Any], skill_id: str):
    """Look up a skill definition in either a bundle or a class-config dict."""
    if "config" in bundle_or_config and isinstance(bundle_or_config["config"], dict):
        cfg = bundle_or_config["config"]
    else:
        cfg = bundle_or_config
    for section in ("skills", "awakening_skills", "rabam_skills", "preawakening_utility"):
        skills = cfg.get(section) or {}
        if isinstance(skills, dict) and skill_id in skills:
            return skills[skill_id]
    return None
