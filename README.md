# BDO Trainer — Skill Combo Overlay

A transparent, click-through game overlay for **Black Desert Online** that displays skill combo sequences as floating outlined text over the game window. Steps advance in real time as you press the correct key and mouse combinations. Runs quietly from the system tray.

All **27 BDO classes × 2 specs (54 total)** are included out of the box — Awakening + Succession for every class, ready to go.

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue) ![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey) ![macOS: partial](https://img.shields.io/badge/macOS-partial-yellow)

![In-game overlay screenshot](doc/images/in-game-overlay.png)

---

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running](#running)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
  - [Global Settings — `config/combos.yaml`](#global-settings--configcombosyaml)
  - [Class/Spec Files — `config/classes/*.yaml`](#classspec-files--configclassesyaml)
  - [Combo Step Format](#combo-step-format)
  - [Key Remapping](#key-remapping)
- [Usage Guide](#usage-guide)
  - [Tray Menu](#tray-menu)
  - [Global Hotkeys](#global-hotkeys)
  - [Reposition Mode](#reposition-mode)
  - [Idle Reset](#idle-reset)
- [Overlay Animations](#overlay-animations)
- [Class & Combo Editor](#class--combo-editor)
- [Adding a New Class or Spec](#adding-a-new-class-or-spec)
- [Architecture](#architecture)
- [macOS Support](#macos-support)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

| Feature | Description |
|---|---|
| **Transparent overlay** | Fullscreen, click-through window rendered on top of BDO using Win32 `WS_EX_TRANSPARENT` + `WS_EX_LAYERED` |
| **Outlined text** | Canvas-based outlined text for readability over any background |
| **Step-by-step combos** | Each step highlights the current input; advances when the correct keys/mouse buttons are pressed |
| **Alternative keys** | Steps can define `alt_keys` so either input is accepted (e.g., `Shift + A` or `Shift + D`) |
| **Hotbar step auto-advance** | Hotbar skills auto-advance after a short delay since hotbar presses can't be detected |
| **Hold step progress bar** | Animated amber → gold → green fill bar with glow and spark effects for hold/channel skills; releasing early advances to the next step |
| **Next skill preview** | Shows the upcoming skill name + required keys below the current step; pulsates between grey and gold when the next step is a hold skill |
| **Slide-up animation** | New steps slide up from below with an ease-out curve (~120 ms, 40 px travel) |
| **Fade-out animation** | Old steps slide upward and fade to transparent, creating a smooth crossfade transition |
| **Setup Guide** | 4-page overlay showing locked skills, hotbar setup, core skill, and skill add-ons per class/spec |
| **Settings GUI** | Tabbed settings window for keybinds, display, timing, and hotkeys — live-reloads on save |
| **Class & Combo Editor** | Full GUI for creating classes, editing skills with key toggle grids and CC checkboxes, building combos with step reordering |
| **System tray** | Pick Class → Spec → Combo from a nested tray menu; Stop, Reposition, Setup Guide, Settings, Editor, Exit |
| **Global hotkeys** | `F5` start/restart, `F6` stop, `F7` next guide page, `F8` reset — work even while BDO has focus (configurable) |
| **Key remapping** | Remap movement and ability keys to match your in-game BDO keybind settings |
| **Reposition mode** | Drag the overlay text to any screen position; saved as relative coordinates in `overlay_position.json` |
| **Idle reset** | Combo automatically resets to step 1 after a configurable inactivity timeout |
| **Auto-discovery** | Drop YAML files into `config/classes/` and they appear in the tray menu automatically |
| **54 pre-built class configs** | All 27 BDO classes × Awakening + Succession included out of the box |
| **macOS support** | Launches and renders on macOS with semi-transparent fallback (no click-through) |

---

## Project Structure

```
bdo-trainer/
├── main.py                          # Entry point — wires everything, auto-elevates admin
├── spec.md                          # Original feature spec
├── requirements.txt                 # pyyaml, pystray, pillow, keyboard, pynput
├── run.bat                          # Windows launcher (auto-elevates, installs deps)
├── run.sh                           # macOS/Linux launcher (venv, deps, permission notes)
├── setup.py                         # Package setup
├── config/
│   ├── combos.yaml                  # Global settings (hotkeys, display, key_bindings, timing)
│   ├── classes/                     # 54 class/spec YAML files (27 classes × 2 specs)
│   │   ├── dark_knight_awakening.yaml
│   │   ├── dark_knight_succession.yaml
│   │   ├── warrior_awakening.yaml
│   │   └── ... (54 files total)
│   └── overlay_position.json        # Auto-generated — saved overlay anchor position
├── src/
│   ├── __init__.py
│   ├── combo_loader.py              # Loads config/classes/*.yaml + combos.yaml settings
│   ├── input_monitor.py             # InputMonitor — keyboard+mouse state tracking via pynput
│   ├── platform.py                  # Platform helpers (click-through, font detection)
│   ├── settings_gui.py              # Settings window (keybinds, display, timing, hotkeys)
│   ├── tray.py                      # System tray icon via pystray
│   ├── overlay/
│   │   ├── __init__.py              # Re-exports ComboOverlay + INPUT_AVAILABLE
│   │   ├── renderer.py              # OverlayContext (shared state) + OverlayRenderer (drawing)
│   │   ├── core.py                  # ComboOverlay — thin coordinator
│   │   ├── combo_player.py          # ComboPlayer — playback state machine + animations
│   │   ├── hold_bar.py              # HoldBar — hold-step progress bar
│   │   ├── setup_guide.py           # SetupGuide — 4-page recommendations
│   │   └── reposition.py            # RepositionHandler — drag-to-move + persistence
│   ├── editor/
│   │   ├── __init__.py              # Re-exports EditorWindow
│   │   ├── window.py                # EditorWindow — main editor with sidebar + tabs
│   │   ├── skill_editor.py          # SkillEditor — skill list + edit form
│   │   └── combo_editor.py          # ComboEditor — combo list + step builder
│   └── utils/
│       ├── __init__.py
│       └── keys.py                  # Key display names + offset utilities
├── tests/
│   ├── __init__.py
│   └── test_basic.py
├── assets/                          # Reserved for future use
├── doc/images/                      # Screenshots for README
├── logs/                            # Created at runtime
├── .gitignore
├── README.md
└── THREAD_SUMMARY.md
```

---

## Requirements

- **Python 3.8+**
- **Windows** (primary — the overlay uses Win32 APIs for click-through)
- **Administrator privileges** on Windows (see [Why Admin?](#why-does-it-need-admin) below)
- macOS is partially supported (see [macOS Support](#macos-support))

### Python Dependencies

| Package | Purpose |
|---|---|
| `pyyaml` | Parse YAML config and combo files |
| `pystray` | System tray icon and menu |
| `pillow` | Image support for the tray icon (required by pystray) |
| `keyboard` | Global hotkeys (`F5`–`F8`) that work over fullscreen games |
| `pynput` | Low-level keyboard and mouse listener hooks for step detection |
| `tkinter` | Overlay window + canvas + all GUIs (included with Python stdlib) |
| `ctypes` | Win32 click-through APIs (included with Python stdlib) |

---

## Installation

### Option A — `pip`

```
git clone <repo-url> bdo-trainer
cd bdo-trainer
pip install -r requirements.txt
```

### Option B — `run.bat` (Windows, recommended)

Double-click `run.bat`. It will:

1. Install/update dependencies from `requirements.txt`
2. Auto-elevate to administrator
3. Launch `main.py`

No manual setup needed.

### Option C — `run.sh` (macOS / Linux)

```
chmod +x run.sh
./run.sh
```

Creates a virtual environment, installs dependencies, and launches. See [macOS Support](#macos-support) for platform notes.

---

## Running

### From the command line

```
python main.py
```

`main.py` will auto-elevate to administrator on Windows if it isn't already running elevated. A UAC prompt will appear the first time.

### From `run.bat` / `run.sh`

Double-click `run.bat` on Windows or run `./run.sh` on macOS — they handle everything.

### What happens on launch

1. Global settings are loaded from `config/combos.yaml`.
2. All class/spec files in `config/classes/*.yaml` are auto-discovered.
3. A transparent fullscreen overlay window is created (invisible until a combo is started).
4. A system tray icon appears — right-click it to access the menu.

---

## How It Works

1. **Pick a combo** from the tray menu (or press `F5` to restart the current one).
2. The overlay displays the combo's steps as outlined text over your game.
3. The **current step** is highlighted. It shows the skill name, protection badge, and required input (e.g., `Shift + LMB`).
4. **Press the correct keys/mouse buttons** — the overlay detects the input via low-level hooks and advances to the next step with a smooth slide-up animation.
5. If a step has **alternative keys** (`alt_keys`), either input combination is accepted.
6. **Hold steps** display an animated progress bar — hold the keys for the specified duration, or release early to advance.
7. **Hotbar steps** auto-advance after a delay since hotbar key presses can't be meaningfully validated.
8. A **next skill preview** below the current step shows what's coming up.
9. When you reach the end, the combo resets to step 1 (loop).
10. If you stop pressing keys, the **idle reset timer** returns the combo to step 1 after the configured timeout.

---

## Configuration

### Global Settings — `config/combos.yaml`

This file contains global settings **only** — no skill or combo data. Example:

```yaml
# Hotkeys (work globally, even while BDO is focused)
hotkeys:
  start_restart: "F5"
  stop: "F6"
  next_guide_page: "F7"
  reset: "F8"

# Display settings
display:
  font_family: "Segoe UI"
  font_size: 18
  text_color: "#FFFFFF"
  outline_color: "#000000"
  highlight_color: "#FFD700"
  outline_width: 2

# Timing
timing:
  idle_reset_timeout_ms: 5000       # Reset combo after 5 s of inactivity
  hotbar_auto_advance_ms: 800       # Auto-advance delay for hotbar steps

# Key bindings — use BDO's in-game action names
# Only remap keys you've changed from defaults
key_bindings:
  Move Forward: "W"
  Move Back: "S"
  Move Left: "A"
  Move Right: "D"
  Jump: "Space"
  Interact: "R"
  Evade: "Shift"
```

All of these settings can also be edited through the **Settings GUI** (right-click tray → Settings).

### Class/Spec Files — `config/classes/*.yaml`

Each file defines one class + spec combination. Files are auto-discovered — place one in `config/classes/` and it will appear in the tray menu on next launch.

**New unified format** (used by the Editor, and by Dark Knight files):

```yaml
class: "Dark Knight"
spec: "Awakening"

skills:
  spirit_hunt:
    name: "Spirit Hunt"
    input: "W + RMB"
    keys: ["w", "rmb"]
    protection: "SA"
    cc: ["stiffness"]
    damage: high
    cooldown_ms: 3000
    description: "Forward-dashing slash with super armor."
    flows_into: ["shattering_darkness"]
    core_effect: "Core: Spirit Hunt"
    notes: "Core gap-close opener."

  shattering_darkness:
    name: "Shattering Darkness"
    input: "Shift + LMB"
    keys: ["shift", "lmb"]
    protection: "FG"
    cc: ["down_smash"]
    damage: high

pve_combos:
  awakening_main_dps:
    name: "Awakening Main DPS"
    difficulty: advanced
    combo_window_ms: 300
    steps:
      - skill: "shattering_darkness"
        note: "Main opener"
      - skill: "flow_bombardment"
        hold_ms: 1500
        note: "Hold to channel"

pvp_combos: { ... }
movement_combos: { ... }

skill_addons:
  pve: [...]

locked_skills:
  - name: "Obsidian Ashes"
    reason: "Too slow for PvE rotation"

hotbar_skills: ["elion_blessing"]

core_skill:
  recommended: "Spirit Hunt"
  effect: "Core: Spirit Hunt"
  reason: "Best gap-close and damage boost"
```

**Old format** (most class files — still fully supported):

Steps include `input:` and `keys:` inline. Skill sections are split into `awakening_skills:`, `rabam_skills:`, `preawakening_utility:`. The combo loader handles both formats seamlessly. Saving through the Editor auto-migrates to the unified format.

### Combo Step Format

In the **new unified format**, steps are simplified — `input` and `keys` are resolved from the skill definition:

| Field | Required | Description |
|---|---|---|
| `skill` | Yes | Skill ID — must match a key in the `skills` section |
| `note` | No | Short contextual hint displayed below the step |
| `hold_ms` | No | Duration in ms for hold/channel skills (displays a progress bar) |
| `input` | No | Human-readable input string (resolved from skill if omitted) |
| `keys` | No | Key list for detection (resolved from skill if omitted) |
| `alt_keys` | No | Alternative key combo that also satisfies this step |

**Simplified step** (input + keys resolved from skill):

```yaml
- skill: "spirit_hunt"
  note: "Main opener"
```

**Hold step** (displays an animated progress bar):

```yaml
- skill: "flow_bombardment"
  hold_ms: 1500
  note: "Hold to channel"
```

**Step with alternative keys** (accepts either `Shift+A` or `Shift+D`):

```yaml
- skill: "dusk"
  alt_keys: ["shift", "d"]
```

**Hotbar step** (auto-advances):

```yaml
- skill: "elion_blessing"
  note: "Press hotbar slot"
```

**Old-format step** (still supported — `input` and `keys` inline):

```yaml
- skill: "spirit_hunt"
  input: "Shift + LMB"
  keys: ["shift", "lmb"]
  note: "Main damage"
```

### Valid Key Names

`w`, `a`, `s`, `d`, `shift`, `lmb`, `rmb`, `mmb`, `space`, `e`, `f`, `q`, `x`, `z`, `hotbar`, `hold`, `down`

### Key Remapping

BDO lets you rebind movement and action keys. If your in-game bindings differ from defaults, update `key_bindings` in `config/combos.yaml` (or use the **Settings GUI**):

```yaml
key_bindings:
  Move Forward: "W"
  Move Back: "S"
  Move Left: "A"
  Move Right: "D"
  Jump: "Space"
  Evade: "Shift"
```

The combo loader translates these into the internal key names. For example, if you rebind `Move Forward` to `Up Arrow`, any combo step referencing forward movement will expect `Up Arrow` instead of `W`.

---

## Usage Guide

### Tray Menu

Right-click the system tray icon to see:

![Tray menu screenshot](doc/images/menu.png)

- **Class → ClassName → SpecName → Combo** — starts the selected combo on the overlay
- **Stop** — stops the current combo and hides the overlay text
- **Reposition Overlay** — toggles drag-to-move mode (checkable)
- **Setup Guide** — opens the 4-page setup overlay for the selected class/spec
- **Settings** — opens the Settings GUI window
- **Class & Combo Editor** — opens the full class/skill/combo editor
- **Exit** — shuts everything down cleanly

### Global Hotkeys

These work globally, even when BDO is in fullscreen focus:

| Hotkey | Action |
|---|---|
| `F5` | Start the selected combo, or restart from step 1 if already running |
| `F6` | Stop the current combo |
| `F7` | Next Setup Guide page (when the guide is active) |
| `F8` | Reset the current combo to step 1 (without stopping) |

Hotkeys are configurable in `config/combos.yaml` under `hotkeys`, or through the Settings GUI.

### Reposition Mode

1. Right-click the tray icon → select **Reposition Overlay** (a checkmark appears).
2. The overlay becomes **draggable** — click and drag the text to the desired screen position.
3. Right-click the tray icon → deselect **Reposition Overlay** to lock the position.
4. The position is saved to `config/overlay_position.json` as relative screen coordinates, so it persists across restarts and adapts to resolution changes.

To reset to center, delete `config/overlay_position.json` and restart.

### Idle Reset

If no relevant keys are pressed within the configured timeout (`idle_reset_timeout_ms` in `config/combos.yaml`, default 5000 ms), the combo automatically resets to step 1. This prevents you from getting stuck mid-combo when you take a break.

---

## Overlay Animations

The overlay uses smooth animations for step transitions:

### Step Layout (top to bottom)

1. **Combo name** — grey italic 14pt
2. **Skill name** — gold bold 32pt + `[PROTECTION]` badge (SA, FG, etc.)
3. **Input keys** — white 22pt
4. **Hold bar** — animated progress bar (only on hold steps)
5. **Note** — grey 14pt (optional)
6. **Step counter** — dark grey 12pt
7. **Next skill preview** — grey 14pt: `next ▸ Skill Name · Input Keys`

### Transition Animation

When the correct keypress is detected:

1. The old content is tagged and a green **✓ Skill Name** confirmation appears.
2. The old content **slides upward** at 3 px/frame and **fades** toward transparent.
3. After ~80 ms delay, the new step **renders and slides up** 40 px with an ease-out curve (~120 ms).
4. Once the slide completes, input is armed for the new step.

### Hold Step Progress Bar

For skills with `hold_ms`, an animated progress bar appears:

- **Amber → gold → green** fill as you hold the keys
- Glow and spark particle effects on the fill edge
- Releasing keys early advances to the next step

### Next Skill Preview Pulse

When the upcoming step is a hold skill, the preview text pulsates between grey and gold (~1.75 s cycle) as a visual warning.

---

## Class & Combo Editor

Accessible from the tray menu via **Class & Combo Editor**. Provides a full GUI for creating and editing class configurations without touching YAML files.

### Features

- **Sidebar** listing all class/spec pairs with selection
- **New Class** dialog — enter a class name and pick a spec (Awakening/Succession)
- **Delete Class** with confirmation prompt
- **Skills tab** — scrollable skill list + full edit form:
  - Key toggle button grid for input keys
  - CC checkbox grid (bound, down, stiffness, etc.)
  - Protection dropdown (SA, FG, iframe, none)
  - Damage dropdown (low, medium, high)
  - Description and notes text areas
- **Combos tab** — categorized combo list (PVE / PVP / Movement) + combo form:
  - Skill dropdown per step
  - Note and `hold_ms` fields per step
  - ▲ / ▼ buttons to reorder steps
  - × button to delete steps

### Workflow

1. Open the editor from the tray menu.
2. Select an existing class/spec from the sidebar, or click **New Class** to create one.
3. Edit skills in the **Skills** tab — add, modify, or remove skill definitions.
4. Build combos in the **Combos** tab — add steps referencing your skills.
5. Click **Save** — the YAML file is written and the tray menu refreshes automatically.

Saving through the editor auto-migrates old skill sections (`awakening_skills`, `rabam_skills`, `preawakening_utility`) into the unified `skills:` format.

---

## Adding a New Class or Spec

### Option A — Use the Editor (recommended)

1. Right-click tray → **Class & Combo Editor**.
2. Click **New Class**, enter the class name and spec.
3. Add skills and combos using the GUI.
4. Save — it appears in the tray menu immediately.

### Option B — Create a YAML file manually

1. Create a new file in `config/classes/`, e.g., `sage_awakening.yaml`.

2. Add the required top-level keys and define skills:

```yaml
class: "Sage"
spec: "Awakening"

skills:
  rift_chain:
    name: "Rift Chain"
    input: "Shift + LMB"
    keys: ["shift", "lmb"]
    protection: "SA"
    cc: ["stiffness"]
    damage: high
    notes: "Main damage skill"

  spatial_collapse:
    name: "Spatial Collapse"
    input: "Shift + RMB"
    keys: ["shift", "rmb"]
    protection: "FG"
    damage: high
```

3. Define combos using those skill IDs:

```yaml
pve_combos:
  basic_grind:
    name: "Basic Grind"
    difficulty: beginner
    steps:
      - skill: "rift_chain"
        note: "Engage"
      - skill: "spatial_collapse"
        hold_ms: 1000
        note: "Hold for full damage"
```

4. Restart the application. The new class/spec appears automatically in the tray menu under **Class → Sage → Awakening**.

No code changes required.

---

## Architecture

### Module Responsibilities

| Module | Role |
|---|---|
| `main.py` | Entry point. Checks/requests admin elevation. Instantiates ComboLoader, ComboOverlay, TrayManager, SettingsWindow, EditorWindow, and keyboard hotkeys. Starts the tkinter main loop. |
| `src/combo_loader.py` | Loads `config/combos.yaml` (global settings) and auto-discovers all `config/classes/*.yaml` files. Provides CRUD methods: `get_class_config()`, `save_class_config()`, `delete_class_config()`, `get_class_tree()`, `get_combo()`. |
| `src/input_monitor.py` | `InputMonitor` class — sets up pynput keyboard + mouse low-level hooks on daemon threads. Tracks pressed-key state. Applies key remapping. |
| `src/overlay/core.py` | `ComboOverlay` — thin coordinator that owns the tkinter root window and delegates to renderer, combo player, hold bar, setup guide, and reposition handler. |
| `src/overlay/renderer.py` | `OverlayContext` (shared state) + `OverlayRenderer` (canvas-based outlined text drawing). |
| `src/overlay/combo_player.py` | `ComboPlayer` — playback state machine, step rendering, slide/fade animations, hold bar integration, next-skill preview pulse. |
| `src/overlay/hold_bar.py` | `HoldBar` — animated hold-step progress bar with glow/spark effects. |
| `src/overlay/setup_guide.py` | `SetupGuide` — 4-page overlay for locked skills, hotbar setup, core skill, skill add-ons. |
| `src/overlay/reposition.py` | `RepositionHandler` — drag-to-move overlay + persistence to `overlay_position.json`. |
| `src/tray.py` | System tray icon and nested menu via pystray. Dynamically builds menu from the class tree. Has `refresh_menu()` to update after editor changes. |
| `src/settings_gui.py` | Tabbed settings window for Key Bindings, Display, Hotkeys, Timing. Saves to `combos.yaml` and live-reloads. |
| `src/editor/window.py` | `EditorWindow` — singleton Toplevel with sidebar (class/spec list) + tabs. |
| `src/editor/skill_editor.py` | `SkillEditor` — skill list + full edit form with key toggle grids, CC checkboxes, dropdowns. |
| `src/editor/combo_editor.py` | `ComboEditor` — categorized combo list + step builder with reordering. |
| `src/platform.py` | Platform helpers — Win32 click-through setup, font detection, OS-specific behavior. |
| `src/utils/keys.py` | Key display name mapping and offset utilities. |

### Threading Model

```
┌──────────────────────────────────────────────────────────────┐
│  Main Thread                                                 │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  tkinter mainloop                                      │  │
│  │  • ComboOverlay (overlay rendering)                    │  │
│  │  • SettingsWindow, EditorWindow (GUI)                  │  │
│  │  • All UI updates via root.after() / overlay.schedule()│  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  Daemon Threads                                              │
│  ┌─────────────────┐  ┌──────────────────────────────────┐  │
│  │  pystray         │  │  pynput (InputMonitor)           │  │
│  │  (TrayManager    │  │  • Keyboard listener (daemon)    │  │
│  │   + menu)        │  │  • Mouse listener   (daemon)     │  │
│  │  (daemon thread) │  │                                  │  │
│  └─────────────────┘  └──────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  keyboard library — internal hook thread for F5/F6/F7/F8    │
└──────────────────────────────────────────────────────────────┘
```

**Cross-thread UI updates**: Any thread that needs to update the overlay calls `overlay.schedule(callback)`, which internally calls `root.after(0, callback)` to marshal the work onto the main tkinter thread. This avoids tkinter's thread-safety issues.

### Key Detection Pipeline

1. **pynput** hooks capture raw keyboard and mouse events on daemon threads.
2. Events are translated through the **key remap table** (built from `key_bindings` in settings).
3. The current pressed-key set is compared against the current step's `keys` (and `alt_keys` if present).
4. On a full match, the combo advances. A UI update is scheduled on the main thread.
5. For **hold steps**, matching keys start the hold bar timer; releasing early or completing the hold advances the combo.

---

## macOS Support

The overlay launches and renders on macOS with the following limitations:

- **No click-through** — macOS does not support the `WS_EX_TRANSPARENT` equivalent, so the overlay window captures mouse events. Reposition mode still works.
- **Semi-transparent fallback** — the window uses a semi-transparent background instead of a fully transparent one.
- **Accessibility permissions** — macOS requires granting Accessibility permissions for `pynput` to capture global keyboard/mouse events. The `run.sh` script will display a note about this.
- **No auto-elevation** — there is no admin auto-elevation on macOS. Run with `sudo` if needed for input monitoring.

---

## Troubleshooting

### "Keys aren't being detected while BDO is in focus"

**Cause**: BDO runs as an elevated (administrator) process. Input hooks from a non-elevated process are blocked by Windows UIPI (User Interface Privilege Isolation).

**Fix**: Make sure the trainer is running as administrator. It should auto-elevate on launch — if the UAC prompt was denied, re-run and accept it.

### The overlay doesn't appear

- Make sure a combo is selected (right-click tray → Class → pick a combo).
- Check that BDO is not running in exclusive fullscreen. Use **Fullscreen Windowed** mode in BDO's settings.
- Try pressing `F5` to start/restart the combo.

### Overlay appears but clicks go through to the game

This is **intended behavior**. The overlay is click-through by design (`WS_EX_TRANSPARENT`). The only exception is **Reposition Mode**, where clicks are captured for dragging.

### Overlay is in the wrong position

1. Right-click tray → **Reposition Overlay**.
2. Drag the text to where you want it.
3. Right-click tray → uncheck **Reposition Overlay** to lock.
4. Position is saved to `config/overlay_position.json` automatically.

To reset to center, delete `config/overlay_position.json` and restart.

### Steps aren't advancing

- Verify you're pressing the **exact combination** shown (e.g., `Shift + LMB` means hold Shift and left-click).
- Check if your BDO keybinds differ from defaults. If so, update `key_bindings` in `config/combos.yaml` (or use **Settings** from the tray menu).
- Hotbar steps auto-advance — you don't need to press anything for those.
- Check `logs/` for error output.

### Combo resets unexpectedly

The **idle reset timer** resets the combo to step 1 after a period of inactivity. Increase `idle_reset_timeout_ms` in `config/combos.yaml` (or via the Settings GUI):

```yaml
timing:
  idle_reset_timeout_ms: 10000   # 10 seconds
```

### "Access denied" or permission errors

The application requires administrator privileges. See below.

### Why does it need admin?

BDO runs as an elevated process. On Windows, [User Interface Privilege Isolation (UIPI)](https://learn.microsoft.com/en-us/windows/win32/winmsg/about-hooks#uipi) prevents lower-privilege processes from installing hooks into higher-privilege processes. Without admin, keyboard and mouse hooks will silently fail to capture input when BDO has focus.

`main.py` handles this automatically — it detects whether it's elevated and re-launches itself via `ShellExecuteW` with `runas` if not.

### Tray icon doesn't appear

- Some Windows configurations hide new tray icons. Check the system tray overflow area (the `^` arrow).
- Make sure `pillow` is installed (`pip install pillow`) — pystray requires it for icon rendering.

### macOS: Input not detected

- Grant **Accessibility** permissions to your terminal / Python in System Settings → Privacy & Security → Accessibility.
- You may need to restart the application after granting permissions.

### Adding the wrong keys / My character does something unexpected

The trainer **only displays information** — it does **not** send any keystrokes to the game. If your character is performing unexpected actions, it's not caused by this tool.

---

## License

MIT License