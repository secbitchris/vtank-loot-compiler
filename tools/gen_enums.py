#!/usr/bin/env python3
"""Regenerate vtclassic_enums.py from a decompilation of the plugin binaries.

The tables the compiler encodes against are read out of the shipped assemblies
rather than transcribed by hand, so they cannot drift or acquire typos.

Decompile first (ilspycmd is a dotnet global tool):

    ilspycmd -p -o <srcdir> "C:/Games/VirindiPlugins/VirindiTankClassicLooter/VTClassic.dll"
    ilspycmd -t uTank2.LootPlugins.IntValueKey    ".../VirindiTank/utank2-i.dll" > <srcdir>/IntValueKey.cs
    ilspycmd -t uTank2.LootPlugins.DoubleValueKey ".../VirindiTank/utank2-i.dll" > <srcdir>/DoubleValueKey.cs
    ilspycmd -t uTank2.LootPlugins.StringValueKey ".../VirindiTank/utank2-i.dll" > <srcdir>/StringValueKey.cs
    ilspycmd -t uTank2.LootPlugins.ObjectClass    ".../VirindiTank/utank2-i.dll" > <srcdir>/ObjectClass.cs

Then:

    py -3 tools/gen_enums.py <srcdir> -o vtclassic_enums.py

No decompiled source is vendored into this repo -- only the resulting numeric
tables, which are facts about the file format.
"""

import argparse
import os
import re
import sys

MEMBER = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*(-?\d+))?\s*,?\s*$")

# (python table name, filename to search, C# enum name, origin assembly)
SOURCES = [
    ("LOOT_RULE_TYPE",   "eLootRuleType.cs",  "eLootRuleType",  "VTClassic.dll"),
    ("LOOT_ACTION",      "eLootAction.cs",    "eLootAction",    "VTClassic.dll"),
    ("SKILL_ID",         "VTCSkillID.cs",     "VTCSkillID",     "VTClassic.dll"),
    ("INT_VALUE_KEY",    "IntValueKey.cs",    "IntValueKey",    "utank2-i.dll"),
    ("DOUBLE_VALUE_KEY", "DoubleValueKey.cs", "DoubleValueKey", "utank2-i.dll"),
    ("STRING_VALUE_KEY", "StringValueKey.cs", "StringValueKey", "utank2-i.dll"),
    ("OBJECT_CLASS",     "ObjectClass.cs",    "ObjectClass",    "utank2-i.dll"),
]


def find(srcdir, filename):
    for root, _dirs, files in os.walk(srcdir):
        if filename in files:
            return os.path.join(root, filename)
    sys.exit(f"{filename} not found under {srcdir}")


def parse_enum(path, enum_name):
    """Return [(name, value)] in declaration order, honouring implicit increment."""
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"enum\s+" + re.escape(enum_name) + r"\s*\{", text)
    if not m:
        sys.exit(f"enum {enum_name} not found in {path}")
    i, depth = m.end(), 1
    while depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1

    out, nxt = [], 0
    for line in text[m.end():i - 1].splitlines():
        mm = MEMBER.match(line.split("//")[0])
        if not mm:
            continue          # also skips ilspycmd's interleaved version banner
        name, val = mm.group(1), mm.group(2)
        v = int(val) if val is not None else nxt
        out.append((name, v))
        nxt = v + 1
    return out


HEADER = '''"""Authoritative VTClassic / uTank2 enum tables.

GENERATED FILE - do not edit by hand. Regenerate with tools/gen_enums.py from a
decompilation of the shipped plugin binaries:

    VTClassic.dll  (VirindiTankClassicLooter) -> eLootRuleType, eLootAction, VTCSkillID
    utank2-i.dll   (VirindiTank)              -> IntValueKey, DoubleValueKey,
                                                 StringValueKey, ObjectClass

These are the ground truth the compiler encodes against. Every table below was
read out of the binaries, not inferred from sample profiles.
"""
'''

FOOTER = '''

def _snake(name):
    """CamelCase -> snake_case (matches the YAML condition spelling)."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\\1_\\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\\1_\\2", s)
    return s.lower()


def _snake_table(d):
    return {_snake(k): v for k, v in d.items()}


# snake_case lookup tables used by the YAML front end.
INT_KEY_BY_SNAKE = _snake_table(INT_VALUE_KEY)
DOUBLE_KEY_BY_SNAKE = _snake_table(DOUBLE_VALUE_KEY)
STRING_KEY_BY_SNAKE = _snake_table(STRING_VALUE_KEY)
SKILL_BY_SNAKE = _snake_table(SKILL_ID)
OBJECT_CLASS_BY_LOWER = {k.lower(): v for k, v in OBJECT_CLASS.items()}


def _rev(d):
    """Reverse a table for decoding. First declared name wins on duplicates."""
    out = {}
    for k, v in d.items():
        out.setdefault(v, k)
    return out


INT_KEY_NAME = _rev(INT_VALUE_KEY)
DOUBLE_KEY_NAME = _rev(DOUBLE_VALUE_KEY)
STRING_KEY_NAME = _rev(STRING_VALUE_KEY)
OBJECT_CLASS_NAME = _rev(OBJECT_CLASS)
SKILL_NAME = _rev(SKILL_ID)
RULE_TYPE_NAME = _rev(LOOT_RULE_TYPE)
ACTION_NAME = _rev(LOOT_ACTION)
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("srcdir", help="directory holding the decompiled .cs files")
    ap.add_argument("-o", "--out", default="vtclassic_enums.py")
    args = ap.parse_args()

    parsed = {}
    for var, filename, enum, origin in SOURCES:
        members = parse_enum(find(args.srcdir, filename), enum)
        parsed[var] = (members, enum, origin)
        print(f"{var:18s} {len(members):4d} members from {enum} ({origin})")

    # The YAML front end resolves a bare condition name against the int table
    # first and the double table second, so the two must not share a name.
    clash = set(n for n, _ in parsed["INT_VALUE_KEY"][0]) & \
        set(n for n, _ in parsed["DOUBLE_VALUE_KEY"][0])
    if clash:
        sys.exit(f"int/double value key name collision: {sorted(clash)}")
    print("int/double name collisions: NONE")

    aliases = {}
    seen = {}
    for n, v in parsed["INT_VALUE_KEY"][0]:
        seen.setdefault(v, []).append(n)
    aliases = {v: ns for v, ns in seen.items() if len(ns) > 1}
    print(f"IntValueKey duplicate values: {aliases or 'NONE'}")

    lines = [HEADER, "import re", "",
             "# Two IntValueKey members share a value; the first declared name is",
             "# canonical and the alias is kept here so a decoder can report it.",
             "INT_VALUE_KEY_ALIASES = {"]
    lines += [f"    {v}: {ns!r}," for v, ns in sorted(aliases.items())]
    lines += ["}", ""]

    for var, (members, enum, origin) in parsed.items():
        lines.append(f"# {enum} ({origin}) - {len(members)} members")
        lines.append(f"{var} = {{")
        lines += [f'    "{n}": {v},' for n, v in members]
        lines += ["}", ""]

    lines.append(FOOTER)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
