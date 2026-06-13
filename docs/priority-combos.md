# Priority Combos

A **priority combo** is an alternative to the default sequence combo.
Instead of advancing a fixed list of steps in order, the trainer shows
the highest-priority skill that is currently off cooldown. As soon as
you press that skill's keys it is marked on cooldown, and the display
re-resolves to the next-highest off-cooldown skill.

This document is the canonical schema reference and is shared with
[bdodojo.com](https://bdodojo.com) so that combos created in either
editor round-trip cleanly.

## When to use it

- Class playstyles where rotation is dictated by **cooldowns**, not a
  fixed sequence (most BDO Witch / Wizard rotations, Drakania PvE,
  filler-grind loops).
- Combos that mix a small set of "must always be on cooldown" buffs
  / debuffs with a longer list of damage skills.
- Catch-all rotations where the player wants the trainer to remind
  them of the *best available* skill rather than walk a script.

If your combo is a strict sequence (grab → boulder crush → savage hack
→ …), keep using the default `mode: sequence` combo — priority combos
do not enforce step order.

## Combo file shape

A combo file lives at `config/combos/<slug>/<bundle_id>/<combo_id>.yaml`
and must declare the canonical fields below.

### Common header (both modes)

| Field | Type | Required | Notes |
|---|---|---|---|
| `combo_id` | string | yes | Unique within the bundle |
| `class` | string | yes | Class name (e.g. `Witch`) |
| `spec` | string | yes | `Awakening` \| `Succession` |
| `bundle_id` | string | yes | Parent bundle id |
| `category` | string | yes | `pve` \| `pvp` \| `movement` |
| `name` | string | yes | Display name shown in tray menu |
| `description` | string | no | Free-form description |
| `difficulty` | string | no | `easy` \| `intermediate` \| `advanced` |
| `combo_window_ms` | int | no | Per-step transition (sequence only). Ignored for priority combos |
| `mode` | string | no | `sequence` (default) \| `priority` |

When `mode` is omitted the combo is treated as a sequence combo for
backward compatibility — every existing combo continues to load
unchanged.

### Sequence mode

```yaml
mode: sequence    # optional — this is the default
steps:
  - skill: searing_fang
    note: First hit only.
  - skill: glorious_advance
    alt_skill: avalanche_strike
    alt_note: SA gap-closer alternative when out of range.
```

Step shape is the same as it was in v0.5.x — see the existing combos
under `config/combos/` for examples.

### Priority mode

```yaml
mode: priority
priority:
  - tier: Highest Priority
    description: Always cast on cooldown — buffs / debuffs.
    skills:
      - skill: voltaic_pulse
      - skill: lightning_blast
      - skill: toxic_flood

  - tier: Main DPS
    description: Highest-damage skills.
    skills:
      - skill: fissure_wave
      - skill: thunderstorm
      - skill: yoke_of_ordeal
      - skill: barrage_of_lightning
      - skill: thorns_of_denial
        boost_after: voltaic_pulse
        boost_window_ms: 4000
        boost_to_tier: 0
        note: Faster cast after Voltaic Pulse.

  - tier: Filler
    description: Low-priority gap fillers.
    skills:
      - skill: detonative_flow
      - skill: earthen_eruption
      - skill: equilibrium_break
```

#### `priority` block

`priority` is a list of **tiers**, in priority order (lowest index = highest priority).

| Field | Type | Required | Notes |
|---|---|---|---|
| `tier` | string | yes | Display label for this tier |
| `description` | string | no | Tooltip / sub-label shown under the tier |
| `skills` | list | yes | Ordered list of skill entries |

#### `skills` entries

Each entry can be either a bare skill id string (`voltaic_pulse`) or
a dict with these fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `skill` | string | yes | Skill id from the class library |
| `note` | string | no | One-line note rendered under the skill name |
| `boost_after` | string \| list[string] | no | Skill id (or list of ids) whose cast within `boost_window_ms` promotes this skill — list form is "any-of" semantics, useful for state buffs cast by several skills (e.g. Maegu's Spiritforging set: Hazy Path, Foxflare Charge, Emberclaw Slash, Sweep, Finale, Crush, Torrent) |
| `boost_window_ms` | int | no | How long the boost persists after `boost_after` is cast (default `5000`) |
| `boost_to_tier` | int | no | Target tier index when boosted; default = current tier minus 1, clamped to 0 |
| `requires_prev` | string \| list[string] | no | **Hard gate** — the skill is only eligible when the named skill (or any of the named skills, list form) was the *most-recent* cast and we're still inside `requires_window_ms` |
| `requires_window_ms` | int | no | Max ms after `requires_prev` was cast for this skill to remain eligible (default `5000`) |
| `prefers_after` | string \| list[string] | no | **Soft preference** — boosts priority while the named skill (or any of, list form) was the *most-recent* cast within `prefers_window_ms`. Use for "notable cancels" — e.g. Foxflare Fleche skips the linger animation when chained right after Foxflare Ambush |
| `prefers_window_ms` | int | no | Max ms after `prefers_after` was cast for the boost to remain (default `5000`) |
| `prefers_to_tier` | int | no | Tier this skill promotes to while preferred (default = current tier minus 1, clamped to 0) |

The two equivalent forms (bare string vs. dict) are interchangeable —
the parser accepts a plain string and treats it as `{skill: <string>}`.

`boost_after` checks any cast within the window; `prefers_after`
checks the *most-recent* cast specifically. If you press something
else between the trigger skill and the dependent skill,
`boost_after` still fires but `prefers_after` does not.

## How priority resolution works at runtime

On every change in cooldown state (a key press, a cooldown timer
expiring, or the combo starting), the player walks the tiers
top-to-bottom and returns the first skill matching all of:

1. The skill is **off cooldown** (no recorded cast within
   `cooldown_ms`, taken from `data/classes/<slug>.yaml`).
2. The skill has at least one usable key combination (any combo —
   not `hotbar`-only).
3. If `requires_prev` is set, the named skill must have been the
   most-recent cast and within `requires_window_ms`. Otherwise the
   row is skipped entirely.
4. The row's effective tier is computed:
   - If `boost_after` is set and the named skill was cast within
     `boost_window_ms`, tier promotes to `boost_to_tier`.
   - If `prefers_after` is set and the named skill is the
     most-recent cast and within `prefers_window_ms`, tier promotes
     to `prefers_to_tier`.
   - Otherwise the row's native tier applies.

When the user presses the displayed skill's keys, the player stamps
`last_cast[<skill_id>] = now`, also updates the most-recent cast
pointer, and immediately re-resolves to pick the next skill.

### Cooldown timing notes

The trainer can only observe cooldowns through key presses; it doesn't
read the game state. As a result a skill may show "ready" 0.1–0.3 s
before the game has actually accepted the cast. This is acceptable
for grind use; for tight PvP rotations stick with sequence combos.

If `cooldown_ms` is missing or zero the skill is treated as
"always available" (it will keep getting picked unless something
above it in the list comes off cooldown).

## Worked example — Witch Awakening

```yaml
combo_id: pve_priority_grind
class: Witch
spec: Awakening
bundle_id: default
category: pve
mode: priority
name: 'PvE — Priority Grind Loop'
description: |
  Highest-priority buffs/debuffs always on cooldown, then main DPS
  cycle, then fillers. Thorns of Denial gets promoted into Tier 0
  briefly after Voltaic Pulse for the faster cast.
priority:
  - tier: Highest Priority
    description: Buffs / debuffs — always on cooldown.
    skills:
      - skill: voltaic_pulse
        note: 20% Casting Speed buff.
      - skill: lightning_blast
        note: 18% Crit Rate buff.
      - skill: toxic_flood
        note: -15 Magic DP debuff.

  - tier: Main DPS
    description: Highest-damage skills.
    skills:
      - skill: fissure_wave
      - skill: thunderstorm
      - skill: yoke_of_ordeal
      - skill: barrage_of_lightning
      - skill: thorns_of_denial
        boost_after: voltaic_pulse
        boost_window_ms: 4000
        note: Cast faster after Voltaic Pulse — promoted briefly into Tier 0.

  - tier: Filler
    description: Low-priority damage fillers.
    skills:
      - skill: detonative_flow
      - skill: earthen_eruption
      - skill: equilibrium_break
```

## Chain mode (PvP kill chains)

A priority combo may opt into **chain mode** by adding an optional
`chain:` block at the top level. This turns the priority combo from
"highest off-cooldown skill" into a **dynamic CC-chain flowchart**:
the trainer tracks which skill you've just cast, computes which
subsequent priority skills are legal (off cooldown, CC category not
saturated, hard-CC count under cap), and renders the live
"frontier" so you know what to press next during a PvP catch.

A chain combo is still a priority combo — the priority tiers and
all the existing `boost_after` / `prefers_after` / `requires_prev`
machinery applies. The `chain:` block only adds CC-rule gating on
top of cooldown gating.

```yaml
mode: priority
name: 'PvP — Catch & Burst'
chain:
  max_hard_cc: 4         # diminishing-returns cap (default 4)
  window_ms: 6000        # rolling window for the DR cap (default 6000)
  idle_reset_ms: 3000    # reset cursor after this much inactivity
                         # (default 3000)
  finishers:             # casting any of these ends the chain
    - spirit_parade
  cc_categories:         # optional — overrides the BDO defaults
    grab: [grab]
    hard: [stun, knockdown, knockback, bound, floating]
    soft: [stiffness]
    smash: [down_attack, down_smash, air_attack, air_smash]
priority:
  - tier: Opener
    skills:
      - skill: charmed
      - skill: hazy_path
  - tier: Catch
    skills:
      - skill: twirling_rhapsody
      - skill: foxflare_ambush
  ...
```

### How chain mode works

- **Opener** — the first cast since the chain reset. Anything in
  the priority list that's off cooldown can open. Once cast, the
  cursor moves to that node and its CC categories are "spent".
- **Frontier** — at any moment the resolver computes the legal
  next steps: priority skills that are off cooldown AND would not
  exceed `max_hard_cc` within `window_ms` AND whose `requires_prev`
  / `boost_after` / `prefers_after` rules are satisfied.
- **On-chain advance** — pressing a frontier skill moves the
  cursor and adds the skill's CC categories to the chain history.
- **Off-chain reset** — pressing a priority skill that is *not*
  in the current frontier (off cooldown but DR-saturated, or
  prevented by a chain rule) resets the cursor to the start. The
  trainer flashes a brief red overlay so you see the reset.
- **Idle reset** — `idle_reset_ms` of no on-chain press also
  resets the cursor.
- **Finisher** — casting a skill in the `finishers:` list ends
  the chain cleanly (no red flash). Use for combo finishers
  like `spirit_parade` or disengages.
- **Non-priority skills are ignored** — pressing a movement /
  utility skill that's not in the priority list does *not*
  break the chain. Only priority skills participate.

### CC categories

The defaults follow the standard BDO grouping:

| Category | Tags |
|---|---|
| `grab` | grab |
| `hard` | stun, knockdown, knockback, bound, floating |
| `soft` | stiffness |
| `smash` | down_attack, down_smash, air_attack, air_smash |

Only `hard` counts toward `max_hard_cc`. `smash` modifiers ride
on top of a hard-CC and don't consume the budget. `grab` is its
own slot — typically the chain opener. `soft` doesn't count
toward DR but can't be repeated within `window_ms`.

A combo can override these via `cc_categories:` if the in-game
rules change or you want a per-combo flavour (e.g. excluding
`floating` from hard for a knockdown-only combo).

### Renderer

When a `chain:` block is present, the priority overlay switches
from the single-skill display to a **vertical flowchart**:

- **Cursor column** (left) — the most recent on-chain cast plus
  a compact history of previous nodes in the chain.
- **Frontier column** (right) — legal-next priority skills,
  each with its key chord and a cooldown ring (or "ready"
  indicator for off-CD skills). The next-best skill flashes
  its key chord.
- **Off-chain reset** flashes a brief red overlay over the
  frontier list.

(A horizontal flowchart with edges between every node is the
intended end state — see the overlay code for the current
visualisation; the schema is forward-compatible.)

## Editor support

The Combo Editor (tray → **Combo Editor**) ships a **Mode** toggle on
every combo:

- **Sequence** — the existing step builder (skill / note / alt skill).
- **Priority** — a tier editor where each tier has a label, a
  description, and an ordered skill list. Each skill row exposes the
  optional `boost_after` / `boost_window_ms` / `boost_to_tier` fields.

Switching modes preserves any fields shared by both forms (header,
description, etc.); the mode-specific block (`steps:` vs.
`priority:`) is replaced when you save.

## Portability — `.bdt` schema

The `.bdt` v2 bundle format already supports the new combo shape — a
combo entry inside a bundle is opaque to the bundle schema, so any
combo with `mode: priority` round-trips through export / import
without changes. The bdodojo upload path is identical.

## Migration

- Existing combos (no `mode` field) continue to work — the loader
  defaults to `mode: sequence`.
- There is no automatic conversion from sequence to priority. The
  rotation styles are conceptually different and a script-style
  combo would not produce a useful priority list.

## bdodojo notes

When bdodojo's editor adds priority-combo support it should:

1. Read `mode` from the uploaded combo file. Treat absence as
   `sequence` for back-compat.
2. Render the same fields as the desktop editor (tier label,
   tier description, skills with optional boost fields).
3. Validate that every `skill` / `boost_after` reference exists in
   the bundle's class skill library. Unknown skills should be
   rejected with a clear error rather than silently dropped.
4. Echo the `mode` field in the published combo JSON so trainer
   downloads stay round-trippable.
