"""Cell PPU (PowerPC 64, VMX) decoding, disassembly and an instruction census.

    python -m ps3kit.ppu GAME.elf --at 0x10200 [--count 20]
    python -m ps3kit.ppu GAME.elf --mix

decode(word) returns an Ins with the *canonical* operation name ("addi",
"rldicl", "bc", "lvx", ...) and its raw fields; that is what the recompiler
consumes. text(ins, addr) renders it for reading, with the few simplified
mnemonics that make PPU code legible (li, lis, mr, nop, blr, bctr, mflr,
clrldi).

Covered: the user-mode PowerPC 64 set the PS3's PPU runs (64-bit integer,
the doubleword rotates, DS-form loads and stores, the 128-byte dcbz), the
FPU, and the VMX (AltiVec) instructions by name. Supervisor instructions are
decoded only as far as a game binary ever contains them (never, so far).
No dependencies.
"""
import argparse
import collections
import struct


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


class Ins:
    __slots__ = ("op", "f", "word")

    def __init__(self, op, word, **f):
        self.op, self.word, self.f = op, word, f

    def __repr__(self):
        return f"Ins({self.op} {self.f})"


# --- opcode tables --------------------------------------------------------------

_D_FORM = {7: "mulli", 8: "subfic", 12: "addic", 13: "addic.", 14: "addi", 15: "addis"}
_LOGIC_IMM = {24: "ori", 25: "oris", 26: "xori", 27: "xoris", 28: "andi.", 29: "andis."}
_LOADSTORE = {32: "lwz", 33: "lwzu", 34: "lbz", 35: "lbzu", 36: "stw", 37: "stwu",
              38: "stb", 39: "stbu", 40: "lhz", 41: "lhzu", 42: "lha", 43: "lhau",
              44: "sth", 45: "sthu", 46: "lmw", 47: "stmw", 48: "lfs", 49: "lfsu",
              50: "lfd", 51: "lfdu", 52: "stfs", 53: "stfsu", 54: "stfd", 55: "stfdu"}

# opcode 31, XO-form arithmetic: a 9-bit XO and the OE bit above it
_X31_XO = {8: "subfc", 9: "mulhdu", 10: "addc", 11: "mulhwu", 40: "subf", 73: "mulhd",
           75: "mulhw", 104: "neg", 136: "subfe", 138: "adde", 200: "subfze", 202: "addze",
           232: "subfme", 233: "mulld", 234: "addme", 235: "mullw", 266: "add",
           457: "divdu", 459: "divwu", 489: "divd", 491: "divw"}

# opcode 31, X-form: a 10-bit XO
_X31 = {
    0: "cmp", 4: "tw", 19: "mfcr", 20: "lwarx", 21: "ldx", 23: "lwzx", 24: "slw",
    26: "cntlzw", 27: "sld", 28: "and", 32: "cmpl", 53: "ldux", 54: "dcbst", 55: "lwzux",
    58: "cntlzd", 60: "andc", 68: "td", 83: "mfmsr", 84: "ldarx", 86: "dcbf", 87: "lbzx",
    119: "lbzux", 124: "nor", 144: "mtcrf", 149: "stdx", 150: "stwcx.", 151: "stwx",
    181: "stdux", 183: "stwux", 214: "stdcx.", 215: "stbx", 246: "dcbtst", 247: "stbux",
    278: "dcbt", 279: "lhzx", 284: "eqv", 311: "lhzux", 316: "xor", 339: "mfspr",
    341: "lwax", 343: "lhax", 371: "mftb", 373: "lwaux", 375: "lhaux", 407: "sthx",
    412: "orc", 439: "sthux", 444: "or", 467: "mtspr", 476: "nand", 512: "mcrxr",
    532: "ldbrx", 533: "lswx", 534: "lwbrx", 535: "lfsx", 536: "srw", 539: "srd",
    567: "lfsux", 597: "lswi", 598: "sync", 599: "lfdx", 631: "lfdux", 660: "stdbrx",
    661: "stswx", 662: "stwbrx", 663: "stfsx", 695: "stfsux", 725: "stswi", 727: "stfdx",
    759: "stfdux", 790: "lhbrx", 792: "sraw", 794: "srad", 824: "srawi", 854: "eieio",
    918: "sthbrx", 922: "extsh", 954: "extsb", 982: "icbi", 983: "stfiwx", 986: "extsw",
    1014: "dcbz",
    # VMX loads and stores live in opcode 31
    6: "lvsl", 7: "lvebx", 38: "lvsr", 39: "lvehx", 71: "lvewx", 103: "lvx", 135: "stvebx",
    167: "stvehx", 199: "stvewx", 231: "stvx", 359: "lvxl", 487: "stvxl", 519: "lvlx",
    551: "lvrx", 647: "stvlx", 679: "stvrx", 775: "lvlxl", 807: "lvrxl", 903: "stvlxl",
    935: "stvrxl",
}

_X19 = {0: "mcrf", 16: "bclr", 33: "crnor", 129: "crandc", 150: "isync", 193: "crxor",
        225: "crnand", 257: "crand", 289: "creqv", 417: "crorc", 449: "cror", 528: "bcctr"}

_A59 = {18: "fdivs", 20: "fsubs", 21: "fadds", 22: "fsqrts", 24: "fres", 25: "fmuls",
        28: "fmsubs", 29: "fmadds", 30: "fnmsubs", 31: "fnmadds"}
_A63 = {18: "fdiv", 20: "fsub", 21: "fadd", 22: "fsqrt", 23: "fsel", 25: "fmul",
        26: "frsqrte", 28: "fmsub", 29: "fmadd", 30: "fnmsub", 31: "fnmadd"}
_X63 = {0: "fcmpu", 12: "frsp", 14: "fctiw", 15: "fctiwz", 32: "fcmpo", 38: "mtfsb1",
        40: "fneg", 64: "mcrfs", 70: "mtfsb0", 72: "fmr", 134: "mtfsfi", 136: "fnabs",
        264: "fabs", 583: "mffs", 711: "mtfsf", 814: "fctid", 815: "fctidz", 846: "fcfid"}

# opcode 4, VMX. VA-form: a 6-bit XO and a fourth register
_VA = {32: "vmhaddshs", 33: "vmhraddshs", 34: "vmladduhm", 36: "vmsumubm", 37: "vmsummbm",
       38: "vmsumuhm", 39: "vmsumuhs", 40: "vmsumshm", 41: "vmsumshs", 42: "vsel",
       43: "vperm", 44: "vsldoi", 46: "vmaddfp", 47: "vnmsubfp"}
# VC-form compares: a 10-bit XO and Rc at bit 10
_VC = {6: "vcmpequb", 70: "vcmpequh", 134: "vcmpequw", 198: "vcmpeqfp", 454: "vcmpgefp",
       518: "vcmpgtub", 582: "vcmpgtuh", 646: "vcmpgtuw", 710: "vcmpgtfp", 774: "vcmpgtsb",
       838: "vcmpgtsh", 902: "vcmpgtsw", 966: "vcmpbfp"}
# VX-form: an 11-bit XO
_VX = {
    0: "vaddubm", 2: "vmaxub", 4: "vrlb", 8: "vmuloub", 10: "vaddfp", 12: "vmrghb",
    14: "vpkuhum", 64: "vadduhm", 66: "vmaxuh", 68: "vrlh", 72: "vmulouh", 74: "vsubfp",
    76: "vmrghh", 78: "vpkuwum", 128: "vadduwm", 130: "vmaxuw", 132: "vrlw", 140: "vmrghw",
    142: "vpkuhus", 206: "vpkuwus", 258: "vmaxsb", 260: "vslb", 264: "vmulosb",
    266: "vrefp", 268: "vmrglb", 270: "vpkshus", 322: "vmaxsh", 324: "vslh", 328: "vmulosh",
    330: "vrsqrtefp", 332: "vmrglh", 334: "vpkswus", 384: "vaddcuw", 386: "vmaxsw",
    388: "vslw", 394: "vexptefp", 396: "vmrglw", 398: "vpkshss", 452: "vsl", 458: "vlogefp",
    462: "vpkswss", 512: "vaddubs", 514: "vminub", 516: "vsrb", 520: "vmuleub",
    522: "vrfin", 524: "vspltb", 526: "vupkhsb", 576: "vadduhs", 578: "vminuh", 580: "vsrh",
    584: "vmuleuh", 586: "vrfiz", 588: "vsplth", 590: "vupkhsh", 640: "vadduws",
    642: "vminuw", 644: "vsrw", 650: "vrfip", 652: "vspltw", 654: "vupklsb", 708: "vsr",
    714: "vrfim", 718: "vupklsh", 768: "vaddsbs", 770: "vminsb", 772: "vsrab",
    776: "vmulesb", 778: "vcfux", 780: "vspltisb", 782: "vpkpx", 832: "vaddshs",
    834: "vminsh", 836: "vsrah", 840: "vmulesh", 842: "vcfsx", 844: "vspltish",
    846: "vupkhpx", 896: "vaddsws", 898: "vminsw", 900: "vsraw", 906: "vctuxs",
    908: "vspltisw", 970: "vctsxs", 974: "vupklpx", 1024: "vsububm", 1026: "vavgub",
    1028: "vand", 1034: "vmaxfp", 1036: "vslo", 1088: "vsubuhm", 1090: "vavguh",
    1092: "vandc", 1098: "vminfp", 1100: "vsro", 1152: "vsubuwm", 1154: "vavguw",
    1156: "vor", 1220: "vxor", 1282: "vavgsb", 1284: "vnor", 1346: "vavgsh", 1408: "vsubcuw",
    1410: "vavgsw", 1536: "vsububs", 1540: "mfvscr", 1544: "vsum4ubs", 1600: "vsubuhs",
    1604: "mtvscr", 1608: "vsum4shs", 1664: "vsubuws", 1672: "vsum2sws", 1792: "vsubsbs",
    1800: "vsum4sbs", 1856: "vsubshs", 1920: "vsubsws", 1928: "vsumsws",
}

SPR_NAMES = {1: "xer", 8: "lr", 9: "ctr", 256: "vrsave", 268: "tbl", 269: "tbu"}


def decode(w):
    """The instruction in one big-endian word: Ins(op, word, **fields)."""
    op = w >> 26
    D, A, B, C = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, (w >> 6) & 31
    rc = w & 1

    if op == 18:
        li = w & 0x03FFFFFC
        if li & 0x02000000:
            li -= 0x04000000
        return Ins("b", w, LI=li, AA=(w >> 1) & 1, LK=w & 1)
    if op == 16:
        return Ins("bc", w, BO=D, BI=A, BD=_s16(w & 0xFFFC), AA=(w >> 1) & 1, LK=w & 1)
    if op == 19:
        xo = (w >> 1) & 0x3FF
        name = _X19.get(xo)
        if name in ("bclr", "bcctr"):
            return Ins(name, w, BO=D, BI=A, BH=(w >> 11) & 3, LK=w & 1)
        if name == "mcrf":
            return Ins(name, w, crfD=D >> 2, crfS=A >> 2)
        if name == "isync":
            return Ins(name, w)
        if name:
            return Ins(name, w, crbD=D, crbA=A, crbB=B)
        return Ins("illegal", w)
    if op == 17:
        return Ins("sc", w, LEV=(w >> 5) & 0x7F)

    if op in _D_FORM:
        return Ins(_D_FORM[op], w, D=D, A=A, simm=_s16(w & 0xFFFF))
    if op in _LOGIC_IMM:
        return Ins(_LOGIC_IMM[op], w, S=D, A=A, uimm=w & 0xFFFF)
    if op == 10:
        return Ins("cmpli", w, crfD=D >> 2, L=D & 1, A=A, imm=w & 0xFFFF)
    if op == 11:
        return Ins("cmpi", w, crfD=D >> 2, L=D & 1, A=A, imm=_s16(w & 0xFFFF))
    if op == 3:
        return Ins("twi", w, TO=D, A=A, simm=_s16(w & 0xFFFF))
    if op == 2:
        return Ins("tdi", w, TO=D, A=A, simm=_s16(w & 0xFFFF))
    if op in (20, 21, 23):
        name = {20: "rlwimi", 21: "rlwinm", 23: "rlwnm"}[op]
        return Ins(name, w, S=D, A=A, SH=B, MB=(w >> 6) & 31, ME=(w >> 1) & 31, Rc=rc)
    if op == 30:
        sh = B | ((w >> 1) & 1) << 5
        mb = ((w >> 6) & 31) | ((w >> 5) & 1) << 5         # mb5 || mb0:4
        xo = (w >> 2) & 7
        if xo < 4:
            name = ("rldicl", "rldicr", "rldic", "rldimi")[xo]
            return Ins(name, w, S=D, A=A, SH=sh, MB=mb, Rc=rc)
        xo4 = (w >> 1) & 15
        if xo4 in (8, 9):
            return Ins("rldcl" if xo4 == 8 else "rldcr", w, S=D, A=A, B=B, MB=mb, Rc=rc)
        return Ins("illegal", w)
    if op in _LOADSTORE:
        return Ins(_LOADSTORE[op], w, D=D, A=A, d=_s16(w & 0xFFFF))
    if op == 58:
        name = {0: "ld", 1: "ldu", 2: "lwa"}.get(w & 3, "illegal")
        return Ins(name, w, D=D, A=A, d=_s16(w & 0xFFFC))
    if op == 62:
        name = {0: "std", 1: "stdu"}.get(w & 3, "illegal")
        return Ins(name, w, D=D, A=A, d=_s16(w & 0xFFFC))

    if op == 31:
        xo9 = (w >> 1) & 0x1FF
        if xo9 in _X31_XO and (w >> 1) & 0x3FF in (xo9, xo9 | 0x200):
            return Ins(_X31_XO[xo9], w, D=D, A=A, B=B, OE=(w >> 10) & 1, Rc=rc)
        xo = (w >> 1) & 0x3FF
        if (w >> 2) & 0x1FF == 413:                           # sradi: sh5 in bit 1
            return Ins("sradi", w, S=D, A=A, SH=B | (w >> 1 & 1) << 5, Rc=rc)
        name = _X31.get(xo)
        if name is None:
            return Ins("illegal", w)
        if name in ("cmp", "cmpl"):
            return Ins(name, w, crfD=D >> 2, L=D & 1, A=A, B=B)
        if name in ("tw", "td"):
            return Ins(name, w, TO=D, A=A, B=B)
        if name in ("mfspr", "mtspr", "mftb"):
            spr = ((w >> 16) & 31) | ((w >> 11) & 31) << 5
            return Ins(name, w, D=D, spr=spr)
        if name == "mfcr":
            return Ins(name, w, D=D, one=(w >> 20) & 1, CRM=(w >> 12) & 0xFF)
        if name == "mtcrf":
            return Ins(name, w, S=D, one=(w >> 20) & 1, CRM=(w >> 12) & 0xFF)
        if name == "srawi":
            return Ins(name, w, S=D, A=A, SH=B, Rc=rc)
        if name in ("lswi", "stswi"):
            return Ins(name, w, D=D, A=A, NB=B)
        if name in ("and", "andc", "or", "orc", "xor", "nor", "nand", "eqv", "slw", "srw",
                    "sraw", "sld", "srd", "srad", "cntlzw", "cntlzd", "extsb", "extsh",
                    "extsw"):
            return Ins(name, w, S=D, A=A, B=B, Rc=rc)
        if name == "mcrxr":
            return Ins(name, w, crfD=D >> 2)
        return Ins(name, w, D=D, A=A, B=B, Rc=rc)

    if op == 59:
        name = _A59.get((w >> 1) & 31)
        if name:
            return Ins(name, w, D=D, A=A, B=B, C=C, Rc=rc)
        return Ins("illegal", w)
    if op == 63:
        xo5 = (w >> 1) & 31
        if xo5 in _A63:
            return Ins(_A63[xo5], w, D=D, A=A, B=B, C=C, Rc=rc)
        name = _X63.get((w >> 1) & 0x3FF)
        if name is None:
            return Ins("illegal", w)
        if name in ("fcmpu", "fcmpo"):
            return Ins(name, w, crfD=D >> 2, A=A, B=B)
        if name == "mcrfs":
            return Ins(name, w, crfD=D >> 2, crfS=A >> 2)
        if name == "mtfsf":
            return Ins(name, w, FM=(w >> 17) & 0xFF, B=B, Rc=rc)
        if name == "mtfsfi":
            return Ins(name, w, crfD=D >> 2, IMM=(w >> 12) & 15, Rc=rc)
        if name in ("mtfsb0", "mtfsb1"):
            return Ins(name, w, crbD=D, Rc=rc)
        return Ins(name, w, D=D, A=A, B=B, Rc=rc)

    if op == 4:
        va = w & 63
        if va in _VA:
            return Ins(_VA[va], w, D=D, A=A, B=B, C=C, SHB=C & 15)
        vc = w & 0x3FF
        if vc in _VC:
            return Ins(_VC[vc], w, D=D, A=A, B=B, Rc=(w >> 10) & 1)
        name = _VX.get(w & 0x7FF)
        if name:
            return Ins(name, w, D=D, A=A, B=B, UIMM=A, SIMM=A - 32 if A & 16 else A)
        return Ins("illegal", w)

    return Ins("illegal", w)


def branch_target(ins, addr):
    """The static target of a b or bc, or None."""
    if ins.op == "b":
        return ins.f["LI"] if ins.f["AA"] else (addr + ins.f["LI"]) & 0xFFFFFFFF
    if ins.op == "bc":
        return ins.f["BD"] if ins.f["AA"] else (addr + ins.f["BD"]) & 0xFFFFFFFF
    return None


# --- reading ----------------------------------------------------------------------

def _imm(v):
    return f"0x{v:X}" if v >= 0 else f"-0x{-v:X}"


_COND = {(12, 0): "blt", (12, 1): "bgt", (12, 2): "beq", (12, 3): "bso",
         (4, 0): "bge", (4, 1): "ble", (4, 2): "bne", (4, 3): "bns"}


def text(ins, addr=0):
    """The instruction as a line of assembly, simplified where that helps."""
    op, f = ins.op, ins.f
    if op == "ori" and f["S"] == f["A"] == 0 and f["uimm"] == 0:
        return "nop"
    if op == "addi" and f["A"] == 0:
        return f"li r{f['D']}, {_imm(f['simm'])}"
    if op == "addis" and f["A"] == 0:
        return f"lis r{f['D']}, {_imm(f['simm'])}"
    if op == "or" and f["S"] == f["B"] and not f["Rc"]:
        return f"mr r{f['A']}, r{f['S']}"
    if op == "rldicl" and f["SH"] == 0:
        return f"clrldi r{f['A']}, r{f['S']}, {f['MB']}"
    if op in ("mfspr", "mtspr") and f["spr"] in SPR_NAMES:
        return f"{op[:2]}{SPR_NAMES[f['spr']]} r{f['D']}"
    if op == "bclr" and f["BO"] == 20:
        return "blrl" if f["LK"] else "blr"
    if op == "bcctr" and f["BO"] == 20:
        return "bctrl" if f["LK"] else "bctr"
    if op in ("b", "bc"):
        t = branch_target(ins, addr)
        name = op + ("l" if f["LK"] else "")
        if op == "bc":
            key = (f["BO"] & 0x1C, f["BI"] & 3)
            if key in _COND:
                name = _COND[key] + ("l" if f["LK"] else "")
                return f"{name} cr{f['BI'] >> 2}, 0x{t:08X}"
            return f"{name} {f['BO']}, {f['BI']}, 0x{t:08X}"
        return f"{name} 0x{t:08X}"
    if "d" in f and "A" in f:
        return f"{op} r{f['D']}, {_imm(f['d'])}(r{f['A']})"
    parts = []
    for k, v in f.items():
        if k in ("Rc", "OE", "LK", "AA") and not v:
            continue
        parts.append(f"{k}={v}")
    return f"{op} " + ", ".join(parts)


# --- the census ------------------------------------------------------------------------

def mix(img, ranges):
    """Instruction counts by canonical name over [(start, end)) code ranges."""
    n = collections.Counter()
    for start, end in ranges:
        for a in range(start, end, 4):
            n[decode(img.u32(a)).op] += 1
    return n


def main():
    from .elf import Image
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("elf")
    ap.add_argument("--at", type=lambda s: int(s, 16))
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--mix", action="store_true")
    a = ap.parse_args()
    img = Image(a.elf)
    if a.at is not None:
        for k in range(a.count):
            addr = a.at + 4 * k
            w = img.u32(addr)
            print(f"{addr:08X}  {w:08X}  {text(decode(w), addr)}")
    if a.mix:
        from .recomp.program import code_ranges
        n = mix(img, code_ranges(img))
        total = sum(n.values())
        print(f"{total} instructions, {len(n)} operations")
        for op, k in n.most_common():
            print(f"  {op:12s} {k:9d}")


if __name__ == "__main__":
    main()
