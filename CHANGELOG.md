# Changelog

All notable changes to this project are documented in this file.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and adheres to [Semantic Versioning](https://semver.org/).

## [0.5.3] — 2026-05-31

### Added
- **CC Skills overlay panel** — new tray menu entry **Show CC Skills**.
  Toggle it on to see a list of every CC-applying skill for the
  currently-selected class: skill name, CC tags, and the physical key
  combo to trigger it. Each row uses outlined text so it stays readable
  over the BDO client.
  - **Cooldown wipe.** When you press a skill's keys, the row dims to
    grey and "fills back in" left-to-right as the cooldown ticks down,
    using the skill's `cooldown_ms` as the timer.
  - **PvE / PvP-only annotations.** CC tags are parsed from the skill's
    notes and labelled `(PvE)` / `(PvP)` when an effect only applies in
    one mode (e.g. `Floating (PvE)` on Cleansing Flame).
  - **Roman-numeral grades stripped** from displayed names so
    "Glorious Advance IV" reads as "Glorious Advance".
  - **Hotbar-only skills are skipped** — the panel only lists skills
    that have a fixed physical key combo to listen for.
  - **Repositionable.** The panel can be dragged independently of the
    combo overlay while Reposition Mode is active; its position saves
    to `config/cc_panel_position.json`.
  - **Persisted across launches.** The toggle state is stored in
    `config/combos.yaml` under `settings.show_cc_panel`.
- **Secondary input taps** in `InputMonitor` (`add_tap` /
  `remove_tap` / `clear_taps`) so multiple consumers can listen for key
  combinations at once. The combo player keeps its exclusive
  `set_target` channel; the new CC panel uses taps so the two coexist.
- **22 Guardian combos** under `config/combos/guardian_awakening/` and
  `config/combos/guardian_succession/` — full PvE rotations, PvP catch
  / mobility chains, Gate Crasher cancel combos, anti-evasion variants,
  and the Bread 'n' Butter family. Existing legacy Guardian Awakening
  combos (`awakening_main_combo_1/2/3`, `infinite_combo_1`) were
  removed in favour of the new set.
- **Pulverization skill** added to `data/classes/guardian_awakening.yaml`
  so the new PvP combos resolve.

### Changed
- **Reposition mode handles the CC panel.** `RepositionHandler` now
  routes a drag to whichever target's anchor is closer — combo overlay
  or CC panel — and saves both positions when reposition mode ends.
- **Guardian Awakening loadout** updated with rationale for each locked
  / hotbarred skill (Lock & hotbar Fireborne Rupture, hotbar God
  Incinerator + Cleansing Flame as awakening swaps, etc.) so the setup
  guide matches community recommendations.

## [0.5.2] — 2026-05-30

### Fixed
- **macOS startup crash in tray-only mode.** The pynput keyboard
  listener thread was being started even when the overlay window was
  suppressed; on macOS under Python 3.14 it could throw
  `KeyError: 'AXIsProcessTrusted'` from a pyobjc lazy-import bug.
  When `show_window=False` (the macOS default), the input listener
  daemon threads are no longer started — they aren't needed without
  an in-game overlay to drive. The `InputMonitor` instance is still
  constructed so the player and hold bar still get their dependency.

### Changed
- **Removed three internal tooling scripts** (`scripts/scrape_bdocodex.py`,
  `scripts/build_class_yaml.py`, `scripts/apply_skill_patches.py`).
  These were one-off internal tools used to seed the initial 48 class
  skill libraries; they aren't part of the shipped product and have no
  place in the user-facing repo. The shipped class skill data stays
  exactly as-is — `data/classes/<slug>.yaml` is the authoritative
  source going forward, edited via the **Class Editor**.

### Documentation
- **README restructured.** Reorganised so a new user can install,
  start a combo, and share to bdodojo.com without scrolling past
  architecture details and YAML schemas. Layout is now Getting
  started → Editing combos → Sharing → Troubleshooting → (divider) →
  Technical reference.
- **Added a full `bdodojo.com` upload walkthrough** to the README —
  export from the Combo Editor, sign in, upload, polish the listing,
  publish — plus tips for good listings and troubleshooting common
  upload errors.

## [0.5.1] — 2026-05-30

### Added
- **All 54 BDO classes shipped with skill data.** Every skill has a
  name, description, cooldown; ~50–60 % also have parsed input keys,
  protection (SA / FG / iframe / none), and CC tags. The 6 hand-
  curated classes (Dark Knight A/S, Witch A/S, Lahn A, Guardian A)
  carry the richest data; the rest ship with seed entries that can be
  polished through the Class Editor.
- **Live filter input** above each editor's class list. Live, case-
  insensitive narrowing — Combo Editor matches against class + spec
  + bundle id/name; Class Editor matches against class + spec.
- **Editable combo IDs.** The Combo Editor's Combo ID field is now an
  Entry instead of a Label. Renaming sanitises (lowercase / underscore
  / alnum), checks for duplicates within the category, and re-keys the
  in-memory combos dict; the disk file is moved at the next save.
- **Per-combo `.bdt` export.** New "Export Combo" button next to
  "Export Combos" exports the currently-selected combo as a single-
  combo bundle, with the parent bundle's loadout (locked / hotbar /
  core / addons) embedded for context.
- **Tray-only mode on macOS.** Defaults to no overlay window so the
  tray + editor flow is usable without an empty transparent window
  obscuring the screen. `--overlay` forces it on; `--no-overlay` is
  the explicit opt-out flag.
- **scripts/seed_class_shells.py** — idempotent script that creates
  empty class shells for any BDO class missing from `data/classes/`.

### Changed
- **Combo Editor** tolerates `hotbar_skills` entries that are dicts
  (the legacy richer format with `name` / `reason` / `hotbar_key`).
  Entries are rendered as `name :: reason` lines and saved back as
  dicts when a reason is present. Fixes a TypeError on Witch /
  Awakening's bundle.
- **Native prompt z-order on macOS.** Every `simpledialog.askstring`
  call (New Bundle, Rename Bundle, Combo ID Conflict, Rename Class,
  New Target Bundle) now goes through a wrapper that drops the
  parent's `-topmost` for the duration of the prompt, so the prompt
  doesn't sink behind the editor.
- **Build script polish.** Arrow-glyph keybinds (↑/↓/←/→) now map to
  `w`/`s`/`a`/`d` in the canonical key list. `"Absolute:"` skill-name
  prefixes route to Succession only.

## [0.5.0] — 2026-05-30

### Added
- **Combo library.** Class definitions are split from combo content.
  Skills now live under `data/classes/<slug>.yaml` (ships with the app);
  combos live under `config/combos/<slug>/<bundle_id>/`, one file per
  combo, alongside a `_bundle.yaml` carrying the bundle's loadout.
- **Multiple bundles per class/spec.** Each bundle has its own
  `bundle_id`, name, description, locked-skills list, hotbar setup,
  core skill, and PVE add-ons. The tray menu drills four levels deep:
  class → spec → bundle → combo.
- **Active bundle persistence.** The active bundle for each class/spec
  is remembered in `config/combos.yaml` under
  `settings.active_bundle_per_class` so the in-game setup guide
  always shows the loadout for whatever bundle the user is running.
- **Two editor windows.** The single Class & Combo Editor was split:
  - **Combo Editor** — sidebar tree of class → bundle, right pane has
    bundle metadata + loadout above the existing combo step builder.
    Bundle CRUD (new / rename / delete) plus `.bdt` export, import,
    and inspect.
  - **Class Editor** — sidebar of class/spec, Skills tab only. Bundle
    CRUD (`.bdc` export, import, inspect).
- **Tray menu has separate "Combo Editor" and "Class Editor" entries.**
- **`.bdt` v2 schema.** Combo bundles now carry `bundle_id`, `name`,
  `description`, `loadout` (locked / hotbar / core / addons), and
  `combos` keyed by combo_id. Importing a `.bdt` lets you optionally
  pull the loadout into the target bundle.
- **`.bdc` extension** for class-only bundles (skills only, no
  combos, no loadout).
- **Auto-migration on launch.** When the trainer detects legacy
  `config/classes/*.yaml` files, it splits them into the new layout
  before constructing the loaders. The originals are archived to
  `config/classes/_legacy/` rather than deleted.
- **`scripts/migrate_class_yaml.py`** — manual migration script with a
  `--dry-run` mode that prints what would happen.

### Changed
- `src/combo_loader.py` rewritten as four pieces:
  `ClassLoader`, `BundleLoader`, `SettingsLoader`, plus an
  `AppLoader` facade. The `ComboLoader` symbol is preserved as a
  compatibility shim that returns `AppLoader`, so existing callsites
  in `main.py`, the overlay, and the tray didn't change shape.
- `src/editor/portability.py` rewritten for the v2 bundle schema with
  a discriminator (`kind = "combos" | "class"`). v1 `.bdt` files from
  0.4.x continue to decode and route through the class importer.
- The combo step format gained a stable `category: pve|pvp|movement`
  field (instead of being inferred from the legacy
  `pve_combos` / `pvp_combos` / `movement_combos` section a combo
  lived in).

### Migration
Users upgrading from 0.4.x get an automatic, in-place migration the
first time the new release runs. Each existing
`config/classes/<class>_<spec>.yaml` produces:
- `data/classes/<slug>.yaml` (skills only)
- `config/combos/<slug>/default/_bundle.yaml` (loadout)
- `config/combos/<slug>/default/<combo_id>.yaml` (one per combo)

The original file is moved to `config/classes/_legacy/`.

## [0.4.2] — 2026-05-28

### Fixed
- **Updater dialog stays in front on macOS.** The update window and its
  follow-up prompts (replace configs?, update installed, update failed)
  now reliably appear above the parent window. Previously these could
  land behind the editor on macOS — same z-order bug we already fixed
  for the editor dialogs in 0.4.0.

### Internal
- Added a local `_force_to_front` helper that suspends the parent
  Toplevel's `-topmost` for the dialog's lifetime and lifts the dialog
  across several ticks so it outlasts macOS reordering.
- All `messagebox.*` calls in the updater now go through a
  `_show_messagebox` wrapper that briefly drops the update window's
  `-topmost` so the native message box can land above it.

## [0.4.1] — 2026-05-28

### Changed
- **Updater — opt-in config replacement.** After clicking *Download &&
  Install*, the updater now asks whether to replace the existing
  `config/` with the one from the new release. Default is **No** (keep
  your settings).
- **Updater — timestamped config backup.** When the user opts in to
  replacing configs, the live `config/` is moved to
  `config_backup_<YYYYMMDD-HHMMSS>/` before the release's `config/` is
  extracted. The success dialog tells the user where the backup lives.
- **Updater — clearer post-install instructions.** The success dialog
  now explicitly tells the user to fully exit BDO Trainer before doing
  anything else, since the running process still holds stale module
  imports and continuing to use it can crash the app.

### Internal
- `install_zipball()` returns the backup directory path (or `None`) and
  accepts a `replace_config` flag so callers/tests can drive both modes.
- `.gitignore` now covers `_update/`, `logs/`, and
  `config_backup_*/` so updater artefacts don't end up in commits.

## [0.4.0] — 2026-05-28

### Added
- **Class & Combo portability** — new `.bdt` (gzipped JSON) bundle format.
  - **Export** — save the selected class as a `.bdt` file.
  - **Import** — open a `.bdt`; choose between importing the whole class
    (with replace / rename collision handling) or merging selected combos
    into an existing class. Combo-id collisions prompt for a new id.
  - **Export All** — bulk-export every loaded class as `.bdt` files into
    a chosen folder.
  - **Inspect** — read-only viewer for any `.bdt` file, with Combos and
    Skills tabs and missing-skill warnings.
  - **Preview Changes** — diff dialog inside the import flow that lists
    combos to add, combos that would overwrite, and skills that would be
    pulled in alongside the selected combos.
- **Solarized Dark theme** applied across the Settings, Editor, and tray
  icon. The in-game overlay keeps its high-contrast subtitle palette so
  it stays readable over the BDO client.
- **Editable skill IDs** — the Skills tab in the editor now exposes the
  skill ID as an editable Entry. Renaming an ID propagates automatically
  to `flows_into` references and to every combo step that referenced
  it, so combos never silently break after a rename.
- **Combo step dropdown improvements** — step rows now show the skill
  *name* (with the id in parentheses), sorted alphabetically by name.
  Stale references to deleted skills surface as `⚠ id (missing)` rather
  than disappearing.
- **Inline "detect" capture button** next to every key binding and
  hotkey row in Settings. Click it, press the key, done — useful for
  users with hardware-mapped keys.
- **`--editor` CLI flag** — `python main.py --editor` (or
  `./run.sh --editor`) launches just the Class & Combo editor with no
  overlay, no tray, no global hotkey listener. Handy for editing
  configs on macOS without triggering the `keyboard`-library Abort trap.
- **Auto-update support** (`src/updater.py`) — checks the GitHub
  Releases API and offers to download and install newer versions.
- **macOS Accessibility prompt** — `main.py` now triggers the native
  Accessibility-permissions prompt on first run on macOS.

### Changed
- **Mouse-button bindings removed** from the Settings → Key Bindings
  tab and the rebind popup. Class YAMLs still use `lmb`/`rmb`/`mmb` as
  canonical key names for ability inputs; users just no longer bind
  BDO actions to mouse buttons.
- **Cross-thread overlay scheduling** now uses a `queue.Queue` polled
  by the Tk main loop, replacing the previous direct `root.after()`
  calls from foreign threads. Fixes a Python 3.14 GIL-state crash on
  macOS triggered by tray callbacks.
- **`run.sh`** detects existing `.venv` / `venv` directories and
  recreates the venv if it was created on a different OS (Windows
  layout `Scripts/` vs. POSIX `bin/`). Also surfaces a clearer message
  when tkinter is missing inside the venv.
- **Modal dialog stacking on macOS** — Import / Inspect / Preview
  dialogs now stay reliably above the editor window. The editor's
  `-topmost` is suspended for the dialog's lifetime and restored on
  close, fixing the "dialog buried behind editor" issue.

### Fixed
- **macOS GIL crash** when selecting a combo from the tray menu.
- **`keyboard` library abort** on macOS without root: import is skipped
  entirely when not running as root; tray-driven control still works.
- **Half-configured key remap** (e.g., `Q: "a"` without
  `Move Left: "q"`) is now logged as a clear warning instead of silently
  routing two abilities to the same physical key.
- **Settings window crash** when opened via the tray on macOS, caused
  by the same GIL issue as the combo selection.
- **CRLF / LF line endings** normalised across all source files (only
  `run.bat` retains CRLF as a DOS batch file).

### Notes for users
- `config/combos.yaml` `key_bindings` section is now documented in
  the file header. The default layout is still AD-movement / QE-abilities;
  if you swap them in-game, set both halves (e.g., `Move Left: "q"` and
  `Q: "a"`) so the remap is consistent.

## [0.3.0]

Initial editor + setup-guide release. See git history for details.

[0.5.3]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.3
[0.5.2]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.2
[0.5.1]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.1
[0.5.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.0
[0.4.2]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.2
[0.4.1]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.1
[0.4.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.0
[0.3.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.3.0
