# BDO Classes — Config Checklist

Track which class/spec YAML files have been created under `config/classes/`.

## Naming Convention

- File: `config/classes/{class_name}_{spec}.yaml`
- Snake_case, lowercase: `dark_knight_awakening.yaml`
- Each file must have top-level `class:` and `spec:` keys

---

## Classes

| #  | Class       | Awakening                              | Succession                              |
|----|-------------|----------------------------------------|-----------------------------------------|
| 1  | Warrior     | [x] `warrior_awakening.yaml`           | [x] `warrior_succession.yaml`           |
| 2  | Ranger      | [x] `ranger_awakening.yaml`            | [x] `ranger_succession.yaml`            |
| 3  | Sorceress   | [x] `sorceress_awakening.yaml`         | [x] `sorceress_succession.yaml`         |
| 4  | Berserker   | [x] `berserker_awakening.yaml`         | [x] `berserker_succession.yaml`         |
| 5  | Tamer       | [x] `tamer_awakening.yaml`             | [x] `tamer_succession.yaml`             |
| 6  | Musa        | [x] `musa_awakening.yaml`              | [x] `musa_succession.yaml`              |
| 7  | Maehwa      | [x] `maehwa_awakening.yaml`            | [x] `maehwa_succession.yaml`            |
| 8  | Valkyrie    | [x] `valkyrie_awakening.yaml`          | [x] `valkyrie_succession.yaml`          |
| 9  | Kunoichi    | [x] `kunoichi_awakening.yaml`          | [x] `kunoichi_succession.yaml`          |
| 10 | Ninja       | [x] `ninja_awakening.yaml`             | [x] `ninja_succession.yaml`             |
| 11 | Wizard      | [x] `wizard_awakening.yaml`            | [x] `wizard_succession.yaml`            |
| 12 | Witch       | [x] `witch_awakening.yaml`             | [x] `witch_succession.yaml`             |
| 13 | Dark Knight | [x] `dark_knight_awakening.yaml`       | [x] `dark_knight_succession.yaml`       |
| 14 | Striker     | [x] `striker_awakening.yaml`           | [x] `striker_succession.yaml`           |
| 15 | Mystic      | [x] `mystic_awakening.yaml`            | [x] `mystic_succession.yaml`            |
| 16 | Lahn        | [x] `lahn_awakening.yaml`              | [x] `lahn_succession.yaml`              |
| 17 | Archer      | [x] `archer_awakening.yaml`            | [x] `archer_succession.yaml`            |
| 18 | Shai        | [x] `shai_talent.yaml`                 | [x] `shai_succession.yaml`              |
| 19 | Guardian    | [x] `guardian_awakening.yaml`          | [x] `guardian_succession.yaml`          |
| 20 | Hashashin   | [x] `hashashin_awakening.yaml`         | [x] `hashashin_succession.yaml`         |
| 21 | Nova        | [x] `nova_awakening.yaml`              | [x] `nova_succession.yaml`              |
| 22 | Sage        | [x] `sage_awakening.yaml`              | [x] `sage_succession.yaml`              |
| 23 | Corsair     | [x] `corsair_awakening.yaml`           | [x] `corsair_succession.yaml`           |
| 24 | Drakania    | [x] `drakania_awakening.yaml`          | [x] `drakania_succession.yaml`          |
| 25 | Woosa       | [x] `woosa_awakening.yaml`             | [x] `woosa_succession.yaml`             |
| 26 | Maegu       | [x] `maegu_awakening.yaml`             | [x] `maegu_succession.yaml`             |
| 27 | Scholar     | [x] `scholar_awakening.yaml`           | [x] `scholar_succession.yaml`           |

**Progress: 54 / 54 ✅ COMPLETE**

---

## Notes

- **Shai** uses "Talent" instead of "Awakening" (support / music kit). Set `spec: Talent` in her awakening-equivalent file.
- **Archer** was originally awakening-only but now has Succession as well.
- Each file should follow the structure in `dark_knight_awakening.yaml`: skills, combos (pve/pvp/movement), skill addons, locked skills, hotbar layout.
- Sources: [BDFoundry](https://www.blackdesertfoundry.com/), class Discords, [GrumpyGreenCricket](https://grumpygreen.cricket/), community guides.
