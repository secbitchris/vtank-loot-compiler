"""Compile a friendly YAML loot spec into a VTClassic .utl profile.

    py -3 utl_compile.py loot.yaml -o my.utl

Drop the resulting .utl in your Virindi Tank folder and load it in-game.

Every rule type, action and value key is encoded from the tables in
vtclassic_enums.py, which are read straight out of the shipped plugin binaries.
"""

import argparse
import sys

import yaml

import utl
from vtclassic_enums import (
    DOUBLE_KEY_BY_SNAKE,
    INT_KEY_BY_SNAKE,
    LOOT_ACTION,
    LOOT_RULE_TYPE as T,
    OBJECT_CLASS_BY_LOWER,
    SKILL_BY_SNAKE,
    STRING_KEY_BY_SNAKE,
)

# eLootAction, lowercased: noloot, keep, salvage, sell, read, user1..user5, keepupto
ACTIONS = {name.lower(): v for name, v in LOOT_ACTION.items()}

# Default SalvageCombine trailing block (captured from a known-good profile) so the
# generated file is complete and VTank's salvage logic never sees a null block.
# Body is: <version> <default combine string> <n> then n * (<material> <combine>).
DEFAULT_SALVAGE_BLOCK = (
    b"1\r\n1-9,10\r\n32\r\n10\r\n1-10\r\n14\r\n1-10\r\n16\r\n1-10\r\n17\r\n1-10\r\n"
    b"18\r\n1-10\r\n19\r\n1-10\r\n22\r\n1-10\r\n25\r\n1-10\r\n29\r\n1-10\r\n30\r\n"
    b"1-10\r\n36\r\n1-10\r\n37\r\n1-10\r\n41\r\n1-10\r\n47\r\n1-10\r\n35\r\n1-10\r\n"
    b"27\r\n1-10\r\n26\r\n1-10\r\n21\r\n1-10\r\n15\r\n1-10\r\n13\r\n1-10\r\n50\r\n"
    b"1-10\r\n49\r\n1-10\r\n34\r\n1-10\r\n52\r\n1-10\r\n51\r\n1-10\r\n63\r\n1-10\r\n"
    b"57\r\n1-7,8,9,10\r\n67\r\n1-7,8,9,10\r\n64\r\n1-7,8,9,10\r\n74\r\n1-7,8,9,10\r\n"
    b"23\r\n1-7,8,9,10\r\n8\r\n1-6,7,8,9,10\r\n")

RULE_KEYS = {"name", "action", "count", "when", "enabled", "expression"}


def _int(v):
    """Format an int the way C# Convert.ToString(int, InvariantCulture) would."""
    return str(int(v))


def _dbl(v):
    """Format a double the way C# Convert.ToString(double, InvariantCulture) would.

    .NET Framework's default double formatting is G15, which prints 10.0 as "10"
    and 1.16 as "1.16" -- matching the bytes VTank itself writes.
    """
    return f"{float(v):.15g}".replace("e", "E")


def _req(ruletype, *lines):
    body = "".join(f"{x}\r\n" for x in lines).encode("latin-1")
    return utl.Requirement(ruletype, body)


def _field(cond, spec, key, *, required=True, default=None):
    if key not in spec:
        if required:
            raise ValueError(f"condition '{cond}': missing field '{key}'")
        return default
    return spec[key]


def _skill(cond, v):
    s = SKILL_BY_SNAKE.get(str(v).lower().replace(" ", "_"))
    if s is None:
        raise ValueError(f"condition '{cond}': unknown skill '{v}'")
    return s


def _color(cond, spec, ruletype, *extra):
    """Shared encoder for the colour rules: R, G, B, maxdiff-H, maxdiff-SV, [extra]."""
    rgb = _field(cond, spec, "rgb")
    if not (isinstance(rgb, (list, tuple)) and len(rgb) == 3):
        raise ValueError(f"condition '{cond}': 'rgb' must be a list of 3 values")
    return _req(ruletype, *(_int(c) for c in rgb),
                _dbl(_field(cond, spec, "max_hue_diff", required=False, default=10.0)),
                _dbl(_field(cond, spec, "max_sv_diff", required=False, default=0.1)),
                *extra)


# Conditions with a dedicated rule type. These are matched BEFORE the generic
# <valuekey>_<op> fallback, because several of them collide with an IntValueKey
# member of the same name -- e.g. spell_count_ge means SpellCountGE (rule type 8),
# not LongValKeyGE against IntValueKey.SpellCount.
def _dispatch(key, v):
    if key == "type":
        oc = OBJECT_CLASS_BY_LOWER.get(str(v).lower())
        if oc is None or str(v).lower() == "numobjectclasses":
            raise ValueError(f"unknown item type '{v}'")
        return _req(T["ObjectClass"], _int(oc))

    if key == "spell_name_matches":
        return _req(T["SpellNameMatch"], v)

    if key == "spell_match":
        return _req(T["SpellMatch"],
                    _field(key, v, "matches", required=False, default=""),
                    _field(key, v, "not_matches", required=False, default=""),
                    _int(_field(key, v, "count", required=False, default=1)))

    if key == "spell_count_ge":
        return _req(T["SpellCountGE"], _int(v))

    # doubles with no value key
    for name, rt in (("min_damage_ge", "MinDamageGE"),
                     ("damage_percent_ge", "DamagePercentGE"),
                     ("total_ratings_ge", "TotalRatingsGE"),
                     ("buffed_median_damage_ge", "BuffedMedianDamageGE"),
                     ("buffed_missile_damage_ge", "BuffedMissileDamageGE"),
                     ("calcd_buffed_tinked_damage_ge", "CalcdBuffedTinkedDamageGE")):
        if key == name:
            return _req(T[rt], _dbl(v))

    if key == "calced_buffed_tinked_target_melee":
        return _req(T["CalcedBuffedTinkedTargetMeleeGE"],
                    _dbl(_field(key, v, "dot")),
                    _dbl(_field(key, v, "melee_defense_bonus")),
                    _dbl(_field(key, v, "attack_bonus")))

    # character-state conditions
    if key == "char_level_ge":
        return _req(T["CharacterLevelGE"], _int(v))
    if key == "char_level_le":
        return _req(T["CharacterLevelLE"], _int(v))
    if key == "main_pack_empty_slots_ge":
        return _req(T["CharacterMainPackEmptySlotsGE"], _int(v))
    if key == "char_skill_ge":
        return _req(T["CharacterSkillGE"], _int(_field(key, v, "value")),
                    _int(_skill(key, _field(key, v, "skill"))))
    if key == "char_base_skill":
        return _req(T["CharacterBaseSkill"],
                    _int(_skill(key, _field(key, v, "skill"))),
                    _int(_field(key, v, "min", required=False, default=0)),
                    _int(_field(key, v, "max", required=False, default=999)))

    if key == "flag_exists":
        name = str(_field(key, v, "key"))
        ivk = INT_KEY_BY_SNAKE.get(name)
        if ivk is None:
            raise ValueError(f"condition 'flag_exists': unknown value key '{name}'")
        return _req(T["LongValKeyFlagExists"], _int(_field(key, v, "flag")), _int(ivk))

    # colour rules
    if key == "any_similar_color":
        return _color(key, v, T["AnySimilarColor"])
    if key == "similar_color_armor_type":
        return _color(key, v, T["SimilarColorArmorType"],
                      str(_field(key, v, "armor_group")))
    if key == "slot_similar_color":
        return _color(key, v, T["SlotSimilarColor"], _int(_field(key, v, "slot")))
    if key == "slot_exact_palette":
        return _req(T["SlotExactPalette"], _int(_field(key, v, "slot")),
                    _int(_field(key, v, "palette")))

    return None


_INT_OPS = {"_ge": "LongValKeyGE", "_le": "LongValKeyLE",
            "_eq": "LongValKeyE", "_ne": "LongValKeyNE"}
_DBL_OPS = {"_ge": "DoubleValKeyGE", "_le": "DoubleValKeyLE"}


def _generic(key, v):
    """<valuekey>_ge/_le/_eq/_ne, buffed_<valuekey>_ge, and <stringkey>_matches."""
    if key.endswith("_matches"):
        svk = STRING_KEY_BY_SNAKE.get(key[:-len("_matches")])
        if svk is not None:
            return _req(T["StringValueMatch"], v, _int(svk))

    for suffix in ("_ge", "_le", "_eq", "_ne"):
        if not key.endswith(suffix):
            continue
        base = key[:-len(suffix)]
        buffed = base.startswith("buffed_")
        name = base[len("buffed_"):] if buffed else base

        if name in INT_KEY_BY_SNAKE:
            if buffed:
                if suffix != "_ge":
                    raise ValueError(f"condition '{key}': buffed keys support only _ge")
                return _req(T["BuffedLongValKeyGE"], _int(v), _int(INT_KEY_BY_SNAKE[name]))
            return _req(T[_INT_OPS[suffix]], _int(v), _int(INT_KEY_BY_SNAKE[name]))

        if name in DOUBLE_KEY_BY_SNAKE:
            if buffed:
                if suffix != "_ge":
                    raise ValueError(f"condition '{key}': buffed keys support only _ge")
                return _req(T["BuffedDoubleValKeyGE"], _dbl(v),
                            _int(DOUBLE_KEY_BY_SNAKE[name]))
            if suffix not in _DBL_OPS:
                raise ValueError(
                    f"condition '{key}': '{name}' is a decimal value key, which "
                    f"supports only _ge and _le")
            return _req(T[_DBL_OPS[suffix]], _dbl(v), _int(DOUBLE_KEY_BY_SNAKE[name]))
    return None


def _condition(key, v):
    req = _dispatch(key, v)
    if req is None:
        req = _generic(key, v)
    if req is None:
        raise ValueError(f"unknown condition '{key}'")
    return req


def compile_spec(spec) -> utl.Profile:
    p = utl.Profile()
    p.version = 1
    for i, rspec in enumerate(spec.get("rules", [])):
        rule = utl.Rule()
        rule.name = str(rspec.get("name", f"Rule {i + 1}"))

        unknown = set(rspec) - RULE_KEYS
        if unknown:
            raise ValueError(f"rule '{rule.name}': unknown key(s) "
                             f"{sorted(unknown)}; expected {sorted(RULE_KEYS)}")

        action = str(rspec.get("action", "keep")).lower()
        if action not in ACTIONS:
            raise ValueError(f"rule '{rule.name}': unknown action '{action}'; "
                             f"expected one of {sorted(ACTIONS)}")
        rule.action = ACTIONS[action]
        if rule.action == ACTIONS["keepupto"]:
            rule.keep_up_to = int(rspec.get("count", 1))
        rule.custom_expression = str(rspec.get("expression", ""))

        conds = rspec.get("when", {}) or {}
        if not conds:
            raise ValueError(f"rule '{rule.name}': has no 'when' conditions")
        for key, v in conds.items():
            # A list value repeats the condition once per element (all AND-ed).
            # No single condition takes a list natively, so this is unambiguous --
            # it is how a rule carries e.g. two name_matches, which VTank's GUI
            # emits and a plain mapping cannot hold.
            for item in (v if isinstance(v, list) else [v]):
                try:
                    rule.requirements.append(_condition(key, item))
                except ValueError as e:
                    raise ValueError(f"rule '{rule.name}': {e}") from None

        # A DisabledRule requirement never matches, which is how VTank switches a
        # rule off while keeping it in the file.
        if rspec.get("enabled", True) is False:
            rule.requirements.append(_req(T["DisabledRule"], "true"))

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

    try:
        profile = compile_spec(spec)
    except ValueError as e:
        sys.exit(f"{args.spec}: {e}")
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
