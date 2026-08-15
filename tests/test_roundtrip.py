"""Proof the .utl codec and the condition encoder are correct.

Four layers, weakest to strongest:

1. container codec  - parse real VTank profiles and re-emit them byte-for-byte
2. encoder goldens  - each condition must produce the exact bytes VTank writes
3. enum tables      - spot-check values read out of the plugin binaries
4. full round-trip  - decompile every real profile and recompile it

Layer 2 is the one that matters: layer 1 preserves requirement bodies as opaque
bytes, so it can pass even if every condition were encoded wrongly.

Run:  python tests/test_roundtrip.py     (or: pytest tests/)
"""

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import utl  # noqa: E402
import utl_compile  # noqa: E402
import utl_decompile  # noqa: E402
import vtclassic_enums as E  # noqa: E402
import yaml  # noqa: E402

FIXTURES = sorted(glob.glob(os.path.join(HERE, "fixtures", "*.utl")))


def _compile_one(key, value):
    req = utl_compile._condition(key, value)
    return req.ruletype, req.body


# (yaml key, yaml value, expected ruletype, expected body)
# Bodies marked REAL are copied from bytes VTank itself wrote in tests/fixtures.
GOLDENS = [
    # --- value keys -------------------------------------------------------
    ("value_ge",          5000,      3, b"5000\r\n19\r\n"),
    ("value_le",          20000,     2, b"20000\r\n19\r\n"),        # REAL
    ("armor_level_ge",    250,       3, b"250\r\n28\r\n"),          # REAL
    ("burden_le",         50,        2, b"50\r\n5\r\n"),
    ("workmanship_ge",    8,         3, b"8\r\n105\r\n"),
    ("stack_count_ge",    10,        3, b"10\r\n218103814\r\n"),
    ("material_eq",       66,       12, b"66\r\n131\r\n"),          # REAL
    ("icon_ne",           27658,    13, b"27658\r\n218103809\r\n"),  # REAL
    ("max_damage_ge",     222,       3, b"222\r\n218103842\r\n"),
    # --- decimal value keys (were unreachable before) ---------------------
    ("salvage_workmanship_ge", 10,   5, b"10\r\n167772169\r\n"),    # REAL
    ("attack_bonus_ge",   1.16,      5, b"1.16\r\n167772172\r\n"),  # REAL
    ("melee_defense_bonus_ge", 1.13, 5, b"1.13\r\n29\r\n"),         # REAL
    ("damage_bonus_ge",   2.3,       5, b"2.3\r\n167772174\r\n"),   # REAL
    ("variance_le",       0.5,       4, b"0.5\r\n167772171\r\n"),   # REAL
    ("mana_c_bonus_ge",   0.091,     5, b"0.091\r\n144\r\n"),       # REAL
    # --- dedicated rule types ---------------------------------------------
    ("type",              "Armor",   7, b"2\r\n"),
    ("type",              "WandStaffOrb", 7, b"31\r\n"),            # REAL
    ("name_matches",      "Foo|Bar", 1, b"Foo|Bar\r\n1\r\n"),
    ("full_description_matches", "x", 1, b"x\r\n16\r\n"),
    ("spell_name_matches", "Clouded Soul|Horizon's Blades|Cloaked in Skill",
                                     0, b"Clouded Soul|Horizon's Blades|Cloaked in Skill\r\n"),  # REAL
    ("spell_count_ge",    1,         8, b"1\r\n"),                  # REAL
    ("min_damage_ge",     12,       10, b"12\r\n"),                 # REAL
    ("spell_match", {"matches": "Bane", "not_matches": "", "count": 3},
                                     9, b"Bane\r\n\r\n3\r\n"),      # REAL
    ("flag_exists", {"key": "equipable_slots", "flag": 222},
                                    11, b"222\r\n218103822\r\n"),   # REAL
    # --- character-state rule types ---------------------------------------
    ("main_pack_empty_slots_ge", 4, 1001, b"4\r\n"),                # REAL
    ("char_level_le",     274,    1003, b"274\r\n"),                # REAL
    ("char_skill_ge", {"skill": "lockpick", "value": 150},
                                  1000, b"150\r\n23\r\n"),          # REAL
    ("char_base_skill", {"skill": "lockpick", "min": 150, "max": 999},
                                  1004, b"23\r\n150\r\n999\r\n"),   # REAL
    # --- colour rule types ------------------------------------------------
    ("any_similar_color", {"rgb": [255, 255, 255], "max_hue_diff": 10,
                           "max_sv_diff": 0.1},
                                    14, b"255\r\n255\r\n255\r\n10\r\n0.1\r\n"),  # REAL
    ("slot_exact_palette", {"slot": 0, "palette": 7684},
                                    17, b"0\r\n7684\r\n"),          # REAL
]


def test_encoder_goldens():
    """Every condition must emit the exact bytes VTClassic's own Write() emits."""
    for key, value, want_type, want_body in GOLDENS:
        got_type, got_body = _compile_one(key, value)
        assert got_type == want_type, \
            f"{key}: ruletype {got_type} != {want_type}"
        assert got_body == want_body, \
            f"{key}: body {got_body!r} != {want_body!r}"
    print(f"  ok  {len(GOLDENS)} condition goldens byte-exact")


def test_goldens_appear_in_real_profiles():
    """Cross-check: goldens marked REAL must actually occur in VTank's output."""
    seen = set()
    for path in FIXTURES:
        with open(path, "rb") as f:
            for rule in utl.parse(f.read()).rules:
                for q in rule.requirements:
                    seen.add((q.ruletype, q.body))
    matched = [(k, v) for k, v, t, b in GOLDENS if (t, b) in seen]
    assert len(matched) == 22, \
        f"{len(matched)} goldens corroborated by real VTank bytes, expected 22"
    print(f"  ok  {len(matched)}/{len(GOLDENS)} goldens found verbatim in real profiles")


def test_double_formatting():
    """C# Convert.ToString(double) is G15: 10.0 prints as '10', not '10.0'."""
    assert utl_compile._dbl(10.0) == "10"
    assert utl_compile._dbl(1.16) == "1.16"
    assert utl_compile._dbl(0.1) == "0.1"
    assert utl_compile._dbl(2.3) == "2.3"
    assert utl_compile._dbl(0.1 + 0.2) == "0.3"   # repr() would give 0.30000000000000004
    print("  ok  double formatting matches .NET G15")


def test_enum_tables():
    """Spot-check tables read out of the plugin binaries."""
    assert E.INT_VALUE_KEY["Workmanship"] == 105
    assert E.INT_VALUE_KEY["Burden"] == 5
    assert E.INT_VALUE_KEY["Value"] == 19
    assert E.DOUBLE_VALUE_KEY["SalvageWorkmanship"] == 167772169
    assert E.STRING_VALUE_KEY["Name"] == 1
    assert E.OBJECT_CLASS["WandStaffOrb"] == 31
    assert E.LOOT_ACTION["KeepUpTo"] == 10
    assert E.LOOT_RULE_TYPE["DisabledRule"] == 9999
    # names must not collide between the int and double key namespaces, because
    # a bare condition name is resolved against int first, then double
    assert not (set(E.INT_VALUE_KEY) & set(E.DOUBLE_VALUE_KEY))
    print(f"  ok  enum tables ({len(E.INT_VALUE_KEY)} int keys, "
          f"{len(E.LOOT_RULE_TYPE)} rule types)")


def test_fixture_roundtrip():
    """Container codec: real VTank profiles re-emit byte-for-byte."""
    assert FIXTURES, "no fixtures found"
    for path in FIXTURES:
        with open(path, "rb") as f:
            original = f.read()
        rebuilt = utl.dump(utl.parse(original))
        assert rebuilt == original, f"round-trip mismatch: {os.path.basename(path)}"
        print(f"  ok  {os.path.basename(path):18s} "
              f"{len(utl.parse(original).rules)} rules")


def test_decompile_roundtrip():
    """Every real profile decompiles to YAML and recompiles equivalently."""
    targets = FIXTURES + sorted(glob.glob(os.path.join(ROOT, "profiles", "*.utl")))
    for path in targets:
        with open(path, "rb") as f:
            original = f.read()
        parsed = utl.parse(original)
        spec, warnings = utl_decompile.decompile(parsed)
        assert not warnings, f"{os.path.basename(path)}: {warnings}"
        assert len(spec["rules"]) == len(parsed.rules), \
            f"{os.path.basename(path)}: dropped rules"
        # round-trip the YAML text itself, not just the dict
        reloaded = yaml.safe_load(yaml.safe_dump(spec, sort_keys=False))
        rebuilt = utl.dump(utl_compile.compile_spec(reloaded))
        assert utl_decompile.equivalent(parsed, utl.parse(rebuilt)), \
            f"{os.path.basename(path)}: recompile not equivalent"
        print(f"  ok  {os.path.basename(path):22s} {len(parsed.rules):3d} rules "
              f"-> YAML -> {'byte-exact' if rebuilt == original else 'equivalent'}")


def test_committed_profiles_match_their_yaml():
    """The .utl files committed next to each profile must match a fresh compile."""
    sys.path.insert(0, ROOT)
    import deploy  # noqa: E402
    n = 0
    for y in sorted(glob.glob(os.path.join(ROOT, "profiles", "*.yaml"))):
        with open(y, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        expected_path = os.path.join(ROOT, "profiles", deploy.out_name(y, spec))
        if not os.path.exists(expected_path):
            continue
        with open(expected_path, "rb") as f:
            committed = f.read()
        assert utl.dump(utl_compile.compile_spec(spec)) == committed, \
            f"{os.path.basename(y)} no longer compiles to its committed .utl"
        n += 1
    print(f"  ok  {n} committed profiles reproduce byte-for-byte")


def test_compiler_output_is_valid():
    with open(os.path.join(ROOT, "loot.example.yaml"), encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    data = utl.dump(utl_compile.compile_spec(spec))
    assert utl.dump(utl.parse(data)) == data
    p = utl.parse(data)
    assert len(p.rules) == len(spec["rules"])
    assert p.extra_blocks and p.extra_blocks[0][0] == "SalvageCombine"
    print(f"  ok  compiled example -> {len(p.rules)} rules, {len(data)} bytes")


def test_rejects_bad_input():
    """Typos must fail loudly rather than compile to a silently-wrong profile."""
    for spec, why in [
        ({"rules": [{"name": "x", "action": "keep", "when": {"nonsense_ge": 1}}]},
         "unknown condition"),
        ({"rules": [{"name": "x", "action": "hoard", "when": {"value_ge": 1}}]},
         "unknown action"),
        ({"rules": [{"name": "x", "action": "keep", "when": {"type": "Sandwich"}}]},
         "unknown item type"),
        ({"rules": [{"name": "x", "action": "keep", "whn": {"value_ge": 1}}]},
         "misspelled rule key"),
        ({"rules": [{"name": "x", "action": "keep", "when": {}}]},
         "empty when"),
        ({"rules": [{"name": "x", "action": "keep", "when": {"variance_eq": 1}}]},
         "_eq on a decimal key"),
    ]:
        try:
            utl_compile.compile_spec(spec)
        except ValueError:
            continue
        raise AssertionError(f"should have rejected: {why}")
    print("  ok  bad input rejected (6 cases)")


if __name__ == "__main__":
    print("encoder goldens (bytes match VTClassic's own Write()):")
    test_encoder_goldens()
    test_goldens_appear_in_real_profiles()
    test_double_formatting()
    print("enum tables (read from the plugin binaries):")
    test_enum_tables()
    print("container codec (parser matches VTank byte-for-byte):")
    test_fixture_roundtrip()
    print("decompile -> YAML -> recompile:")
    test_decompile_roundtrip()
    print("regression:")
    test_committed_profiles_match_their_yaml()
    test_compiler_output_is_valid()
    test_rejects_bad_input()
    print("\nALL PASS")
