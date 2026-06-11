# Changelog

All notable changes to this project are documented in this file.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and adheres to [Semantic Versioning](https://semver.org/).

## [0.5.9] — 2026-06-11

### Fixed
- **"Reset configs to release defaults" no longer hangs.** When the
  user picked Yes on the "replace configs" prompt, `install_zipball`
  used `shutil.move(config, config_backup_<ts>)` to clear the live
  config dir before installing the release's defaults. On Windows
  that move reliably failed with `PermissionError` because the
  running trainer still held open handles into `config/`
  (`combos.yaml`, `overlay_position.json`, the editor's bundle
  paths). The failed move + the watchdog from v0.5.8 was the
  "Installing…" hang.
  - The backup phase is now a per-file copy that retries / skips
    locked files instead of moving the directory.
  - `config/` is no longer cleared before the new files are written;
    the release's defaults overwrite the live ones in place, with
    the same retry/skip policy as every other file in the install.
- **Replace-configs prompt rewritten** so users understand it's the
  destructive option and that NO is the right answer for almost
  everyone. Most "Installing…" hangs in v0.5.7 / v0.5.8 came from
  users picking Yes thinking it was a benign reset.

## [0.5.8] — 2026-06-11

### Fixed
- **Updater no longer hangs on "Installing…".** Defensive patches to
  the auto-update flow:
  - **Per-file resilience.** `install_zipball` no longer aborts the
    whole update if one file can't be written (Windows holds locks on
    `.pyc` / `.pyd` files while the trainer is still running, AV
    scanners briefly hold write locks too). Each copy is retried up
    to 3 times with a short backoff; permanently-failed files are
    logged and surfaced in the success dialog with a "restart and
    re-run update to finish" hint.
  - **Watchdog timeout.** If the install hasn't completed within 5
    minutes the dialog now shows a TimeoutError instead of staring at
    "Installing…" forever. Pointer to `logs/bdo_trainer.log` for the
    diagnosis.
  - **Throttled progress callback.** The download loop fired one
    Tk-thread `after(0, …)` per 64 KB chunk, which on a fast
    connection drowned the Tk event queue and could make the UI
    appear frozen. Now throttled to at most once per 256 KB *or*
    100 ms (whichever comes first), with a final flush at EOF.
  - **Better logging** — explicit log lines mark the start of
    download, the start of install, and any per-file failures so
    future hangs are diagnosable from `logs/bdo_trainer.log`.

## [0.5.7] — 2026-06-11

### Fixed
- **Settings window saves now persist.** `SettingsWindow._save_to_yaml`
  read `self.loader.settings_path`, but `AppLoader` didn't expose that
  attribute — the call raised `AttributeError` and saves were silently
  dropped. This affected every Settings tab (key bindings, hotkeys,
  display, timing, and the new Updates channel selector). Added a
  `settings_path` property on `AppLoader` that forwards to the
  underlying `SettingsLoader`. As a side effect: the Stable / Beta
  update channel selector now actually persists across launches.

### Added
- **Maegu Awakening PvP combo set** (courtesy of fafi, guide last
  updated 2026-06-05). Nine combos under
  `config/combos/maegu_awakening/default/`:
  - Two **default protected chains** that form the squishy-killer
    foundation (Hazy Path Spiritforge → Twirling Rhapsody catch
    → Emberclaw Finale → Foxflare Fleche → Foxflare Ambush →
    Twirling Foxflare → Flow: Foxflare Encore → Spirit Parade →
    Flower Shroud disengage; one variant repositions with
    Twirling Retreat early, the other late).
  - **Standard DR combo** — Spiritforged Fan Kick (+10% Air Attack)
    into Emberclaw Slash (-20 DR shred).
  - **Standard Evasion combo** — Foxflare Cleave (-12 Evasion) into
    Emberclaw Slash.
  - **Float Burst variants** — Fan Kick re-float, and a Foxflare
    Ambush opener.
  - **Long 1v1 combos** — two long DR/evasion-shred chains plus a
    knockdown / down-attack variant for downsmash playstyles.
  - Bundle metadata captures the buff/debuff cheatsheet (Charmed +20
    AP, Foxflare Fleche +30% Crit, Emberclaw Slash -20 DR, Foxflare
    Cleave -12 Evasion, Fan Kick +5/+10% Air, Foxflare Stroke +18
    AP, Emberclaw Finale -15% MS), catch lists per spec, and add-on
    suggestions (Twirling Rhapsody = DR, Foxflare Ambush = Crit,
    Charmed = Attack Speed).
- **Maegu Succession PvP priority combo** —
  `config/combos/maegu_succession/default/pvp_dps_priority.yaml`.
  Five tiers: Spiritforge Entry (Hazy Path / Emberclaw Slash /
  backups), Top Priority (Emberclaw Slash for -DP, Foxflare Cleave,
  Twirling Rhapsody, Foxflare Fleche, Flow: Emberclaw Sweep), Core
  DPS (Twirling Foxflare → Flow Foxflare Encore + the rest of the
  awakening kit), Filler (Fan Kick + on-CD repeats), and AoE / Pre-
  Awakening (Constricting Charm / Spirit Sparks / Foxspirit Tag).

## [0.5.6] — 2026-05-31

### Changed
- **Priority combos absorb out-of-turn presses.** Previously the
  priority player only listened for the currently-displayed skill, so
  an accidental press of a lower-tier skill went unrecorded and the
  trainer would re-display that same skill instantly. The player now
  arms a tap for every skill in the combo at start, so any cast —
  intended or not — stamps that skill's cooldown and the resolver
  hides it until the cooldown elapses.
  - Skills sharing an identical key combo are folded into a single
    tap whose cast is attributed to the highest-priority owner, so
    we don't double-burn cooldowns when keys overlap.
  - Re-arms automatically when the user changes their key remap
    while a priority combo is running.

## [0.5.5] — 2026-05-31

### Fixed
- **Priority combo crash on key press.** `InputMonitor._check` and
  `_reset_edge_trigger` iterated `self._taps.values()` while tap
  callbacks could mutate the dict (the priority player re-arms a
  different tap on every press, so each press triggered a
  ``RuntimeError: dictionary changed size during iteration`` from the
  pynput listener thread). Both loops now snapshot the values via
  ``list(...)`` before iterating, so callbacks can add/remove taps
  freely.

## [0.5.4] — 2026-05-31

### Added
- **Priority combos.** Combo files now support a second mode alongside
  sequence playback — `mode: priority` with a `priority:` block of
  tiers, each containing an ordered skill list. The trainer walks tiers
  top-to-bottom and shows the highest-priority skill that's currently
  off cooldown. When you press the displayed skill's keys, it stamps
  the cooldown and re-resolves to the next-highest off-cooldown skill.
  - **`boost_after` rule** promotes a skill into a higher tier
    temporarily after another skill is cast (Witch's Thorns of Denial
    after Voltaic Pulse, for example).
  - **Combo Editor** gains a **Mode** dropdown (sequence | priority).
    Priority mode swaps the Steps editor for a Priority Tiers editor
    with reorderable tiers and skills, plus per-skill `boost_after` /
    `boost_window_ms` / `boost_to_tier` fields. Switching modes
    preserves edits in both blocks until save.
  - **Schema reference** at `docs/priority-combos.md` covers the YAML
    shape, runtime resolution, editor support, and notes for
    bdodojo.com to extend its web editor with the same shape.
- **`PriorityPlayer` overlay component** in `src/overlay/priority_player.py`.
  Reuses `InputMonitor.add_tap` to listen for the displayed skill's
  keys without disturbing the combo player's primary target channel.
  ComboOverlay's lifecycle dispatches by `mode`; setup-guide /
  reposition / pause / resume now route to whichever player is active.
- **Update channels — Stable | Beta.** Tray → Settings → Updates picks
  which GitHub Releases the auto-updater watches:
  - **Stable** (default) uses GitHub's `/releases/latest` — never
    surfaces prereleases.
  - **Beta** lists `/releases?per_page=30` and offers the highest
    version, prerelease or not.
  - The update dialog labels prerelease builds and surfaces the
    current channel.
  - Switching from Beta back to Stable while running a higher version
    won't downgrade — the updater shows an "ahead of channel" notice
    instead of silently rolling you back.
  - Selection persists in `config/combos.yaml` under
    `settings.update_channel`.
- **Witch Awakening priority combo** — `pve_priority_grind`. Three
  tiers: Highest Priority (Voltaic Pulse / Lightning Blast / Toxic
  Flood), Main DPS (Fissure Wave, Thunderstorm, Yoke of Ordeal,
  Barrage of Lightning, Thorns of Denial with `boost_after:
  voltaic_pulse`), Filler (Detonative Flow, Earthen Eruption,
  Equilibrium Break).
- **Two missing skills added** to `data/classes/witch_awakening.yaml` —
  Thorns of Denial (`shift+q`, 9 s cd) and Earthen Eruption
  (`f`, 8 s cd) — so the new priority combo resolves cleanly.

### Changed
- `src/editor/portability.py` — `collect_skill_ids_used_by_combo` now
  also walks `priority:` blocks (and `alt_skill` on sequence steps),
  so `.bdt` exports include every referenced skill.
- Toxic Flood notes corrected from "-20 Magic DR" to "-15 Magic DP"
  to match the in-game tooltip.

### Internal
- `SettingsLoader._persist_top_level` reused for the new
  `update_channel` key — same shape as `show_cc_panel`.
- `fetch_latest_release` now takes a `channel` arg; `check_and_prompt`
  forwards the user's preference from `main.py`.

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

[0.5.9]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.9
[0.5.8]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.8
[0.5.7]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.7
[0.5.6]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.6
[0.5.5]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.5
[0.5.4]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.4
[0.5.3]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.3
[0.5.2]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.2
[0.5.1]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.1
[0.5.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.5.0
[0.4.2]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.2
[0.4.1]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.1
[0.4.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.0
[0.3.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.3.0
