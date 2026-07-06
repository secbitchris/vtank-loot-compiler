"""Compile a friendly YAML loot spec into a VTClassic .utl profile.

    py -3 utl_compile.py loot.yaml -o my.utl

Drop the resulting .utl in your Virindi Tank folder and load it in-game.
All encoding is verified against the VTClassic source (byte-exact round-trip).
"""

import argparse
import sys

import yaml

import utl

# ---- enums lifted verbatim from the VTClassic source --------------------------

ACTIONS = {"noloot": 0, "keep": 1, "salvage": 2, "sell": 3, "keepupto": 10}

# eLootRuleType (requirement type codes)
R_STRINGMATCH = 1
R_LONG_LE, R_LONG_GE = 2, 3
R_DOUBLE_LE, R_DOUBLE_GE = 4, 5
R_OBJECTCLASS = 7
R_SPELLCOUNT_GE = 8
R_MINDAMAGE_GE = 10
R_LONG_E, R_LONG_NE = 12, 13

# IntValueKey (AC PropertyInt codes)
IVK = {"value": 0x13, "total_value": 20, "armor_level": 0x1C, "workmanship": 0x69,
       "material": 0x83, "burden": 0x05, "stack_count": 0xD000006,
       "max_damage": 0xD000022}
# StringValueKey
SVK_NAME = 1
# ObjectClass (0-based, in source order)
OBJECTCLASS = {n.lower(): i for i, n in enumerate([
    "Unknown", "MeleeWeapon", "Armor", "Clothing", "Jewelry", "Monster", "Food",
    "Money", "Misc", "MissileWeapon", "Container", "Gem", "SpellComponent", "Key",
    "Portal", "TradeNote", "ManaStone", "Plant", "BaseCooking", "BaseAlchemy",
    "BaseFletching", "CraftedCooking", "CraftedAlchemy", "CraftedFletching",
    "Player", "Vendor", "Door", "Corpse", "Lifestone", "HealingKit", "Lockpick",
    "WandStaffOrb", "Bundle", "Book", "Journal", "Sign", "Housing", "Npc", "Foci",
    "Salvage", "Ust", "Services", "Scroll", "CombatPet"])}

# Default SalvageCombine trailing block (captured from a known-good profile) so the
# generated file is complete and VTank's salvage logic never sees a null block.
DEFAULT_SALVAGE_BLOCK = (
    b"1\r\n1-9,10\r\n32\r\n10\r\n1-10\r\n14\r\n1-10\r\n16\r\n1-10\r\n17\r\n1-10\r\n"
    b"18\r\n1-10\r\n19\r\n1-10\r\n22\r\n1-10\r\n25\r\n1-10\r\n29\r\n1-10\r\n30\r\n"
    b"1-10\r\n36\r\n1-10\r\n37\r\n1-10\r\n41\r\n1-10\r\n47\r\n1-10\r\n35\r\n1-10\r\n"
    b"27\r\n1-10\r\n26\r\n1-10\r\n21\r\n1-10\r\n15\r\n1-10\r\n13\r\n1-10\r\n50\r\n"
    b"1-10\r\n49\r\n1-10\r\n34\r\n1-10\r\n52\r\n1-10\r\n51\r\n1-10\r\n63\r\n1-10\r\n"
    b"57\r\n1-7,8,9,10\r\n67\r\n1-7,8,9,10\r\n64\r\n1-7,8,9,10\r\n74\r\n1-7,8,9,10\r\n"
    b"23\r\n1-7,8,9,10\r\n8\r\n1-6,7,8,9,10\r\n")


def _num(v):
    """Format a number the way C# Convert.ToString(InvariantCulture) would."""
    f = float(v)
    return str(int(f)) if f.is_integer() else repr(f)


def _body(*lines):
    return "".join(f"{x}\r\n" for x in lines).encode("latin-1")


def _long(key, op, v):
    ivk = IVK.get(key)
    if ivk is None:
        raise ValueError(f"unknown value key '{key}'")
    return utl.Requirement(op, _body(int(v), ivk))


# Each condition key -> function returning a Requirement.
def _condition(key, v):
    if key == "type":
        oc = OBJECTCLASS.get(str(v).lower())
        if oc is None:
            raise ValueError(f"unknown item type '{v}'")
        return utl.Requirement(R_OBJECTCLASS, _body(oc))
    if key == "name_matches":
        return utl.Requirement(R_STRINGMATCH, _body(v, SVK_NAME))
    if key == "min_damage_ge":
        return utl.Requirement(R_MINDAMAGE_GE, _body(_num(v)))
    if key == "spell_count_ge":
        return utl.Requirement(R_SPELLCOUNT_GE, _body(int(v)))
    if key.endswith("_ge"):
        return _long(key[:-3], R_LONG_GE, v)
    if key.endswith("_le"):
        return _long(key[:-3], R_LONG_LE, v)
    if key.endswith("_eq"):
        return _long(key[:-3], R_LONG_E, v)
    raise ValueError(f"unknown condition '{key}'")


def compile_spec(spec) -> utl.Profile:
    p = utl.Profile()
    p.version = 1
    for i, rspec in enumerate(spec.get("rules", [])):
        rule = utl.Rule()
        rule.name = str(rspec.get("name", f"Rule {i + 1}"))
        action = str(rspec.get("action", "keep")).lower()
        if action not in ACTIONS:
            raise ValueError(f"rule '{rule.name}': unknown action '{action}'")
        rule.action = ACTIONS[action]
        if rule.action == ACTIONS["keepupto"]:
            rule.keep_up_to = int(rspec.get("count", 1))
        conds = rspec.get("when", {}) or {}
        if not conds:
            raise ValueError(f"rule '{rule.name}': has no 'when' conditions")
        for key, v in conds.items():
            rule.requirements.append(_condition(key, v))
        p.rules.append(rule)
    p.extra_blocks.append(("SalvageCombine", DEFAULT_SALVAGE_BLOCK))
    return p


def main():
    ap = argparse.ArgumentParser(description="Compile YAML loot spec -> VTClassic .utl")
    ap.add_argument("spec", help="input YAML file")
    ap.add_argument("-o", "--out", help="output .utl (default: <spec>.utl)")
    args = ap.parse_args()

    with open(args.spec, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    profile = compile_spec(spec)
    data = utl.dump(profile)

    # self-check: the file we just wrote must re-parse to an identical profile
    assert utl.dump(utl.parse(data)) == data, "internal round-trip check failed"

    out = args.out or (args.spec.rsplit(".", 1)[0] + ".utl")
    with open(out, "wb") as f:
        f.write(data)
    print(f"Wrote {out}: {len(profile.rules)} rules, {len(data)} bytes "
          f"(verified round-trip).")


if __name__ == "__main__":
    main()
