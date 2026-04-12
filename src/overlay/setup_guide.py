"""Setup Guide — multi-page class/spec setup recommendations."""

import logging
from typing import Any, Dict, Optional

from src.overlay.renderer import OverlayContext, OverlayRenderer

logger = logging.getLogger("bdo_trainer")


class SetupGuide:
    _PAGE_NAMES = ["Core Skill", "Skills to Lock", "Hotbar Setup", "Skill Add-ons"]

    def __init__(self, ctx: OverlayContext, renderer: OverlayRenderer) -> None:
        self.ctx = ctx
        self.renderer = renderer
        self._active: bool = False
        self._data: Optional[Dict[str, Any]] = None
        self._page: int = 0
        self._num_pages: int = 4

    @property
    def is_active(self) -> bool:
        return self._active

    def show(self, guide_data: Dict[str, Any]) -> None:
        if self._active:
            self._data = guide_data
            self._page = 0
            self._render_page()
            return
        self._active = True
        self._data = guide_data
        self._page = 0
        self.renderer.clear("guide")
        self._render_page()
        label = f"{guide_data.get('class', '?')} / {guide_data.get('spec', '?')}"
        logger.info(f"Setup guide shown for {label}")

    def hide(self) -> None:
        was_active = self._active
        self._active = False
        self._data = None
        self.renderer.clear("guide")
        if was_active:
            logger.info("Setup guide hidden")

    def toggle(self, guide_data: Optional[Dict[str, Any]] = None) -> bool:
        if self._active:
            self.hide()
            return False
        if guide_data:
            self.show(guide_data)
            return True
        return False

    def next_page(self) -> None:
        if not self._active:
            return
        self._page = (self._page + 1) % self._num_pages
        self._render_page()

    # ----- page rendering ------------------------------------------------

    def _render_page(self) -> None:
        self.renderer.clear("guide")
        if not self._active or not self._data:
            return
        data = self._data
        ctx = self.ctx
        label = f"{data.get('class', '')} ({data.get('spec', '')})"
        page = self._page
        mid_y = ctx.screen_h // 2

        # Header
        self.renderer.draw_outlined_text(
            ctx.cx,
            mid_y - 210,
            f"SETUP GUIDE  —  {label}",
            ctx.input_font,
            "#FFD700",
            tag="guide",
        )
        self.renderer.draw_outlined_text(
            ctx.cx,
            mid_y - 183,
            "━" * 40,
            ctx.counter_font,
            "#555555",
            tag="guide",
        )

        # Body
        body_y = mid_y - 155
        if page == 0:
            self._render_core(body_y)
        elif page == 1:
            self._render_locked(body_y)
        elif page == 2:
            self._render_hotbar(body_y)
        elif page == 3:
            self._render_addons(body_y)

        # Footer
        dots = ""
        for i in range(self._num_pages):
            dots += "  ●  " if i == page else "  ○  "
        self.renderer.draw_outlined_text(
            ctx.cx,
            mid_y + 210,
            dots,
            ctx.input_font,
            "#FFD700",
            tag="guide",
        )
        page_label = self._PAGE_NAMES[page]
        self.renderer.draw_outlined_text(
            ctx.cx,
            mid_y + 240,
            f"Page {page + 1}/{self._num_pages}:  {page_label}",
            ctx.counter_font,
            "#888888",
            tag="guide",
        )
        self.renderer.draw_outlined_text(
            ctx.cx,
            mid_y + 262,
            "Press F7 for next page   ·   Uncheck Setup Guide in tray to close",
            ctx.counter_font,
            "#666666",
            tag="guide",
        )

    def _section_header(self, y: int, title: str, items, empty_msg: str) -> bool:
        """Draw section title. Returns True if items are empty (draws empty_msg too)."""
        self.renderer.draw_outlined_text(
            self.ctx.cx,
            y,
            title,
            self.ctx.note_font,
            "#AAAAAA",
            tag="guide",
        )
        if not items:
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                y + 50,
                empty_msg,
                self.ctx.note_font,
                self.ctx.note_color,
                tag="guide",
            )
            return True
        return False

    def _render_core(self, y: int) -> None:
        data = self._data or {}
        core = data.get("core_skill", {})
        if self._section_header(
            y, "CORE SKILL RECOMMENDATION", core, "No core skill data available."
        ):
            return
        name = core.get("recommended", "Unknown")
        effect = core.get("effect", "")
        reason = core.get("reason", "")
        self.renderer.draw_outlined_text(
            self.ctx.cx,
            y + 50,
            f"★  {name}",
            self.ctx.skill_font,
            self.ctx.skill_color,
            tag="guide",
        )
        if effect:
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                y + 95,
                effect,
                self.ctx.input_font,
                "#4CAF50",
                tag="guide",
            )
        if reason:
            reason_clean = " ".join(reason.split())
            lines = OverlayRenderer.wrap_text(reason_clean, 70)
            for i, line in enumerate(lines[:5]):
                self.renderer.draw_outlined_text(
                    self.ctx.cx,
                    y + 140 + i * 26,
                    line,
                    self.ctx.note_font,
                    self.ctx.note_color,
                    tag="guide",
                )

    def _render_locked(self, y: int) -> None:
        data = self._data or {}
        locked = data.get("locked_skills", [])
        count = len(locked)
        if self._section_header(
            y, f"SKILLS TO LOCK  ({count})", locked, "No lock recommendations."
        ):
            return
        max_rows = 10
        items = locked[:max_rows]
        row_y = y + 35
        spacing = 32
        for i, item in enumerate(items):
            name = item.get("name", "?") if isinstance(item, dict) else str(item)
            reason = item.get("reason", "") if isinstance(item, dict) else ""
            short = reason[:50] + ("…" if len(reason) > 50 else "")
            line = f"🔒  {name}  —  {short}" if short else f"🔒  {name}"
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                row_y + i * spacing,
                line,
                self.ctx.note_font,
                "#F44336",
                tag="guide",
            )
        if count > max_rows:
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                row_y + max_rows * spacing,
                f"… and {count - max_rows} more",
                self.ctx.counter_font,
                "#888888",
                tag="guide",
            )

    def _render_hotbar(self, y: int) -> None:
        data = self._data or {}
        hotbar = data.get("hotbar_skills", [])
        count = len(hotbar)
        if self._section_header(
            y, f"RECOMMENDED HOTBAR  ({count})", hotbar, "No hotbar recommendations."
        ):
            return
        max_rows = 12
        items = hotbar[:max_rows]
        row_y = y + 35
        spacing = 28
        for i, skill_name in enumerate(items):
            name = skill_name if isinstance(skill_name, str) else str(skill_name)
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                row_y + i * spacing,
                f"{i + 1}.  {name}",
                self.ctx.note_font,
                "#FFD700",
                tag="guide",
            )
        if count > max_rows:
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                row_y + max_rows * spacing,
                f"… and {count - max_rows} more",
                self.ctx.counter_font,
                "#888888",
                tag="guide",
            )

    def _render_addons(self, y: int) -> None:
        data = self._data or {}
        addons = data.get("skill_addons", {})
        pve = addons.get("pve", []) if isinstance(addons, dict) else []
        count = len(pve)
        if self._section_header(
            y, f"SKILL ADD-ONS  —  PVE  ({count})", pve, "No add-on recommendations."
        ):
            return
        max_rows = 6
        items = pve[:max_rows]
        row_y = y + 35
        spacing = 55
        for i, entry in enumerate(items):
            if not isinstance(entry, dict):
                continue
            skill = entry.get("skill", "?")
            a1 = entry.get("addon_1", "")
            a2 = entry.get("addon_2", "")
            self.renderer.draw_outlined_text(
                self.ctx.cx,
                row_y + i * spacing,
                skill,
                self.ctx.note_font,
                self.ctx.skill_color,
                tag="guide",
            )
            parts = []
            if a1:
                parts.append(f"+ {a1}")
            if a2:
                parts.append(f"+ {a2}")
            if parts:
                self.renderer.draw_outlined_text(
                    self.ctx.cx,
                    row_y + i * spacing + 22,
                    "   |   ".join(parts),
                    self.ctx.counter_font,
                    "#4CAF50",
                    tag="guide",
                )
