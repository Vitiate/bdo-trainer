"""Skill-icon loader for the chain renderer.

Reads icons from ``~/bdo-skill-icons`` (the community-maintained icon
set) and serves them up as Tk-friendly ``PhotoImage`` instances at a
configurable size, with a transparent background.

The icon repo's ``metadata.json`` maps **lowercase** skill display
names to a ``<class_slug>/<file_stem>`` path (no extension, no
``.webp``). We resolve a skill id by:

1. Pulling its display name from the trainer's class data.
2. Lowercasing and looking up ``by_name`` in the metadata.
3. Locating the actual file under ``icons/<class_slug>/<stem>.<ext>``
   — most files are ``.webp`` but the metadata is extension-agnostic
   so we glob.

Background handling:
  - Many BDO icons ship with a near-uniform dark border / colour
    behind the artwork. We sample the four corners; if they agree
    within a tolerance we treat that as the background colour and
    alpha-key it out across the whole image.
  - Icons that already have transparency are left alone.

PIL is required (already a project dep through pystray / pillow).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger("bdo_trainer")

ICON_REPO = Path.home() / "bdo-skill-icons"
ICON_DIR = ICON_REPO / "icons"
METADATA_PATH = ICON_REPO / "metadata.json"

DEFAULT_SIZE_PX = 48
# Tolerance for the corner-colour-keyed background removal — pixels
# whose RGB is within this Euclidean distance of the sampled BG
# colour become transparent.
_BG_TOLERANCE = 18


class IconLoader:
    """Cached, sized, alpha-keyed Tk PhotoImage loader.

    Construction is cheap; loading happens lazily on first
    ``get(class_slug, skill_name)`` call. Caches by (skill_name, size)
    so repeated lookups are free.
    """

    def __init__(self, *, size_px: int = DEFAULT_SIZE_PX) -> None:
        self._size_px = int(size_px) if size_px else DEFAULT_SIZE_PX
        self._metadata: Optional[Dict[str, str]] = None
        # Cache: (size, class_slug, name_lower) → PhotoImage
        self._cache: Dict[Tuple[int, str, str], object] = {}
        # Negative cache: skill names that don't resolve, so we don't
        # retry the file system lookup on every render frame.
        self._missing: set = set()

    @property
    def size_px(self) -> int:
        return self._size_px

    def set_size(self, size_px: int) -> None:
        if size_px and int(size_px) != self._size_px:
            self._size_px = int(size_px)
            # Resize invalidates the cache.
            self._cache.clear()

    # ------------------------------------------------------------------
    # Public lookup
    # ------------------------------------------------------------------
    def get(
        self,
        class_slug: str,
        skill_name: str,
        *,
        dim_factor: float = 1.0,
    ) -> object:
        """Return a Tk PhotoImage for the skill, or ``None`` if the
        icon repo or the skill isn't available.

        ``dim_factor`` (0.0–1.0) multiplies the alpha channel so the
        chain renderer can fade non-active nodes. The result is
        cached separately per quantised dim level (10 % buckets) to
        keep the cache bounded.
        """
        if not skill_name:
            return None
        # Quantise to 10 % buckets so we don't blow the cache out
        # with floating-point noise across renders.
        dim_q = max(0.05, min(1.0, round(dim_factor * 10) / 10.0))
        name_lower = skill_name.strip().lower()
        key = (
            self._size_px,
            (class_slug or "").lower(),
            name_lower,
            dim_q,
        )
        if key in self._cache:
            return self._cache[key]
        if name_lower in self._missing:
            return None
        path = self._resolve_path(class_slug, name_lower)
        if path is None:
            self._missing.add(name_lower)
            return None
        try:
            photo = self._load_photo(path, dim_factor=dim_q)
        except Exception as exc:
            logger.warning(f"Icon load failed for {skill_name}: {exc}")
            self._missing.add(name_lower)
            return None
        self._cache[key] = photo
        return photo

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------
    def _load_metadata(self) -> Dict[str, str]:
        if self._metadata is not None:
            return self._metadata
        if not METADATA_PATH.exists():
            logger.info(
                f"Icon metadata not found at {METADATA_PATH}; "
                "icons disabled."
            )
            self._metadata = {}
            return self._metadata
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            self._metadata = doc.get("by_name") or {}
            logger.info(
                f"Icon metadata: loaded {len(self._metadata)} entries"
            )
        except Exception as exc:
            logger.warning(f"Could not read icon metadata: {exc}")
            self._metadata = {}
        return self._metadata

    def _resolve_path(
        self, class_slug: str, name_lower: str
    ) -> Optional[Path]:
        meta = self._load_metadata()
        # Metadata key is lowercase display name; values like
        # "maegu/pkow_skill_7333" (no extension).
        ref = meta.get(name_lower)
        if not ref:
            return None
        rel = ref.split("/", 1)
        if len(rel) != 2:
            return None
        cls_in_meta, stem = rel
        # Trust the metadata's class — bdocodex paths don't always
        # match our slug (e.g. nova / odyllita variants).
        for ext in (".webp", ".png", ".jpg", ".jpeg"):
            candidate = ICON_DIR / cls_in_meta / f"{stem}{ext}"
            if candidate.exists():
                return candidate
        return None

    # ------------------------------------------------------------------
    # Image processing
    # ------------------------------------------------------------------
    def _load_photo(self, path: Path, dim_factor: float = 1.0):
        # Lazy import — keeps the trainer working when PIL is missing
        # (icons just don't render; the renderer falls back to text).
        try:
            from PIL import Image, ImageTk  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Pillow not installed") from exc

        img = Image.open(path).convert("RGBA")
        # If the image already has any transparent pixels, skip the
        # corner-key step and keep what's there — nothing to do.
        alpha = img.getchannel("A")
        # Cheap "any non-opaque?" check via extrema.
        a_min, _ = alpha.getextrema()
        if a_min > 240:
            img = self._key_out_corner_bg(img)
        # Resize *after* keying so anti-aliasing doesn't reintroduce
        # the BG colour into edge pixels.
        if img.size != (self._size_px, self._size_px):
            img = img.resize(
                (self._size_px, self._size_px),
                Image.LANCZOS,
            )
        if dim_factor < 0.99:
            img = self._dim_alpha(img, dim_factor)
        return ImageTk.PhotoImage(img)

    @staticmethod
    def _dim_alpha(img, dim_factor: float):
        """Multiply the alpha channel by ``dim_factor`` to fade the
        icon. Leaves the RGB intact so the icon's colour is unchanged
        — only its opacity drops."""
        from PIL import Image  # type: ignore

        r, g, b, a = img.split()
        a = a.point(lambda v: int(v * dim_factor))
        return Image.merge("RGBA", (r, g, b, a))

    def _key_out_corner_bg(self, img):
        """Sample the 4 corners. If they agree within tolerance, treat
        that colour as the background and alpha-key matching pixels."""
        from PIL import Image  # type: ignore

        w, h = img.size
        corners = [
            img.getpixel((0, 0)),
            img.getpixel((w - 1, 0)),
            img.getpixel((0, h - 1)),
            img.getpixel((w - 1, h - 1)),
        ]
        # All corners need to be roughly the same colour for us to
        # treat it as a proper background; otherwise the icon's edge
        # bleeds into a corner and we'd kill artwork.
        ref_r, ref_g, ref_b = corners[0][0], corners[0][1], corners[0][2]
        for r, g, b, _a in corners[1:]:
            if (
                abs(r - ref_r) > _BG_TOLERANCE
                or abs(g - ref_g) > _BG_TOLERANCE
                or abs(b - ref_b) > _BG_TOLERANCE
            ):
                # Corners disagree — leave the image alone.
                return img

        # All four corners agree. Key out the BG.
        pixels = img.load()
        tol = _BG_TOLERANCE
        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                if (
                    abs(r - ref_r) <= tol
                    and abs(g - ref_g) <= tol
                    and abs(b - ref_b) <= tol
                ):
                    pixels[x, y] = (r, g, b, 0)
        return img
