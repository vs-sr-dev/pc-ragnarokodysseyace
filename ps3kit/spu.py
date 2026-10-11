"""Cell SPU decoding, disassembly and an instruction census.

    python -m ps3kit.spu GAME.elf --at 0xF3D260 [--count 20] [--base 0xF3D200]
    python -m ps3kit.spu GAME.elf --mix 0xF3D200:0xFE20 [--mix ...]

An SPU program runs from its local store, so its addresses are local-store
addresses: --base names the executable address that local-store address 0
was loaded from, and branch targets are shown in local-store terms.

decode(word) returns an Ins with the canonical operation name and its
fields; text(ins, pc) renders it for reading. Every SPU instruction is one
word, in one of seven formats told apart by the width of the opcode at its
top (4, 7, 8, 9, 10 or 11 bits); no two formats' opcodes overlap, so the
widths are tried from the narrowest. No dependencies.
"""
import argparse
import collections


class Ins:
    __slots__ = ("op", "form", "f", "word")

    def __init__(self, op, form, word, **f):
        self.op, self.form, self.word, self.f = op, form, word, f

    def __repr__(self):
        return f"Ins({self.op} {self.f})"


def _sext(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


# --- opcode tables, by opcode width -----------------------------------------------

_RRR = {0x8: "selb", 0xB: "shufb", 0xC: "mpya", 0xD: "fnms", 0xE: "fma", 0xF: "fms"}

_RI18 = {0x08: "hbra", 0x09: "hbrr", 0x21: "ila"}

_RI10 = {0x34: "lqd", 0x24: "stqd", 0x1D: "ahi", 0x1C: "ai", 0x0D: "sfhi", 0x0C: "sfi",
         0x74: "mpyi", 0x75: "mpyui", 0x16: "andbi", 0x15: "andhi", 0x14: "andi",
         0x06: "orbi", 0x05: "orhi", 0x04: "ori", 0x46: "xorbi", 0x45: "xorhi", 0x44: "xori",
         0x7F: "heqi", 0x4F: "hgti", 0x5F: "hlgti", 0x7E: "ceqbi", 0x7D: "ceqhi", 0x7C: "ceqi",
         0x4E: "cgtbi", 0x4D: "cgthi", 0x4C: "cgti", 0x5E: "clgtbi", 0x5D: "clgthi", 0x5C: "clgti"}

_RI16 = {0x061: "lqa", 0x067: "lqr", 0x041: "stqa", 0x047: "stqr", 0x083: "ilh", 0x082: "ilhu",
         0x081: "il", 0x0C1: "iohl", 0x065: "fsmbi", 0x064: "br", 0x060: "bra", 0x066: "brsl",
         0x062: "brasl", 0x042: "brnz", 0x040: "brz", 0x046: "brhnz", 0x044: "brhz"}

_RI8 = {0x1D8: "cflts", 0x1D9: "cfltu", 0x1DA: "csflt", 0x1DB: "cuflt"}

# 11-bit opcodes: RR, and RI7 where the RB field is an immediate
_RR = {
    0x000: "stop", 0x140: "stopd", 0x001: "lnop", 0x201: "nop", 0x002: "sync", 0x003: "dsync",
    0x00C: "mfspr", 0x10C: "mtspr", 0x00D: "rdch", 0x00F: "rchcnt", 0x10D: "wrch",
    0x1C4: "lqx", 0x144: "stqx", 0x1D4: "cbx", 0x1D5: "chx", 0x1D6: "cwx", 0x1D7: "cdx",
    0x0C0: "a", 0x0C8: "ah", 0x040: "sf", 0x048: "sfh", 0x340: "addx", 0x0C2: "cg", 0x342: "cgx",
    0x341: "sfx", 0x042: "bg", 0x343: "bgx",
    0x3C4: "mpy", 0x3CC: "mpyu", 0x3C5: "mpyh", 0x3C7: "mpys", 0x3C6: "mpyhh", 0x346: "mpyhha",
    0x3CE: "mpyhhu", 0x34E: "mpyhhau",
    0x2A5: "clz", 0x2B4: "cntb", 0x1B6: "fsmb", 0x1B5: "fsmh", 0x1B4: "fsm", 0x1B2: "gbb",
    0x1B1: "gbh", 0x1B0: "gb", 0x0D3: "avgb", 0x053: "absdb", 0x253: "sumb",
    0x2B6: "xsbh", 0x2AE: "xshw", 0x2A6: "xswd",
    0x0C1: "and", 0x2C1: "andc", 0x041: "or", 0x2C9: "orc", 0x1F0: "orx", 0x241: "xor",
    0x0C9: "nand", 0x049: "nor", 0x249: "eqv",
    0x05F: "shlh", 0x05B: "shl", 0x1DB: "shlqbi", 0x1DF: "shlqby", 0x1CF: "shlqbybi",
    0x05C: "roth", 0x058: "rot", 0x1DC: "rotqby", 0x1CC: "rotqbybi", 0x1D8: "rotqbi",
    0x05D: "rothm", 0x059: "rotm", 0x1DD: "rotqmby", 0x1CD: "rotqmbybi", 0x1D9: "rotqmbi",
    0x05E: "rotmah", 0x05A: "rotma",
    0x3D8: "heq", 0x258: "hgt", 0x2D8: "hlgt",
    0x3D0: "ceqb", 0x3C8: "ceqh", 0x3C0: "ceq", 0x250: "cgtb", 0x248: "cgth", 0x240: "cgt",
    0x2D0: "clgtb", 0x2C8: "clgth", 0x2C0: "clgt",
    0x1A8: "bi", 0x1AA: "iret", 0x1AB: "bisled", 0x1A9: "bisl", 0x128: "biz", 0x129: "binz",
    0x12A: "bihz", 0x12B: "bihnz", 0x1AC: "hbr",
    0x2C4: "fa", 0x2CC: "dfa", 0x2C5: "fs", 0x2CD: "dfs", 0x2C6: "fm", 0x2CE: "dfm",
    0x35C: "dfma", 0x35E: "dfnms", 0x35D: "dfms", 0x35F: "dfnma",
    0x1B8: "frest", 0x1B9: "frsqest", 0x3D4: "fi", 0x3B9: "frds", 0x3B8: "fesd",
    0x3C2: "fceq", 0x3CA: "fcmeq", 0x2C2: "fcgt", 0x2CA: "fcmgt",
    0x3C3: "dfceq", 0x3CB: "dfcmeq", 0x2C3: "dfcgt", 0x2CB: "dfcmgt",
    0x398: "fscrrd", 0x3BA: "fscrwr",
}
_RI7 = {
    0x1F4: "cbd", 0x1F5: "chd", 0x1F6: "cwd", 0x1F7: "cdd",
    0x07F: "shlhi", 0x07B: "shli", 0x1FB: "shlqbii", 0x1FF: "shlqbyi",
    0x07C: "rothi", 0x078: "roti", 0x1FC: "rotqbyi", 0x1F8: "rotqbii",
    0x07D: "rothmi", 0x079: "rotmi", 0x1FD: "rotqmbyi", 0x1F9: "rotqmbii",
    0x07E: "rotmahi", 0x07A: "rotmai", 0x3BF: "dftsv",
}


def decode(w):
    """The instruction in word w; op is "illegal" when no opcode matches."""
    rt, ra, rb = w & 0x7F, (w >> 7) & 0x7F, (w >> 14) & 0x7F
    op = _RRR.get(w >> 28)
    if op:
        return Ins(op, "RRR", w, rt=(w >> 21) & 0x7F, ra=ra, rb=rb, rc=rt)
    op = _RI18.get(w >> 25)
    if op:
        if op == "ila":
            return Ins(op, "RI18", w, rt=rt, i18=(w >> 7) & 0x3FFFF)
        # hbra/hbrr: a 9-bit branch-instruction offset split around the I16 target
        roh = (w >> 23) & 3
        return Ins(op, "HBR", w, ro=_sext((roh << 7) | rt, 9), i16=_sext((w >> 7) & 0xFFFF, 16))
    op = _RI10.get(w >> 24)
    if op:
        return Ins(op, "RI10", w, rt=rt, ra=ra, i10=_sext((w >> 14) & 0x3FF, 10))
    op = _RI16.get(w >> 23)
    if op:
        return Ins(op, "RI16", w, rt=rt, i16=(w >> 7) & 0xFFFF)
    op = _RI8.get(w >> 22)
    if op:
        return Ins(op, "RI8", w, rt=rt, ra=ra, i8=(w >> 14) & 0xFF)
    o11 = w >> 21
    op = _RI7.get(o11)
    if op:
        return Ins(op, "RI7", w, rt=rt, ra=ra, i7=_sext(rb, 7))
    op = _RR.get(o11)
    if op:
        if op == "hbr":
            return Ins(op, "HBR", w, ro=_sext(((w >> 18) & 3) << 7 | rt, 9), ra=ra, p=(w >> 20) & 1)
        if op in ("bi", "bisl", "bisled", "iret", "biz", "binz", "bihz", "bihnz"):
            return Ins(op, "RR", w, rt=rt, ra=ra, rb=rb, d=(w >> 19) & 1, e=(w >> 18) & 1)
        if op in ("stop", "stopd"):
            return Ins(op, "RR", w, code=w & 0x3FFF)
        return Ins(op, "RR", w, rt=rt, ra=ra, rb=rb)
    return Ins("illegal", "?", w)


# Instructions whose I16 is a branch or load target (word offset; relative or absolute)
_REL16 = {"br", "brsl", "brnz", "brz", "brhnz", "brhz", "lqr", "stqr"}
_ABS16 = {"bra", "brasl", "lqa", "stqa"}


def target(ins, pc):
    """A branch's or a direct load's local-store target, or None."""
    if ins.op in _REL16:
        return (pc + (_sext(ins.f["i16"], 16) << 2)) & 0x3FFFF
    if ins.op in _ABS16:
        return (_sext(ins.f["i16"], 16) << 2) & 0x3FFFF
    return None


def text(ins, pc=0):
    f, op = ins.f, ins.op
    t = target(ins, pc)
    if op in ("br", "bra"):
        return f"{op} 0x{t:05X}"
    if t is not None:
        return f"{op} ${f['rt']}, 0x{t:05X}"
    if ins.form == "HBR":
        if op == "hbr":
            return f"hbr 0x{(pc + (f['ro'] << 2)) & 0x3FFFF:05X}, ${f['ra']}"
        dest = (pc + (f["i16"] << 2)) & 0x3FFFF if op == "hbrr" else (f["i16"] << 2) & 0x3FFFF
        return f"{op} 0x{(pc + (f['ro'] << 2)) & 0x3FFFF:05X}, 0x{dest:05X}"
    if ins.form == "RRR":
        return f"{op} ${f['rt']}, ${f['ra']}, ${f['rb']}, ${f['rc']}"
    if ins.form == "RI18":
        return f"ila ${f['rt']}, 0x{f['i18']:X}"
    if ins.form == "RI16":
        return f"{op} ${f['rt']}, 0x{f['i16']:X}"
    if ins.form == "RI10":
        if op in ("lqd", "stqd"):
            return f"{op} ${f['rt']}, {f['i10'] << 4}(${f['ra']})"
        return f"{op} ${f['rt']}, ${f['ra']}, {f['i10']}"
    if ins.form == "RI8":
        return f"{op} ${f['rt']}, ${f['ra']}, {f['i8']}"
    if ins.form == "RI7":
        if op in ("cbd", "chd", "cwd", "cdd"):
            return f"{op} ${f['rt']}, {f['i7']}(${f['ra']})"
        return f"{op} ${f['rt']}, ${f['ra']}, {f['i7']}"
    if op in ("stop", "stopd"):
        return f"{op} 0x{f['code']:X}"
    if op in ("lnop", "nop", "sync", "dsync", "illegal"):
        return op if op != "illegal" else f"illegal {ins.word:08X}"
    if op in ("rdch", "rchcnt"):
        return f"{op} ${f['rt']}, ch{f['ra']}"
    if op == "wrch":
        return f"wrch ch{f['ra']}, ${f['rt']}"
    if op in ("bi", "iret", "biz", "binz", "bihz", "bihnz", "bisl", "bisled"):
        if op in ("bi", "iret"):
            return f"{op} ${f['ra']}"
        return f"{op} ${f['rt']}, ${f['ra']}"
    return f"{op} ${f['rt']}, ${f['ra']}, ${f['rb']}"


def mix(words):
    return collections.Counter(decode(w).op for w in words)


def main():
    from .elf import Image
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("elf")
    ap.add_argument("--at", type=lambda s: int(s, 16))
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--base", type=lambda s: int(s, 16), help="executable address of local-store 0")
    ap.add_argument("--mix", action="append", default=[], help="START:SIZE in hex, executable addresses")
    a = ap.parse_args()
    img = Image(a.elf)
    if a.at is not None:
        base = a.base if a.base is not None else a.at
        for k in range(a.count):
            addr = a.at + 4 * k
            w = img.u32(addr)
            pc = addr - base
            print(f"{addr:08X} {pc:05X}  {w:08X}  {text(decode(w), pc)}")
    if a.mix:
        n = collections.Counter()
        for r in a.mix:
            start, size = (int(x, 16) for x in r.split(":"))
            blob = img.read(start, size)
            n += mix(int.from_bytes(blob[i:i + 4], "big") for i in range(0, size - 3, 4))
        total = sum(n.values())
        print(f"{total} words, {len(n)} operations")
        for op, k in n.most_common():
            print(f"  {op:10s} {k:7d}")


if __name__ == "__main__":
    main()
