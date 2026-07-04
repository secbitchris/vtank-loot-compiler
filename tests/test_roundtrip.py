"""Proof the .utl codec is correct: parse real VTank-authored profiles and
re-emit them byte-for-byte, and check the compiler's output round-trips too.

Run:  python tests/test_roundtrip.py
"""

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import utl  # noqa: E402
import utl_compile  # noqa: E402
import yaml  # noqa: E402


def test_fixture_roundtrip():
    fixtures = sorted(glob.glob(os.path.join(HERE, "fixtures", "*.utl")))
    assert fixtures, "no fixtures found"
    for path in fixtures:
        with open(path, "rb") as f:
            original = f.read()
        rebuilt = utl.dump(utl.parse(original))
        assert rebuilt == original, f"round-trip mismatch: {os.path.basename(path)}"
        print(f"  ok  {os.path.basename(path):18s} "
              f"{len(utl.parse(original).rules)} rules")


def test_compiler_output_is_valid():
    with open(os.path.join(ROOT, "loot.example.yaml"), encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    data = utl.dump(utl_compile.compile_spec(spec))
    # the emitted profile must itself parse and round-trip
    assert utl.dump(utl.parse(data)) == data
    p = utl.parse(data)
    assert len(p.rules) == len(spec["rules"])
    assert p.extra_blocks and p.extra_blocks[0][0] == "SalvageCombine"
    print(f"  ok  compiled example -> {len(p.rules)} rules, {len(data)} bytes")


if __name__ == "__main__":
    print("fixture round-trip (parser matches VTank byte-for-byte):")
    test_fixture_roundtrip()
    print("compiler output validity:")
    test_compiler_output_is_valid()
    print("\nALL PASS")
