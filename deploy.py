#!/usr/bin/env python3
"""Recompile every profile in profiles/ and deploy the .utl into the VTank folder.

    py -3 deploy.py                    # compile all -> repo + default VTank folder
    py -3 deploy.py --dry-run          # show what would happen, write nothing
    py -3 deploy.py --vtank <path>     # override the VTank folder
    py -3 deploy.py --only thistlecrown   # deploy only profiles whose name matches

Each profiles/*.yaml declares its output filename with a top-level `out:` key
(e.g. `out: ThistlecrownCash.utl`); it falls back to the yaml basename + .utl.
The compiler ignores unknown top-level keys, so `out:` is invisible to it.

Every profile is round-trip self-checked before it is written (same guarantee
as utl_compile.py). Files in the VTank folder that this repo does not manage
(e.g. LootSnobV4.utl) are never touched.
"""
import argparse
import glob
import os
import sys

import yaml

import utl
import utl_compile

DEFAULT_VTANK = r"C:\Games\VirindiPlugins\VirindiTank"
# UtilityBelt reads ItemGiver (/ub ig) profiles from its OWN folder, not VTank's.
DEFAULT_ITEMGIVER = os.path.expanduser(
    r"~\Documents\Decal Plugins\UtilityBelt\itemgiver")
# Mag-Tools AutoPack reads <CharName>.autopack.utl from its own folder.
DEFAULT_MAGTOOLS = os.path.expanduser(r"~\Documents\Decal Plugins\Mag-Tools")
HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "profiles")


def out_name(path, spec):
    name = (spec or {}).get("out")
    if not name:
        name = os.path.splitext(os.path.basename(path))[0] + ".utl"
    return name


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vtank", default=DEFAULT_VTANK, help="VTank plugin folder")
    ap.add_argument("--itemgiver", default=DEFAULT_ITEMGIVER,
                    help="UtilityBelt ItemGiver folder (for profiles with itemgiver: true)")
    ap.add_argument("--magtools", default=DEFAULT_MAGTOOLS,
                    help="Mag-Tools folder (for autopack profiles with magtools: true)")
    ap.add_argument("--dry-run", action="store_true", help="write nothing; just report")
    ap.add_argument("--only", default="", help="substring filter on the yaml filename")
    args = ap.parse_args()

    yamls = sorted(glob.glob(os.path.join(PROFILES, "*.yaml")))
    if args.only:
        yamls = [y for y in yamls if args.only.lower() in os.path.basename(y).lower()]
    if not yamls:
        sys.exit("no matching profiles in profiles/")

    if not args.dry_run and not os.path.isdir(args.vtank):
        sys.exit(f"VTank folder not found: {args.vtank}\n"
                 f"Pass --vtank <path> or create it first.")

    for y in yamls:
        base = os.path.basename(y)
        with open(y, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        name = out_name(y, spec)

        profile = utl_compile.compile_spec(spec)
        data = utl.dump(profile)
        assert utl.dump(utl.parse(data)) == data, f"{name}: round-trip self-check failed"

        # Mag-Tools autopack profiles go to the Mag-Tools folder instead of the
        # VTank loot folder (they aren't loot profiles). Give-profiles also go to
        # the UtilityBelt itemgiver folder.
        mt = bool((spec or {}).get("magtools")) and args.magtools
        ig = bool((spec or {}).get("itemgiver")) and args.itemgiver
        dests = [os.path.join(PROFILES, name)]
        if mt:
            dests.append(os.path.join(args.magtools, name))
        else:
            dests.append(os.path.join(args.vtank, name))
            if ig:
                dests.append(os.path.join(args.itemgiver, name))
        tag = "  (+magtools)" if mt else ("  (+itemgiver)" if ig else "")

        if args.dry_run:
            print(f"[dry] {base:34s} -> {name:22s} "
                  f"{len(profile.rules):2d} rules{tag}")
            continue

        for dest in dests:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
        print(f"ok  {base:34s} -> {name:22s} "
              f"{len(profile.rules):2d} rules, {len(data)} bytes{tag}")

    if not args.dry_run:
        print(f"\nDeployed to {args.vtank}. In-game: reload VTank or re-open the "
              f"Loot tab to refresh the dropdown.")


if __name__ == "__main__":
    main()
