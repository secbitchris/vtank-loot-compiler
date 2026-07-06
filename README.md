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
    when: { type: Armor, workmanship_ge: 8 }
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

The encoder/decoder is derived directly from the VTClassic source and **verified by
round-tripping real VTank-authored profiles byte-for-byte** (see `tests/`). The
compiler also re-parses its own output as a self-check on every run.

```sh
python tests/test_roundtrip.py
```

## Install

Requires Python 3.8+.

```sh
pip install -r requirements.txt   # just PyYAML
```

## Loot spec reference

A profile is a list of `rules`. Each rule has a `name`, an `action`, and a `when`
block whose conditions are **AND-ed** together.

### Actions
| action | meaning |
|--------|---------|
| `keep` | keep every matching item |
| `keepupto` | keep up to `count:` of them (add a `count:` field) |
| `salvage` | tag for salvaging |
| `sell` | tag for selling to a vendor |

### Conditions (inside `when:`)
| condition | matches |
|-----------|---------|
| `type: <ObjectClass>` | item class: `MeleeWeapon`, `MissileWeapon`, `Armor`, `Clothing`, `Jewelry`, `Gem`, `WandStaffOrb`, `Food`, `Scroll`, `Salvage`, … |
| `name_matches: "<regex>"` | item name (regular expression, `|` = OR) |
| `value_ge` / `value_le` | item Value (pyreals) ≥ / ≤ |
| `burden_ge` / `burden_le` | item Burden (weight) ≥ / ≤ — pair with `value_*` for value-density looting |
| `workmanship_ge` | item workmanship ≥ |
| `armor_level_ge` / `armor_level_le` | armor level ≥ / ≤ |
| `min_damage_ge` | computed min damage ≥ (weapons) |
| `spell_count_ge` | number of spells ≥ |
| `stack_count_ge` / `stack_count_le` | stack size ≥ / ≤ |

The underlying format supports ~20 requirement types; the ones above are the common
subset. Adding more is a one-line entry in `utl_compile.py`.

## In-game workflow

1. Edit `loot.yaml`.
2. `python utl_compile.py loot.yaml -o my.utl` (copy into the Virindi Tank folder).
3. In-game: Loot tab → re-select the profile to reload the edited rules.

Profile switching can also be automated from VTank metas / UtilityBelt commands,
so you can bind different profiles (e.g. "cash farm" vs "hunt rares") to hotkeys or
triggers.

## Credits & license

Format decoded from the open-source VTClassic loot system. Test fixtures come from
[lino-ranta/vtank-loot-profiles](https://github.com/lino-ranta/vtank-loot-profiles)
(BSD 2-Clause) — see `tests/fixtures/SOURCE.md`.

Unofficial third-party tool, not affiliated with Virindi Tank or Decal.

[MIT](LICENSE)
