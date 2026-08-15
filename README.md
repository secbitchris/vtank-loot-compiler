# VTank Loot Compiler

Write Virindi Tank loot profiles as **readable YAML**, compile them to VTank's
`.utl` format. Version-control your looting instead of clicking through a GUI.

```yaml
# loot.yaml
rules:
  - name: "High-value loot"
    action: keep
    when: { value_ge: 50000 }

  - name: "Good melee weapons"
    action: keep
    when: { type: MeleeWeapon, min_damage_ge: 20 }

  - name: "Salvage decent armor"
    action: salvage
    when: { type: Armor, salvage_workmanship_ge: 8 }
```

```sh
python utl_compile.py loot.yaml -o my.utl
```

Drop `my.utl` in your Virindi Tank folder, pick it from the **Loot tab dropdown**
in-game, and it loads live — no client restart.

## Why

VTank's `.utl` files are a terse line-based format meant to be produced by a GUI
editor. That makes them hard to diff, review, reuse across characters, or keep in
git. This tool lets you keep a friendly YAML source of truth and generate the
`.utl` deterministically.

**"Loot only what you want" is how VTank already works:** anything not matched by a
`keep`/`keepupto` rule is left behind. Rules evaluate top-down, first match wins —
so put specific rules above broad ones.

## Correctness

Every rule type, action and value key is encoded from the tables in
`vtclassic_enums.py`, which are read straight out of the shipped plugin binaries
(`VTClassic.dll`, `utank2-i.dll`) rather than transcribed by hand — see
`tools/gen_enums.py`. The tests check four separate things:

| layer | what it proves |
|-------|----------------|
| container codec | real VTank profiles parse and re-emit byte-for-byte |
| **encoder goldens** | **each condition emits the exact bytes VTClassic's own `Write()` emits** |
| enum tables | key/type/action values match the binaries |
| full round-trip | every real profile decompiles to YAML and recompiles equivalently |

The goldens are the layer that matters. The container codec keeps requirement
bodies as opaque bytes, so it would pass even if every condition were encoded
wrongly — 22 of the 30 goldens are corroborated by bytes VTank itself wrote into
`tests/fixtures/`.

```sh
python tests/test_roundtrip.py     # or: pytest tests/
```

## Install

Requires Python 3.8+.

```sh
pip install -r requirements.txt   # just PyYAML
```

## Loot spec reference

A profile is a list of `rules`. Each rule has a `name`, an `action`, and a `when`
block whose conditions are **AND-ed** together. Optional per-rule keys are
`count:` (for `keepupto`), `enabled: false`, and `expression:`.

### Actions
| action | meaning |
|--------|---------|
| `keep` | keep every matching item |
| `keepupto` | keep up to `count:` of them (add a `count:` field) |
| `salvage` | tag for salvaging |
| `sell` | tag for selling to a vendor |
| `noloot` | explicitly leave it — put above a broader `keep` to carve out exceptions |
| `read` | tag for reading |
| `user1` … `user5` | custom slots that VTank metas can act on |

### Value-key conditions

Any value key can be used as `<key>_ge`, `_le`, `_eq`, `_ne`, spelled in
snake_case. Common ones:

| condition | matches |
|-----------|---------|
| `value_ge` / `value_le` | item Value (pyreals) |
| `burden_ge` / `burden_le` | item Burden — pair with `value_*` for value-density looting |
| `workmanship_ge` | item workmanship |
| `armor_level_ge` / `armor_level_le` | armor level |
| `stack_count_ge` / `stack_count_le` | stack size |
| `material_eq` | material id |
| `max_damage_ge`, `total_value_ge`, `spellcraft_ge`, … | 173 int keys in all |

Decimal keys support `_ge` / `_le` only: `salvage_workmanship_ge`,
`attack_bonus_ge`, `melee_defense_bonus_ge`, `damage_bonus_ge`, `variance_le`,
`magic_d_bonus_ge`, and the rest of the 25 in `DOUBLE_VALUE_KEY`.

Prefix any key with `buffed_` (with `_ge`) to test the item as it would be when
buffed: `buffed_armor_level_ge: 300`.

### Other conditions
| condition | matches |
|-----------|---------|
| `type: <ObjectClass>` | `MeleeWeapon`, `MissileWeapon`, `Armor`, `Clothing`, `Jewelry`, `Gem`, `WandStaffOrb`, `Food`, `Scroll`, `Salvage`, … |
| `name_matches: "<regex>"` | item name (regex, `\|` = OR). Any string key works: `full_description_matches`, `inscription_matches`, … |
| `spell_name_matches: "<regex>"` | any spell on the item |
| `spell_match: {matches, not_matches, count}` | spell regex with an exclusion and a minimum count |
| `spell_count_ge` | number of spells |
| `min_damage_ge`, `damage_percent_ge`, `total_ratings_ge` | computed weapon values |
| `buffed_median_damage_ge`, `buffed_missile_damage_ge`, `calcd_buffed_tinked_damage_ge` | buffed/tinked damage |
| `calced_buffed_tinked_target_melee: {dot, melee_defense_bonus, attack_bonus}` | combined melee target |
| `char_level_ge` / `char_level_le` | **your** level, not the item's |
| `char_skill_ge: {skill, value}` / `char_base_skill: {skill, min, max}` | your skill |
| `main_pack_empty_slots_ge` | free main-pack slots — stop looting when full |
| `flag_exists: {key, flag}` | bit flag set on an int key |
| `any_similar_color`, `similar_color_armor_type`, `slot_similar_color`, `slot_exact_palette` | colour matching |

A condition may be given a **list** to repeat it, since all conditions are AND-ed:

```yaml
when:
  name_matches: ["Olthoi", "Celdon"]   # name must match BOTH patterns
```

### Identify cost — rule order is a performance decision

VTank can evaluate some conditions on an unidentified item and not others.
`cLootRules.NeedsID` walks the rules top-down: if a rule matches using only
ID-free conditions, the item is classified immediately; if it first reaches a
rule that needs an identified property, VTank has to ID the item before it can
decide. **So put ID-free rules that catch common items above the rest.**

| free (no ID) | needs an identify |
|---|---|
| `type`, `name_matches` | `full_description_matches` and other string keys |
| `value_ge` / `value_le` | `total_value_*` |
| `stack_count_*`, `material_*`, `icon_*`, `equipable_slots_*` | `burden_*`, `armor_level_*`, `workmanship_*`, `spellcraft_*` |
| **`salvage_workmanship_*`** | `attack_bonus_*`, `damage_bonus_*`, `variance_*`, `melee_defense_bonus_*` |
| `char_level_*`, `char_skill_ge`, `main_pack_empty_slots_ge` | `spell_count_ge`, `spell_match`, `spell_name_matches` |
| the colour rules, `damage_percent_ge` | `min_damage_ge`, `total_ratings_ge`, everything `buffed_*` |

29 of the 171 int keys are usable without an ID; the rest are not.

> **`salvage_workmanship_ge` is the one you usually want, not `workmanship_ge`.**
> `IntValueKey.Workmanship` (105) and `DoubleValueKey.SalvageWorkmanship` carry
> the same number — measured across 252 identified items in a Virindi Global
> Inventory scan, they agreed in every case — but only the latter is readable
> without identifying the item. That is why VTank's own GUI profiles use it
> exclusively: key 105 appears zero times in 3,205 real requirements.

Note that `burden_*` needs an ID, which makes value-density rules more expensive
than they look; a `value_ge` or `type` gate above them will short-circuit most
items.

## Importing an existing profile

Already have a profile built in VTank's GUI? Pull it into YAML:

```sh
python utl_decompile.py LootSnobV4.utl -o loot.yaml --verify
```

`--verify` recompiles the result and compares it with the input, reporting
`BYTE-IDENTICAL` or `SEMANTICALLY IDENTICAL` (requirements regrouped — a rule's
requirements are AND-ed, so their order does not affect matching). All 563 rules
across the three real profiles in `tests/fixtures/` import cleanly.

## In-game workflow

1. Edit `loot.yaml`.
2. `python utl_compile.py loot.yaml -o my.utl` (copy into the Virindi Tank folder).
3. In-game: Loot tab → re-select the profile to reload the edited rules.

For a whole folder of profiles, `python deploy.py` recompiles every
`profiles/*.yaml` and copies the `.utl` straight into the VTank plugin folder in
one shot (each profile names its output via a top-level `out:` key). Use
`--dry-run` to preview, `--vtank <path>` to override the destination.

Profile switching can also be automated from VTank metas / UtilityBelt commands,
so you can bind different profiles (e.g. "cash farm" vs "hunt rares") to hotkeys or
triggers.

## Credits & license

Format decoded from the VTClassic loot system. The enum tables in
`vtclassic_enums.py` are generated from the locally-installed `VTClassic.dll` and
`utank2-i.dll` — numeric facts about the file format only; no decompiled source is
vendored here. Test fixtures come from
[lino-ranta/vtank-loot-profiles](https://github.com/lino-ranta/vtank-loot-profiles)
(BSD 2-Clause) — see `tests/fixtures/SOURCE.md`.

Unofficial third-party tool, not affiliated with Virindi Tank or Decal.

[MIT](LICENSE)
