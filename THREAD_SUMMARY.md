# BDO Trainer — Thread Handoff Summary

## What This Project Is

A **transparent game overlay** for Black Desert Online that displays Awakened Dark Knight skill combos as floating outlined text over the game client. Steps advance when the user presses the correct key/mouse combination (not on a timer). It runs from the system tray.

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
│   ├── combos.yaml                  # Global settings only (hotkeys, display, key_bindings, timing)
│   ├── classes/
│   │   └── dark_knight_awakening.yaml  # DK Awakening — skills, combos, recommendations (~785 lines)
│   ├── overlay_position.json        # Auto-generated — saved overlay anchor position
│   └── config.example.ini           # Legacy config (not actively used)
├── src/
│   ├── __init__.py                  # Exports ComboLoader, ComboOverlay, TrayManager
│   ├── combo_loader.py              # Loads config/classes/*.yaml + combos.yaml settings
│   ├── overlay.py                   # Transparent tkinter overlay + InputMonitor (pynput) + reposition mode
│   ├── tray.py                      # System tray icon via pystray (Class > Spec > Combo menu)
│   ├── gui/                         # OLD — legacy tabbed GUI, not used anymore
│   │   ├── __init__.py
│   │   └── main_window.py
│   └── utils/
│       ├── __init__.py
│       ├── config_manager.py        # INI config manager (legacy, still importable)
│       └── logger.py                # Logging utilities
├── tests/
│   ├── __init__.py
│   └── test_basic.py                # Basic unit tests (need updating for new arch)
├── assets/                          # Empty — for future icons/images
├── logs/                            # Created at runtime
├── run.bat                          # Windows launcher script
├── setup.py                         # setuptools packaging
├── .gitignore
├── README.md
├── QUICKSTART.md
└── DEVELOPMENT.md
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
  │
  ├─► ComboOverlay (src/overlay.py)   ◄── runs tkinter mainloop (BLOCKS)
  │     Full-screen transparent window (click-through on Windows)
  │     Canvas-based outlined text (no background strip)
  │     Contains InputMonitor (pynput keyboard+mouse listeners, multi-set matching)
  │     Steps wait for correct key combo (+ alt_keys), then flash green ✓, then advance
  │     Reposition mode: toggle via tray, drag to move, position saved to overlay_position.json
  │     Key remapping via set_key_remap() — translates combo keys → physical keys before matching
  │
  ├─► TrayManager (src/tray.py)       ◄── runs in daemon thread
  │     pystray icon with "DK" label
  │     Menu: Class > ClassName > SpecName > Combos / Stop / Reposition ✓ / Exit
  │     Callbacks: on_combo_selected(cls, spec, id) / on_stop / on_reposition_toggle / on_exit
  │
  └─► keyboard library                ◄── global hotkeys (F5/F6/F8)
        F5 = start/restart combo
        F6 = stop combo
        F8 = reset combo
```

### Threading Model

| Thread | What runs | How it communicates |
|--------|-----------|---------------------|
| **Main thread** | tkinter mainloop (`overlay.run()`) | Direct method calls |
| **Tray thread** | `pystray.Icon.run()` (daemon) | `overlay.schedule()` → `root.after()` |
| **pynput keyboard listener** | `pynput.keyboard.Listener` (daemon) | `root.after(0, callback)` |
| **pynput mouse listener** | `pynput.mouse.Listener` (daemon) | `root.after(0, callback)` |
| **keyboard lib** | Internal hooks for F5/F6/F8 | `overlay.schedule()` → `root.after()` |

All cross-thread UI updates go through `overlay.schedule(func)` which calls `root.after(delay, func)` — this is tkinter's thread-safe mechanism.

### Key Flow: User Selects a Combo

1. User right-clicks tray → Class → "Dark Knight" → "Awakening" → "Basic PVE Grind"
2. `TrayManager._make_combo_action()` closure fires `on_combo_selected("Dark Knight", "Awakening", "basic_grind")` from tray thread
3. `BDOTrainerApp._on_combo_selected()` stores class/spec/combo_id, calls `overlay.schedule(lambda: self._start_combo(...))`
4. On Tk thread: `_start_combo()` binds `overlay.get_skill_info` to the current class/spec, calls `loader.get_combo(cls, spec, id)`, then `overlay.start_combo(combo_data, ...)`
5. Overlay shows 2-second intro splash, then `_show_current_step()`
6. `_render_step()` draws outlined text on canvas; `_arm_input()` sets `InputMonitor` target keys
7. User presses correct keys in-game → `InputMonitor._check()` fires `_on_keys_matched()`
8. Green "✓ Skill Name" flash → after `combo_window_ms` delay → `_advance()` → next step
9. Loops until user clicks "Stop" in tray or presses F6

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
| `pyyaml` | >=6.0 | Parse combos.yaml |
| `pystray` | >=0.19 | System tray icon |
| `pillow` | >=10.0 | Generate tray icon image (also pystray dependency) |
| `keyboard` | >=0.13 | Global hotkeys (F5/F6/F8) |
| `pynput` | >=1.7 | Keyboard + mouse input monitoring for combo step detection |
| `tkinter` | stdlib | Transparent overlay window + canvas |
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

Users can remap keys in `config/combos.yaml` under `settings.key_bindings`. Names use **BDO game-client terminology**:

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
2. **Admin privileges** — if BDO runs as admin, the trainer may need admin too for pynput/keyboard hooks to work
3. **`src/gui/main_window.py`** — legacy tabbed GUI, no longer used, can be deleted
4. **`tests/test_basic.py`** — tests reference the old architecture, need updating
5. **`setup.py`** — references old dependencies, needs updating
6. **`config.example.ini`** — INI config is legacy; the app now uses `combos.yaml` + `config/classes/` exclusively
7. **No settings UI** — all config is done by editing YAML files directly
8. **No key remapping UI** — users edit `key_bindings` in `combos.yaml` (remapping IS supported, just not via a GUI)
9. **Outline rendering performance** — drawing 8+ shadow copies per text element per step; could be optimised with cached images if needed
10. **Linux/Mac** — click-through, `-transparentcolor`, and reposition mode are Windows-only; Linux/Mac fall back to alpha transparency (not ideal)
11. **`QUICKSTART.md`, `README.md`, `DEVELOPMENT.md`** — written for the old tabbed GUI, need rewriting to match the overlay architecture
12. **Only Dark Knight Awakening** — only one class/spec config exists so far; structure supports adding more via new YAML files in `config/classes/`
13. **No Succession specs** — no succession combo data written yet for any class

## How to Run

```bash
cd bdo-trainer
pip install -r requirements.txt
python main.py
```

Then right-click the "DK" tray icon → pick a combo → press the keys shown on screen.