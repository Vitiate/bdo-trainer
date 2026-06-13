"""Priority Player — cooldown-driven combo display.

Walks the combo's ``priority`` tiers top-to-bottom and shows the
highest-priority skill that is currently off cooldown. When the user
presses the displayed skill's keys the player stamps its cooldown and
immediately re-resolves to the next-highest off-cooldown skill.

Schema reference: ``docs/priority-combos.md``.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.input_monitor import INPUT_AVAILABLE, InputMonitor
from src.overlay.renderer import (
    PROTECTION_COLORS,
    OverlayContext,
    OverlayRenderer,
)
from src.utils.keys import format_key_display

logger = logging.getLogger("bdo_trainer")

_TICK_MS = 250  # cooldown re-check rate (ms). 250ms is more than smooth
                # enough for a cooldown-driven display and ~2.5× cheaper
                # than the original 100ms tick.
_DEFAULT_BOOST_WINDOW_MS = 5000


class PriorityPlayer:
    """Drives ``mode: priority`` combos."""

    def __init__(
        self,
        ctx: OverlayContext,
        renderer: OverlayRenderer,
        input_monitor: InputMonitor,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self.input_monitor = input_monitor

        # Resolved skill rows. Each entry:
        #   {
        #     "id": str, "name": str, "tier": int, "tier_label": str,
        #     "keys": [str], "keys_alt": [str], "cooldown_ms": int,
        #     "note": str,
        #     "boost_after": str | None,
        #     "boost_window_ms": int,
        #     "boost_to_tier": int,
        #   }
        self._rows: List[Dict[str, Any]] = []

        # Tier metadata, indexed by tier number → label.
        self._tier_labels: List[str] = []

        self._combo_data: Optional[Dict[str, Any]] = None
        self._combo_name: str = ""

        # Runtime state
        self._is_running: bool = False
        self._key_remap: Dict[str, str] = {}
        # skill_id → monotonic timestamp of last cast (cooldown start)
        self._last_cast: Dict[str, float] = {}
        # Most-recent cast in time, to enforce requires_prev/prefers_after.
        self._last_cast_id: Optional[str] = None
        self._last_cast_at: float = 0.0
        self._displayed_skill: Optional[str] = None
        # Cached state of the displayed row, used to skip no-op re-renders.
        self._displayed_eff_tier: Optional[int] = None
        self._tick_after_id: Optional[str] = None

        # ---- Chain-mode state -----------------------------------------
        # Chain config (None when the combo doesn't opt into chain mode).
        # Shape:
        #   {
        #     "max_hard_cc": int,
        #     "window_ms": int,
        #     "idle_reset_ms": int,
        #     "finishers": set[str],
        #     "tag_to_category": dict[str, str],   # cc tag → category name
        #   }
        self._chain_cfg: Optional[Dict[str, Any]] = None
        # Cursor — most recent on-chain cast (skill id).
        self._chain_cursor: Optional[str] = None
        # History of (skill_id, monotonic_ts) for the current chain run.
        self._chain_history: List[Tuple[str, float]] = []
        # Last "off-chain reset" timestamp (used by the renderer to flash
        # a red overlay for ~250 ms).
        self._chain_reset_at: float = 0.0
        # External callbacks the renderer subscribes to.
        # Signature: fn(state_dict). Fires when the chain state changes
        # (advance, reset, idle reset). See _chain_state() for the
        # dict shape.
        self.on_chain_changed: Optional[Callable] = None

        # External hooks (parity with ComboPlayer so the dispatcher can
        # forward the same setters).
        self.on_combo_finished: Optional[Callable] = None
        self.get_skill_info: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_key_remap(self, remap: Dict[str, str]) -> None:
        self._key_remap = remap
        if self._is_running:
            # Keys changed — re-arm every tap against the new physical
            # bindings so accidental presses still register.
            self._arm_all_taps()
            self._resolve_and_render()

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def chain_active(self) -> bool:
        """True when the current combo declared a `chain:` block."""
        return self._chain_cfg is not None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(
        self,
        combo_data: Dict[str, Any],
        combo_name: str = "",
    ) -> None:
        self.stop()
        self._combo_data = combo_data
        self._combo_name = combo_name or combo_data.get("name", "Priority Combo")
        self._build_rows(combo_data)
        if not self._rows:
            logger.warning(
                f"Priority combo '{self._combo_name}' has no resolvable skills"
            )
            return
        # Parse the optional chain block. None means "this is a plain
        # priority combo — keep using the single-skill display".
        self._chain_cfg = self._build_chain_cfg(combo_data.get("chain"))
        if self._chain_cfg is not None:
            logger.info(
                f"Chain mode active for {self._combo_name}: "
                f"max_hard={self._chain_cfg['max_hard_cc']}, "
                f"window={self._chain_cfg['window_ms']}ms, "
                f"idle_reset={self._chain_cfg['idle_reset_ms']}ms"
            )
        self._is_running = True
        self._last_cast.clear()
        self._last_cast_id = None
        self._last_cast_at = 0.0
        self._displayed_skill = None
        self._chain_cursor = None
        self._chain_history = []
        self._chain_reset_at = 0.0
        logger.info(
            f"Starting priority combo: {self._combo_name} "
            f"({len(self._rows)} skills, "
            f"{len(self._tier_labels)} tiers)"
        )
        # Arm one tap per skill in the combo so accidental / out-of-turn
        # casts also start the skill's cooldown — the next resolve will
        # then skip that skill instead of immediately re-displaying it.
        self._arm_all_taps()
        self._resolve_and_render()
        self._start_tick()

    def stop(self) -> None:
        was_running = self._is_running
        self._is_running = False
        self._stop_tick()
        self._disarm_all_taps()
        try:
            self.renderer.clear_step()
        except Exception:
            pass
        if was_running:
            logger.info("Priority combo stopped")

    def pause(self) -> None:
        self._stop_tick()
        self._disarm_all_taps()

    def resume(self) -> None:
        if self._is_running and self._rows:
            self._arm_all_taps()
            self._resolve_and_render()
            self._start_tick()

    # ------------------------------------------------------------------
    # Row construction
    # ------------------------------------------------------------------
    def _build_rows(self, combo_data: Dict[str, Any]) -> None:
        self._rows = []
        self._tier_labels = []
        priority = combo_data.get("priority") or []
        if not isinstance(priority, list):
            return
        for tier_idx, tier_block in enumerate(priority):
            if not isinstance(tier_block, dict):
                continue
            label = str(tier_block.get("tier", f"Tier {tier_idx + 1}"))
            self._tier_labels.append(label)
            for entry in tier_block.get("skills", []) or []:
                row = self._build_row(entry, tier_idx, label)
                if row is not None:
                    self._rows.append(row)

    def _build_row(
        self,
        entry: Any,
        tier_idx: int,
        tier_label: str,
    ) -> Optional[Dict[str, Any]]:
        if isinstance(entry, str):
            entry = {"skill": entry}
        if not isinstance(entry, dict):
            return None
        skill_id = entry.get("skill")
        if not skill_id:
            return None

        info: Dict[str, Any] = {}
        if self.get_skill_info:
            info = self.get_skill_info(skill_id) or {}

        keys = list(info.get("keys") or [])
        keys_alt = list(info.get("keys_alt") or [])
        # Skip hotbar-only entries — without a fixed key combo there's
        # nothing for the trainer to listen for.
        if not keys or all(str(k).lower() == "hotbar" for k in keys):
            logger.debug(
                f"Priority combo: skipping {skill_id} (no fixed key combo)"
            )
            return None

        cooldown_ms = int(info.get("cooldown_ms") or 0)
        boost_to = entry.get("boost_to_tier")
        if boost_to is None:
            boost_to = max(0, tier_idx - 1)

        # Parse PvP damage modifier from the freeform notes blob.
        # BDO ships a per-skill "X% damage in PvP only" line — higher
        # value means the skill keeps more of its tooltip damage in
        # PvP, so it's a useful "is this worth pressing" tiebreaker.
        # Allow YAML overrides: pvp_damage_pct on the skill or on the
        # combo entry trumps the parsed value.
        pvp_damage_pct = info.get("pvp_damage_pct")
        if pvp_damage_pct is None:
            pvp_damage_pct = entry.get("pvp_damage_pct")
        if pvp_damage_pct is None:
            pvp_damage_pct = self._parse_pvp_damage(info.get("notes"))

        return {
            "id": skill_id,
            "name": info.get(
                "name", skill_id.replace("_", " ").title()
            ),
            "tier": tier_idx,
            "tier_label": tier_label,
            "keys": keys,
            "keys_alt": keys_alt,
            "cooldown_ms": cooldown_ms,
            "input": info.get("input", ""),
            "protection": info.get("protection", ""),
            "note": entry.get("note", ""),
            "boost_after": entry.get("boost_after"),
            "boost_window_ms": int(
                entry.get("boost_window_ms", _DEFAULT_BOOST_WINDOW_MS)
            ),
            "boost_to_tier": int(boost_to),
            # Hard gate: this skill is only eligible for the next 'requires_window_ms'
            # after the named skill is cast (e.g. Flow: Emberclaw Sweep needs
            # Emberclaw Slash as the most-recent cast). Skipped when missing.
            "requires_prev": entry.get("requires_prev"),
            "requires_window_ms": int(
                entry.get("requires_window_ms", _DEFAULT_BOOST_WINDOW_MS)
            ),
            # Soft preference: priority is boosted while the named skill was
            # recently cast (e.g. Foxflare Fleche right after Foxflare Ambush
            # skips the linger animation). Falls back to native tier.
            "prefers_after": entry.get("prefers_after"),
            "prefers_window_ms": int(
                entry.get("prefers_window_ms", _DEFAULT_BOOST_WINDOW_MS)
            ),
            "prefers_to_tier": int(
                entry.get("prefers_to_tier", max(0, tier_idx - 1))
            ),
            "pvp_damage_pct": (
                float(pvp_damage_pct) if pvp_damage_pct is not None else None
            ),
            # PvP-effective CC tags. Many BDO skills list a CC that
            # only applies in PvE (bdocodex notes flag these as
            # "(PvE only)"). Two override hooks:
            #   1. cc_pvp on the skill data (preferred — survives
            #      across combos, lives in the class yaml)
            #   2. cc_pvp on the combo entry (per-combo override)
            # If neither is set we parse the notes for inline
            # "(PvE only)" qualifiers and strip the affected tags.
            "cc_tags": tuple(self._resolve_pvp_cc_tags(info, entry)),
            "tags": tuple(info.get("tags") or ()),
        }

    # PvP damage modifier — BDO ships a per-skill "X% damage in PvP
    # only" line in the bdocodex notes. Picks the largest match (some
    # skills list multiple hit groups; the headline figure is what
    # builds use as the "PvP damage" rating).
    _PVP_DMG_RE = re.compile(
        r"([0-9]+(?:\.[0-9]+)?)\s*%\s*damage\s*in\s*PvP",
        re.IGNORECASE,
    )

    # CC potency weight — higher = stronger lock.
    # Grab > KD/stun (1.5 s) > knockback (1.5 s) > float (1.0 s) >
    # bound (0.8 s) > stiffness (0.5 s) > down_smash bonus stays in
    # the smash weight, not here. Tags that aren't CCs (down_attack
    # etc.) score 0 — they're handled by the smash window weight.
    _CC_WEIGHTS: Dict[str, float] = {
        "grab": 1.5,
        "stun": 1.0,
        "knockdown": 1.0,
        "knockback": 0.85,
        "floating": 0.7,
        "bound": 0.55,
        "stiffness": 0.4,
    }
    # Down-/air-smash tag weights — only fire during a smash window
    # but when they fire they boost the score significantly so the
    # right "smash this" skill rises above plain CC reapplications.
    _SMASH_WEIGHTS: Dict[str, float] = {
        "down_smash": 1.0,
        "air_smash": 0.8,
        "down_attack": 0.55,
        "air_attack": 0.45,
    }

    @classmethod
    def _cc_weight(cls, cc_tags: Tuple[str, ...]) -> float:
        if not cc_tags:
            return 0.0
        return max(
            (cls._CC_WEIGHTS.get(str(t).lower(), 0.0) for t in cc_tags),
            default=0.0,
        )

    @classmethod
    def _smash_weight(cls, cc_tags: Tuple[str, ...]) -> float:
        if not cc_tags:
            return 0.0
        return max(
            (cls._SMASH_WEIGHTS.get(str(t).lower(), 0.0) for t in cc_tags),
            default=0.0,
        )

    @classmethod
    def _resolve_pvp_cc_tags(
        cls, info: Dict[str, Any], entry: Dict[str, Any],
    ) -> List[str]:
        """Return the CC tags that *actually fire in PvP*.

        Many BDO skills list a CC in the notes that only applies in
        PvE — e.g. Prime: Bared Claws lists "Stiffness on attack 2
        hits (PvE only)" so its real PvP CC is none. The trainer's
        priority sort and chain budget would otherwise treat the
        skill as a re-CC link that doesn't actually re-CC.

        Resolution order:
          1. ``cc_pvp`` on the combo entry (highest priority).
          2. ``cc_pvp`` on the skill data.
          3. ``cc`` minus tags inline-flagged "(PvE only)" in notes.
          4. ``cc`` as-is (nothing in notes).
        """
        # Explicit override on combo entry.
        entry_override = entry.get("cc_pvp")
        if entry_override is not None:
            return [str(t).lower() for t in (entry_override or [])]
        # Explicit override on skill data.
        skill_override = info.get("cc_pvp")
        if skill_override is not None:
            return [str(t).lower() for t in (skill_override or [])]
        # Note-parse fallback.
        cc_tags = list(info.get("cc") or [])
        if not cc_tags:
            return []
        notes = info.get("notes")
        if not isinstance(notes, str) or not notes:
            return cc_tags
        kept: List[str] = []
        for tag in cc_tags:
            # Look for "<tag>... (PvE only)" within ~80 chars after
            # any occurrence of the tag in the notes. Case-insensitive.
            tag_str = str(tag).lower()
            pve_only = False
            for m in re.finditer(
                rf"\b{re.escape(tag_str)}\b", notes, re.IGNORECASE,
            ):
                window = notes[m.end():m.end() + 80]
                if re.search(
                    r"\(\s*PvE\s+only\s*\)", window, re.IGNORECASE,
                ):
                    pve_only = True
                    break
            if not pve_only:
                kept.append(tag_str)
        return kept

    @classmethod
    def _parse_pvp_damage(cls, notes: Any) -> Optional[float]:
        if not isinstance(notes, str) or not notes:
            return None
        matches = cls._PVP_DMG_RE.findall(notes)
        if not matches:
            return None
        try:
            return max(float(m) for m in matches)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    @staticmethod
    def _as_id_list(value: Any) -> tuple:
        """Normalise a `boost_after` / `prefers_after` / `requires_prev`
        value into a tuple of skill ids. Accepts:
          - ``None`` / empty → ``()``
          - a single string → ``(string,)``
          - a list of strings → ``(*list,)``
        Lists give "any-of" semantics — the gate / boost fires when ANY
        of the named skills was cast. Used to express groups like
        Maegu's spiritforging set (Hazy Path, Foxflare Charge,
        Emberclaw Slash, …) without naming them on every empowered
        row individually.
        """
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,) if value else ()
        if isinstance(value, (list, tuple)):
            return tuple(v for v in value if isinstance(v, str) and v)
        return ()

    def _effective_tier(self, row: Dict[str, Any], now: float) -> int:
        """Return the tier this row should be considered at right now,
        applying any active ``boost_after`` / ``prefers_after`` rule."""
        tier = row["tier"]

        boosters = self._as_id_list(row.get("boost_after"))
        if boosters:
            window_ms = row["boost_window_ms"]
            for booster in boosters:
                last = self._last_cast.get(booster, 0.0)
                if last > 0 and (now - last) * 1000.0 < window_ms:
                    tier = min(tier, int(row["boost_to_tier"]))
                    break

        # prefers_after only fires while the *most-recent* cast was the
        # named skill (or one of them, if a list). Pressing anything
        # else cancels the boost.
        prefers = self._as_id_list(row.get("prefers_after"))
        if (
            prefers
            and self._last_cast_id in prefers
            and (now - self._last_cast_at) * 1000.0 < row["prefers_window_ms"]
        ):
            tier = min(tier, int(row["prefers_to_tier"]))
        return tier

    def _meets_requires(self, row: Dict[str, Any], now: float) -> bool:
        """Hard gate — if requires_prev is set, the row is only eligible
        when the named skill (or one of the named skills) was the
        *most-recent* cast and we're still inside requires_window_ms."""
        reqs = self._as_id_list(row.get("requires_prev"))
        if not reqs:
            return True
        if self._last_cast_id not in reqs:
            return False
        return (now - self._last_cast_at) * 1000.0 < row["requires_window_ms"]

    def _resolve_next(self) -> Optional[Dict[str, Any]]:
        """Pick the highest-priority off-cooldown skill, honouring
        requires_prev gates and boost / prefers_after promotions."""
        if not self._rows:
            return None
        now = time.monotonic()
        candidates: List[tuple] = []
        for idx, row in enumerate(self._rows):
            cd = row["cooldown_ms"]
            last = self._last_cast.get(row["id"], 0.0)
            on_cd = (
                cd > 0
                and last > 0
                and (now - last) * 1000.0 < cd
            )
            if on_cd:
                continue
            if not self._meets_requires(row, now):
                continue
            eff = self._effective_tier(row, now)
            candidates.append((eff, idx, row))
        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][2]

    # ------------------------------------------------------------------
    # Tap arming — one tap per skill so any key press stamps a cooldown
    # ------------------------------------------------------------------
    def _arm_all_taps(self) -> None:
        """Register a tap for every skill in the combo.

        Skills that share an identical canonical key combo are folded
        into a single tap whose callback stamps the highest-priority
        owner — that way a Tier-2 skill sharing keys with a Tier-0 one
        doesn't double-burn both cooldowns on a single press.
        """
        self._disarm_all_taps()
        if not INPUT_AVAILABLE:
            return
        # combo-key signature → list of (tier, idx, skill_id)
        groups: Dict[tuple, List[tuple]] = {}
        for idx, row in enumerate(self._rows):
            for key_set in self._row_key_sets(row):
                signature = tuple(sorted(key_set))
                groups.setdefault(signature, []).append(
                    (row["tier"], idx, row["id"])
                )
        for signature, owners in groups.items():
            owners.sort(key=lambda o: (o[0], o[1]))
            primary_id = owners[0][2]
            tap_name = f"priority_player:{signature!r}"
            self.input_monitor.add_tap(
                tap_name,
                [list(signature)],
                on_match=self._make_trigger(primary_id),
            )

    def _disarm_all_taps(self) -> None:
        # Remove every tap we may have registered. Cheap (no scan).
        if not INPUT_AVAILABLE:
            return
        for row in self._rows:
            for key_set in self._row_key_sets(row):
                signature = tuple(sorted(key_set))
                tap_name = f"priority_player:{signature!r}"
                try:
                    self.input_monitor.remove_tap(tap_name)
                except Exception:
                    pass

    def _row_key_sets(self, row: Dict[str, Any]) -> List[List[str]]:
        """Return the row's primary + alt key combos after key remap,
        skipping anything empty or hotbar-only."""
        sets: List[List[str]] = []
        primary = self._remap_keys(row["keys"])
        if primary:
            sets.append(primary)
        if row["keys_alt"]:
            alt = self._remap_keys(row["keys_alt"])
            if alt:
                sets.append(alt)
        return sets

    def _remap_keys(self, keys: List[str]) -> List[str]:
        return [
            self._key_remap.get(str(k).lower(), str(k).lower())
            for k in keys
            if str(k).lower() != "hotbar"
        ]

    def _make_trigger(self, skill_id: str) -> Callable[[], None]:
        def _fire() -> None:
            self.ctx.root.after(0, lambda: self._on_pressed(skill_id))
        return _fire

    def _on_pressed(self, skill_id: str) -> None:
        if not self._is_running:
            return
        now = time.monotonic()
        self._last_cast[skill_id] = now
        self._last_cast_id = skill_id
        self._last_cast_at = now
        # Chain bookkeeping (no-op when chain mode is off).
        self._chain_on_press(skill_id, now)
        self._resolve_and_render()

    # ------------------------------------------------------------------
    # Chain mode
    # ------------------------------------------------------------------
    # Default BDO CC categories. A combo's `chain.cc_categories` block,
    # if present, replaces this verbatim.
    _DEFAULT_CC_CATEGORIES: Dict[str, List[str]] = {
        "grab": ["grab"],
        "hard": ["stun", "knockdown", "knockback", "bound", "floating"],
        "soft": ["stiffness"],
        "smash": ["down_attack", "down_smash", "air_attack", "air_smash"],
    }
    # How long each CC tag locks the target (seconds). Used by the
    # ChainRenderer to drain the per-node ring. A combo can override
    # any of these via ``chain.cc_durations:`` — keys are cc tags
    # (not category names).
    _DEFAULT_CC_DURATIONS_S: Dict[str, float] = {
        "grab": 2.0,
        "stun": 1.5,
        "knockdown": 1.5,
        "knockback": 1.0,
        "bound": 1.2,
        "floating": 1.0,
        "stiffness": 0.8,
        # Smash modifiers don't lock the target — they're damage
        # multipliers — but list them so a missing-key lookup
        # doesn't fall through to the default.
        "down_attack": 0.0,
        "down_smash": 0.0,
        "air_attack": 0.0,
        "air_smash": 0.0,
    }

    def _build_chain_cfg(
        self, raw: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Parse a combo's `chain:` block, or return None if absent."""
        if not isinstance(raw, dict):
            return None
        cats = raw.get("cc_categories")
        if not isinstance(cats, dict) or not cats:
            cats = self._DEFAULT_CC_CATEGORIES
        # Build a flat reverse lookup: cc-tag → category name.
        tag_to_cat: Dict[str, str] = {}
        for cat_name, tags in cats.items():
            if not isinstance(tags, list):
                continue
            for tag in tags:
                tag_to_cat[str(tag).lower()] = str(cat_name).lower()
        finishers = raw.get("finishers") or []
        finisher_set: set = set()
        if isinstance(finishers, list):
            for f in finishers:
                if isinstance(f, str) and f:
                    finisher_set.add(f)
        # CC tag durations — start with defaults, layer combo
        # overrides on top. Keys are cc tags (e.g. "knockdown"); the
        # value is duration in seconds.
        durations: Dict[str, float] = dict(self._DEFAULT_CC_DURATIONS_S)
        raw_durations = raw.get("cc_durations") or {}
        if isinstance(raw_durations, dict):
            for tag, secs in raw_durations.items():
                try:
                    durations[str(tag).lower()] = float(secs)
                except (TypeError, ValueError):
                    pass
        return {
            "max_hard_cc": int(raw.get("max_hard_cc", 4)),
            "window_ms": int(raw.get("window_ms", 6000)),
            "idle_reset_ms": int(raw.get("idle_reset_ms", 3000)),
            "finishers": finisher_set,
            "tag_to_category": tag_to_cat,
            "cc_durations": durations,
        }

    def _row_for(self, skill_id: str) -> Optional[Dict[str, Any]]:
        for r in self._rows:
            if r["id"] == skill_id:
                return r
        return None

    def _row_categories(self, row: Dict[str, Any]) -> List[str]:
        """Return the chain categories triggered by this row's CC tags
        (deduplicated, ordered)."""
        if self._chain_cfg is None:
            return []
        info: Dict[str, Any] = {}
        if self.get_skill_info:
            info = self.get_skill_info(row["id"]) or {}
        tags = info.get("cc") or []
        seen: List[str] = []
        for t in tags:
            cat = self._chain_cfg["tag_to_category"].get(str(t).lower())
            if cat and cat not in seen:
                seen.append(cat)
        return seen

    # Skill role for chain rendering. The chain engine doesn't actually
    # need to know "this is a buff" vs "this is burst" to compute
    # frontier eligibility — that's pure CC-rule plus cooldown — but
    # the renderer wants the role to (a) hide reposition skills from
    # the frontier when they don't apply CC, (b) keep pre-buff skills
    # always-eligible regardless of chain state, and (c) reorder
    # burst skills above CC continuations when the cursor's lock is
    # a knockdown (smash-window).
    _CC_TAGS_BINDING: set = {
        "stun", "stiffness", "knockdown", "knockback",
        "floating", "bound", "grab",
    }
    _CC_TAGS_SMASH: set = {
        "down_attack", "down_smash", "air_attack", "air_smash",
    }
    _DAMAGE_BURST_TIERS: set = {"high", "very_high"}

    def classify_role(self, row: Dict[str, Any]) -> str:
        """Bucket each skill row into one of:
            "catch"      — applies a binding CC (KD / float / bound /
                           stiffen / etc.). Default chain participant.
            "burst"      — high-damage skill with no binding CC, but
                           may have smash modifiers. Eligible while
                           a target is locked; reordered above CC
                           continuations during a knockdown window.
            "pre_buff"   — buff/utility cast outside the chain
                           (e.g. Foxspirit Conduit, Charmed). Always
                           eligible; doesn't gate chain advance.
            "reposition" — movement / iframe with no damage and no
                           CC. Hidden from chain frontier unless it
                           applies CC.
            "filler"     — anything else (low / medium damage, no
                           CC). Hidden from chain frontier.
        """
        info: Dict[str, Any] = {}
        if self.get_skill_info:
            info = self.get_skill_info(row["id"]) or {}
        tags = {str(t).lower() for t in (info.get("cc") or [])}
        damage = str(info.get("damage") or "").lower()
        protection = str(info.get("protection") or "").lower()

        # Has a binding CC? It's a chain participant.
        if tags & self._CC_TAGS_BINDING:
            return "catch"
        # Damage skill with no binding CC → burst (smash modifiers
        # tag along, but they don't open a chain).
        if damage in self._DAMAGE_BURST_TIERS:
            return "burst"
        # Has smash modifiers but no binding CC and no `damage:`
        # field — common for follow-up burst skills (Flow:
        # Foxflare Encore, Flow: Emberclaw Sweep, etc.) where the
        # YAML didn't populate `damage:`. Smash tags are a strong
        # signal that the skill belongs in a chain's burst window.
        if tags & self._CC_TAGS_SMASH:
            return "burst"
        # Buffs/utilities — heuristic: protection iframe + no
        # damage, OR an AP/buff hint in notes. We can't perfectly
        # detect a buff from the data we have, so the simpler
        # rule is "skills explicitly marked pre-awakening / utility
        # in name", but those mostly self-classify already. For
        # awakening we keep this conservative: a skill with no
        # damage, no CC, and an iframe or no-protection (i.e. not
        # SA/FG which suggest a damaging skill) is a buff/utility.
        if not damage and protection in ("iframe", "none", ""):
            return "pre_buff"
        # No CC, no notable damage, has a protected stance →
        # reposition / utility.
        if not damage:
            return "reposition"
        return "filler"

    def _row_smash_tags(self, row: Dict[str, Any]) -> set:
        info: Dict[str, Any] = {}
        if self.get_skill_info:
            info = self.get_skill_info(row["id"]) or {}
        tags = {str(t).lower() for t in (info.get("cc") or [])}
        return tags & self._CC_TAGS_SMASH

    def _last_history_was_knockdown(self, now: float) -> bool:
        """True iff the most recent chain history entry was a skill
        whose CC included a hard-CC keeping the target on the ground
        (knockdown / floating / bound). Used to prefer smash-tagged
        burst skills."""
        if not self._chain_history:
            return False
        sid, _ts = self._chain_history[-1]
        row = self._row_for(sid)
        if row is None:
            return False
        info: Dict[str, Any] = {}
        if self.get_skill_info:
            info = self.get_skill_info(sid) or {}
        tags = {str(t).lower() for t in (info.get("cc") or [])}
        return bool(tags & {"knockdown", "floating", "bound"})

    def _row_lock_duration_s(self, row: Dict[str, Any]) -> float:
        """Longest CC lock this skill applies, in seconds. Used by
        the renderer to size the per-node duration ring. Returns 0
        for skills with no binding CC (chain renderer skips drawing
        a ring in that case)."""
        if self._chain_cfg is None:
            return 0.0
        info: Dict[str, Any] = {}
        if self.get_skill_info:
            info = self.get_skill_info(row["id"]) or {}
        tags = info.get("cc") or []
        durations = self._chain_cfg["cc_durations"]
        longest = 0.0
        for t in tags:
            d = float(durations.get(str(t).lower(), 0.0))
            if d > longest:
                longest = d
        return longest

    def _chain_history_within_window(
        self, now: float
    ) -> List[Tuple[str, float]]:
        """Slice of chain history that's still within the DR window."""
        if self._chain_cfg is None:
            return []
        win = self._chain_cfg["window_ms"] / 1000.0
        return [(sid, ts) for sid, ts in self._chain_history if now - ts < win]

    def _hard_count_in_window(self, now: float) -> int:
        if self._chain_cfg is None:
            return 0
        count = 0
        for sid, _ts in self._chain_history_within_window(now):
            row = self._row_for(sid)
            if row is None:
                continue
            if "hard" in self._row_categories(row):
                count += 1
        return count

    def _categories_used_in_window(self, now: float) -> set:
        """Set of (skill_id, category) the chain has already spent in
        the current window. Used to block re-applying the same CC by
        the same skill (BDO ignores re-CCs by the same skill on a
        target during DR)."""
        used: set = set()
        for sid, _ts in self._chain_history_within_window(now):
            row = self._row_for(sid)
            if row is None:
                continue
            for cat in self._row_categories(row):
                used.add((sid, cat))
        return used

    def _is_chain_legal(self, row: Dict[str, Any], now: float) -> bool:
        """Would casting *row* now be a legal chain advance?

        Decided by role + CC rules:
        - **pre_buff** — always legal (buffs cast independently of
          the chain; don't consume the DR budget).
        - **catch** — CC rules apply (hard-CC cap, no repeat-by-
          same-skill within the window).
        - **burst** — only legal while the cursor still holds the
          target. The chain engine doesn't know the lock duration
          here, so we approximate "target is held" as "history is
          non-empty AND most-recent cast was within the lock for
          its CC tag" via lock_seconds.
        - **reposition** — only legal if it applies a CC (in which
          case classify_role would have returned "catch"). With no
          CC, never in the frontier.
        - **filler** — same as reposition: hidden when in chain
          mode unless it has CC.
        """
        if self._chain_cfg is None:
            return True
        role = self.classify_role(row)
        if role == "pre_buff":
            # Buffs / utilities are always eligible.
            return True
        if role in ("reposition", "filler"):
            return False
        # Catch / re-CC: standard chain rules.
        if role == "catch":
            cats = self._row_categories(row)
            used = self._categories_used_in_window(now)
            for cat in cats:
                if (row["id"], cat) in used:
                    return False
            if "hard" in cats:
                if (
                    self._hard_count_in_window(now)
                    >= self._chain_cfg["max_hard_cc"]
                ):
                    return False
            return True
        # Burst: needs a target locked (some history within window
        # AND the most-recent cast's lock hasn't expired yet).
        if role == "burst":
            if not self._chain_history:
                return False
            last_sid, last_ts = self._chain_history[-1]
            last_row = self._row_for(last_sid)
            if last_row is None:
                return False
            lock_s = self._row_lock_duration_s(last_row)
            if lock_s <= 0:
                return False
            return (now - last_ts) < lock_s
        return True

    def _chain_idle_expired(self, now: float) -> bool:
        if self._chain_cfg is None or not self._chain_history:
            return False
        last_ts = self._chain_history[-1][1]
        return (now - last_ts) * 1000.0 > self._chain_cfg["idle_reset_ms"]

    def _chain_reset(self, *, reason: str) -> None:
        if self._chain_cursor is None and not self._chain_history:
            return
        self._chain_cursor = None
        self._chain_history = []
        if reason == "off_chain":
            self._chain_reset_at = time.monotonic()
        logger.debug(f"Chain reset ({reason})")
        self._fire_chain_changed()

    def _chain_on_press(self, skill_id: str, now: float) -> None:
        if self._chain_cfg is None:
            return
        # Idle reset before processing the press.
        if self._chain_idle_expired(now):
            self._chain_reset(reason="idle")
        # Non-priority skills don't participate.
        row = self._row_for(skill_id)
        if row is None:
            return
        # Finisher always closes the chain cleanly (no reset flash).
        if skill_id in self._chain_cfg["finishers"]:
            self._chain_cursor = skill_id
            self._chain_history.append((skill_id, now))
            logger.debug(f"Chain finisher: {skill_id}")
            self._fire_chain_changed()
            self._chain_reset(reason="finisher")
            return
        # Legal advance?
        if self._is_chain_legal(row, now):
            self._chain_cursor = skill_id
            self._chain_history.append((skill_id, now))
            logger.debug(f"Chain advance: {skill_id}")
            self._fire_chain_changed()
        else:
            # Off-chain — flash + reset.
            self._chain_reset(reason="off_chain")

    def chain_state(self) -> Dict[str, Any]:
        """Snapshot of the current chain state for the renderer."""
        now = time.monotonic()
        if self._chain_cfg is None:
            return {"active": False}
        # Compute frontier — every priority row that:
        #   - is off cooldown,
        #   - meets requires_prev / boost_after gates (existing logic),
        #   - is chain-legal.
        frontier: List[Dict[str, Any]] = []
        for row in self._rows:
            cd = row["cooldown_ms"]
            last = self._last_cast.get(row["id"], 0.0)
            on_cd = (
                cd > 0 and last > 0 and (now - last) * 1000.0 < cd
            )
            if on_cd:
                continue
            if not self._meets_requires(row, now):
                continue
            if not self._is_chain_legal(row, now):
                continue
            frontier.append(row)
        # Class / spec / tier labels travel with the state so the
        # renderer can resolve icon paths and label tier columns
        # without poking back into the player.
        cls = ""
        spec = ""
        if isinstance(self._combo_data, dict):
            cls = str(self._combo_data.get("class") or "")
            spec = str(self._combo_data.get("spec") or "")
        # Build a lock-duration map per skill id so the renderer can
        # draw the drain ring without re-walking get_skill_info.
        lock_seconds: Dict[str, float] = {}
        roles: Dict[str, str] = {}
        for row in self._rows:
            secs = self._row_lock_duration_s(row)
            if secs > 0:
                lock_seconds[row["id"]] = secs
            roles[row["id"]] = self.classify_role(row)

        # Reorder frontier so the highest-impact eligible skill
        # floats to the top. Order is:
        #
        #   bucket 0 — burst skills during a smash window
        #              (knockdown / float / bound landed recently)
        #   bucket 1 — catch / re-CC skills
        #   bucket 2 — burst skills outside a smash window
        #   bucket 3 — pre-buffs (always last)
        #
        # Within a bucket we sort by a *score* that combines:
        #   • CC potency  (grab > stun/kd > float > stiffen > none)
        #   • PvP damage modifier  (parsed from skill notes; 0 if N/A)
        #   • smash-tag weight when in a smash window
        # higher score → higher position. tier acts as a tie-break so
        # the YAML's authored ordering still matters when two skills
        # are otherwise equivalent.
        smash_window = self._last_history_was_knockdown(now)

        def _bucket(role: str) -> int:
            if role == "pre_buff":
                return 3
            if role == "burst":
                return 0 if smash_window else 2
            return 1  # catch / re-CC / filler / reposition

        def _score(row: Dict[str, Any]) -> float:
            cc_w = self._cc_weight(row.get("cc_tags") or ())
            dmg = float(row.get("pvp_damage_pct") or 0.0)
            smash = (
                self._smash_weight(row.get("cc_tags") or ())
                if smash_window else 0.0
            )
            # Tunable mix. CC weight dominates because hitting the
            # right CC is what unlocks the chain at all; damage
            # tiebreaks within a CC tier; smash bonus only fires
            # during a smash window.
            return cc_w * 100.0 + smash * 60.0 + dmg

        def _frontier_sort_key(row: Dict[str, Any]):
            sid = row["id"]
            role = roles.get(sid, "filler")
            tier = int(row.get("tier", 0))
            # Negative score so higher score sorts first under
            # ascending tuple sort.
            return (_bucket(role), -_score(row), tier)

        frontier_sorted = sorted(frontier, key=_frontier_sort_key)
        return {
            "active": True,
            "class": cls,
            "spec": spec,
            "class_slug": cls.lower().replace(" ", "_"),
            "tier_labels": list(self._tier_labels),
            "cursor": self._chain_cursor,
            "history": list(self._chain_history),
            "lock_seconds": lock_seconds,
            "roles": roles,
            "smash_window": smash_window,
            "frontier_ids": [r["id"] for r in frontier_sorted],
            "rows": list(self._rows),
            "reset_flash_at": self._chain_reset_at,
            "idle_reset_ms": self._chain_cfg["idle_reset_ms"],
            "max_hard_cc": self._chain_cfg["max_hard_cc"],
            "hard_count": self._hard_count_in_window(now),
        }

    def _fire_chain_changed(self) -> None:
        if self.on_chain_changed is None:
            return
        try:
            self.on_chain_changed(self.chain_state())
        except Exception:
            logger.exception("on_chain_changed callback failed")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _resolve_and_render(self) -> None:
        if not self._is_running:
            return
        row = self._resolve_next()
        self._displayed_skill = row["id"] if row else None
        self._displayed_eff_tier = (
            self._effective_tier(row, time.monotonic()) if row else None
        )
        self._render(row)

    def _render(self, row: Optional[Dict[str, Any]]) -> None:
        renderer = self.renderer
        ctx = self.ctx
        renderer.clear_step()

        # In chain mode the dedicated ChainRenderer drives the display
        # via on_chain_changed — the single-skill view would overlap
        # the flowchart, so we skip drawing here.
        if self._chain_cfg is not None:
            return

        if row is None:
            renderer.draw_outlined_text(
                ctx.cx, ctx.cy - 30,
                self._combo_name, ctx.skill_font, ctx.skill_color,
            )
            renderer.draw_outlined_text(
                ctx.cx, ctx.cy + 20,
                "all skills on cooldown…",
                ctx.note_font, "#888888",
            )
            return

        y = ctx.cy

        # Combo name
        renderer.draw_outlined_text(
            ctx.cx, y - 80,
            self._combo_name, ctx.header_font, "#888888",
        )

        # Tier label as a small pill above the skill name
        tier_text = f"Tier {row['tier'] + 1} — {row['tier_label']}"
        eff = self._effective_tier(row, time.monotonic())
        if eff != row["tier"]:
            tier_text += "  ↑ boosted"
        renderer.draw_outlined_text(
            ctx.cx, y - 55,
            tier_text, ctx.counter_font, "#FFD700",
        )

        # Skill name + protection badge
        renderer.draw_outlined_text(
            ctx.cx, y - 25,
            row["name"], ctx.skill_font, ctx.skill_color,
        )
        if row["protection"] and ctx.show_protection:
            badge_color = PROTECTION_COLORS.get(row["protection"], "#888888")
            half_w = ctx.skill_font.measure(row["name"]) // 2
            renderer.draw_outlined_text(
                ctx.cx + half_w + 35, y - 25,
                f"[{row['protection'].upper()}]",
                ctx.note_font, badge_color,
            )

        # Input keys — render the canonical key chord (with the user's
        # remap applied) rather than the skill's free-text `input:`
        # field. Many skill `input:` strings encode the BDOCodex tooltip
        # verbatim ("E E after other skills…") which double-prints the
        # key when shown under a skill name. The chord is always shorter
        # and unambiguous.
        input_text = self._format_keys(row["keys"])
        if not input_text:
            input_text = row["input"] or ""
        if row["keys_alt"]:
            alt_text = self._format_keys(row["keys_alt"])
            if alt_text and alt_text != input_text:
                input_text = f"{input_text}  /  {alt_text}"
        renderer.draw_outlined_text(
            ctx.cx, y + 20,
            input_text, ctx.input_font, ctx.input_color,
        )

        # Per-skill note
        if ctx.show_notes and row["note"]:
            renderer.draw_outlined_text(
                ctx.cx, y + 58,
                row["note"], ctx.note_font, ctx.note_color,
            )

    def _format_keys(self, keys: List[str]) -> str:
        parts: List[str] = []
        for k in keys:
            canonical = str(k).lower()
            if canonical == "hotbar":
                return "Hotbar"
            physical = self._key_remap.get(canonical, canonical)
            parts.append(format_key_display(physical))
        return " + ".join(parts)

    # ------------------------------------------------------------------
    # Tick — re-resolve when a cooldown expires above the current pick
    # ------------------------------------------------------------------
    def _start_tick(self) -> None:
        if self._tick_after_id is not None:
            return
        self._tick_after_id = self.ctx.root.after(_TICK_MS, self._tick)

    def _stop_tick(self) -> None:
        if self._tick_after_id is not None:
            try:
                self.ctx.root.after_cancel(self._tick_after_id)
            except Exception:
                pass
            self._tick_after_id = None

    def _tick(self) -> None:
        if not self._is_running:
            self._tick_after_id = None
            return
        # Chain idle reset — fires even without a press, so the
        # cursor goes idle once the user has been quiet long enough.
        if self._chain_cfg is not None:
            now = time.monotonic()
            if self._chain_idle_expired(now):
                self._chain_reset(reason="idle")
            else:
                # Still emit a state tick so the renderer can refresh
                # cooldown rings and frontier composition.
                self._fire_chain_changed()
        new_row = self._resolve_next()
        new_id = new_row["id"] if new_row else None
        new_eff = (
            self._effective_tier(new_row, time.monotonic())
            if new_row is not None
            else None
        )
        if new_id != self._displayed_skill or new_eff != self._displayed_eff_tier:
            self._displayed_skill = new_id
            self._displayed_eff_tier = new_eff
            self._render(new_row)
        self._tick_after_id = self.ctx.root.after(_TICK_MS, self._tick)
