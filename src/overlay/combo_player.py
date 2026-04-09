"""Combo Player — combo playback state machine and step rendering."""

import logging
import math
import re
from typing import Any, Callable, Dict, List, Optional

from src.input_monitor import INPUT_AVAILABLE, InputMonitor
from src.overlay.hold_bar import HoldBar
from src.overlay.renderer import (
    DEFAULT_SUCCESS_COLOR,
    OUTLINE_COLOR,
    OUTLINE_OFFSETS,
    PROTECTION_COLORS,
    TRANSPARENT_COLOR,
    OverlayContext,
    OverlayRenderer,
)
from src.utils.keys import format_key_display

logger = logging.getLogger("bdo_trainer")

# Slide-up animation parameters
_SLIDE_DISTANCE = 40  # pixels to travel
_SLIDE_TICK_MS = 20  # frame interval (~50 fps)

# Fade-out parameters
_FADE_SLIDE_PX = 3  # pixels to move old content up per fade frame
_FADE_LERP = 0.18  # colour lerp factor per frame toward transparent

# Preview pulse parameters (for hold steps)
_PULSE_TICK_MS = 50  # frame interval for pulse (~20 fps, plenty smooth)
_PULSE_SPEED = 0.18  # radians per tick  →  ~1.75 s full cycle
_PULSE_COLOR_LO = "#888888"  # dim grey (trough)
_PULSE_COLOR_HI = "#FFD700"  # gold (peak)


class ComboPlayer:
    """Drives combo playback: step display, input detection, hold steps."""

    def __init__(
        self,
        ctx: OverlayContext,
        renderer: OverlayRenderer,
        input_monitor: InputMonitor,
        hold_bar: HoldBar,
    ) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self.input_monitor = input_monitor
        self.hold_bar = hold_bar

        # Playback state
        self._combo_data: Optional[Dict[str, Any]] = None
        self._combo_name: str = ""
        self._steps: List[Dict[str, Any]] = []
        self._current_step: int = 0
        self._transition_ms: int = 200
        self._is_running: bool = False
        self._loop: bool = True
        self._after_id: Optional[str] = None

        # Idle reset
        self._idle_reset_ms: int = 0
        self._idle_reset_id: Optional[str] = None

        # Key remapping
        self._key_remap: Dict[str, str] = {}

        # External hooks (set by core)
        self.on_combo_finished: Optional[Callable] = None
        self.get_skill_info: Optional[Callable] = None

        # Slide animation state
        self._slide_remaining: int = 0
        self._slide_step: Optional[Dict[str, Any]] = None
        self._slide_after_id: Optional[str] = None

        # Fade-out animation state
        self._fade_after_id: Optional[str] = None
        self._fade_items: List[int] = []
        self._fade_frames_left: int = 0

        # Preview pulse animation state
        self._pulse_after_id: Optional[str] = None
        self._pulse_phase: float = 0.0

    # -----------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------
    def set_key_remap(self, remap: Dict[str, str]) -> None:
        self._key_remap = remap
        if remap:
            logger.info(f"Key remap active: {remap}")

    def set_idle_reset_ms(self, ms: int) -> None:
        self._idle_reset_ms = max(int(ms), 0)
        if self._idle_reset_ms:
            logger.info(f"Idle reset timeout: {self._idle_reset_ms}ms")

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def steps(self) -> List[Dict[str, Any]]:
        return self._steps

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------
    def start(
        self,
        combo_data: Dict[str, Any],
        combo_name: str = "",
        step_delay_ms: Optional[int] = None,
        loop: bool = True,
    ) -> None:
        self.stop()
        self._combo_data = combo_data
        self._combo_name = combo_name or combo_data.get("name", "Combo")
        self._steps = combo_data.get("steps", [])
        self._current_step = 0
        self._loop = loop
        if step_delay_ms is not None:
            self._transition_ms = step_delay_ms
        else:
            self._transition_ms = combo_data.get("combo_window_ms", 200)
        if not self._steps:
            logger.warning(f"Combo '{self._combo_name}' has no steps")
            return
        self._is_running = True
        logger.info(
            f"Starting combo: {self._combo_name} "
            f"({len(self._steps)} steps, {self._transition_ms}ms transition)"
        )
        self._show_intro()

    def stop(self) -> None:
        was_running = self._is_running
        self._is_running = False
        self.hold_bar.cancel()
        self._cancel_pulse()
        self._cancel_slide()
        self._cancel_fade()
        self.input_monitor.clear_target()
        try:
            self._cancel_idle_reset()
            if self._after_id is not None:
                self.ctx.root.after_cancel(self._after_id)
                self._after_id = None
            self.renderer.clear_step()
        except Exception:
            pass
        if was_running:
            logger.info("Combo stopped")

    def pause(self) -> None:
        """Pause input detection without stopping the combo."""
        self.hold_bar.cancel()
        self._cancel_pulse()
        self._cancel_slide()
        self._cancel_fade()
        self.input_monitor.clear_target()
        self._cancel_idle_reset()
        if self._after_id is not None:
            self.ctx.root.after_cancel(self._after_id)
            self._after_id = None

    def resume(self) -> None:
        """Resume the combo from the current step."""
        if self._is_running and self._steps:
            self._show_current_step()

    # -----------------------------------------------------------------
    # Intro screen
    # -----------------------------------------------------------------
    def _show_intro(self) -> None:
        self.renderer.clear_step()
        ctx = self.ctx
        self.renderer.draw_outlined_text(
            ctx.cx,
            ctx.cy - 30,
            self._combo_name,
            ctx.skill_font,
            ctx.skill_color,
        )
        mode_label = "press keys to advance" if INPUT_AVAILABLE else "timed mode"
        self.renderer.draw_outlined_text(
            ctx.cx,
            ctx.cy + 20,
            f"{len(self._steps)} steps \u2014 {mode_label}",
            ctx.note_font,
            ctx.note_color,
        )
        self._after_id = self.ctx.root.after(2000, self._show_current_step)

    # -----------------------------------------------------------------
    # Skill resolution
    # -----------------------------------------------------------------
    def _resolve_skill_name(self, skill_id: str) -> str:
        name = skill_id.replace("_", " ").title()
        if self.get_skill_info:
            info = self.get_skill_info(skill_id)
            if info and "name" in info:
                name = info["name"]
        return name

    def _resolve_protection(self, skill_id: str) -> str:
        if not self.ctx.show_protection or not self.get_skill_info:
            return ""
        info = self.get_skill_info(skill_id)
        if info:
            return info.get("protection", "")
        return ""

    def _resolve_keys(self, step: Dict[str, Any]) -> List[str]:
        keys = step.get("keys", [])
        if keys:
            return keys
        skill_id = step.get("skill", "")
        if skill_id and self.get_skill_info:
            info = self.get_skill_info(skill_id)
            if info:
                return info.get("keys", [])
        return []

    def _resolve_input(self, step: Dict[str, Any], skill_id: str) -> str:
        text = step.get("input", "")
        if text:
            return text
        if skill_id and self.get_skill_info:
            info = self.get_skill_info(skill_id)
            if info:
                return info.get("input", "")
        return ""

    # -----------------------------------------------------------------
    # Next-skill preview helper
    # -----------------------------------------------------------------
    def _build_preview_text(self, step_index: int) -> str:
        """Build the 'next > Skill Name · Input' preview string for a step."""
        step = self._steps[step_index]
        skill_id = step.get("skill", "")
        name = self._resolve_skill_name(skill_id)
        raw_input = self._resolve_input(step, skill_id)
        display_input = self._remap_display_text(raw_input) if raw_input else ""
        if display_input:
            return f"next \u25b8 {name}  \u00b7  {display_input}"
        return f"next \u25b8 {name}"

    def _resolve_next_index(self) -> int:
        """Return the index of the next step, or -1 if there is none."""
        next_idx = self._current_step + 1
        if next_idx >= len(self._steps):
            if self._loop:
                next_idx = 0
            else:
                return -1
        if next_idx == self._current_step:
            return -1
        return next_idx

    # -----------------------------------------------------------------
    # Step display
    # -----------------------------------------------------------------
    def _show_current_step(self) -> None:
        if not self._is_running:
            return
        if self._current_step >= len(self._steps):
            if self._loop:
                self._current_step = 0
            else:
                self.stop()
                if self.on_combo_finished:
                    self.on_combo_finished()
                return
        step = self._steps[self._current_step]
        self._render_step(step)
        self._arm_input(step)

    def _render_step(self, step: Dict[str, Any]) -> None:
        self._cancel_pulse()
        self.renderer.clear_step()
        ctx = self.ctx
        skill_id: str = step.get("skill", "")
        skill_name = self._resolve_skill_name(skill_id)
        protection = self._resolve_protection(skill_id)
        input_text: str = self._resolve_input(step, skill_id)
        input_text = self._remap_display_text(input_text)
        note: str = step.get("note", "")
        total = len(self._steps)
        counter = f"Step {self._current_step + 1} / {total}"
        y = ctx.cy

        # Row 1 — combo name
        self.renderer.draw_outlined_text(
            ctx.cx,
            y - 80,
            self._combo_name,
            ctx.header_font,
            "#888888",
        )
        # Row 2 — skill name
        self.renderer.draw_outlined_text(
            ctx.cx,
            y - 35,
            skill_name,
            ctx.skill_font,
            ctx.skill_color,
        )
        # Protection badge
        if protection:
            prot_color = PROTECTION_COLORS.get(protection, "#888888")
            half_w = ctx.skill_font.measure(skill_name) // 2
            self.renderer.draw_outlined_text(
                ctx.cx + half_w + 35,
                y - 35,
                f"[{protection.upper()}]",
                ctx.note_font,
                prot_color,
            )
        # Row 3 — input keys
        self.renderer.draw_outlined_text(
            ctx.cx,
            y + 10,
            input_text,
            ctx.input_font,
            ctx.input_color,
        )
        # Hold step detection
        is_hold_step = self._resolve_keys(step) == ["hold"]
        hold_bar_offset = 40 if is_hold_step else 0
        # Row 4 — note
        if ctx.show_notes and note:
            self.renderer.draw_outlined_text(
                ctx.cx,
                y + 48 + hold_bar_offset,
                note,
                ctx.note_font,
                ctx.note_color,
            )
        # Row 5 — step counter
        counter_y = (
            (y + 78 + hold_bar_offset)
            if (ctx.show_notes and note)
            else (y + 48 + hold_bar_offset)
        )
        self.renderer.draw_outlined_text(
            ctx.cx,
            counter_y,
            counter,
            ctx.counter_font,
            "#666666",
        )

        # Row 6 — next skill preview (name + keys, brighter / larger)
        next_idx = self._resolve_next_index()
        if next_idx >= 0:
            preview_text = self._build_preview_text(next_idx)
            preview_y = counter_y + 28

            # Detect whether the upcoming step involves holding
            next_step = self._steps[next_idx]
            next_keys = self._resolve_keys(next_step)
            has_hold = (
                "hold" in preview_text.lower()
                or next_keys == ["hold"]
                or "hold_ms" in next_step
            )

            if has_hold:
                self._draw_pulsing_preview(preview_text, preview_y)
            else:
                self.renderer.draw_outlined_text(
                    ctx.cx,
                    preview_y,
                    preview_text,
                    ctx.note_font,
                    "#AAAAAA",
                )

    # -----------------------------------------------------------------
    # Input detection
    # -----------------------------------------------------------------
    def _arm_input(self, step: Dict[str, Any]) -> None:
        raw_keys: List[str] = self._resolve_keys(step)

        # Hold step
        if raw_keys == ["hold"]:
            hold_ms = step.get("hold_ms", 1500)
            self.hold_bar.start(hold_ms, on_complete=self._on_keys_matched)
            # Also arm the next step's keys so pressing them skips the hold
            self._arm_next_step_during_hold()
            return

        alt_keys: List[str] = step.get("alt_keys", [])
        # Fall back to skill definition's keys_alt
        if not alt_keys and self.get_skill_info:
            skill_id = step.get("skill", "")
            if skill_id:
                info = self.get_skill_info(skill_id)
                if info and "keys_alt" in info:
                    alt_keys = info["keys_alt"]

        def _remap_and_filter(keys: List[str]) -> List[str]:
            return [
                self._key_remap.get(k.lower(), k.lower())
                for k in keys
                if k.lower() != "hotbar"
            ]

        primary = _remap_and_filter(raw_keys)
        key_sets: List[List[str]] = []
        if primary:
            key_sets.append(primary)
        if alt_keys:
            alt = _remap_and_filter(alt_keys)
            if alt:
                key_sets.append(alt)

        if not key_sets or not INPUT_AVAILABLE:
            fallback_ms = max(self._transition_ms, 1500)
            self._after_id = self.ctx.root.after(fallback_ms, self._advance)
            return

        # Save for hold bar
        self.hold_bar.last_armed_key_sets = [list(ks) for ks in key_sets]

        self.input_monitor.set_target(
            key_sets,
            on_match=lambda: self.ctx.root.after(0, self._on_keys_matched),
        )

        # Idle reset timer
        self._cancel_idle_reset()
        if self._idle_reset_ms > 0 and self._current_step > 0:
            self._idle_reset_id = self.ctx.root.after(
                self._idle_reset_ms, self._idle_reset
            )

    def _arm_next_step_during_hold(self) -> None:
        """During a hold step, arm the InputMonitor for the *next* step's
        keys so pressing them skips the hold and advances immediately."""
        next_idx = self._current_step + 1
        if next_idx >= len(self._steps):
            if self._loop:
                next_idx = 0
            else:
                return
        if next_idx == self._current_step:
            return

        next_step = self._steps[next_idx]
        next_raw = self._resolve_keys(next_step)
        if not next_raw or next_raw == ["hold"] or next_raw == ["hotbar"]:
            return

        # Resolve alt keys for the next step
        alt_keys: List[str] = next_step.get("alt_keys", [])
        if not alt_keys and self.get_skill_info:
            sid = next_step.get("skill", "")
            if sid:
                info = self.get_skill_info(sid)
                if info and "keys_alt" in info:
                    alt_keys = info["keys_alt"]

        def _remap(keys: List[str]) -> List[str]:
            return [
                self._key_remap.get(k.lower(), k.lower())
                for k in keys
                if k.lower() != "hotbar"
            ]

        primary = _remap(next_raw)
        key_sets: List[List[str]] = []
        if primary:
            key_sets.append(primary)
        if alt_keys:
            alt = _remap(alt_keys)
            if alt:
                key_sets.append(alt)

        if key_sets:
            self.input_monitor.set_target(
                key_sets,
                on_match=lambda: self.ctx.root.after(0, self._on_hold_skip),
            )

    def _on_keys_matched(self) -> None:
        if not self._is_running:
            return
        self._cancel_idle_reset()
        self._cancel_pulse()
        self._cancel_fade()  # clean up any previous fade still running
        self.hold_bar.cancel()  # stop hold bar if still running

        step = self._steps[self._current_step]
        skill_id: str = step.get("skill", "")
        skill_name = self._resolve_skill_name(skill_id)

        canvas = self.ctx.canvas

        # ---- Re-tag old content for fade-out animation ------------------
        canvas.addtag_withtag("step_old", "step")
        canvas.dtag("step_old", "step")
        canvas.addtag_withtag("step_old", "hold_bar")
        canvas.dtag("step_old", "hold_bar")

        # Draw success indicator on old content (fades with it)
        self.renderer.draw_outlined_text(
            self.ctx.cx,
            self.ctx.cy - 35,
            f"\u2713  {skill_name}",
            self.ctx.skill_font,
            DEFAULT_SUCCESS_COLOR,
            tag="step_old",
        )

        # Draw next-skill preview on old content (fades with it)
        # Use the NEXT step index (current + 1) since we haven't
        # incremented _current_step yet.
        upcoming_idx = self._current_step + 1
        if upcoming_idx >= len(self._steps):
            upcoming_idx = 0 if self._loop else -1
        if 0 <= upcoming_idx < len(self._steps) and upcoming_idx != self._current_step:
            preview = self._build_preview_text(upcoming_idx)
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                self.ctx.cy + 15,
                preview,
                self.ctx.note_font,
                "#AAAAAA",
                tag="step_old",
            )

        # ---- Start fade-out animation for old content -------------------
        self._fade_items = list(canvas.find_withtag("step_old"))
        self._fade_frames_left = max(self._transition_ms // _SLIDE_TICK_MS, 6)
        self._fade_after_id = self.ctx.root.after(_SLIDE_TICK_MS, self._fade_out_tick)

        # ---- Prepare and schedule the new step slide-in -----------------
        self.input_monitor.clear_target()
        self._current_step += 1
        slide_delay = max(self._transition_ms // 3, 60)
        self._after_id = self.ctx.root.after(slide_delay, self._slide_in_step)

    def _on_hold_skip(self) -> None:
        """Called when the next step's keys are pressed during a hold step."""
        if not self._is_running or not self.hold_bar.is_active:
            return
        logger.info("Hold skipped — next step keys pressed")
        self.hold_bar.cancel()
        self._on_keys_matched()

    # -----------------------------------------------------------------
    # Fade-out animation for old content
    # -----------------------------------------------------------------
    def _fade_out_tick(self) -> None:
        """One frame of old-content fade + upward slide."""
        if not self._is_running or self._fade_frames_left <= 0:
            self._cleanup_fade()
            return

        self._fade_frames_left -= 1
        canvas = self.ctx.canvas

        # Slide old content upward
        try:
            canvas.move("step_old", 0, -_FADE_SLIDE_PX)
        except Exception:
            pass

        # Lerp every text item's colour toward the transparent background
        for item_id in self._fade_items:
            try:
                if canvas.type(item_id) == "text":
                    current = canvas.itemcget(item_id, "fill")
                    faded = OverlayRenderer.lerp_color(
                        current, TRANSPARENT_COLOR, _FADE_LERP
                    )
                    canvas.itemconfigure(item_id, fill=faded)
            except Exception:
                pass

        if self._fade_frames_left > 0:
            self._fade_after_id = self.ctx.root.after(
                _SLIDE_TICK_MS, self._fade_out_tick
            )
        else:
            self._cleanup_fade()

    def _cleanup_fade(self) -> None:
        """Remove all old-content canvas items and reset state."""
        try:
            self.ctx.canvas.delete("step_old")
        except Exception:
            pass
        self._fade_items = []
        self._fade_after_id = None
        self._fade_frames_left = 0

    def _cancel_fade(self) -> None:
        """Cancel any in-progress fade animation and clean up."""
        if self._fade_after_id is not None:
            try:
                self.ctx.root.after_cancel(self._fade_after_id)
            except Exception:
                pass
            self._fade_after_id = None
        self._cleanup_fade()

    # -----------------------------------------------------------------
    # Preview pulse animation (for hold steps)
    # -----------------------------------------------------------------
    def _draw_pulsing_preview(self, text: str, y: int) -> None:
        """Draw the next-skill preview with outlined text and start a
        colour-pulse animation on the main (non-outline) text item."""
        ctx = self.ctx
        canvas = ctx.canvas

        # Outline copies — tagged "step" so they are cleaned up normally
        for dx, dy in OUTLINE_OFFSETS:
            canvas.create_text(
                ctx.cx + dx,
                y + dy,
                text=text,
                font=ctx.note_font,
                fill=OUTLINE_COLOR,
                anchor="center",
                tags=("step",),
            )

        # Main text — extra tag "preview_pulse" so the timer can find it
        canvas.create_text(
            ctx.cx,
            y,
            text=text,
            font=ctx.note_font,
            fill="#AAAAAA",
            anchor="center",
            tags=("step", "preview_pulse"),
        )

        # Kick off the pulse loop
        self._pulse_phase = 0.0
        self._pulse_after_id = self.ctx.root.after(_PULSE_TICK_MS, self._pulse_tick)

    def _pulse_tick(self) -> None:
        """One frame of the sine-wave colour pulse."""
        if not self._is_running:
            self._pulse_after_id = None
            return

        self._pulse_phase += _PULSE_SPEED
        t = (math.sin(self._pulse_phase) + 1.0) / 2.0  # 0 … 1
        color = OverlayRenderer.lerp_color(_PULSE_COLOR_LO, _PULSE_COLOR_HI, t)

        canvas = self.ctx.canvas
        for item_id in canvas.find_withtag("preview_pulse"):
            try:
                canvas.itemconfigure(item_id, fill=color)
            except Exception:
                pass

        self._pulse_after_id = self.ctx.root.after(_PULSE_TICK_MS, self._pulse_tick)

    def _cancel_pulse(self) -> None:
        """Stop the preview pulse timer."""
        if self._pulse_after_id is not None:
            try:
                self.ctx.root.after_cancel(self._pulse_after_id)
            except Exception:
                pass
            self._pulse_after_id = None

    # -----------------------------------------------------------------
    # Idle reset / advance
    # -----------------------------------------------------------------
    def _cancel_idle_reset(self) -> None:
        if self._idle_reset_id is not None:
            self.ctx.root.after_cancel(self._idle_reset_id)
            self._idle_reset_id = None

    def _idle_reset(self) -> None:
        self._idle_reset_id = None
        if not self._is_running:
            return
        logger.info(
            f"Idle timeout ({self._idle_reset_ms}ms) \u2014 resetting to step 1"
        )
        self.input_monitor.clear_target()
        self._current_step = 0
        self._show_current_step()

    def _advance(self) -> None:
        """Advance to the next step (used by hotbar fallback / non-animated paths)."""
        if not self._is_running:
            return
        self.input_monitor.clear_target()
        self._current_step += 1
        self._slide_in_step()

    # -----------------------------------------------------------------
    # Slide-up animation for new content
    # -----------------------------------------------------------------
    def _slide_in_step(self) -> None:
        """Render the new step off-screen and slide it up into position."""
        if not self._is_running:
            return
        self._cancel_fade()  # clean up any lingering old content

        if self._current_step >= len(self._steps):
            if self._loop:
                self._current_step = 0
            else:
                self.stop()
                if self.on_combo_finished:
                    self.on_combo_finished()
                return

        step = self._steps[self._current_step]
        self._render_step(step)

        # Push all "step" items down, then animate them sliding back up
        self.ctx.canvas.move("step", 0, _SLIDE_DISTANCE)
        self._slide_remaining = _SLIDE_DISTANCE
        self._slide_step = step
        self._slide_after_id = self.ctx.root.after(_SLIDE_TICK_MS, self._slide_tick)

    def _slide_tick(self) -> None:
        """One frame of the slide-up ease-out animation."""
        if not self._is_running or self._slide_remaining <= 0:
            self._slide_after_id = None
            if self._is_running and self._slide_step is not None:
                self._arm_input(self._slide_step)
            self._slide_step = None
            return

        # Ease-out: larger moves at the start, smaller near the end
        move = max(2, int(self._slide_remaining * 0.35))
        if self._slide_remaining - move < 2:
            move = self._slide_remaining  # snap to exact final position
        self.ctx.canvas.move("step", 0, -move)
        self._slide_remaining -= move

        if self._slide_remaining <= 0:
            self._slide_after_id = None
            if self._is_running and self._slide_step is not None:
                self._arm_input(self._slide_step)
            self._slide_step = None
        else:
            self._slide_after_id = self.ctx.root.after(_SLIDE_TICK_MS, self._slide_tick)

    def _cancel_slide(self) -> None:
        """Cancel any in-progress slide animation."""
        if self._slide_after_id is not None:
            self.ctx.root.after_cancel(self._slide_after_id)
            self._slide_after_id = None
        self._slide_remaining = 0
        self._slide_step = None

    # -----------------------------------------------------------------
    # Display-text remapping
    # -----------------------------------------------------------------
    def _remap_display_text(self, input_text: str) -> str:
        if not self._key_remap:
            return input_text
        alternatives = input_text.split(" / ")
        remapped = [self._remap_single_input(alt) for alt in alternatives]
        return " / ".join(remapped)

    def _remap_single_input(self, text: str) -> str:
        match = re.match(r"^(.*?)(\s*\(.*\))$", text)
        if match:
            key_part = match.group(1)
            suffix = match.group(2)
        else:
            key_part = text
            suffix = ""
        tokens = [t.strip() for t in key_part.split("+")]
        remapped = [self._remap_display_token(t) for t in tokens]
        return " + ".join(remapped) + suffix

    def _remap_display_token(self, token: str) -> str:
        canonical = token.lower().strip()
        physical = self._key_remap.get(canonical, canonical)
        if physical == canonical:
            return token
        return format_key_display(physical)
