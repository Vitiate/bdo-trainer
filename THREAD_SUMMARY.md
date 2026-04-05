# BDO Trainer — Thread Handoff Summary

## Completed Task — Overlay Modularization ✅

### Refactor: 1,643-line monolith → 8 focused modules

The monolithic `src/overlay.py` (1,643 lines, 2 classes — one being a 1,340-line god class) was decomposed into a clean package with single-responsibility modules.

**New structure:**

| File | Class | Lines | Responsibility |
|------|-------|-------|----------------|
| `src/input_monitor.py` | `InputMonitor` | 217 | Keyboard+mouse state tracking via pynput |
| `src/platform.py` | — | 69 | Click-through window helpers, platform font detection |
| `src/overlay/__init__.py` | — | 11 | Re-exports `ComboOverlay` + `INPUT_AVAILABLE` |
| `src/overlay/renderer.py` | `OverlayContext`, `OverlayRenderer` | 229 | Shared mutable state + drawing primitives + colour utilities |
| `src/overlay/core.py` | `ComboOverlay` | 196 | Thin coordinator — creates Tk window, wires components, delegates API |
| `src/overlay/combo_player.py` | `ComboPlayer` | 414 | Playback state machine, step rendering, input arming, key remapping |
| `src/overlay/hold_bar.py` | `HoldBar` | 144 | Hold-step progress bar (animated fill, glow, spark, timer) |
| `src/overlay/setup_guide.py` | `SetupGuide` | 226 | 4-page setup recommendation overlay |
| `src/overlay/reposition.py` | `RepositionHandler` | 135 | Drag-to-move mode + position persistence |

**Architecture pattern — composition via shared context:**
- `OverlayContext` holds mutable shared state (root, canvas, cx/cy anchor, fonts, display settings)
- `OverlayRenderer` provides drawing primitives (`draw_outlined_text`, `clear`, colour utilities)
- Each component receives `ctx` + `renderer` in its constructor
- `ComboOverlay` in `core.py` is a ~196-line coordinator that delegates every public API call

**Import compatibility preserved:**
- `from src.overlay import ComboOverlay` still works — `__init__.py` re-exports from `core.py`
- `main.py` required zero import changes

---

## Completed Task — YAML Restructuring ✅

### Unified `skills:` section + simplified combo steps

All class config YAML files were restructured to eliminate duplication between skill definitions and combo steps.

**Changes to all 3 Dark Knight YAML files** (awakening, succession, updated succession):

1. **Merged skill sections** — `awakening_skills:`, `rabam_skills:`, and `preawakening_utility:` replaced with a single `skills:` section. All skill properties preserved (name, input, keys, keys_alt, protection, cc, damage, cooldown_ms, description, flows_into, core_effect, notes, level).

2. **Added missing flow/utility skills** — Skills referenced in combos but never defined are now in `skills:`:
   - **Awakening**: `flow_bombardment`, `flow_root_of_catastrophe`, `root_of_catastrophe`, `furia_di_vedir`, `grip_of_grudge`, `dark_nebula`, `spirit_blaze`, `shadow_bullet`, `obsidian_ashes`, `smoky_haze`
   - **Succession**: `flow_vedir_strike`, `flow_cultivation`
   - **Updated Succession**: `flow_vedir_strike`, `flow_cultivation`, plus various base skill references needed by combos

3. **Simplified combo steps** — Removed `input:` and `keys:` (and `alt_keys:`) from every combo step. Steps now only contain:
   - `skill:` — references the pre-defined skill in `skills:`
   - `note:` — optional context
   - `hold_ms:` — only for hold-continuation steps

4. **Replaced updated succession file** — `config/updated_dark_knight_succession.yaml` was moved to `config/classes/dark_knight_succession.yaml`, replacing the old version. The stale file in `config/` was removed.

**Code changes to support the new structure:**

- `src/combo_loader.py` — `SKILL_SECTIONS` updated to `["skills", "awakening_skills", "rabam_skills", "preawakening_utility"]` (new name first, old names kept for backward compat with other class files)
- `src/overlay/combo_player.py` — `_resolve_keys(step)` and `_resolve_input(step, skill_id)` methods look up `keys`/`input` from the skill definition when not present in the combo step. `alt_keys` already fell back to the skill definition's `keys_alt`.

**Before (combo step):**
```yaml
- skill: "shattering_darkness"
  input: "SHIFT + LMB"
  keys: ["shift", "lmb"]
  note: "Main opener"
```

**After (combo step):**
```yaml
- skill: "shattering_darkness"
  note: "Main opener"
```

The `input` and `keys` are resolved at runtime from the skill definition in `skills:`.

---

## Completed Task — macOS Support ✅

### Changes for cross-platform testing

The app was Windows-only. Changes were made so it can launch and be tested on macOS (full game integration is Windows-only by nature, but the UI, configs, and overlay render on macOS).

**New file:**
- `run.sh` — macOS/Linux equivalent of `run.bat`. Finds python3, creates venv, installs deps, prints Accessibility permission notes, runs `main.py`. No auto-sudo.

**Code changes:**
- `main.py` — `keyboard` library import now catches all exceptions (not just `ImportError`), since on macOS it can throw `OSError` without root/Accessibility permissions.
- `src/platform.py` — `default_font_family()` returns platform-appropriate fonts:
  - macOS: `"Helvetica Neue"`
  - Windows: `"Segoe UI"`
  - Linux: `"DejaVu Sans"`

**Already cross-platform (no changes needed):**
- `_make_click_through` / `_remove_click_through` — guarded with `sys.platform != "win32"`
- `-transparentcolor` vs `-alpha` — platform branch in overlay init (macOS gets `-alpha 0.90`)
- `_ensure_admin()` — returns early on non-Windows
- `pystray` — works on macOS via AppKit backend
- `pynput` — works on macOS with Accessibility permissions
- `arial.ttf` in `tray.py` — already has `ImageFont.load_default()` fallback

**Known macOS limitations:**
- Overlay uses semi-transparent black background (no `transparentcolor` equivalent in macOS tkinter)
- Click-through does not work — overlay captures mouse events
- `keyboard` global hotkeys (F5–F8) need Accessibility permissions or root
- `pynput` input monitoring needs Accessibility permissions

---

## Completed Task — Setup Guide Overlay ✅

### Setup Guide Feature — IMPLEMENTED & BUG-FIXED

Added a toggleable **Setup Guide** overlay that shows class/spec recommendations (locked skills, hotbar setup, core skill, skill add-ons) as manually-paged screens over the game.

**Files modified:**
- `src/combo_loader.py` — Added `get_locked_skills()`, `get_hotbar_skills()`, `get_core_skill()`, `get_skill_addons()`, `get_setup_guide()` methods
- `src/overlay/setup_guide.py` — `SetupGuide` class with `show()`, `hide()`, `toggle()`, `next_page()`, 4 page renderers (core, locked, hotbar, addons)
- `src/tray.py` — Added "Setup Guide" checkable menu item with `on_setup_guide_toggle` callback, `set_setup_guide_mode()` for external sync
- `main.py` — Wired up tray → loader → overlay; F7 hotkey cycles pages; auto-dismisses guide when a combo is started

**How it works:**
1. User selects a combo (sets the current class/spec)
2. User right-clicks tray → checks "Setup Guide"
3. Overlay pauses any active combo, shows page 1 of 4:
   - Page 1: Core Skill recommendation (name, effect, reason)
   - Page 2: Skills to Lock (🔒 name — reason, up to 10)
   - Page 3: Hotbar Setup (numbered list, up to 12)
   - Page 4: Skill Add-ons PVE (skill + addon_1 + addon_2)
4. **F7 manually advances pages** (no auto-cycling); page dots (● ○ ○ ○) show position
5. Unchecking "Setup Guide" in tray hides it and resumes combo immediately
6. Starting a new combo auto-dismisses the guide

---

## Completed Task — Class/Spec YAML Population ✅

All **27 BDO classes × 2 specs (Awakening + Succession) = 54 total files** have been created under `config/classes/`.

### Status: 54 / 54 COMPLETE

All classes populated with awakening + succession configs:
Warrior, Ranger, Sorceress, Berserker, Tamer, Musa, Maehwa, Valkyrie, Kunoichi, Ninja, Wizard, Witch, Dark Knight, Striker, Mystic, Lahn, Archer, Shai (Talent + Succession), Guardian, Hashashin, Nova, Sage, Corsair, Drakania, Woosa, Maegu, Scholar

### YAML file structure (new unified format)

Each class YAML file has:
- Top-level `class:` and `spec:` keys
- `skills:` — unified section containing all skill definitions (awakening/succession, rabam, pre-awakening utility, flow skills) with name, input, keys[], keys_alt[], protection, cc[], damage, cooldown_ms, description, flows_into, core_effect, notes, level
- `pve_combos:` — 4+ combos (basic_grind, large_pack_clear, speed_clear, endgame_grind, etc.)
- `pvp_combos:` — 7 combos (protected_engage, grab/catch combos, quick_burst, grab_punish, kite_disengage, large_scale_siege)
- `movement_combos:` — 2 combos (fast_travel, awakening/succession_movement)
- `skill_addons:` — 6 PVE add-on recommendations
- `locked_skills:` — 6-9 skills to lock with reasons
- `hotbar_skills:` — 7-11 recommended hotbar skills
- `core_skill:` — recommended core/prime skill with effect and reason

**Note:** The Dark Knight files have been restructured to the new unified `skills:` format. The remaining 52 class files still use the old `awakening_skills:` / `rabam_skills:` / `preawakening_utility:` sections — `combo_loader.py` supports both formats via `SKILL_SECTIONS = ["skills", "awakening_skills", "rabam_skills", "preawakening_utility"]`.

### Sources

- [BDFoundry](https://www.blackdesertfoundry.com/) — class guides, skill data
- [GrumpyGreenCricket](https://grumpygreen.cricket/) — skill tables
- [bdocodex.com](https://bdocodex.com/) — skill database
- Class Discord servers — meta combos
- In-game skill descriptions — protection types, CCs, cooldowns

---

## Completed Task — Settings GUI ✅

`src/settings_gui.py` — A tkinter-based settings window (~1150 lines) launched from the tray menu.

**Features:**
- **Keybinds tab** — scrollable list of all BDO key bindings with click-to-capture rebinding (KeyCapturePopup)
- **Display tab** — font family, font size, text color, outline color, highlight color, outline width
- **Hotkeys tab** — global hotkey configuration (start/stop/reset/next) with capture
- **Timing tab** — combo_window_ms, idle_reset_timeout_ms, hotbar_auto_advance_ms, step_highlight_duration_ms
- **Save** writes directly to `config/combos.yaml` and live-reloads settings in the running app (key remap, idle reset, hotkeys re-registered)
- **Reset to Defaults** button per tab

Wired into `main.py` via `_on_settings()` → `SettingsWindow.open()` → `_on_settings_saved()` callback chain.

---

## Completed Task — Legacy Cleanup ✅

Removed legacy/unused files and updated outdated references:

**Deleted:**
- `src/overlay.py` — replaced by `src/overlay/` package (7 modules)
- Old `src/utils/` empty directory
- `classes.md` — completed development checklist
- `scripts/` directory — icon downloader and bdocodex cache
- `assets/icons/` and `assets/icon_map.yaml` — downloaded skill icons

### Skill Icons — REMOVED

The bdocodex.com icon scraper was removed. After a full scrape of IDs 900-8300:
- 5,798 skills scraped from bdocodex tooltip API
- 516/1,057 YAML skills matched to icons (~49% match rate)
- 436/510 icon downloads failed (CDN returning errors for .webp files)

**Plan: revisit later with a game resource dump** for reliable icon extraction instead of web scraping.

---

## What This Project Is

A **transparent game overlay** for Black Desert Online that displays skill combos as floating outlined text over the game client. All 27 classes × 2 specs (54 total) are included. Steps advance when the user presses the correct key/mouse combination (not on a timer). It runs from the system tray.

## Spec (from `spec.md`)

- Overlay BDO game client with a transparent window containing skill text
- Text is configurable size/colour, rendered like subtitles (outlined, no background)
- Controls are configurable (users may remap hotkeys)
- `combo_window_ms` = transition delay after a successful key press before showing next step
- Class/spec data stored in per-class YAML files under `config\classes\`; global settings in `config\combos.yaml`
- Combo selection via a system tray menu (right-click)
- Tray icon for exit, stop, and starting combos
- **Steps wait for the user to press the correct keys** — they do NOT auto-advance on a timer

## Project Structure

```
bdo-trainer/
├── main.py                          # Entry point — wires everything together
├── spec.md                          # Original feature spec
├── requirements.txt                 # pyyaml, pystray, pillow, keyboard, pynput
├── run.bat                          # Windows launcher (auto-elevates, installs deps)
├── run.sh                           # macOS/Linux launcher (venv, deps, permission notes)
├── config/
│   ├── combos.yaml                  # Global settings (hotkeys, display, key_bindings, timing)
│   ├── classes/                     # 54 class/spec YAML files (27 classes × 2 specs)
│   │   ├── dark_knight_awakening.yaml   # Restructured: unified skills: section
│   │   ├── dark_knight_succession.yaml  # Restructured: unified skills: section
│   │   ├── warrior_awakening.yaml
│   │   ├── ...                          # 52 files still using old section names (backward compat)
│   │   └── scholar_succession.yaml
│   └── overlay_position.json        # Auto-generated — saved overlay anchor position
├── src/
│   ├── __init__.py                  # Package exports
│   ├── combo_loader.py              # Loads config/classes/*.yaml + combos.yaml settings
│   ├── input_monitor.py             # InputMonitor — keyboard+mouse state tracking via pynput
│   ├── platform.py                  # Platform helpers (click-through, font detection)
│   ├── settings_gui.py              # Settings window (keybinds, display, timing, hotkeys)
│   ├── tray.py                      # System tray icon via pystray
│   ├── overlay/
│   │   ├── __init__.py              # Re-exports ComboOverlay + INPUT_AVAILABLE
│   │   ├── renderer.py              # OverlayContext (shared state) + OverlayRenderer (drawing)
│   │   ├── core.py                  # ComboOverlay — thin coordinator
│   │   ├── combo_player.py          # ComboPlayer — playback state machine
│   │   ├── hold_bar.py              # HoldBar — hold-step progress bar
│   │   ├── setup_guide.py           # SetupGuide — 4-page recommendations
│   │   └── reposition.py            # RepositionHandler — drag-to-move + persistence
│   └── utils/
│       ├── __init__.py
│       └── keys.py                  # Key display names + outline offset utilities
├── tests/
│   ├── __init__.py
│   └── test_basic.py                # Unit tests for ComboLoader
├── assets/                          # Reserved for future use
├── doc/
│   └── images/                      # Screenshots for README
├── logs/                            # Created at runtime
├── setup.py                         # setuptools packaging (v0.3.0)
├── .gitignore
├── README.md
└── THREAD_SUMMARY.md                # This file
```

## Architecture

### Component Diagram

```
main.py (BDOTrainerApp)
  │
  ├─► ComboLoader (src/combo_loader.py)
  │     Reads config/combos.yaml (settings) + config/classes/*.yaml (class data)
  │     Provides: get_class_tree(), get_combo(cls, spec, id), get_skill_info(id, cls, spec)
  │     SKILL_SECTIONS: ["skills", "awakening_skills", "rabam_skills", "preawakening_utility"]
  │     Key remapping: get_key_remap() builds canonical→physical key map from key_bindings
  │     Setup guide: get_setup_guide(cls, spec) → locked_skills, hotbar, core_skill, addons
  │
  ├─► ComboOverlay (src/overlay/core.py)   ◄── thin coordinator, runs tkinter mainloop (BLOCKS)
  │     Creates Tk root, canvas, OverlayContext, OverlayRenderer
  │     Instantiates and wires all components:
  │     │
  │     ├─► InputMonitor (src/input_monitor.py)
  │     │     pynput keyboard+mouse listeners, multi-set key matching
  │     │
  │     ├─► ComboPlayer (src/overlay/combo_player.py)
  │     │     Playback state machine: start/stop/pause/resume
  │     │     Step rendering, skill resolution (name, keys, input, protection)
  │     │     Input arming + key remapping + idle reset
  │     │     Resolves keys/input from skill definitions when absent from combo steps
  │     │
  │     ├─► HoldBar (src/overlay/hold_bar.py)
  │     │     Hold-step progress bar (~33fps tick, animated fill/glow/spark)
  │     │
  │     ├─► SetupGuide (src/overlay/setup_guide.py)
  │     │     4-page manual display (core/locked/hotbar/addons), F7 to cycle
  │     │
  │     └─► RepositionHandler (src/overlay/reposition.py)
  │           Drag-to-move mode, position saved to overlay_position.json
  │
  ├─► SettingsWindow (src/settings_gui.py)  ◄── modal dialog on Tk thread
  │     Tabbed UI: Keybinds / Display / Hotkeys / Timing
  │     Saves to combos.yaml, live-reloads via on_save callback
  │
  ├─► TrayManager (src/tray.py)       ◄── runs in daemon thread
  │     pystray icon with "DK" label
  │     Menu: Class > Spec > Combos / Stop / Reposition ✓ / Setup Guide ✓ / Settings / Exit
  │
  └─► keyboard library                ◄── global hotkeys (F5/F6/F7/F8)
        F5 = start/restart combo
        F6 = stop combo
        F7 = next setup guide page (when guide is active)
        F8 = reset combo
```

### Threading Model

| Thread | What runs | How it communicates |
|--------|-----------|---------------------|
| **Main thread** | tkinter mainloop (`overlay.run()`) | Direct method calls |
| **Tray thread** | `pystray.Icon.run()` (daemon) | `overlay.schedule()` → `root.after()` |
| **pynput keyboard listener** | `pynput.keyboard.Listener` (daemon) | `root.after(0, callback)` |
| **pynput mouse listener** | `pynput.mouse.Listener` (daemon) | `root.after(0, callback)` |
| **keyboard lib** | Internal hooks for F5/F6/F7/F8 | `overlay.schedule()` → `root.after()` |

All cross-thread UI updates go through `overlay.schedule(func)` which calls `root.after(delay, func)` — this is tkinter's thread-safe mechanism.

### Key Flow: User Selects a Combo

1. User right-clicks tray → Class → "Dark Knight" → "Awakening" → "Basic PVE Grind"
2. `TrayManager._make_combo_action()` closure fires `on_combo_selected("Dark Knight", "Awakening", "basic_grind")` from tray thread
3. `BDOTrainerApp._on_combo_selected()` stores class/spec/combo_id, calls `overlay.schedule(lambda: self._start_combo(...))`
4. On Tk thread: `_start_combo()` auto-dismisses setup guide if active, binds `overlay.get_skill_info` to the current class/spec, calls `loader.get_combo(cls, spec, id)`, then `overlay.start_combo(combo_data, ...)`
5. `ComboOverlay.start_combo()` delegates to `ComboPlayer.start()`
6. Player shows 2-second intro splash, then `_show_current_step()`
7. `_render_step()` resolves skill name/input/keys/protection from the `skills:` section, draws outlined text on canvas
8. `_arm_input()` resolves keys from skill definition if not in step, applies key remapping, sets `InputMonitor` target keys
9. User presses correct keys in-game → `InputMonitor._check()` fires `_on_keys_matched()`
10. Green "✓ Skill Name" flash → after `combo_window_ms` delay → `_advance()` → next step
11. Loops until user clicks "Stop" in tray or presses F6

### Key Flow: Setup Guide

1. User right-clicks tray → checks "Setup Guide" (requires a class/spec to be selected first)
2. `TrayManager._on_setup_guide_clicked()` fires `on_setup_guide_toggle(True)` from tray thread
3. `BDOTrainerApp._on_setup_guide_toggle()` schedules `_show_setup_guide()` on Tk thread
4. `_show_setup_guide()` calls `loader.get_setup_guide(cls, spec)` → returns dict with locked_skills, hotbar_skills, core_skill, skill_addons
5. `ComboOverlay.show_setup_guide()` pauses the player, delegates to `SetupGuide.show()`
6. `_render_page()` draws header + page body + navigation dots + footer hint (all tagged `"guide"`)
7. Page stays put until user presses **F7** → `next_page()` (no auto-advance)
8. User unchecks "Setup Guide" in tray → `ComboOverlay.hide_setup_guide()` calls `SetupGuide.hide()`, then `ComboPlayer.resume()` if a combo was active

### Key Flow: Hotbar Steps (Fallback)

Steps with `keys: ["hotbar"]` cannot be detected (user could bind hotbar to anything). These auto-advance after `max(combo_window_ms, 1500)` ms as a fallback. Same fallback applies if pynput is not installed.

### Key Flow: Hold Steps

Steps where the skill has `keys: ["hold"]` delegate to `HoldBar`:
1. `ComboPlayer._arm_input()` detects `keys == ["hold"]`, calls `hold_bar.start(hold_ms, on_complete=self._on_keys_matched)`
2. `HoldBar` ticks at ~33fps, checks if previously-armed keys are still held via `InputMonitor._pressed`
3. Animated progress bar renders on canvas (amber → gold → green gradient with glow/spark effects)
4. On 100% completion, fires `on_complete` callback which advances the combo

## Config File Structure

Config is split into **global settings** and **per-class/spec** YAML files.

### `config/combos.yaml` — Global Settings

```yaml
settings:
    active_combo: "basic_grind"
    default_combo_window_ms: 250
    display:                # show_protection_type, show_cc_type, etc.
    hotkeys:                # start_combo: F5, stop_combo: F6, next_step: F7, reset_combo: F8
    key_bindings:           # BDO game-client names → physical keys (see Key Remapping below)
        Move Forward: "w"
        Move Back: "s"
        Move Left: "a"
        Move Right: "d"
        LMB: "lmb"
        RMB: "rmb"
        MMB: "mmb"
        Jump: "space"
        Sprint: "shift"
        Q: "q"
        E: "e"
        F: "f"
        X: "x"
        Z: "z"
    timing:                 # step_highlight_duration_ms, transition_delay_ms, auto_advance
```

### `config/classes/*.yaml` — Class/Spec Data

Each file must have top-level `class:` and `spec:` keys. `ComboLoader` auto-discovers all `*.yaml` files in `config/classes/`.

**New format (Dark Knight files):**
```yaml
class: Dark Knight
spec: Awakening

skills:                    # Unified section: all skills (awakening, rabam, pre-awakening, flows)
    spirit_hunt:
        name: "Spirit Hunt"
        input: "W + RMB"
        keys: ["w", "rmb"]
        protection: "SA"
        cc: ["stiffness"]
        damage: high
        cooldown_ms: 3000
        description: "Draw close to the enemy..."
        flows_into: ["shattering_darkness", "seed_of_catastrophe"]
        core_effect: "Core: Spirit Hunt - Stiffness on good hits"
        notes: "Core gap-close opener."

    shadow_strike:           # Rabam skills keep their level: field
        name: "Shadow Strike"
        level: 56
        input: "Shift + X"
        keys: ["shift", "x"]
        ...

    flow_bombardment:        # Flow skills defined with keys: ["hold"]
        name: "Flow: Bombardment"
        input: "Hold after Shattering Darkness"
        keys: ["hold"]
        ...

pve_combos:                # Steps reference skills by ID — no duplicated input/keys
    awakening_main_dps:
        name: "Awakening Main DPS"
        difficulty: advanced
        combo_window_ms: 300
        steps:
            - skill: "shattering_darkness"
              note: "Main opener"
            - skill: "flow_bombardment"
              hold_ms: 1500
              note: "First flow after Shattering Darkness"
            - skill: "spirit_legacy"
              note: "Big frontal hit"

pvp_combos:                # Same simplified step format
movement_combos:           # Same simplified step format
skill_addons:              # PVE add-on recommendations
locked_skills:             # Skills to lock with reasons
hotbar_skills:             # Recommended hotbar layout
core_skill:                # Recommended core skill with effect and reason
```

**Old format (52 other class files — still supported):**
```yaml
awakening_skills:          # Separate sections for skill categories
rabam_skills:
preawakening_utility:

pve_combos:                # Steps duplicate input/keys from skill definitions
    basic_grind:
        steps:
            - skill: "spirit_legacy"
              input: "Shift + LMB"
              keys: ["shift", "lmb"]
              note: "Main damage"
```

`ComboLoader` supports both formats. `ComboPlayer` resolves missing `input`/`keys` from the skill definition at runtime, so both old and new YAML files work seamlessly.

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pyyaml` | >=6.0 | Parse combos.yaml + class YAML files |
| `pystray` | >=0.19 | System tray icon |
| `pillow` | >=10.0 | Generate tray icon image (also pystray dependency) |
| `keyboard` | >=0.13 | Global hotkeys (F5/F6/F7/F8) |
| `pynput` | >=1.7 | Keyboard + mouse input monitoring for combo step detection |
| `tkinter` | stdlib | Transparent overlay window + canvas + settings GUI |
| `ctypes` | stdlib | Win32 API for click-through window (Windows only) |

## Overlay Rendering Details

- **Window**: Full-screen, borderless (`overrideredirect`), always-on-top, transparent background `#010101`
- **Windows transparency**: `-transparentcolor` attribute makes `#010101` pixels invisible
- **macOS transparency**: `-alpha 0.90` semi-transparent fallback (no transparent-colour equivalent)
- **Click-through**: Win32 `WS_EX_TRANSPARENT | WS_EX_LAYERED` via `ctypes` in `src/platform.py` (mouse events pass to game); no-op on macOS/Linux
- **Text**: Canvas `create_text` with dark outline (pre-computed offset copies in `#000000`, main text on top in colour) via `OverlayRenderer.draw_outlined_text()`
- **Fonts**: Platform-detected via `platform.default_font_family()` — Segoe UI (Windows), Helvetica Neue (macOS), DejaVu Sans (Linux)
- **Position**: Bottom-centre of screen (`relx=0.5, rely=0.85`), persisted to `overlay_position.json` as relative coordinates
- **Layout per step** (top to bottom): combo name (grey italic) → skill name (gold 32pt bold) + [PROTECTION] badge → input keys (white 22pt) → note (grey 14pt) → step counter (dark grey 12pt)
- **Success flash**: "✓ Skill Name" in green, displayed for `combo_window_ms` before advancing

## InputMonitor Details (`src/input_monitor.py`)

- `InputMonitor` maintains a `_pressed: Set[str]` of currently held keys/buttons
- `set_target(key_sets, on_match)` accepts a **list of key-lists** (multiple valid combinations)
- On each key press/mouse click event, `_check()` tests if **any** required set is a subset of `_pressed`
- **Edge-triggered**: `_matched` flag prevents re-firing while keys stay held. Resets only when a key is released.
- Key normalisation: pynput `Key.shift_l`/`Key.shift_r` both map to `"shift"`, `KeyCode` → `.char.lower()`, mouse `Button.left` → `"lmb"`, etc.
- Before keys reach the InputMonitor, `ComboPlayer._arm_input()` applies key remapping (canonical combo key → physical key) and merges `keys` + `alt_keys` (from step or skill definition) into the key-sets list.

## Reposition Mode

Toggled via the **Reposition Overlay** checkable menu item in the system tray. Managed by `RepositionHandler` in `src/overlay/reposition.py`.

| Entering reposition mode | Exiting reposition mode |
|---|---|
| `ComboOverlay` pauses the `ComboPlayer` | Unbinds drag events, resets cursor |
| `RepositionHandler.enable()` calls `platform.remove_click_through()` | Deletes `"reposition"` tag canvas items |
| Sets `fleur` (↕↔) cursor, binds drag events | Calls `platform.make_click_through()` to restore pass-through |
| Draws dashed gold rectangle, crosshair, sample text, and instructions | Saves position to `config/overlay_position.json` as `{"rx": 0.5, "ry": 0.85}` |
| | `ComboOverlay` resumes the `ComboPlayer` if a combo was active |

Drag uses `canvas.move("all", dx, dy)` — shifts every canvas item in one call (smooth, no redraw). Position is stored as screen-fraction coordinates so it survives resolution changes.

## Key Remapping

Users can remap keys in `config/combos.yaml` under `settings.key_bindings`, or via the **Settings GUI** (tray → Settings → Keybinds tab). Names use **BDO game-client terminology**:

| BDO Name | Default | Canonical combo key |
|---|---|---|
| Move Forward | `"w"` | `w` |
| Move Back | `"s"` | `s` |
| Move Left | `"a"` | `a` |
| Move Right | `"d"` | `d` |
| LMB | `"lmb"` | `lmb` |
| RMB | `"rmb"` | `rmb` |
| Sprint | `"shift"` | `shift` |
| Jump | `"space"` | `space` |
| Q / E / F / X / Z | `"q"` … `"z"` | `q` … `z` |

`ComboLoader.get_key_remap()` reads the `key_bindings` section, maps each BDO name to its canonical combo key via `_BDO_TO_COMBO_KEY`, and returns a dict of non-identity mappings. `ComboPlayer.set_key_remap(remap)` stores this. In `_arm_input()`, every key in `keys` and `alt_keys` passes through `remap.get(k, k)` before reaching the InputMonitor.

Example: if a user plays with ESDF instead of WASD, they set `Move Forward: "e"`, `Move Left: "s"`, etc. The combo step `keys: ["w", "rmb"]` is then matched against physical keys `"e"` + `"rmb"`.

## What Has NOT Been Done / Known Issues

1. **Not tested end-to-end** — the code compiles and the architecture is sound but has not been run against BDO yet
2. **Admin privileges** — if BDO runs as admin, the trainer may need admin too for pynput/keyboard hooks to work (`main.py` auto-elevates via UAC on Windows)
3. **Outline rendering performance** — drawing 8+ shadow copies per text element per step; could be optimised with cached images if needed
4. **macOS/Linux** — click-through and `-transparentcolor` are Windows-only; macOS/Linux fall back to alpha transparency (functional for testing, not ideal for gameplay)
5. **Skill data accuracy** — class YAML files were bulk-generated from community knowledge; exact cooldowns, protection types, and CC values should be verified in-game per class
6. **Skill icons** — removed; bdocodex web scraping yielded ~49% match rate with broken CDN links. Plan to revisit with a game resource dump
7. **YAML migration** — only the Dark Knight files have been migrated to the new unified `skills:` format; the other 52 class files still use the old section names (fully backward compatible)

## How to Run

**Windows:**
```bash
cd bdo-trainer
pip install -r requirements.txt
python main.py
```
Or double-click `run.bat` (handles venv, deps, and admin elevation automatically).

**macOS/Linux:**
```bash
cd bdo-trainer
chmod +x run.sh
./run.sh
```
Or manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Then right-click the tray icon → pick a class → spec → combo → press the keys shown on screen.