# BDO Trainer — Thread Handoff Summary

## Completed Task — Setup Guide Overlay ✅

### Setup Guide Feature — IMPLEMENTED & BUG-FIXED

Added a toggleable **Setup Guide** overlay that shows class/spec recommendations (locked skills, hotbar setup, core skill, skill add-ons) as manually-paged screens over the game.

**Files modified:**
- `src/combo_loader.py` — Added `get_locked_skills()`, `get_hotbar_skills()`, `get_core_skill()`, `get_skill_addons()`, `get_setup_guide()` methods
- `src/overlay.py` — Added setup guide rendering system (~370 lines): `show_setup_guide()`, `hide_setup_guide()`, `toggle_setup_guide()`, `next_setup_page()`, 4 page renderers (core, locked, hotbar, addons), text wrapping helper
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

**Bug fix applied:** Initial implementation had an auto-advance timer (10s page cycling) that caused the tray icon to hang and the guide to keep rendering after being unchecked. Fixed by:
- Removing `_guide_auto_advance()` and `_cancel_guide_auto()` entirely — pages are **manual F7 only**
- Making `hide_setup_guide()` unconditionally clear state (`_setup_guide_active = False`, `_setup_guide_data = None`, `canvas.delete("guide")`) before checking whether to resume a combo
- Adding `_setup_guide_active` guard at the top of `_render_guide_page()` so a stale scheduled render is a no-op

---

## Completed Task — Class/Spec YAML Population ✅

All **27 BDO classes × 2 specs (Awakening + Succession) = 54 total files** have been created under `config/classes/`.

### Status: 54 / 54 COMPLETE

All classes populated with awakening + succession configs:
Warrior, Ranger, Sorceress, Berserker, Tamer, Musa, Maehwa, Valkyrie, Kunoichi, Ninja, Wizard, Witch, Dark Knight, Striker, Mystic, Lahn, Archer, Shai (Talent + Succession), Guardian, Hashashin, Nova, Sage, Corsair, Drakania, Woosa, Maegu, Scholar

### YAML file structure (each ~750-880 lines)

Each class YAML file has:
- Top-level `class:` and `spec:` keys
- `awakening_skills:` — 13-18 skill definitions with name, input, keys[], keys_alt[], protection, cc[], damage, cooldown_ms, description, flows_into, core_effect, notes
- `rabam_skills:` — 3 Rabam skill choices (L56, L57, L58)
- `preawakening_utility:` — 4-7 useful pre-awakening skills carried into the spec
- `pve_combos:` — 4 combos (basic_grind, large_pack_clear, speed_clear, endgame_grind)
- `pvp_combos:` — 7 combos (protected_engage, grab/catch combos, quick_burst, grab_punish, kite_disengage, large_scale_siege)
- `movement_combos:` — 2 combos (fast_travel, awakening/succession_movement)
- `skill_addons:` — 6 PVE add-on recommendations
- `locked_skills:` — 6-9 skills to lock with reasons
- `hotbar_skills:` — 7-11 recommended hotbar skills
- `core_skill:` — recommended core/prime skill with effect and reason

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
- `src/utils/` — empty directory (just a 3-line `__init__.py`, nothing imported it)
- `classes.md` — completed 54/54 development checklist, served its purpose
- `scripts/` directory — icon downloader and bdocodex cache removed (see note below)
- `assets/icons/` and `assets/icon_map.yaml` — downloaded skill icons removed

**Updated:**
- `README.md` — rewritten to reflect all 27 classes, Setup Guide, Settings GUI, correct project structure
- `setup.py` — bumped to v0.3.0
- `requirements.txt` — removed `requests` (was only used by deleted icon script)
- `src/combo_loader.py` — removed `ASSETS_ICONS_DIR` constant and `get_icon_path()` method
- `src/__init__.py` — exports ComboLoader, ComboOverlay, SettingsWindow, TrayManager

### Skill Icons — REMOVED

The bdocodex.com icon scraper (`scripts/download_icons.py`) was removed. After a full scrape of IDs 900-8300:
- 5,798 skills scraped from bdocodex tooltip API
- 516/1,057 YAML skills matched to icons (~49% match rate)
- 436/510 icon downloads failed (CDN returning errors for .webp files)
- Only 74 icons actually on disk

The low match rate (name differences between community guides and bdocodex) plus the CDN failures made this approach impractical. **Plan: revisit later with a game resource dump** for reliable icon extraction instead of web scraping.

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
├── config/
│   ├── combos.yaml                  # Global settings (hotkeys, display, key_bindings, timing)
│   ├── classes/                     # 54 class/spec YAML files (27 classes × awakening + succession)
│   │   ├── dark_knight_awakening.yaml
│   │   ├── dark_knight_succession.yaml
│   │   ├── warrior_awakening.yaml
│   │   ├── ...                         # All 27 classes × 2 specs = 54 files total
│   │   └── scholar_succession.yaml
│   └── overlay_position.json        # Auto-generated — saved overlay anchor position
├── src/
│   ├── __init__.py                  # Exports ComboLoader, ComboOverlay, SettingsWindow, TrayManager
│   ├── combo_loader.py              # Loads config/classes/*.yaml + combos.yaml settings
│   ├── overlay.py                   # Transparent tkinter overlay + InputMonitor (pynput) + reposition mode
│   ├── settings_gui.py              # Settings window (keybinds, display, timing, hotkeys)
│   └── tray.py                      # System tray icon via pystray (Class > Spec > Combo menu)
├── tests/
│   ├── __init__.py
│   └── test_basic.py                # Unit tests for ComboLoader
├── assets/                          # Empty — reserved for future use
├── doc/
│   └── images/                      # Screenshots for README
│       ├── in-game-overlay.png
│       └── menu.png
├── logs/                            # Created at runtime
├── run.bat                          # Windows launcher script (auto-elevates, installs deps)
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
  │     Key remapping: get_key_remap() builds canonical→physical key map from key_bindings
  │     Setup guide: get_setup_guide(cls, spec) → locked_skills, hotbar, core_skill, addons
  │
  ├─► ComboOverlay (src/overlay.py)   ◄── runs tkinter mainloop (BLOCKS)
  │     Full-screen transparent window (click-through on Windows)
  │     Canvas-based outlined text (no background strip)
  │     Contains InputMonitor (pynput keyboard+mouse listeners, multi-set matching)
  │     Steps wait for correct key combo (+ alt_keys), then flash green ✓, then advance
  │     Reposition mode: toggle via tray, drag to move, position saved to overlay_position.json
  │     Setup guide mode: 4-page manual display (core/locked/hotbar/addons), F7 to cycle
  │     Key remapping via set_key_remap() — translates combo keys → physical keys before matching
  │
  ├─► SettingsWindow (src/settings_gui.py)  ◄── modal dialog on Tk thread
  │     Tabbed UI: Keybinds / Display / Hotkeys / Timing
  │     Saves to combos.yaml, live-reloads via on_save callback
  │
  ├─► TrayManager (src/tray.py)       ◄── runs in daemon thread
  │     pystray icon with "DK" label
  │     Menu: Class > ClassName > SpecName > Combos / Stop / Reposition ✓ / Setup Guide ✓ / Settings / Exit
  │     Callbacks: on_combo_selected / on_stop / on_reposition_toggle / on_setup_guide_toggle / on_settings / on_exit
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
5. Overlay shows 2-second intro splash, then `_show_current_step()`
6. `_render_step()` draws outlined text on canvas; `_arm_input()` sets `InputMonitor` target keys
7. User presses correct keys in-game → `InputMonitor._check()` fires `_on_keys_matched()`
8. Green "✓ Skill Name" flash → after `combo_window_ms` delay → `_advance()` → next step
9. Loops until user clicks "Stop" in tray or presses F6

### Key Flow: Setup Guide

1. User right-clicks tray → checks "Setup Guide" (requires a class/spec to be selected first)
2. `TrayManager._on_setup_guide_clicked()` fires `on_setup_guide_toggle(True)` from tray thread
3. `BDOTrainerApp._on_setup_guide_toggle()` schedules `_show_setup_guide()` on Tk thread
4. `_show_setup_guide()` calls `loader.get_setup_guide(cls, spec)` → returns dict with locked_skills, hotbar_skills, core_skill, skill_addons
5. `overlay.show_setup_guide(guide_data)` — pauses combo input, clears display, renders page 0
6. `_render_guide_page()` draws header + page body + navigation dots + footer hint (all tagged `"guide"`)
7. Page stays put until user presses **F7** → `next_setup_page()` (no auto-advance)
8. User unchecks "Setup Guide" in tray → `hide_setup_guide()` unconditionally clears state + deletes `"guide"` canvas items, then resumes combo if one was active

### Key Flow: Hotbar Steps (Fallback)

Steps with `keys: ["hotbar"]` cannot be detected (user could bind hotbar to anything). These auto-advance after `max(combo_window_ms, 1500)` ms as a fallback. Same fallback applies if pynput is not installed.

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

### `config/classes/dark_knight_awakening.yaml` — Class/Spec Data (~785 lines)

Each file must have top-level `class:` and `spec:` keys.  `ComboLoader` auto-discovers all `*.yaml` files in `config/classes/`.

```yaml
class: Dark Knight
spec: Awakening

awakening_skills:          # 14 skills with name, input, keys[], keys_alt[], protection, cc[], damage, cooldown, flows_into, notes
rabam_skills:              # 3 skills (Shadow Strike L56, Obsidian Blaze L57, Balanced Strike L58)
preawakening_utility:      # 4 skills (Unveiled Dagger, Kamasylvia Slash, Twilight Dash, Evasion)

pve_combos:                # 4 combos: basic_grind, large_pack_clear, speed_clear, endgame_grind
pvp_combos:                # 7 combos: protected_engage, catch_combo, iframe_engage, quick_burst, grab_punish, kite_disengage, large_scale_siege
movement_combos:           # 2 combos: fast_travel, awakening_movement

skill_addons:              # PVE add-on recommendations (from BDFoundry/Sieg)
locked_skills:             # Skills to lock (8 entries with reasons)
hotbar_skills:             # Recommended hotbar layout (7 skills)
core_skill:                # Recommended: Seed of Catastrophe (SA during skill)
```

To add a new class/spec, create a new file (e.g. `dark_knight_succession.yaml`, `sorceress_awakening.yaml`) with the same structure.

Each combo step looks like:
```yaml
- skill: "spirit_hunt"         # ID used to look up skill metadata in awakening_skills
  input: "Shift + LMB"         # Display string shown to user
  keys: ["shift", "lmb"]       # Keys pynput watches for (lowercase)
  note: "Main damage"          # Context hint shown below input
```

Steps with alternative inputs (e.g. Shift+A or Shift+D for "Dusk") use `alt_keys`:
```yaml
- skill: "dusk"
  input: "Shift + A/D"
  keys: ["shift", "a"]         # Primary key set
  alt_keys: ["shift", "d"]     # Alternative key set — either set triggers the step
  note: "Iframe side dash"
```

If a step omits `alt_keys`, the system falls back to the skill definition's `keys_alt` field (if present).

Key name conventions in `keys[]`: `shift`, `space`, `ctrl`, `alt`, `w`, `a`, `s`, `d`, `e`, `f`, `q`, `x`, `z`, `lmb`, `rmb`, `mmb`, `hotbar`

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pyyaml` | >=6.0 | Parse combos.yaml + class YAML files |
| `pystray` | >=0.19 | System tray icon |
| `pillow` | >=10.0 | Generate tray icon image (also pystray dependency) |
| `keyboard` | >=0.13 | Global hotkeys (F5/F6/F7/F8) |
| `pynput` | >=1.7 | Keyboard + mouse input monitoring for combo step detection |
| `tkinter` | stdlib | Transparent overlay window + canvas + settings GUI |
| `ctypes` | stdlib | Win32 API for click-through window |

## Overlay Rendering Details

- **Window**: Full-screen, borderless (`overrideredirect`), always-on-top, transparent background `#010101`
- **Windows transparency**: `-transparentcolor` attribute makes `#010101` pixels invisible
- **Click-through**: Win32 `WS_EX_TRANSPARENT | WS_EX_LAYERED` via `ctypes` (mouse events pass to game)
- **Text**: Canvas `create_text` with dark outline (8 offset copies in `#000000`, main text on top in colour)
- **Position**: Bottom-centre of screen (`relx=0.5, rely=0.85`)
- **Layout per step** (top to bottom): combo name (grey italic) → skill name (gold 32pt bold) + [PROTECTION] badge → input keys (white 22pt) → note (grey 14pt) → step counter (dark grey 12pt)
- **Success flash**: "✓ Skill Name" in green, displayed for `combo_window_ms` before advancing

## InputMonitor Details (`src/overlay.py`)

- `InputMonitor` maintains a `_pressed: Set[str]` of currently held keys/buttons
- `set_target(key_sets, on_match)` accepts a **list of key-lists** (multiple valid combinations)
- On each key press/mouse click event, `_check()` tests if **any** required set is a subset of `_pressed`
- **Edge-triggered**: `_matched` flag prevents re-firing while keys stay held. Resets only when **no** required set is fully held.
- Key normalisation: pynput `Key.shift_l`/`Key.shift_r` both map to `"shift"`, `KeyCode` → `.char.lower()`, mouse `Button.left` → `"lmb"`, etc.
- Before keys reach the InputMonitor, `_arm_input()` applies key remapping (canonical combo key → physical key) and merges `keys` + `alt_keys` into the key-sets list.

## Reposition Mode

Toggled via the **Reposition Overlay** checkable menu item in the system tray.

| Entering reposition mode | Exiting reposition mode |
|---|---|
| Clears InputMonitor target + cancels pending timers (combo paused) | Unbinds drag events, resets cursor |
| Calls `_remove_click_through()` — strips `WS_EX_TRANSPARENT` so the window captures clicks | Deletes `"reposition"` tag canvas items |
| Sets `fleur` (↕↔) cursor, binds `<ButtonPress-1>` + `<B1-Motion>` | Calls `_make_click_through()` to restore pass-through |
| Draws dashed gold rectangle, crosshair, and instructions; if no combo is running, shows sample text | Saves position to `config/overlay_position.json` as relative coords `{"rx": 0.5, "ry": 0.85}` |
| | Resumes combo from current step if one was active |

Drag uses `canvas.move("all", dx, dy)` — shifts every canvas item in one call (no redraw), so it's smooth. Position is stored as screen-fraction coordinates so it survives resolution changes.

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

`ComboLoader.get_key_remap()` reads the `key_bindings` section, maps each BDO name to its canonical combo key via `_BDO_TO_COMBO_KEY`, and returns a dict of non-identity mappings. `ComboOverlay.set_key_remap(remap)` stores this. In `_arm_input()`, every key in `keys` and `alt_keys` passes through `remap.get(k, k)` before reaching the InputMonitor.

Example: if a user plays with ESDF instead of WASD, they set `Move Forward: "e"`, `Move Left: "s"`, etc. The combo step `keys: ["w", "rmb"]` is then matched against physical keys `"e"` + `"rmb"`.

## What Has NOT Been Done / Known Issues

1. **Not tested end-to-end** — the code compiles and the architecture is sound but has not been run against BDO yet
2. **Admin privileges** — if BDO runs as admin, the trainer may need admin too for pynput/keyboard hooks to work (`main.py` auto-elevates via UAC)
3. **Outline rendering performance** — drawing 8+ shadow copies per text element per step; could be optimised with cached images if needed
4. **Linux/Mac** — click-through, `-transparentcolor`, and reposition mode are Windows-only; Linux/Mac fall back to alpha transparency (not ideal)
5. **Skill data accuracy** — class YAML files were bulk-generated from community knowledge; exact cooldowns, protection types, and CC values should be verified in-game per class
6. **Skill icons** — removed; bdocodex web scraping yielded ~49% match rate with broken CDN links. Plan to revisit with a game resource dump for reliable icon extraction

## How to Run

```bash
cd bdo-trainer
pip install -r requirements.txt
python main.py
```

Or on Windows, double-click `run.bat` (handles venv, deps, and admin elevation automatically).

Then right-click the tray icon → pick a class → spec → combo → press the keys shown on screen.