"""VTClassic .utl loot-profile parser/writer, derived from the VTClassic source
(IbespwnAC/VirindiTank: LootRules.cs / UTLFileExtraBlockManager.cs).

Grammar (file version >= 1, CRLF line endings):
    "UTL"
    <fileversion>
    <rulecount>
    rule * rulecount
    extrablock * until EOF

rule (cLootItemRule):
    <name>
    <customexpression>                     # empty string if none
    <priority>;<action>[;<ruletype>]*      # the 'big line'
    [<keepuptodata>]                        # ONLY if action == KeepUpTo (10)
    per ruletype, in order:
        <lengthcode>                        # byte length of the body that follows
        <body>                              # <lengthcode> raw bytes (incl. trailing CRLFs)

extrablock (UTLFileExtraBlockManager):
    <blocktype>                             # e.g. "SalvageCombine"
    <blocklen>                              # byte length of body
    <body>                                  # <blocklen> raw bytes

Bodies are preserved verbatim as bytes, so this round-trips exactly regardless of
which requirement types appear.
"""

CRLF = b"\r\n"
KEEP_UP_TO = 10  # eLootAction.KeepUpTo


class ByteReader:
    def __init__(self, data: bytes):
        self.d = data
        self.i = 0

    def line(self) -> str:
        j = self.d.find(CRLF, self.i)
        if j < 0:
            s = self.d[self.i:]
            self.i = len(self.d)
            return s.decode("latin-1")
        s = self.d[self.i:j]
        self.i = j + 2
        return s.decode("latin-1")

    def take(self, n: int) -> bytes:
        b = self.d[self.i:self.i + n]
        self.i += n
        return b

    def eof(self) -> bool:
        return self.i >= len(self.d)


class Requirement:
    def __init__(self, ruletype: int, body: bytes):
        self.ruletype = ruletype
        self.body = body


class Rule:
    def __init__(self):
        self.name = ""
        self.custom_expression = ""
        self.priority = 0
        self.action = 0
        self.keep_up_to = None      # int or None
        self.requirements = []      # list[Requirement]


class Profile:
    def __init__(self):
        self.version = 1
        self.rules = []             # list[Rule]
        self.extra_blocks = []      # list[(blocktype:str, body:bytes)]


def parse(data: bytes) -> Profile:
    r = ByteReader(data)
    p = Profile()

    first = r.line()
    if first == "UTL":
        p.version = int(r.line())
        count = int(r.line())
    else:                            # legacy version-0 file: starts with rulecount
        p.version = 0
        count = int(first)

    for _ in range(count):
        rule = Rule()
        rule.name = r.line()
        rule.custom_expression = r.line()
        big = r.line().split(";")
        rule.priority = int(big[0])
        rule.action = int(big[1])
        types = [int(x) for x in big[2:]]
        if rule.action == KEEP_UP_TO:
            rule.keep_up_to = int(r.line())
        for t in types:
            length = int(r.line())
            body = r.take(length)
            rule.requirements.append(Requirement(t, body))
        p.rules.append(rule)

    while not r.eof():
        blocktype = r.line()
        if blocktype == "" and r.eof():
            break
        blocklen = int(r.line())
        body = r.take(blocklen)
        p.extra_blocks.append((blocktype, body))

    return p


def dump(p: Profile) -> bytes:
    out = bytearray()

    def wl(s):
        out.extend(s.encode("latin-1"))
        out.extend(CRLF)

    if p.version >= 1:
        wl("UTL")
        wl(str(p.version))
    wl(str(len(p.rules)))

    for rule in p.rules:
        wl(rule.name)
        wl(rule.custom_expression)
        big = [str(rule.priority), str(rule.action)]
        big += [str(req.ruletype) for req in rule.requirements]
        wl(";".join(big))
        if rule.action == KEEP_UP_TO:
            wl(str(rule.keep_up_to))
        for req in rule.requirements:
            wl(str(len(req.body)))     # recomputed length prefix
            out.extend(req.body)

    for blocktype, body in p.extra_blocks:
        wl(blocktype)
        wl(str(len(body)))
        out.extend(body)

    return bytes(out)


if __name__ == "__main__":
    import sys
    import glob
    files = sys.argv[1:] or sorted(glob.glob("*.utl"))
    ok = True
    for path in files:
        with open(path, "rb") as f:
            original = f.read()
        try:
            p = parse(original)
            rebuilt = dump(p)
        except Exception as e:
            print(f"FAIL  {path:20s} parse/dump error: {e}")
            ok = False
            continue
        if rebuilt == original:
            print(f"OK    {path:20s} {len(p.rules):4d} rules, "
                  f"{len(p.extra_blocks)} extra block(s)  [byte-exact round-trip]")
        else:
            ok = False
            n = min(len(rebuilt), len(original))
            diff = next((k for k in range(n) if rebuilt[k] != original[k]), n)
            print(f"DIFF  {path:20s} first mismatch at byte {diff} "
                  f"(orig {len(original)}B vs rebuilt {len(rebuilt)}B)")
            print(f"      orig ...{original[max(0,diff-20):diff+20]!r}")
            print(f"      new  ...{rebuilt[max(0,diff-20):diff+20]!r}")
    sys.exit(0 if ok else 1)
