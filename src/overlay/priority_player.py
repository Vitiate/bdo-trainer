"""Priority Player — cooldown-driven combo display.

Walks the combo's ``priority`` tiers top-to-bottom and shows the
highest-priority skill that is currently off cooldown. When the user
presses the displayed skill's keys the player stamps its cooldown and
immediately re-resolves to the next-highest off-cooldown skill.

Schema reference: ``docs/priority-combos.md``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

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
        self._is_running = True
        self._last_cast.clear()
        self._last_cast_id = None
        self._last_cast_at = 0.0
        self._displayed_skill = None
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
        }

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
        self._resolve_and_render()

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
