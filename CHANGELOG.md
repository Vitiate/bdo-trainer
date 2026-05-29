# Changelog

All notable changes to this project are documented in this file.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and adheres to [Semantic Versioning](https://semver.org/).

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

[0.4.2]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.2
[0.4.1]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.1
[0.4.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.4.0
[0.3.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.3.0
