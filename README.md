# BDO Trainer — Skill Combo Overlay

A transparent, click-through game overlay for **Black Desert Online** that displays skill combo sequences as floating outlined text over the game window. Steps advance in real time as you press the correct key and mouse combinations. Runs quietly from the system tray.

All **27 BDO classes × 2 specs (54 total)** ship with skill data.

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue) ![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey) ![macOS: tray-only](https://img.shields.io/badge/macOS-tray%20only-yellow) ![Version](https://img.shields.io/badge/version-0.5.2-green)

![In-game overlay screenshot](doc/images/in-game-overlay.png)

---

## Table of Contents

**Getting started**

- [Install](#install)
- [Run it](#run-it)
- [Pick a combo and play](#pick-a-combo-and-play)
- [Hotkeys](#hotkeys)
- [Move the overlay](#move-the-overlay)
- [Setup Guide](#setup-guide)

**Editing combos**

- [Combo Editor](#combo-editor)
- [Class Editor](#class-editor)
- [Adding a new class, bundle, or combo](#adding-a-new-class-bundle-or-combo)

**Sharing**

- [Share a combo on bdodojo.com](#share-a-combo-on-bdodojocom)
- [Import a combo from bdodojo.com](#import-a-combo-from-bdodojocom)

**Help**

- [Troubleshooting](#troubleshooting)

**Technical reference**

- [Project structure](#project-structure)
- [Configuration files](#configuration-files)
- [Bundle file formats — `.bdt` and `.bdc`](#bundle-file-formats--bdt-and-bdc)
- [Architecture](#architecture)
- [macOS specifics](#macos-specifics)
- [Migration from 0.4.x](#migration-from-04x)
- [License](#license)

---

# Getting started

## Install

### Windows (recommended)

Double-click **`run.bat`**. It installs/updates dependencies, asks for admin (BDO runs elevated, so the trainer needs to as well), and launches.

### macOS / Linux

```
chmod +x run.sh
./run.sh
```

Creates a virtual environment, installs dependencies, and launches in tray-only mode on macOS.

### Manual

```
git clone https://github.com/Vitiate/bdo-trainer
cd bdo-trainer
pip install -r requirements.txt
python main.py
```

You need Python 3.8+ and Windows to use the in-game overlay. macOS users get a tray + editor-only experience (BDO doesn't run there).

---

## Run it

After launch, look for the **DK** icon in your system tray (Windows) or menu bar (macOS). Right-click it for the menu.

Useful CLI flags:

```
python main.py                # Default
python main.py --overlay      # Force the overlay window on (any platform)
python main.py --no-overlay   # Force the overlay window off (any platform)
python main.py --editor       # Editor windows only — no tray, no overlay
```

---

## Pick a combo and play

1. Right-click the tray icon.
2. Drill into **Class → Spec → Bundle → Combo** and click the combo you want.
3. The overlay appears over BDO showing step 1.
4. Press the keys / mouse buttons it shows you. Each correct input advances to the next step with a slide-up animation.
5. **Hold steps** show an animated progress bar — hold the keys until it fills (or release early to advance).
6. When you reach the end, the combo loops back to step 1.

Press **F6** or click **Stop Combo** in the tray menu to end it.

If you stop pressing keys for a while, the combo automatically resets back to step 1 (configurable — see [Hotkeys](#hotkeys) and the Settings window).

---

## Hotkeys

These work even while BDO is in the foreground (Windows; macOS needs `sudo`):

| Hotkey | Action |
|---|---|
| `F5` | Start the selected combo, or restart from step 1 |
| `F6` | Stop the current combo |
| `F7` | Next page of the Setup Guide (when it's open) |
| `F8` | Reset the combo to step 1 (without stopping) |

To rebind: tray → **Settings → Hotkeys**.

---

## Move the overlay

By default the overlay text sits at the bottom-centre of the screen. To reposition:

1. Right-click tray → tick **Reposition Overlay**.
2. Drag the text to where you want it.
3. Right-click tray → untick **Reposition Overlay** to lock.

Position is saved automatically and survives resolution changes. To reset, delete `config/overlay_position.json`.

---

## Setup Guide

Each combo bundle carries a recommended **loadout** — which skills to lock, which to put on the hotbar, which Core skill to pick, and which PVE skill add-ons to use. To see it in-game:

1. Pick any combo from that bundle first.
2. Right-click tray → tick **Setup Guide**.
3. Press `F7` to flip through pages: Core skill → Locked skills → Hotbar → Add-ons.

Untick **Setup Guide** in the tray menu to dismiss.

---

# Editing combos

The trainer ships with two editors. Open them from the tray menu.

## Combo Editor

Right-click tray → **Combo Editor**. This is where you create, edit, import, and export combos.

The window has three parts:

- **Sidebar (left)** — a tree of every loaded class/spec, with the bundles inside it. The filter input at the top narrows the list as you type — try typing your class name or a bundle name like `grind`. Each class lists its bundles; click `+ New Bundle` under any class to add a new one.
- **Loadout panel (top right)** — bundle name, description, hotbar skills, locked skills, core skill, PVE add-ons. Edit free-text fields here. Lists like locked skills and hotbar use `name :: reason` lines (one per line).
- **Combo step builder (bottom right)** — pick a combo from the bundle's combo list, then edit its ID, name, category (PVE / PVP / Movement), step window, description, and ordered steps. Each step row has a skill dropdown, a note field, and a hold-duration field. Use the ▲/▼/× buttons to reorder or delete steps.

Action buttons in the sidebar:

| Button | What it does |
|---|---|
| **Rename Bundle** | Change the bundle's id on disk |
| **Delete Bundle** | Permanently remove the bundle and every combo in it |
| **Export Combo** | Save just the currently-selected combo as a `.bdt` file (with the parent bundle's loadout for context) |
| **Export Combos** | Save the entire bundle (loadout + all combos) as one `.bdt` file |
| **Import Combos** | Open a `.bdt` and pick which combos to merge into a target bundle |
| **Inspect** | Read-only viewer for any `.bdt` or `.bdc` file before importing |

Click **Save Bundle** at the bottom-right when you're done editing. Combo IDs are editable — renaming one moves the file on disk at the next save.

## Class Editor

Right-click tray → **Class Editor**. This is where you edit the **skill library** for a class — the underlying skill definitions that combos reference.

For most users this is rarely needed. The 6 hand-curated classes (Dark Knight A/S, Witch A/S, Lahn A, Guardian A) carry the richest skill data; the other 48 ship with seed entries you can polish here as you use them.

The editor has:

- **Sidebar** — class/spec list with a live filter.
- **Skills tab** — full form per skill: ID, name, input string (e.g. `SHIFT + LMB`), key toggle grid, alt-keys grid, protection (SA / FG / iframe / none), damage tier, cooldown, level, CC checkboxes, description, notes, flows-into list, core-effect text.
- **+ New Class** — pick a name and spec; auto-creates a default bundle so the class shows up in the tray menu immediately.
- **Delete Class** — removes the class file *and* every bundle and combo for that class.
- **Export Class / Import Class / Inspect** — for `.bdc` (class-bundle) files.

Renaming a skill ID propagates to every combo step in every bundle that references it.

---

## Adding a new class, bundle, or combo

### A new class

1. **Class Editor → + New Class** — pick a name and spec.
2. Add skill definitions in the **Skills tab**.
3. Switch to **Combo Editor** to author combos against those skills.

If BDO releases a new class, just open the Class Editor and add it.

### A new bundle

A "bundle" is a named group of combos with a shared loadout. Use bundles to keep, for example, your PVE grind setup separate from your PVP setup on the same class.

1. **Combo Editor** → click `+ New Bundle` under any class in the sidebar.
2. Enter a bundle id (lowercase, alnum / underscore — e.g. `grinding` or `pvp_smallscale`).
3. Fill in the loadout fields and start adding combos.

### A new combo

1. Open the bundle you want it under.
2. Click **+ New Combo** at the bottom-left of the right pane.
3. Edit the ID, name, category, step window, description, and steps.
4. Click **Save Bundle**.

---

# Sharing

## Share a combo on bdodojo.com

A short walkthrough for taking a combo you've built in BDO Trainer and publishing it to **https://bdodojo.com** so other players can use it.

### 1. Export the combo from BDO Trainer

1. Open BDO Trainer and right-click the tray icon → **Combo Editor**.
2. In the sidebar, click the bundle that contains your combo (e.g., **Dark Knight → Awakening → default**).
3. Click the combo you want to share so it shows up in the right pane.
4. In the sidebar, click **Export Combo**.
5. Choose where to save the file. It will be saved with a `.bdt` extension — for example `dark_knight_awakening_full_pve_chain.bdt`.

That `.bdt` file is everything the site needs. It carries the combo itself plus your bundle's loadout (hotbar / locked skills / core skill / add-ons) so anyone who imports it later sees the same setup you were using.

> **Want to share a whole bundle instead of one combo?** Click **Export Combos** in the same sidebar — that produces a single `.bdt` containing every combo in the selected bundle.

### 2. Sign in to bdodojo.com

1. Go to **https://bdodojo.com**.
2. Click **Sign in** in the top-right corner.
3. Pick your preferred sign-in method: Discord or email.

You only need to be signed in to upload or comment — other players can browse and download without an account.

### 3. Upload the `.bdt`

1. From the top navigation, click **Upload**.
2. Drag your `.bdt` file onto the upload area, or click to browse for it.
3. The site will read the bundle and show you a preview with:
   - The class and spec it's for
   - The combo name and description from the file
   - The loadout that will travel with it
   - A list of the combos inside

Take a moment to verify it parsed correctly. If anything looks off, cancel and re-export from the trainer.

> Bundles are limited to 1 MB and you can publish up to 10 bundles a day per account.

### 4. Add details before publishing

The upload page lets you polish the listing before it goes public:

- **Title** — what other players see in the feed (defaults to the combo name from your file).
- **Description** — explain what it's for: grinding spot, PVP scenario, gear assumption, anything that helps someone decide if it's right for them.
- **Tags** — pick from the suggested tags (e.g., `pve`, `grind`, `pvp`, `large-scale`) so your combo turns up in filters.
- **YouTube link** *(optional)* — add a video showing the combo in action. The site embeds it on the listing page.

### 5. Publish

Click **Publish**.

Your combo goes **live immediately** — no review queue. You'll be sent to its public page, which has a shareable URL like `https://bdodojo.com/config/abc123`.

The combo also shows up:

- In the **main feed** on the homepage
- Under **your class's browse page** (e.g., "Dark Knight → Awakening")
- Under your profile so people can find your other contributions

### Tips for a good listing

- **One combo per upload, scoped tightly.** "PVE grind — Sycraia upper" is more useful than "all my Witch combos."
- **Mention requirements.** GS or AP/DP thresholds, gear-tier assumptions, whether it relies on specific skill add-ons.
- **Note the loadout you exported with.** Other players see your hotbar / locked skills / core, but they won't know *why* without your description.
- **Add a video if you can.** Even a 30-second clip of the rotation in action makes the listing far more useful.

### If something goes wrong

- **"Couldn't read this bundle"** — the file is probably from an older version of BDO Trainer. Re-export from a 0.5.x or newer build.
- **"Daily limit reached"** — wait until tomorrow; the cap resets at UTC midnight.
- **"This file is too large"** — combos shouldn't normally come close to 1 MB. If yours does, you've probably exported a bundle full of combos rather than a single one. Use **Export Combo** for one, or trim the bundle down.
- **Need to take something down?** Delete it from your profile page, or use the **Report** button on someone else's listing if it violates the site's content rules.

---

## Import a combo from bdodojo.com

1. Browse **https://bdodojo.com** and pick a combo you like.
2. Click **Download `.bdt`** on its page.
3. In BDO Trainer: tray → **Combo Editor → Import Combos**.
4. Pick the file you downloaded.
5. Choose the target bundle (or create a new one).
6. Tick which combos to import. Optionally also import the author's loadout.
7. Click **Preview Changes** to see exactly what will be added or overwritten.
8. Click **Import**.

The combos appear in your tray menu immediately under the target bundle.

---

# Troubleshooting

### Keys aren't being detected while BDO is in focus

**Cause**: BDO runs as an elevated process. Input hooks from a non-elevated process are blocked by Windows UIPI.

**Fix**: Make sure the trainer is running as administrator. It auto-elevates on launch — if the UAC prompt was denied, re-run and accept it.

### The overlay doesn't appear

- Make sure a combo is selected (right-click tray → Class → Spec → Bundle → Combo).
- Check that BDO is in **Fullscreen Windowed** mode — exclusive fullscreen blocks overlays.
- Try pressing `F5` to start/restart the combo.

### Overlay appears but clicks go through to the game

This is **intended**. The overlay is click-through by design. The exception is **Reposition Mode**, where clicks are captured for dragging.

### Steps aren't advancing

- Verify you're pressing the **exact combination** shown.
- Check if your BDO keybinds differ from defaults. If so, update them in tray → **Settings → Key Bindings**.
- Hotbar steps auto-advance — you don't need to press anything for those.
- Check `logs/bdo_trainer.log` for error output.

### Combo resets unexpectedly

The **idle reset timer** resets the combo to step 1 after a period of inactivity. Increase the timeout in tray → **Settings → Timing** (or in `config/combos.yaml` under `timing.idle_reset_timeout_ms`).

### Tray icon doesn't appear

- Some Windows configurations hide new tray icons. Check the system tray overflow area (the `^` arrow).
- Make sure `pillow` is installed (`pip install pillow`).

### macOS: editor opens but tray icon does nothing

The `keyboard` library is intentionally skipped on macOS without root. The tray menu still works for combo selection / editor opening / settings; only the global F5–F8 hotkeys are disabled.

### macOS: editor dialogs disappear behind the editor

Fixed in 0.4.x – 0.5.x. If you still see it on a new dialog type, it's a regression — please file an issue.

### My character does something unexpected

The trainer **only displays information** — it does **not** send any keystrokes to the game. If your character is performing unexpected actions, it's not caused by this tool.

### Why does it need admin?

BDO runs as an elevated process. On Windows, [User Interface Privilege Isolation (UIPI)](https://learn.microsoft.com/en-us/windows/win32/winmsg/about-hooks#uipi) prevents lower-privilege processes from installing hooks into higher-privilege processes. `main.py` handles this automatically via `ShellExecuteW` with `runas`.

---

# Technical reference

> Most users don't need anything below this line. Everything past here is for developers, modders, and people who want to understand the file formats or hack on the codebase.

---

## Project structure

```
bdo-trainer/
├── main.py                          # Entry point — wires everything, auto-elevates admin
├── spec.md                          # Original feature spec
├── requirements.txt                 # pyyaml, pystray, pillow, keyboard, pynput
├── run.bat                          # Windows launcher (auto-elevates, installs deps)
├── run.sh                           # macOS / Linux launcher (venv, deps, permission notes)
├── setup.py                         # Package setup
│
├── data/
│   └── classes/                     # 54 class definitions — ships with the app
│       ├── dark_knight_awakening.yaml
│       ├── dark_knight_succession.yaml
│       └── ... (54 files)
│
├── config/
│   ├── combos.yaml                  # Global settings (hotkeys, key_bindings, display, timing,
│   │                                # active_bundle_per_class)
│   ├── combos/                      # User content — combo bundles
│   │   └── <class>_<spec>/
│   │       └── <bundle_id>/
│   │           ├── _bundle.yaml     # Bundle metadata + loadout
│   │           └── <combo_id>.yaml  # One file per combo
│   ├── classes/                     # 0.4.x legacy archive (auto-created during migration)
│   │   └── _legacy/
│   └── overlay_position.json        # Auto-generated — saved overlay anchor position
│
├── src/
│   ├── __init__.py                  # __version__
│   ├── combo_loader.py              # ClassLoader + BundleLoader + SettingsLoader + AppLoader facade
│   ├── input_monitor.py             # InputMonitor — keyboard + mouse via pynput
│   ├── platform.py                  # Click-through helpers, font detection
│   ├── settings_gui.py              # SettingsWindow — tabbed settings GUI
│   ├── tray.py                      # TrayManager — system tray + four-level menu
│   ├── updater.py                   # Auto-updater (GitHub Releases)
│   ├── overlay/                     # Transparent in-game overlay
│   │   ├── __init__.py
│   │   ├── core.py                  # ComboOverlay — coordinator, queue scheduler
│   │   ├── renderer.py              # OverlayContext + OverlayRenderer
│   │   ├── combo_player.py          # Playback state machine + animations
│   │   ├── hold_bar.py              # Hold-step progress bar
│   │   ├── setup_guide.py           # 4-page recommendations overlay
│   │   └── reposition.py            # Drag-to-move + persistence
│   ├── editor/
│   │   ├── __init__.py              # Re-exports ComboEditorWindow + ClassEditorWindow
│   │   ├── theme.py                 # Solarized Dark colours + force_dialog_to_front helper
│   │   ├── combo_window.py          # ComboEditorWindow + ImportComboBundleDialog
│   │   ├── class_window.py          # ClassEditorWindow
│   │   ├── combo_editor.py          # ComboEditor widget (sidebar list + step builder)
│   │   ├── skill_editor.py          # SkillEditor widget (sidebar list + skill form)
│   │   └── portability.py           # .bdt / .bdc pack/unpack/validate
│   └── utils/
│       └── keys.py                  # Key display names + outline offsets
│
├── scripts/
│   ├── seed_class_shells.py         # Idempotent: create empty class shells for any missing BDO class
│   └── migrate_class_yaml.py        # 0.4.x → 0.5.x layout migration (auto-runs on launch)
│
├── tests/
│   └── test_basic.py
├── doc/images/                      # Screenshots
├── logs/                            # Runtime logs
├── CHANGELOG.md
├── THREAD_SUMMARY.md                # Architecture snapshot + historical task records
├── README.md                        # This file
└── .gitignore
```

### Python dependencies

| Package | Purpose |
|---|---|
| `pyyaml` | Parse YAML config / class / bundle files |
| `pystray` | System tray icon and menu |
| `pillow` | Image support for the tray icon (pystray dependency) |
| `keyboard` | Global hotkeys (`F5`–`F8`) — Windows only |
| `pynput` | Low-level keyboard + mouse listener hooks for step detection |
| `tkinter` | Overlay window + canvas + all GUIs (Python stdlib) |
| `ctypes` | Win32 click-through APIs (Python stdlib) |

---

## Configuration files

### Global settings — `config/combos.yaml`

Global settings only — no skill or combo data lives here.

```yaml
settings:
  default_combo_window_ms: 250

  display:
    show_protection_type: true
    show_cc_type: true
    show_key_overlay: true
    highlight_protected_skills: true

  hotkeys:
    start_combo: "F5"
    stop_combo: "F6"
    next_step: "F7"
    reset_combo: "F8"

  key_bindings:                    # BDO action → physical key
    Move Forward: "w"
    Move Back: "s"
    Move Left: "a"
    Move Right: "d"
    LMB: "lmb"
    RMB: "rmb"
    MMB: "mmb"
    Sprint: "shift"
    Jump: "space"
    Q: "q"
    E: "e"
    F: "f"
    X: "x"
    Z: "z"

  timing:
    step_highlight_duration_ms: 500
    transition_delay_ms: 100
    auto_advance: false
    idle_reset_timeout_ms: 10000

  active_bundle_per_class:         # Persisted across launches
    "Dark Knight/Awakening": "default"
    "Witch/Succession": "grinding"
```

All of these can be edited through the **Settings GUI** (right-click tray → Settings).

### Class definitions — `data/classes/<slug>.yaml`

Class definitions ship with the app and contain **skills only**. The slug is `<class>_<spec>` lowercased with spaces replaced by underscores.

```yaml
class: Dark Knight
spec: Awakening
skills:
  spirit_hunt:
    name: Spirit Hunt
    input: W + RMB
    keys: [w, rmb]
    protection: SA
    cc: [stiffness]
    damage: high
    cooldown_ms: 3000
    description: Forward-dashing slash with super armor.
    flows_into: [shattering_darkness]
    core_effect: "Core: Spirit Hunt"
    notes: Core gap-close opener.

  shattering_darkness:
    name: Shattering Darkness
    input: SHIFT + LMB
    keys: [shift, lmb]
    protection: FG
    cc: [down_attack]
    damage: high
```

### Combo bundles — `config/combos/<slug>/<bundle_id>/`

User content lives here. Each bundle is a directory containing one `_bundle.yaml` (loadout + metadata) plus one YAML per combo.

```
config/combos/dark_knight_awakening/
├── default/
│   ├── _bundle.yaml
│   ├── full_pve_chain.yaml
│   ├── awakening_main_dps.yaml
│   └── ...
└── pvp/                              # Optional second bundle
    ├── _bundle.yaml
    └── protected_engage.yaml
```

**`_bundle.yaml`** — bundle metadata + loadout:

```yaml
class: Dark Knight
spec: Awakening
bundle_id: default
name: Default
description: PVE grinding setup.
locked_skills:
  - name: Smoky Haze
    reason: Lock from skill bar to prevent misinputs during movement chains.
hotbar_skills:
  - "Flow: Spirit Blaze"
  - Shadow Strike
  - Grip of Grudge
core_skill:
  recommended: Seed of Catastrophe
  effect: Super Armor during the skill (with Core)
  reason: Adds full SA to the highest-damage nuke.
skill_addons:
  pve:
    - skill: Shattering Darkness
      addon_1: Extra AP Against Monsters +20 for 7 sec
      addon_2: Attack/Casting Speed +7% for 7 sec
```

**`<combo_id>.yaml`** — one combo per file:

```yaml
combo_id: full_pve_chain
class: Dark Knight
spec: Awakening
bundle_id: default
category: pve                        # pve | pvp | movement
name: Full PVE Chain
difficulty: intermediate
combo_window_ms: 300
description: Full grind rotation.
steps:
  - skill: spirit_hunt
    note: Engage
  - skill: shattering_darkness
  - skill: flow_bombardment
    hold_ms: 1500
    note: Hold to channel
```

### Combo step format

| Field | Required | Description |
|---|---|---|
| `skill` | Yes | Skill ID — must match a key in the parent class's `skills` section |
| `note` | No | Short contextual hint displayed below the step |
| `hold_ms` | No | Duration in ms for hold/channel skills (displays a progress bar) |
| `input` | No | Override the human-readable input string from the skill definition |
| `keys` | No | Override the canonical key list from the skill definition |
| `alt_keys` | No | Alternative key combo that also satisfies this step |

`input` and `keys` are normally resolved from the skill definition — only override them when a combo step uses a non-default input (e.g., a directional follow-up).

### Valid key names

`w`, `a`, `s`, `d`, `shift`, `ctrl`, `alt`, `space`, `tab`, `lmb`, `rmb`, `mmb`, `q`, `e`, `f`, `x`, `z`, `r`, `c`, `v`, `hold`, `hotbar`, `down`

### Key remapping

If your in-game BDO bindings differ from defaults, edit `key_bindings` in `config/combos.yaml` (or use the **Settings GUI**). The trainer translates these into the canonical key names that combo steps use.

Example for QE-movement / AD-abilities (full swap):

```yaml
key_bindings:
  Move Left: "q"
  Move Right: "e"
  Q: "a"
  E: "d"
```

The loader will warn in the log if you've half-configured a swap (e.g., `Q: "a"` without also changing `Move Left`).

---

## Bundle file formats — `.bdt` and `.bdc`

Both formats are **gzip-compressed JSON** with a discriminator `kind` field so a single decoder handles either type.

### `.bdt` — combo bundle (`kind = "combos"`)

Carries:

- Class + spec + bundle id + name + description
- Loadout (hotbar / locked / core / addons)
- Combos keyed by combo_id, each with steps

Used to share combo rotations between players. The Combo Editor's **Export Combo** button creates a single-combo bundle that still carries the parent's loadout for context.

### `.bdc` — class bundle (`kind = "class"`)

Carries:

- Class + spec
- Class definition (skills only — no combos, no loadout)

Used to share full class skill libraries. The Class Editor's **Export Class** button creates one.

### v1 `.bdt` (legacy)

`.bdt` files from 0.4.x carried both class metadata and combos in a single `config` field. They still decode and route through the class importer; their combos are surfaced via the import dialog with categories backfilled.

---

## Architecture

### Module responsibilities

| Module | Role |
|---|---|
| `main.py` | Entry point. Auto-elevates admin (Windows). Detects + runs migration. Wires loaders, overlay, tray, hotkeys. |
| `src/combo_loader.py` | `ClassLoader` (data/classes/) + `BundleLoader` (config/combos/) + `SettingsLoader` (config/combos.yaml) + `AppLoader` facade. The legacy `ComboLoader` symbol is preserved as a compatibility shim. |
| `src/input_monitor.py` | `InputMonitor` — pynput keyboard + mouse hooks on daemon threads. Tracks pressed-key state. Applies key remapping. |
| `src/overlay/core.py` | `ComboOverlay` — coordinator that owns the tkinter root and provides a thread-safe `schedule()` queue. |
| `src/overlay/renderer.py` | `OverlayContext` (shared state) + `OverlayRenderer` (canvas-based outlined text). |
| `src/overlay/combo_player.py` | `ComboPlayer` — playback state machine, slide/fade animations, hold bar integration, next-skill preview pulse. |
| `src/overlay/hold_bar.py` | `HoldBar` — animated hold-step progress bar. |
| `src/overlay/setup_guide.py` | `SetupGuide` — 4-page recommendations overlay (reads from active bundle's loadout). |
| `src/overlay/reposition.py` | `RepositionHandler` — drag-to-move + persistence. |
| `src/tray.py` | `TrayManager` — system tray and four-level menu (class → spec → bundle → combo). |
| `src/settings_gui.py` | `SettingsWindow` — tabbed settings GUI. |
| `src/updater.py` | Auto-updater (GitHub Releases). Opt-in config replacement with timestamped backup. |
| `src/editor/combo_window.py` | `ComboEditorWindow` + `ImportComboBundleDialog` + `BundleInspectorDialog`. |
| `src/editor/class_window.py` | `ClassEditorWindow`. |
| `src/editor/combo_editor.py` | `ComboEditor` widget. |
| `src/editor/skill_editor.py` | `SkillEditor` widget. |
| `src/editor/portability.py` | `.bdt` / `.bdc` pack/unpack with v2 schema + v1 fallback. |
| `src/editor/theme.py` | Solarized Dark colours + `force_dialog_to_front` macOS helper. |
| `src/platform.py` | Click-through helpers, font detection. |
| `src/utils/keys.py` | Key display name mapping and outline offset constants. |

### Threading model

```
┌──────────────────────────────────────────────────────────────┐
│  Main Thread                                                 │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  tkinter mainloop                                      │  │
│  │  • ComboOverlay (overlay rendering)                    │  │
│  │  • SettingsWindow, ComboEditorWindow, ClassEditorWindow│  │
│  │  • All UI updates routed via overlay.schedule(...)     │  │
│  │    which uses a queue.Queue polled by root.after()     │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  Daemon Threads                                              │
│  ┌─────────────────┐  ┌──────────────────────────────────┐   │
│  │  pystray         │  │  pynput (InputMonitor)           │   │
│  │  (TrayManager)   │  │  • Keyboard listener (daemon)    │   │
│  │  (daemon thread) │  │  • Mouse listener   (daemon)     │   │
│  └─────────────────┘  └──────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│  keyboard library — internal hook thread (Windows / sudo)    │
└──────────────────────────────────────────────────────────────┘
```

**Cross-thread UI updates** go through a `queue.Queue` polled by the Tk main thread (added in 0.4.x to fix a Python 3.14 GIL crash on macOS). Foreign threads enqueue work; the main thread drains the queue every 50 ms.

### Key detection pipeline

1. **pynput** hooks capture raw keyboard and mouse events on daemon threads.
2. Events are translated through the **key remap table** (built from `key_bindings` in settings).
3. The current pressed-key set is compared against the current step's `keys` (and `alt_keys` if present).
4. On a full match, the combo advances. The UI update is enqueued for the main thread.
5. For **hold steps**, matching keys start the hold bar; releasing early or completing the hold advances the combo.

### Overlay rendering details

Step layout, top to bottom:

1. **Combo name** — grey italic 14pt
2. **Skill name** — gold bold 32pt + `[PROTECTION]` badge (SA, FG, iframe)
3. **Input keys** — white 22pt
4. **Hold bar** — animated progress bar (only on hold steps)
5. **Note** — grey 14pt (optional)
6. **Step counter** — dark grey 12pt
7. **Next skill preview** — grey 14pt: `next ▸ Skill Name · Input Keys`

Transition: when the correct keypress is detected, old content is tagged and a green `✓ Skill Name` confirmation appears. Old content slides upward at 3 px/frame and fades. After ~80 ms delay, the new step renders and slides up 40 px with an ease-out curve (~120 ms). Once the slide completes, input is armed for the new step.

The next-skill preview pulsates between grey and gold (~1.75 s cycle) when the upcoming step is a hold skill.

---

## macOS specifics

macOS support is **tray + editor only** — BDO doesn't run on macOS, so the in-game overlay isn't useful there.

- **Tray-only by default** — the overlay window is suppressed unless `--overlay` is passed.
- **`keyboard` library skipped** without root (it Abort traps when its event-tap listener thread starts unprivileged). Editor + tray still work; global hotkeys do not.
- **Accessibility permissions** are required for `pynput`. On first launch the app pops the native macOS Accessibility prompt via `AXIsProcessTrustedWithOptions`.
- **Modal dialog z-order** — extensive workarounds in place (`force_dialog_to_front`, `_ask_string` wrappers, etc.) so editor dialogs reliably stay above the parent window.
- **`--editor` flag** launches just the editor windows with no tray.

```
./run.sh                # Tray + editor (recommended)
./run.sh --editor       # Editor windows only
./run.sh --overlay      # Force the overlay on (rarely useful on macOS)
```

---

## Migration from 0.4.x

If you're upgrading from 0.4.x and have `config/classes/*.yaml` files in place, the trainer **migrates automatically on first launch**. Each old class file becomes:

- `data/classes/<slug>.yaml` (skills only)
- `config/combos/<slug>/default/_bundle.yaml` (loadout — locked / hotbar / core / addons)
- `config/combos/<slug>/default/<combo_id>.yaml` (one file per combo)

The original is moved to `config/classes/_legacy/` rather than deleted, so the migration is reversible.

To preview without writing anything:

```
python -m scripts.migrate_class_yaml --dry-run
```

---

## License

MIT License
