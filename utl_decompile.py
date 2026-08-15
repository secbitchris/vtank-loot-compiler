"""Decompile a VTClassic .utl profile back into the YAML spec format.

    py -3 utl_decompile.py my.utl -o my.yaml
    py -3 utl_decompile.py my.utl --verify      # recompile and diff the bytes

This is the inverse of utl_compile.py, so a profile authored in VTank's GUI can
be pulled into git and maintained as YAML. Decoding covers every rule type in
eLootRuleType; anything genuinely unknown is reported rather than dropped.

--verify recompiles the emitted YAML and compares it byte-for-byte with the
input, which is the only real proof the import was faithful.
"""

import argparse
import sys

import yaml

import utl
import utl_compile
from vtclassic_enums import (
    ACTION_NAME,
    DOUBLE_KEY_NAME,
    INT_KEY_NAME,
    LOOT_RULE_TYPE as T,
    OBJECT_CLASS_NAME,
    RULE_TYPE_NAME,
    SKILL_NAME,
    STRING_KEY_NAME,
    _snake,
)


class Undecodable(Exception):
    pass


def _lines(req):
    text = req.body.decode("latin-1")
    if text.endswith("\r\n"):
        text = text[:-2]
    return text.split("\r\n")


def _num(s):
    """Decode a numeric line back to int where exact, else float."""
    f = float(s)
    return int(f) if f.is_integer() and "." not in s and "E" not in s.upper() else f


def _intkey(code, what):
    name = INT_KEY_NAME.get(int(code))
    if name is None:
        raise Undecodable(f"{what}: unknown IntValueKey {code}")
    return _snake(name)


def _dblkey(code, what):
    name = DOUBLE_KEY_NAME.get(int(code))
    if name is None:
        raise Undecodable(f"{what}: unknown DoubleValueKey {code}")
    return _snake(name)


def _skill(code):
    name = SKILL_NAME.get(int(code))
    if name is None:
        raise Undecodable(f"unknown skill id {code}")
    return _snake(name)


def _color(L, extra=None):
    out = {"rgb": [int(L[0]), int(L[1]), int(L[2])],
           "max_hue_diff": _num(L[3]), "max_sv_diff": _num(L[4])}
    if extra:
        out[extra[0]] = extra[1]
    return out


def decode_requirement(req):
    """Return (yaml_key, yaml_value) for one requirement."""
    t = req.ruletype
    L = _lines(req)
    name = RULE_TYPE_NAME.get(t, f"type{t}")

    if t == T["ObjectClass"]:
        oc = OBJECT_CLASS_NAME.get(int(L[0]))
        if oc is None:
            raise Undecodable(f"unknown ObjectClass {L[0]}")
        return "type", oc
    if t == T["StringValueMatch"]:
        svk = STRING_KEY_NAME.get(int(L[1]))
        if svk is None:
            raise Undecodable(f"unknown StringValueKey {L[1]}")
        return f"{_snake(svk)}_matches", L[0]
    if t == T["SpellNameMatch"]:
        return "spell_name_matches", L[0]
    if t == T["SpellMatch"]:
        return "spell_match", {"matches": L[0], "not_matches": L[1], "count": int(L[2])}
    if t == T["SpellCountGE"]:
        return "spell_count_ge", int(L[0])

    if t in (T["LongValKeyGE"], T["LongValKeyLE"],
             T["LongValKeyE"], T["LongValKeyNE"]):
        op = {T["LongValKeyGE"]: "ge", T["LongValKeyLE"]: "le",
              T["LongValKeyE"]: "eq", T["LongValKeyNE"]: "ne"}[t]
        return f"{_intkey(L[1], name)}_{op}", int(L[0])
    if t in (T["DoubleValKeyGE"], T["DoubleValKeyLE"]):
        op = "ge" if t == T["DoubleValKeyGE"] else "le"
        return f"{_dblkey(L[1], name)}_{op}", _num(L[0])
    if t == T["BuffedLongValKeyGE"]:
        return f"buffed_{_intkey(L[1], name)}_ge", int(L[0])
    if t == T["BuffedDoubleValKeyGE"]:
        return f"buffed_{_dblkey(L[1], name)}_ge", _num(L[0])
    if t == T["LongValKeyFlagExists"]:
        return "flag_exists", {"key": _intkey(L[1], name), "flag": int(L[0])}

    simple_double = {
        T["MinDamageGE"]: "min_damage_ge",
        T["DamagePercentGE"]: "damage_percent_ge",
        T["TotalRatingsGE"]: "total_ratings_ge",
        T["BuffedMedianDamageGE"]: "buffed_median_damage_ge",
        T["BuffedMissileDamageGE"]: "buffed_missile_damage_ge",
        T["CalcdBuffedTinkedDamageGE"]: "calcd_buffed_tinked_damage_ge",
    }
    if t in simple_double:
        return simple_double[t], _num(L[0])
    if t == T["CalcedBuffedTinkedTargetMeleeGE"]:
        return "calced_buffed_tinked_target_melee", {
            "dot": _num(L[0]), "melee_defense_bonus": _num(L[1]),
            "attack_bonus": _num(L[2])}

    if t == T["CharacterLevelGE"]:
        return "char_level_ge", int(L[0])
    if t == T["CharacterLevelLE"]:
        return "char_level_le", int(L[0])
    if t == T["CharacterMainPackEmptySlotsGE"]:
        return "main_pack_empty_slots_ge", int(L[0])
    if t == T["CharacterSkillGE"]:
        return "char_skill_ge", {"skill": _skill(L[1]), "value": int(L[0])}
    if t == T["CharacterBaseSkill"]:
        return "char_base_skill", {"skill": _skill(L[0]),
                                   "min": int(L[1]), "max": int(L[2])}

    if t == T["AnySimilarColor"]:
        return "any_similar_color", _color(L)
    if t == T["SimilarColorArmorType"]:
        return "similar_color_armor_type", _color(L, ("armor_group", L[5]))
    if t == T["SlotSimilarColor"]:
        return "slot_similar_color", _color(L, ("slot", int(L[5])))
    if t == T["SlotExactPalette"]:
        return "slot_exact_palette", {"slot": int(L[0]), "palette": int(L[1])}

    if t == T["DisabledRule"]:
        return "__disabled__", L[0] == "true"

    raise Undecodable(f"no decoder for rule type {t} ({name})")


def decompile(profile):
    """Return (spec_dict, list_of_warnings)."""
    warnings = []
    rules = []
    for i, rule in enumerate(profile.rules):
        when = {}
        entry = {"name": rule.name,
                 "action": ACTION_NAME.get(rule.action, str(rule.action)).lower()}
        if rule.action == utl.KEEP_UP_TO:
            entry["count"] = rule.keep_up_to
        if rule.custom_expression:
            entry["expression"] = rule.custom_expression

        skip = False
        for req in rule.requirements:
            try:
                key, val = decode_requirement(req)
            except Undecodable as e:
                warnings.append(f"rule {i} {rule.name!r}: {e} -- RULE SKIPPED")
                skip = True
                break
            if key == "__disabled__":
                if val:
                    entry["enabled"] = False
                continue
            # Repeated conditions collapse into a list, which utl_compile expands
            # back into one requirement per element.
            when.setdefault(key, []).append(val)
        if skip:
            continue
        if not when:
            warnings.append(f"rule {i} {rule.name!r}: no conditions -- RULE SKIPPED")
            continue
        entry["when"] = {k: (v[0] if len(v) == 1 else v) for k, v in when.items()}
        rules.append(entry)

    for blocktype, body in profile.extra_blocks:
        if blocktype == "SalvageCombine":
            if body != utl_compile.DEFAULT_SALVAGE_BLOCK:
                warnings.append(
                    "SalvageCombine block differs from the compiler's built-in "
                    "default; recompiling will replace it with the default")
        else:
            warnings.append(f"extra block {blocktype!r} is not preserved on recompile")

    return {"rules": rules}, warnings


def equivalent(a: utl.Profile, b: utl.Profile) -> bool:
    """True if two profiles differ only in the order of a rule's requirements.

    cLootItemRule.Match AND-s every requirement and each Match is a pure
    predicate, so requirement order changes nothing but evaluation speed.
    Rule order, by contrast, IS significant (cLootRules.Classify is first-match-
    wins) and is compared strictly.
    """
    if len(a.rules) != len(b.rules) or a.extra_blocks != b.extra_blocks:
        return False
    for ra, rb in zip(a.rules, b.rules):
        if (ra.name, ra.action, ra.keep_up_to, ra.custom_expression) != \
           (rb.name, rb.action, rb.keep_up_to, rb.custom_expression):
            return False
        ka = sorted((q.ruletype, q.body) for q in ra.requirements)
        kb = sorted((q.ruletype, q.body) for q in rb.requirements)
        if ka != kb:
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Decompile VTClassic .utl -> YAML spec")
    ap.add_argument("profile", help="input .utl file")
    ap.add_argument("-o", "--out", help="output YAML (default: stdout)")
    ap.add_argument("--verify", action="store_true",
                    help="recompile the result and report byte differences")
    args = ap.parse_args()

    with open(args.profile, "rb") as f:
        original = f.read()
    parsed = utl.parse(original)
    spec, warnings = decompile(parsed)

    text = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"decompiled {len(parsed.rules)} rules -> {len(spec['rules'])} YAML rules",
          file=sys.stderr)

    if args.verify:
        rebuilt = utl.dump(utl_compile.compile_spec(yaml.safe_load(text)))
        if rebuilt == original:
            print("verify: BYTE-IDENTICAL to the input", file=sys.stderr)
        elif equivalent(parsed, utl.parse(rebuilt)):
            print("verify: SEMANTICALLY IDENTICAL (requirements regrouped; a rule's "
                  "requirements are AND-ed, so order does not affect matching)",
                  file=sys.stderr)
        else:
            print(f"verify: DIFFERS (orig {len(original)}B, rebuilt {len(rebuilt)}B) "
                  f"-- expected if any rule above was skipped", file=sys.stderr)
            sys.exit(1)

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
