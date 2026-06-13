# Changelog

All notable changes to this project are documented in this file.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and adheres to [Semantic Versioning](https://semver.org/).

## [0.6.4-beta.17] — 2026-06-13

### Fixed
- **Chain renderer was ignoring the priority sort.** The
  player's score-based frontier ordering from beta.16 was
  computed correctly, but the renderer painted nodes by YAML
  declaration order within each tier column, so the visual
  order never changed. Now each tier column re-sorts by the
  frontier rank — highest-priority skill at the top of the
  column.

## [0.6.4-beta.16] — 2026-06-13

### Changed
- **Frontier sort scores by CC weight + PvP damage**, not just
  role bucket. Within a bucket the strongest skill floats up:
  CC weight (grab > stun/KD > knockback > float > bound >
  stiffness) dominates, PvP damage % parsed from the bdocodex
  notes acts as a tiebreaker, and smash tags get an additional
  bonus while a smash window is open.
- Charmed's primary key is now **S + SPACE** (the reliable
  cast). Bare SPACE remains as the alt — it only resolves when
  cast during another skill, which makes the bare-SPACE primary
  misleading.

### Added
- `pvp_damage_pct` parsing in `priority_player._build_row()`.
  Reads the per-skill "X% damage in PvP only" line from the
  notes blob; can be overridden by adding `pvp_damage_pct:` to
  either the skill data or the combo entry.

## [0.6.4-beta.15] — 2026-06-13

### Fixed
- **Chain chart wasn't actually moving.** beta.14 had two bugs.
  (1) the spotlight anchor was clamped at column 1, so a tier-0
  → tier-1 advance produced zero pan delta. (2) the spotlight
  *target* was `frontier_ids[0]`, but that list is sorted by role
  priority — after casting an opener, lower-tier catches still
  rank ahead of burst skills, so the anchor never moved off tier
  0. The spotlight is now anchored to chain progress (`cursor
  tier + 1`) and the chart's spotlight column is centred on the
  overlay so every tier advance produces a visible slide.

## [0.6.4-beta.14] — 2026-06-13

### Changed
- **Chain flowchart now spotlights the next correct skill.** The
  best frontier node always renders one column from the left of
  the overlay; as you advance, the chart slides left so older
  tiers drift off and future tiers stay visible to the right.
  The pan eases over ~5 frames at the 150 ms tick rate so it
  feels like a smooth scroll, not a snap.
- **Icons fade by node state.** Best frontier = full brightness;
  other frontier alternatives = 85 %; cursor = 65 %; history =
  30 %; idle / off-tier = 20 %. Implemented via alpha-channel
  scaling in `IconLoader`, cached per (size, slug, name, dim
  bucket) so repeated renders don't re-process the image.

## [0.6.4-beta.13] — 2026-06-13

### Fixed
- **`maegu_awakening.yaml` was unparseable.** Two `input:` values
  (Spirit Parade, Heavenly Return) contained the substring
  `Flow: Hanpuri` unquoted — PyYAML treats the inner colon as a
  mapping separator and bails on the whole file. Net effect: the
  Maegu class loaded with zero skills and the new chain combo
  warned `no resolvable skills`. Both lines are now single-quoted.

## [0.6.4-beta.12] — 2026-06-13

### Changed
- **`run.sh` now picks a known-good Python version** instead of
  taking whatever `python3` resolves to. Preference order is
  3.13 → 3.12 → 3.11 → fallback. macOS users on Python 3.14 get
  a loud warning about the pyobjc lazy-import bug and a clear
  next step (install 3.13, delete `.venv/`, re-run).
- **Existing venv is recreated** automatically when its Python
  doesn't match what the script would pick now (e.g. you
  installed 3.13 after the .venv was built on 3.14).
- **macOS pyobjc smoke test** runs after dependency install so
  the user knows immediately if input monitoring will be
  disabled at runtime.
- **`run.bat` mirrors the same logic** on Windows via the
  `py -X.Y` launcher: tries `py -3.13`, `py -3.12`, `py -3.11`,
  then falls back to `python` on PATH. Recreates the venv when
  the version drifts.

## [0.6.4-beta.11] — 2026-06-13

### Fixed
- **Detect the macOS pynput lazy-import bug at startup** instead
  of letting the listener thread crash on every key press. Under
  Python 3.14 with current pyobjc, pynput's macOS keyboard
  listener calls ``HIServices.AXIsProcessTrusted()`` on its
  first event and the lazy-importer raises
  ``KeyError: 'AXIsProcessTrusted'`` — the listener thread dies
  silently, the trainer's main loop survives, and every press
  spams a traceback in the log.
  The trainer now probes the symbol from the main thread at
  module-import time. If it can't resolve, ``INPUT_AVAILABLE``
  is forced to ``False`` and a one-line warning explains the
  fix (recreate the venv on Python 3.12 / 3.13, or upgrade
  ``pyobjc-framework-ApplicationServices``). The trainer
  continues running without input monitoring instead of
  spamming tracebacks.

## [0.6.4-beta.10] — 2026-06-13

### Added
- **Skill role classification** in chain mode. Each skill in a
  priority combo is bucketed into one of:
  - `catch` — applies a binding CC (KD / float / bound / stiffen
    / etc.). Standard chain participant.
  - `burst` — high-damage skill OR has smash modifiers (DA / DS /
    AA / AS) without a binding CC. Eligible while the cursor's
    target is still locked; reordered above CC continuations
    when the most-recent CC was a knockdown / floating / bound
    (the smash window).
  - `pre_buff` — buff / utility (no damage, no CC, iframe or no
    protection). Always eligible regardless of chain state;
    doesn't consume the DR budget.
  - `reposition` / `filler` — hidden from the chain frontier
    unless they apply a CC.
- **Smash-window reordering.** When the cursor is on a knockdown,
  burst skills with `down_smash` / `air_smash` / `down_attack` /
  `air_attack` tags float to the top of the frontier, ahead of
  CC continuations. The "best next" flash lands on the highest-
  damage downsmash candidate so you commit to the right finisher
  without having to remember the priority list.

### Changed
- **Chain ring widths bumped** so the ring reads at smaller icon
  sizes. Cursor 5 px (was 3), history 4 px (was 2). Both scale
  lightly with icon size — at 64 px the cursor ring is ~6 px.
- **Pre-buff nodes get a cyan outline** (`#66E0FF`) instead of
  the white frontier outline so they don't read as "next move"
  even when off cooldown.
- **Maegu Awakening — Spirit Parade and Heavenly Return** key
  lists fixed. Both had `keys: [shift, x, e, f]` (the trainer
  flattened the `SHIFT+X — E or F during Flow: Hanpuri` tooltip
  into a single chord, which rendered as `Shift+X+D+F` after
  remap). Now `keys: [shift, x]` with `keys_alt: [e]` for the
  Hanpuri-flow continuation.

## [0.6.4-beta.9] — 2026-06-13

### Changed
- **Chain flowchart nodes now have rounded outlines + a CC drain
  ring.** Replaces the square frame.
  - **Cursor** + **history nodes** show a draining ring computed
    from the cast timestamp + the longest CC duration the skill
    applies. Drains clockwise from 12 o'clock; bright section is
    the time remaining, dim section is elapsed lock.
  - **Frontier nodes** show a thin static rounded outline.
  - **Idle nodes** show a faint dim outline.
- New `chain.cc_durations:` block on chain combos lets you
  override the per-tag lock-time defaults (knockdown 1.5 s,
  bound 1.2 s, stun 1.5 s, knockback 1.0 s, float 1.0 s,
  stiffness 0.8 s, grab 2.0 s). Combos that omit the block use
  the defaults.
- `chain_state` now ships a `lock_seconds` map (skill-id →
  longest CC duration in seconds) so the renderer doesn't need
  to walk skill-info on every render frame.

## [0.6.4-beta.8] — 2026-06-13

### Added
- **Live sliders for the chain flowchart layout** in
  Settings → Display:
  - **Icon size** (24–96 px). Default lowered from 48 to **36** so
    the flowchart reads less cramped at 1080p.
  - **Column spacing** (40–300 px). Default **120** — wider gap
    between tier columns lets the eligibility edges breathe.
  Both sliders write through to `combos.yaml` on every drag and
  the ChainRenderer pulls the values fresh each render frame, so
  changes are visible immediately without restarting the combo.

### Changed
- `ChainRenderer` constructor now takes a `column_gap_provider`
  callable in addition to `icon_size_provider`. Both default to
  the new defaults (36 / 120) when not wired.

## [0.6.4-beta.7] — 2026-06-13

### Changed
- **ChainRenderer is now a horizontal flowchart with skill icons.**
  - Tier columns laid out left → right (Opener → Burst → Reposition
    → Finisher for the Maegu chain combo).
  - Each node = skill icon + name caption + key chord beneath.
  - Eligibility edges drawn faintly between every (node in tier T)
    and every (node in tier T+1).
  - Cursor → frontier edges drawn solid in gold.
  - History trail drawn as a dim-gold polyline through previous
    casts.
  - Per-node states: idle (faint frame), frontier (white frame),
    cursor (gold frame, thick), history (dim gold).
- **Skill icons** loaded from `~/bdo-skill-icons` (community-
  maintained). The icon loader (`src/overlay/icons.py`) reads
  `metadata.json`, samples the four corners of each icon for a
  uniform background colour, and alpha-keys it out before
  rendering — so the dark BDOCodex border vanishes against the
  trainer's transparent overlay. Falls back to text-only nodes
  when the icon repo isn't installed.
- **Configurable icon size.** Default 48 px; set
  `settings.chain_icon_size_px` in `config/combos.yaml` to
  override (clamped 24–128). Picked up at the next
  `start_combo()` so a settings change takes effect on the next
  combo selection without restart.

## [0.6.4-beta.6] — 2026-06-13

### Added
- **Chain mode for priority combos.** Priority combos can now opt
  into a `chain:` block at the top level. This turns the combo
  into a live PvP CC-chain tracker:
  - **Cursor + history** — the trainer tracks every on-chain
    cast as you advance.
  - **Frontier** — at any moment the resolver picks the priority
    skills that are off-cooldown AND don't blow the
    diminishing-returns cap (default 4 hard-CCs per 6s rolling
    window, configurable per combo).
  - **Off-chain reset** — pressing a priority skill that's not
    in the current frontier resets the cursor with a brief red
    "OFF-CHAIN — RESET" overlay. Non-priority skills are ignored
    (movement / utility doesn't break the chain).
  - **Idle reset** — `idle_reset_ms` (default 3 s) of no on-chain
    press resets the cursor automatically.
  - **Finishers** — listed skills end the chain cleanly without
    a red flash.
  - **CC categories** default to BDO standard (grab / hard / soft
    / smash); overridable per combo via `cc_categories:`.
- **ChainRenderer overlay component**
  (`src/overlay/chain_renderer.py`). Vertical two-column display
  — left column is cursor + history, right column is the live
  frontier with key chords and a flashing "best next" pulse.
  Hard-CC budget readout shows how many of `max_hard_cc` you've
  spent in the rolling window.
- **Maegu Awakening chain combo**
  `config/combos/maegu_awakening/default/pvp_chain_kill.yaml`.
  4 tiers (Opener / Burst / Reposition / Finisher), Spirit
  Parade + Flower Shroud as finishers, max_hard_cc 4, 6 s
  window, 3 s idle reset.
- **Schema reference** for chain mode added to
  `docs/priority-combos.md` (sits below the priority-combos
  primer; backward-compatible).

### Changed
- Priority player suppresses its single-skill rendering when a
  chain combo is active — the ChainRenderer drives the display.
- `PriorityPlayer.on_chain_changed` callback hook added (called
  on every chain state change so the renderer can re-draw).
- New `chain_active` property on PriorityPlayer for the
  ComboOverlay dispatcher.

## [0.6.4-beta.5] — 2026-06-12

### Changed
- **CC panel drops PvE-only effects entirely.** Previously skills
  with PvE-only binding tags (e.g. Floating PvE only) still
  rendered with a "(PvE)" suffix. Those tags are now removed from
  the rendered list, and rows whose binding effects are *all*
  PvE-only no longer appear at all. PvP-only and "both" tags are
  unchanged.
- **Diagnostic logging** added when the CC panel opens or
  refreshes — `logs/bdo_trainer.log` now records which class /
  spec the panel is showing and how many bundle-referenced skills
  are eligible. Helps diagnose "wrong spec showing" reports.

## [0.6.4-beta.4] — 2026-06-12

### Changed
- **CC Skills panel scoped to the active spec.** The class data
  files were seeded by BDOCodex with both the awakening and
  succession kits in some cases (notably Maegu Succession's file
  carries the awakening skills too), so the panel was showing
  cross-spec skills for the wrong rotation. The panel now takes a
  per-spec allowlist computed in `main.py` from the active spec's
  bundles — every skill referenced by any combo step / priority
  tier / `boost_after` / `requires_prev` / `prefers_after` /
  hotbar / locked entry. Falls back to the full spec file when no
  bundles exist.
- **CC Skills panel filters to PvP-binding effects only.** Drops
  damage modifiers (down attack / down smash / air attack / air
  smash) and secondary tags (push / pull / freeze) that don't pin
  a target for a follow-up cast. Only stun, stiffness, knockdown,
  knockback, floating, bound, and grab are now eligible. Skills
  that have *only* damage-modifier tags don't appear at all;
  skills with mixed tags only render their binding tags.

## [0.6.4-beta.3] — 2026-06-12

### Added
- **Multi-select boost-after picker.** The Combo Editor's
  boost-after dropdown is now a button that opens a checkbox
  picker — tick any number of skills, click OK. The picker
  scrolls (handy for bundles with 50+ skills), supports a
  Clear All button, and shows the user's full label set
  ("Skill Name  (skill_id)"). The button itself shows
  "(none)", a single skill name, or "Skill Name +N" so you
  can see the multi-select state at a glance.
- **Maegu Succession — PvE bundle metadata** filled in with
  the full Netherax PvE guide:
  - Locked skills (Evasion, Petalblast).
  - Hotbar / quickslot (Prime: Foxspirit Form 3-min +25 AP
    buff, optional Soul Charm).
  - Buffs / debuffs / movement / repositioning sections.
  - Rabams (Lv 56 Heavenly Return primary; Lv 57 Constricting
    Charm > Petal Snare; Lv 58 Spirit Sparks).
  - Magnus skill verdict (leave unlearned — keeps Soulflame
    available).
  - Notable cancels, slow casts to avoid, input traps.
- **Maegu Succession PvE Priority combo** —
  `pve_dps_priority.yaml`. Three tiers:
  - Top Priority (Heavenward Dance, Spirited Away, Petal Play,
    Spirit Swirl).
  - Core DPS (Foxflare, Nukduri Dance, Lurking Claws, Bristling
    Sparks, Flower Shroud / Bared Claws → Foxspirit Tag for
    -DP).
  - Filler (Heavenly Return, Constricting Charm > Spirit Sparks
    chain, Soulflame / Soulsnare → Flow: Hanpuri).
  - Notable cancels encoded as `prefers_after`; the
    Constricting Charm → Spirit Sparks and
    Soulsnare/Soulflame → Flow: Hanpuri chains as
    `requires_prev` gates.

### Removed
- Old miscategorised `pvp_dps_priority.yaml` — the actual
  guide content was always PvE.

## [0.6.4-beta.2] — 2026-06-12

### Added
- **`boost_after` / `requires_prev` / `prefers_after` accept lists.**
  Each of those priority-combo fields now takes a single skill id
  (existing behaviour) OR a list of skill ids with any-of semantics.
  Lets you encode state-style buffs cast by several entry skills —
  Maegu's Spiritforging is the motivating case: any of Hazy Path,
  Foxflare Charge, Emberclaw Slash, Flow: Emberclaw Sweep,
  Emberclaw Finale, Emberclaw Crush, or Emberclaw Torrent enters
  Spiritforged state, and a downstream empowered skill should be
  promoted regardless of which one. List form sidesteps the old
  "name one skill per row" limit.
- **Maegu PvE Priority encodes Spiritforging.** Every empowered
  skill (Twirling Foxflare, Flow: Foxflare Encore, Twirling
  Rhapsody, Foxflare Stroke, Foxflare Cleave, Foxflare Fleche,
  Twirling Retreat, Fan Kick, Foxflare Ambush) now carries
  `boost_after: [<spiritforging set>]` with a 4 s window — so they
  promote a tier while Spiritforging is fresh and fall back to
  base priority once it lapses.
- **Foxflare Charge added** as a Tier 0 Spiritforge entry option
  alongside Hazy Path.
- **Combo description** rewritten with a Spiritforging primer
  drawn from the community guide / video.

### Changed
- Combo Editor preserves list-form `boost_after` on save (the
  dropdown can't represent the list, so it's stashed in the
  preserved-fields path along with the other advanced fields).

## [0.6.4-beta.1] — 2026-06-12

### Changed
- **Maegu Awakening bundle metadata expanded** with the full PvE
  loadout guide (courtesy of Netherax). The bundle's
  `_bundle.yaml` now documents:
  - **Locked skills** — Evasion, Soulsnare (so Foxflare Ambush
    works as the awakening swap), Heavenward Dance (so Hazy Path
    works as the awakening swap), Twirling Crane (preference,
    quickslot it instead).
  - **Hotbar / quickslot additions** — Twirling Crane,
    Foxspirit Conduit (3-min +25 AP buff), Soul Tear (movement
    + S+C / C return-to-awakening), Heavenward Dance (if you
    use it AND have it locked).
  - **Buffs / debuffs / movement / repositioning / core skill**
    sections covering Spirit Step iframes, Soul Tear, Foxflare
    Charge, Hazy Path → Foxflare Ambush engages, Twirling
    Rhapsody / Retreat / Foxflare Fleche reposition options,
    and the Emberclaw Slash vs. Emberclaw Crush core choice.
  - **Rabams / Magnus** — Rabam choices match Succession (see
    succession PvE guide); Magnus skill (Foxflare Fling) is
    useless in PvE.

  PvP-specific cheatsheet (catches, add-on suggestions) is still
  there at the bottom — this bundle still hosts both the
  PvE Priority combo and the PvP combos.

## [0.6.3] — 2026-06-12

Rolls up everything from the v0.6.2 beta cycle into a single stable
release. Skipping straight to **0.6.3** because pre-0.6.3 builds had
a version-comparator bug that prevented in-app updates between
prereleases of the same base version — bumping the patch number
guarantees the updater offers this build to anyone stuck on a
v0.6.2-beta.x.

### Added
- **Auto-restart after update.** The post-install prompt now reads
  "Restart BDO Trainer now?" with Yes (default) / No buttons. On
  Yes the updater spawns a small detached helper process that polls
  the parent PID, waits for it to exit (so all file handles release),
  then launches a fresh copy with the same `sys.executable` +
  `sys.argv`. The trainer goes through its normal `_shutdown` path
  first (combos stopped, input listeners closed, tray torn down),
  with a force-exit safety net. The "No" path keeps the previous
  behaviour — restart whenever you like, the new code is already
  on disk.

### Fixed
- **Updater no longer reports "no update available" between
  prereleases.** The version comparator was stripping the prerelease
  suffix entirely, so `v0.6.2-beta.1` and `v0.6.2-beta.2` compared
  equal. Replaced with a SemVer-aware comparator: plain release
  beats any prerelease of the same base (`v0.6.2 > v0.6.2-rc.1 >
  v0.6.2-beta.2 > v0.6.2-beta.1`); prerelease pieces split into
  `(label, number)` so `beta.10 > beta.2` numerically; mixed-type
  identifiers fall back to int-below-string per SemVer 2.0 §11.4.3.
- **Skill input no longer double-prints the keypress.** The overlay
  was rendering each skill's free-text `input:` field verbatim
  under the skill name. Many of those fields are the BDOCodex
  tooltip ("E E after other skills to perform attack 2"), which
  read awkwardly under a bold "Emberclaw Crush" header. Both
  overlay players now render the canonical chord (`E`, `Shift + LMB`,
  etc.) computed from the skill's `keys` list with the user's
  remap applied. The free-text `input:` field stays around for the
  editor / inspector view.
- **Emberclaw Slash cooldown corrected to 7 s** (was briefly dropped
  to 4 s based on community feel; the in-game cooldown is 7 s).
- **Emberclaw Torrent / Emberclaw Slash inputs trimmed.** The
  `input:` field used to carry the full mechanic dump
  (`SHIFT + RMB Hold RMB to perform attack 3 SHIFT + RMB after
  forward Spirit Step…`), which bloated the overlay. Now just
  `SHIFT + RMB` / `SHIFT + LMB`. Full mechanic stays in `notes:`.

### Changed
- **Maegu DPS Priority combo retagged PvE-only and trimmed.**
  Renamed `pvp_dps_priority` → `pve_dps_priority` (category `pve`).
  The original guide is a PvE rotation; tagging it PvP was
  misleading. Dropped the AoE / Pre-Awakening tier (Constricting
  Charm / Spirit Sparks / Foxspirit Tag) — those are pre-awakening
  swap skills and the priority resolver was happy to display them
  mid-awakening. Per-skill notes also pruned to remove leading
  keypress restatements ("SHIFT + Q. Backup entry." → "Backup
  entry.") now that the chord renders separately.

## [0.6.1] — 2026-06-12

### Fixed
- **Multi-key skills lost to single-key skills with overlapping keys.**
  When two priority-combo skills share keys — e.g. Maegu's
  Foxflare Fleche on `RMB` vs. Twirling Rhapsody on `← / → + RMB`
  — pressing the chord (RMB first, then the modifier) could fire
  the lone-RMB tap *before* the modifier landed. The user reported
  Twirling Rhapsody never working on the QE/AD-swapped keyboard
  layout because of this. Two fixes in `InputMonitor`:
  - **Tap firing is coalesced** across a 30 ms window. Lots of key
    chords land via "modifier slightly before / after the trigger
    key" — the coalesce window absorbs that timing skew before
    deciding which tap to fire.
  - **Most-specific tap wins.** When several taps' required key
    sets all match what's currently held, the one with the
    largest required set fires (and the smaller ones don't get a
    phantom cooldown stamp). Net effect: pressing RMB-then-Q on a
    QE-swap layout fires Twirling Rhapsody, not Foxflare Fleche.

## [0.6.0] — 2026-06-12

### Added
- **Priority schema gains chain-aware fields.** Two new optional
  per-skill fields cover the missing "this skill follows that one"
  case the existing `boost_after` couldn't express:
  - **`requires_prev` / `requires_window_ms`** — *hard gate*. The
    skill is only eligible while the named skill is the
    most-recent cast (within the window). Use for follow-up skills
    like Maegu's `Flow: Emberclaw Sweep` (only after Emberclaw
    Slash) or `Spirit Sparks` (only after Constricting Charm). The
    resolver will skip the row entirely when the gate isn't met,
    instead of displaying an uncastable skill.
  - **`prefers_after` / `prefers_window_ms` / `prefers_to_tier`** —
    *soft preference*. Boosts the row's effective tier while the
    named skill is the most-recent cast (within the window).
    Pressing anything else in between cancels the boost. Use for
    Notable Cancels — e.g. Foxflare Fleche skips its windup when
    chained right after Foxflare Ambush.
  - Schema reference at `docs/priority-combos.md` updated.
  - Combo Editor preserves these advanced fields on save even
    though the GUI doesn't yet surface form widgets for them — set
    them in YAML directly.
- **Maegu Awakening priority combo** —
  `pvp_dps_priority.yaml`. Five tiers (Spiritforge Entry → Top
  Priority → Core DPS → Filler → AoE / Pre-Awakening). Encodes
  Flow: Emberclaw Sweep / Flow: Foxflare Encore as `requires_prev`
  gates, the Notable Cancel chains as `prefers_after` boosts.

### Fixed
- **Charmed broken on press.** `data/classes/maegu_awakening.yaml`
  declared `keys: [s, space]` (both held simultaneously) — the
  trainer never matched a SPACE press. Fixed to `keys: [space]`
  with `keys_alt: [s, space]` for the side-attack form.
- **Foxflare Ambush / Twirling Rhapsody key sets** were a flat list
  of every keystroke option (`[f, a, d, lmb]` and `[a, d, rmb]`),
  which required holding *all* of them. Fixed to a primary key set
  plus an alt key set for the side-attack form, matching the actual
  in-game inputs.
- **Maegu Awakening skill cooldowns retuned.** The seeded values
  from BDOCodex were wrong for several skills:
  - Emberclaw Slash 7 s → 4 s
  - Emberclaw Torrent 7 s → 8 s
  - Foxflare Ambush 6 s → 8 s
  - Twirling Rhapsody 5 s → 7 s
  - Foxflare Fleche 5 s → 6 s
  - Foxflare Cleave 5 s → 7 s
  - Foxflare Stroke 5 s → 9 s
  - Twirling Foxflare 6 s → 9 s
  - Twirling Retreat 6 s → 8 s
  - Hazy Path 4 s → 6 s

### Changed
- **CPU optimisation pass.** Several render-loop hot paths were
  doing more work than necessary:
  - `PriorityPlayer._tick` 100 ms → 250 ms, plus a "no-op redraw
    skip" — only re-renders when the displayed skill OR effective
    tier changes (was re-rendering every tick when any row had a
    `boost_after` set).
  - `CCPanel._tick` 50 ms → 80 ms while a skill is on cooldown,
    500 ms idle (was running 50 ms forever). Each fragment caches
    its last-rendered character cut and skips `itemconfigure` calls
    that wouldn't visibly change anything.

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

[0.6.4-beta.17]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.17
[0.6.4-beta.16]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.16
[0.6.4-beta.15]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.15
[0.6.4-beta.14]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.14
[0.6.4-beta.13]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.13
[0.6.4-beta.12]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.12
[0.6.4-beta.11]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.11
[0.6.4-beta.10]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.10
[0.6.4-beta.9]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.9
[0.6.4-beta.8]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.8
[0.6.4-beta.7]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.7
[0.6.4-beta.6]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.6
[0.6.4-beta.5]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.5
[0.6.4-beta.4]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.4
[0.6.4-beta.3]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.3
[0.6.4-beta.2]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.2
[0.6.4-beta.1]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.4-beta.1
[0.6.3]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.3
[0.6.1]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.1
[0.6.0]: https://github.com/Vitiate/bdo-trainer/releases/tag/v0.6.0
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
