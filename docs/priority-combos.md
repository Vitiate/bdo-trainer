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
| `boost_after` | string | no | Skill id whose cast promotes this skill one or more tiers up |
| `boost_window_ms` | int | no | How long the boost persists after `boost_after` is cast (default `5000`) |
| `boost_to_tier` | int | no | Target tier index when boosted; default = current tier minus 1, clamped to 0 |

The two equivalent forms are interchangeable — the parser accepts a
plain string and treats it as `{skill: <string>}`.

## How priority resolution works at runtime

On every change in cooldown state (a key press, a cooldown timer
expiring, or the combo starting), the player walks the tiers
top-to-bottom and returns the first skill matching all of:

1. The skill is **off cooldown** (no recorded cast within
   `cooldown_ms`, taken from `data/classes/<slug>.yaml`).
2. The skill has at least one usable key combination (any combo —
   not `hotbar`-only).
3. If a `boost_after` rule is in effect for this skill *and* the
   referenced skill was cast within `boost_window_ms`, the skill is
   promoted to `boost_to_tier` for resolution purposes; otherwise the
   skill is considered at its native tier.

When the user presses the displayed skill's keys, the player stamps
`last_cast_at[<skill_id>] = now` and immediately re-resolves to pick
the next skill.

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
