"""Cell PPU instruction -> C++ statement(s), against ps3kit/runtime/ppu.h.

emit(ins, addr, fn) returns a list of C++ lines for one instruction; `fn`
answers the control-flow questions (is this target a label here, what is
the C++ name of the function at an address, the switch table of a bctr).
Every statement is wrapped in its own block so that `goto` never crosses an
initialisation.

The PPU runs 64-bit code (MSR[SF] = 1): GPRs, LR and CTR are 64 bits, the
record forms compare all 64, carries come out of bit 63, and the word
rotates work on the low word copied into both halves. Effective addresses
are truncated to 32 bits, because a game's address space is 32 bits wide.

Tail jumps (a `b` to another function, falling into the next unit) are
`[[clang::musttail]]` calls: a loop that crosses a function boundary must
not grow the host stack.
"""


class Unsupported(Exception):
    pass


def fname(addr):
    return f"f_{addr:08X}"


M64 = (1 << 64) - 1


def _h(v):
    return f"0x{v & M64:X}ull"


def _h32(v):
    return f"0x{v & 0xFFFFFFFF:X}u"


def _mask64(mb, me):
    """MASK(mb, me) in IBM bit order over 64 bits, wrapping when mb > me."""
    m = 0
    i = mb
    while True:
        m |= 1 << (63 - i)
        if i == me:
            break
        i = (i + 1) & 63
    return m


def _r(n):
    return f"c.r[{n}]"


def _ra0(n):                              # rA|0
    return f"c.r[{n}]" if n else "0ull"


def _ea_d(f):
    d = f["d"]
    if f["A"] == 0:
        return _h32(d)
    return f"(uint32_t){_r(f['A'])}" if d == 0 else f"(uint32_t)({_r(f['A'])} + {_h(d)})"


def _ea_x(f):
    return f"(uint32_t){_r(f['B'])}" if f["A"] == 0 else f"(uint32_t)({_r(f['A'])} + {_r(f['B'])})"


def _rc(rc, dst):
    return f" cr0_rc(c, {dst});" if rc else ""


_LOAD = {"lwz": "ld32({ea})", "lbz": "ld8({ea})", "lhz": "ld16({ea})", "ld": "ld64({ea})",
         "lha": "(uint64_t)(int64_t)(int16_t)ld16({ea})",
         "lwa": "(uint64_t)(int64_t)(int32_t)ld32({ea})"}
_STORE = {"stw": "st32({ea}, (uint32_t){v})", "stb": "st8({ea}, (uint8_t){v})",
          "sth": "st16({ea}, (uint16_t){v})", "std": "st64({ea}, {v})"}
_LOADX = {"lwzx": "ld32(ea)", "lbzx": "ld8(ea)", "lhzx": "ld16(ea)", "ldx": "ld64(ea)",
          "lhax": "(uint64_t)(int64_t)(int16_t)ld16(ea)",
          "lwax": "(uint64_t)(int64_t)(int32_t)ld32(ea)",
          "lwbrx": "PPU_BSWAP32(ld32(ea))", "lhbrx": "(uint64_t)PPU_BSWAP16(ld16(ea))",
          "ldbrx": "PPU_BSWAP64(ld64(ea))"}
_STOREX = {"stwx": "st32(ea, (uint32_t){v})", "stbx": "st8(ea, (uint8_t){v})",
           "sthx": "st16(ea, (uint16_t){v})", "stdx": "st64(ea, {v})",
           "stwbrx": "st32(ea, PPU_BSWAP32((uint32_t){v}))",
           "sthbrx": "st16(ea, PPU_BSWAP16((uint16_t){v}))",
           "stdbrx": "st64(ea, PPU_BSWAP64({v}))"}
_LOGIC = {"and": "{s} & {b}", "andc": "{s} & ~{b}", "or": "{s} | {b}", "orc": "{s} | ~{b}",
          "xor": "{s} ^ {b}", "nor": "~({s} | {b})", "nand": "~({s} & {b})", "eqv": "~({s} ^ {b})",
          "slw": "slw({s}, {b})", "srw": "srw({s}, {b})", "sraw": "sraw(c, {s}, {b})",
          "sld": "sld({s}, {b})", "srd": "srd({s}, {b})", "srad": "srad(c, {s}, {b})"}
# carrying adds: (x, y, carry-in) of x + y + cin, all 64 bits
_ADDS = {"addc": ("a", "b", "0"), "adde": ("a", "b", "c.xer_ca"), "addze": ("a", "0ull", "c.xer_ca"),
         "addme": ("a", "~0ull", "c.xer_ca"), "subfc": ("~a", "b", "1"),
         "subfe": ("~a", "b", "c.xer_ca"), "subfze": ("~a", "0ull", "c.xer_ca"),
         "subfme": ("~a", "~0ull", "c.xer_ca")}
_CROPS = {"crand": "a & b", "crandc": "a & !b", "cror": "a | b", "crorc": "a | !b",
          "crxor": "a ^ b", "crnor": "!(a | b)", "crnand": "!(a & b)", "creqv": "!(a ^ b)"}
# the PPC fused multiply-adds round once: std::fma
_FP2 = {"fadd": "a + b", "fsub": "a - b", "fdiv": "a / b", "fmul": "a * cc",
        "fmadd": "std::fma(a, cc, b)", "fmsub": "std::fma(a, cc, -b)",
        "fnmadd": "-std::fma(a, cc, b)", "fnmsub": "-std::fma(a, cc, -b)",
        "fsel": "a >= 0.0 ? cc : b", "fsqrt": "std::sqrt(b)", "frsqrte": "frsqrte(b)"}
_FPS = {"fadds": "a + b", "fsubs": "a - b", "fdivs": "a / b", "fmuls": "a * cc",
        "fmadds": "std::fma(a, cc, b)", "fmsubs": "std::fma(a, cc, -b)",
        "fnmadds": "-std::fma(a, cc, b)", "fnmsubs": "-std::fma(a, cc, -b)",
        "fsqrts": "std::sqrt(b)", "fres": "fres(b)", "frsp": "b"}
_FPMOVE = {"fmr": "b", "fneg": "-b", "fabs": "std::fabs(b)", "fnabs": "-std::fabs(b)"}
_NOP = {"sync", "isync", "eieio", "dcbst", "dcbf", "dcbt", "dcbtst", "icbi"}

# VMX: the runtime has a helper per operation (runtime/vmx.h), named after it
_VMX3 = {"vaddfp", "vsubfp", "vmaxfp", "vminfp", "vand", "vandc", "vor", "vxor", "vnor",
         "vadduwm", "vsubuwm", "vaddubm", "vadduhm", "vsububm", "vsubuhm",
         "vslw", "vsrw", "vsraw", "vslh", "vsrh", "vsrah", "vslb", "vsrb", "vsrab",
         "vmrghw", "vmrglw", "vmrghh", "vmrglh", "vmrghb", "vmrglb",
         "vmaxsw", "vminsw", "vmaxuw", "vminuw", "vmaxsh", "vminsh",
         "vpkuwum", "vpkuhum", "vavgub", "vrlw", "vslo", "vsro", "vsl", "vsr"}
_VMX2 = {"vrefp", "vrsqrtefp", "vrfiz", "vrfin", "vrfip", "vrfim", "vexptefp", "vlogefp",
         "vupkhsh", "vupklsh", "vupkhsb", "vupklsb"}
_VMXCMP = {"vcmpequw", "vcmpequh", "vcmpequb", "vcmpeqfp", "vcmpgefp", "vcmpgtfp",
           "vcmpgtuw", "vcmpgtsw", "vcmpgtuh", "vcmpgtsh", "vcmpgtub", "vcmpgtsb", "vcmpbfp"}


def _bc_cond(bo, bi):
    """(pre-statement, condition) for a BO/BI pair."""
    pre, parts = "", []
    if not bo & 4:
        pre = "c.ctr--; "
        parts.append("c.ctr == 0" if bo & 2 else "c.ctr != 0")
    if not bo & 16:
        parts.append(f"c.cr[{bi}]" if bo & 8 else f"!c.cr[{bi}]")
    return pre, " && ".join(parts)


def emit(ins, addr, fn):
    """C++ lines for one instruction. `fn` provides goto/call/table resolution."""
    op, f = ins.op, ins.f
    nxt = addr + 4
    rc = f.get("Rc")

    # ---- branches -------------------------------------------------------------------
    if op == "b":
        t = f["LI"] & 0xFFFFFFFF if f["AA"] else (addr + f["LI"]) & 0xFFFFFFFF
        if f["LK"]:
            return [f"c.lr = {_h(nxt)}; {fn.call(t)}"]
        return [fn.jump(t, addr)]
    if op == "bc":
        t = f["BD"] & 0xFFFFFFFF if f["AA"] else (addr + f["BD"]) & 0xFFFFFFFF
        pre, cond = _bc_cond(f["BO"], f["BI"])
        if f["LK"]:
            act = f"c.lr = {_h(nxt)};" if t == nxt else f"c.lr = {_h(nxt)}; {fn.call(t)}"
        else:
            act = fn.jump(t, addr)
        return [f"{{ {pre}if ({cond}) {{ {act} }} }}" if cond else f"{{ {pre}{act} }}"]
    if op == "bclr":
        pre, cond = _bc_cond(f["BO"], f["BI"])
        if f["LK"]:
            act = f"{{ uint32_t t = (uint32_t)c.lr; c.lr = {_h(nxt)}; ppu_call_indirect(c, t); }}"
        else:
            act = "return;"
        return [f"{{ {pre}if ({cond}) {act} }}" if cond else f"{{ {pre}{act} }}"]
    if op == "bcctr":
        pre, cond = _bc_cond(f["BO"], f["BI"])
        if f["LK"]:
            act = f"{{ c.lr = {_h(nxt)}; ppu_call_indirect(c, (uint32_t)c.ctr); }}"
        elif not cond and addr in fn.tables:
            cases = " ".join(f"case {_h32(t)}: goto L_{t:08X};" for t in sorted(set(fn.tables[addr]))
                             if fn.entry <= t < fn.end)
            outside = sorted(t for t in set(fn.tables[addr]) if not fn.entry <= t < fn.end)
            cases += "".join(f" case {_h32(t)}: {fn.tail(t)}" for t in outside)
            return [f"switch ((uint32_t)c.ctr) {{ {cases} default: PPU_TAIL(ppu_bctr); }}"]
        else:
            act = "PPU_TAIL(ppu_bctr);"
        return [f"{{ {pre}if ({cond}) {{ {act} }} }}" if cond else f"{{ {pre}{act} }}"]

    # ---- integer, immediate -----------------------------------------------------------
    if op == "addi":
        return [f"c.r[{f['D']}] = {_ra0(f['A'])} + {_h(f['simm'])};"]
    if op == "addis":
        return [f"c.r[{f['D']}] = {_ra0(f['A'])} + {_h(f['simm'] << 16)};"]
    if op in ("addic", "addic."):
        s = f"c.r[{f['D']}] = add_ca(c, c.r[{f['A']}], {_h(f['simm'])}, 0);"
        return [s + _rc(op == "addic.", f"c.r[{f['D']}]")]
    if op == "subfic":
        return [f"c.r[{f['D']}] = add_ca(c, ~c.r[{f['A']}], {_h(f['simm'])}, 1);"]
    if op == "mulli":
        return [f"c.r[{f['D']}] = c.r[{f['A']}] * {_h(f['simm'])};"]
    if op in ("ori", "oris", "xori", "xoris", "andi.", "andis."):
        imm = f["uimm"] << 16 if op.endswith(("is", "is.")) else f["uimm"]
        o = {"o": "|", "x": "^", "a": "&"}[op[0]]
        s = f"c.r[{f['A']}] = c.r[{f['S']}] {o} {_h(imm)};"
        return [s + _rc(op.endswith("."), f"c.r[{f['A']}]")]
    if op in ("cmpi", "cmpli", "cmp", "cmpl"):
        b = _h(f["imm"]) if "imm" in f else f"c.r[{f['B']}]"
        a = f"c.r[{f['A']}]"
        if op in ("cmpi", "cmp"):
            t = "int64_t" if f["L"] else "int32_t"
            return [f"cr_cmp_s(c, {f['crfD']}, ({t}){a}, ({t}){b});"]
        t = "uint64_t" if f["L"] else "uint32_t"
        return [f"cr_cmp_u(c, {f['crfD']}, ({t}){a}, ({t}){b});"]
    if op in ("twi", "tw", "tdi", "td"):
        b = _h(f["simm"]) if op in ("twi", "tdi") else f"c.r[{f['B']}]"
        if f["TO"] == 31:
            return [f"ppu_trap(c, {_h32(addr)});"]
        w = "64" if op in ("tdi", "td") else "32"
        return [f"if (trap_cond{w}({f['TO']}, c.r[{f['A']}], {b})) ppu_trap(c, {_h32(addr)});"]

    # ---- rotates ------------------------------------------------------------------------
    if op in ("rlwinm", "rlwimi", "rlwnm"):
        m = _h(_mask64(f["MB"] + 32, f["ME"] + 32))
        sh = f"(c.r[{f['SH']}] & 31)" if op == "rlwnm" else str(f["SH"])
        rot = f"rotl64(dup32(c.r[{f['S']}]), {sh})"
        if op == "rlwimi":
            s = f"c.r[{f['A']}] = ({rot} & {m}) | (c.r[{f['A']}] & ~{m});"
        else:
            s = f"c.r[{f['A']}] = {rot} & {m};"
        return [s + _rc(rc, f"c.r[{f['A']}]")]
    if op in ("rldicl", "rldicr", "rldic", "rldimi", "rldcl", "rldcr"):
        mb, sh = f["MB"], f.get("SH")
        m = {"rldicl": lambda: _mask64(mb, 63), "rldicr": lambda: _mask64(0, mb),
             "rldic": lambda: _mask64(mb, 63 - sh), "rldimi": lambda: _mask64(mb, 63 - sh),
             "rldcl": lambda: _mask64(mb, 63), "rldcr": lambda: _mask64(0, mb)}[op]()
        n = f"(c.r[{f['B']}] & 63)" if op in ("rldcl", "rldcr") else str(sh)
        rot = f"rotl64(c.r[{f['S']}], {n})" if n != "0" else f"c.r[{f['S']}]"
        if op == "rldimi":
            s = f"c.r[{f['A']}] = ({rot} & {_h(m)}) | (c.r[{f['A']}] & ~{_h(m)});"
        else:
            s = f"c.r[{f['A']}] = {rot} & {_h(m)};"
        return [s + _rc(rc, f"c.r[{f['A']}]")]

    # ---- integer, register ------------------------------------------------------------
    if op in ("add", "subf", "neg", "mullw", "mulhw", "mulhwu", "divw", "divwu",
              "mulld", "mulhd", "mulhdu", "divd", "divdu") or op in _ADDS:
        D, A, B = f["D"], f["A"], f["B"]
        if f.get("OE"):
            raise Unsupported(f"{op}o")
        body = f"uint64_t a = c.r[{A}], b = c.r[{B}]; uint64_t r; (void)b;"
        body += {
            "add": " r = a + b;",
            "subf": " r = b - a;",
            "neg": " r = 0ull - a;",
            "mullw": " r = (uint64_t)((int64_t)(int32_t)a * (int64_t)(int32_t)b);",
            "mulhw": " r = (uint64_t)(int64_t)(int32_t)(((int64_t)(int32_t)a * (int32_t)b) >> 32);",
            "mulhwu": " r = (uint32_t)(((uint64_t)(uint32_t)a * (uint32_t)b) >> 32);",
            "divw": " r = divw(a, b);",
            "divwu": " r = divwu(a, b);",
            "mulld": " r = a * b;",
            "mulhd": " r = mulhd(a, b);",
            "mulhdu": " r = mulhdu(a, b);",
            "divd": " r = divd(a, b);",
            "divdu": " r = divdu(a, b);",
        }.get(op, "")
        if op in _ADDS:
            x, y, cin = _ADDS[op]
            body += f" r = add_ca(c, {x}, {y}, {cin});"
        body += f" c.r[{D}] = r;"
        if rc:
            body += " cr0_rc(c, r);"
        return ["{ " + body + " }"]
    if op in _LOGIC:
        e = _LOGIC[op].format(s=f"c.r[{f['S']}]", b=f"c.r[{f['B']}]")
        return [f"c.r[{f['A']}] = {e};" + _rc(rc, f"c.r[{f['A']}]")]
    if op == "srawi":
        return [f"c.r[{f['A']}] = sraw(c, c.r[{f['S']}], {f['SH']});" + _rc(rc, f"c.r[{f['A']}]")]
    if op == "sradi":
        return [f"c.r[{f['A']}] = srad(c, c.r[{f['S']}], {f['SH']});" + _rc(rc, f"c.r[{f['A']}]")]
    if op in ("cntlzw", "cntlzd", "extsh", "extsb", "extsw"):
        e = {"cntlzw": "cntlzw((uint32_t){s})", "cntlzd": "cntlzd({s})",
             "extsh": "(uint64_t)(int64_t)(int16_t){s}",
             "extsb": "(uint64_t)(int64_t)(int8_t){s}",
             "extsw": "(uint64_t)(int64_t)(int32_t){s}"}[op].format(s=f"c.r[{f['S']}]")
        return [f"c.r[{f['A']}] = {e};" + _rc(rc, f"c.r[{f['A']}]")]

    # ---- loads and stores -----------------------------------------------------------------
    base = op[:-1] if op.endswith("u") else op
    if base in _LOAD and op in (base, base + "u"):
        if op == base:
            return [f"c.r[{f['D']}] = {_LOAD[base].format(ea=_ea_d(f))};"]
        return [f"{{ uint32_t ea = {_ea_d(f)}; c.r[{f['D']}] = {_LOAD[base].format(ea='ea')}; c.r[{f['A']}] = ea; }}"]
    if base in _STORE and op in (base, base + "u"):
        v = f"c.r[{f['D']}]"
        if op == base:
            return [_STORE[base].format(ea=_ea_d(f), v=v) + ";"]
        return [f"{{ uint32_t ea = {_ea_d(f)}; {_STORE[base].format(ea='ea', v=v)}; c.r[{f['A']}] = ea; }}"]
    if op in ("lfs", "lfsu", "lfd", "lfdu", "stfs", "stfsu", "stfd", "stfdu"):
        upd = op.endswith("u")
        k = op.rstrip("u")
        stmt = {"lfs": "c.f[D] = (double)as_f32(ld32(ea));",
                "lfd": "c.f[D] = as_f64(ld64(ea));",
                "stfs": "st32(ea, as_u32((float)c.f[D]));",
                "stfd": "st64(ea, as_u64(c.f[D]));"}[k].replace("[D]", f"[{f['D']}]")
        return [f"{{ uint32_t ea = {_ea_d(f)}; {stmt}" + (f" c.r[{f['A']}] = ea;" if upd else "") + " }"]
    if op in ("lfsx", "lfsux", "lfdx", "lfdux", "stfsx", "stfsux", "stfdx", "stfdux", "stfiwx"):
        upd = op.endswith("ux")
        k = op.replace("ux", "x")
        stmt = {"lfsx": "c.f[D] = (double)as_f32(ld32(ea));",
                "lfdx": "c.f[D] = as_f64(ld64(ea));",
                "stfsx": "st32(ea, as_u32((float)c.f[D]));",
                "stfdx": "st64(ea, as_u64(c.f[D]));",
                "stfiwx": "st32(ea, (uint32_t)as_u64(c.f[D]));"}[k].replace("[D]", f"[{f['D']}]")
        return [f"{{ uint32_t ea = {_ea_x(f)}; {stmt}" + (f" c.r[{f['A']}] = ea;" if upd else "") + " }"]
    if op in _LOADX or (op.endswith("ux") and op.replace("ux", "x") in _LOADX):
        k = op.replace("ux", "x")
        upd = f" c.r[{f['A']}] = ea;" if op.endswith("ux") else ""
        return [f"{{ uint32_t ea = {_ea_x(f)}; c.r[{f['D']}] = {_LOADX[k]};{upd} }}"]
    if op in _STOREX or (op.endswith("ux") and op.replace("ux", "x") in _STOREX):
        k = op.replace("ux", "x")
        upd = f" c.r[{f['A']}] = ea;" if op.endswith("ux") else ""
        return [f"{{ uint32_t ea = {_ea_x(f)}; {_STOREX[k].format(v=f'c.r[{f['D']}]')};{upd} }}"]
    if op in ("lmw", "stmw"):
        out = [f"{{ uint32_t ea = {_ea_d(f)};"]
        for k, rr in enumerate(range(f["D"], 32)):
            out.append(f" c.r[{rr}] = ld32(ea + {4 * k}u);" if op == "lmw"
                       else f" st32(ea + {4 * k}u, (uint32_t)c.r[{rr}]);")
        return ["".join(out) + " }"]
    if op in ("lwarx", "ldarx"):
        return [f"c.r[{f['D']}] = ppu_{op}(c, {_ea_x(f)});"]
    if op in ("stwcx.", "stdcx."):
        return [f"ppu_{op[:-1]}(c, {_ea_x(f)}, c.r[{f['D']}]);"]
    if op == "dcbz":
        return [f"ppu_dcbz({_ea_x(f)});"]
    if op in _NOP:
        return [f"/* {op} */"]

    # ---- system registers ---------------------------------------------------------------
    if op == "mfspr":
        n, D = f["spr"], f["D"]
        src = {1: "mfxer(c)", 8: "c.lr", 9: "c.ctr", 256: "c.vrsave",
               268: "ppu_timebase()", 269: "(ppu_timebase() >> 32)"}.get(n)
        if src is None:
            raise Unsupported(f"mfspr {n}")
        return [f"c.r[{D}] = {src};"]
    if op == "mtspr":
        n, S = f["spr"], f["D"]
        if n == 1:
            return [f"mtxer(c, c.r[{S}]);"]
        dst = {8: "c.lr", 9: "c.ctr", 256: "c.vrsave"}.get(n)
        if dst is None:
            raise Unsupported(f"mtspr {n}")
        return [f"{dst} = c.r[{S}];" if n != 256 else f"c.vrsave = (uint32_t)c.r[{S}];"]
    if op == "mftb":
        return [f"c.r[{f['D']}] = " + ("(ppu_timebase() >> 32);" if f["spr"] == 269 else "ppu_timebase();")]
    if op == "mfcr":
        return [f"c.r[{f['D']}] = mfcr(c);"]
    if op == "mtcrf":
        return [f"mtcrf(c, {_h32(f['CRM'])}, (uint32_t)c.r[{f['S']}]);"]
    if op == "mcrf":
        d, s = f["crfD"] * 4, f["crfS"] * 4
        return ["{ " + " ".join(f"c.cr[{d + k}] = c.cr[{s + k}];" for k in range(4)) + " }"]
    if op == "mcrxr":
        return [f"{{ cr_set(c, {f['crfD']}, c.xer_so, c.xer_ov, c.xer_ca, 0); c.xer_so = c.xer_ov = c.xer_ca = 0; }}"]
    if op in _CROPS:
        e = _CROPS[op].replace("a", "\0A").replace("b", "\0B")
        e = e.replace("\0A", f"c.cr[{f['crbA']}]").replace("\0B", f"c.cr[{f['crbB']}]")
        return [f"c.cr[{f['crbD']}] = (uint8_t)(({e}) & 1);"]
    if op == "sc":
        return [f"ppu_syscall(c, {_h32(addr)});"]

    # ---- floating point ---------------------------------------------------------------
    if op in _FP2 or op in _FPS or op in _FPMOVE:
        D = f["D"]
        load = f"double a = c.f[{f.get('A', 0)}], b = c.f[{f.get('B', 0)}], cc = c.f[{f.get('C', 0)}]; (void)a; (void)cc;"
        if op in _FP2:
            s = f"c.f[{D}] = {_FP2[op]};"
        elif op in _FPS:
            s = f"c.f[{D}] = rs({_FPS[op]});"
        else:
            load = f"double b = c.f[{f['B']}];"
            s = f"c.f[{D}] = {_FPMOVE[op]};"
        return ["{ " + load + " " + s + (" cr1_rc(c);" if rc else "") + " }"]
    if op in ("fcmpu", "fcmpo"):
        return [f"fcmp(c, {f['crfD']}, c.f[{f['A']}], c.f[{f['B']}]);"]
    if op in ("fctiw", "fctiwz"):
        return [f"c.f[{f['D']}] = fctiw_bits(c, c.f[{f['B']}], {str(op == 'fctiwz').lower()});" + (" cr1_rc(c);" if rc else "")]
    if op in ("fctid", "fctidz"):
        return [f"c.f[{f['D']}] = fctid_bits(c, c.f[{f['B']}], {str(op == 'fctidz').lower()});" + (" cr1_rc(c);" if rc else "")]
    if op == "fcfid":
        return [f"c.f[{f['D']}] = (double)(int64_t)as_u64(c.f[{f['B']}]);" + (" cr1_rc(c);" if rc else "")]
    if op == "mffs":
        return [f"c.f[{f['D']}] = as_f64(0xFFF8000000000000ull | c.fpscr);" + (" cr1_rc(c);" if rc else "")]
    if op == "mtfsf":
        return [f"mtfsf(c, {_h32(f['FM'])}, c.f[{f['B']}]);" + (" cr1_rc(c);" if rc else "")]
    if op == "mtfsfi":
        sh = 28 - 4 * f["crfD"]
        return [f"c.fpscr = (c.fpscr & ~{_h32(0xF << sh)}) | {_h32(f['IMM'] << sh)};" + (" cr1_rc(c);" if rc else "")]
    if op in ("mtfsb0", "mtfsb1"):
        bit = _h32(0x80000000 >> f["crbD"])
        s = f"c.fpscr &= ~{bit};" if op == "mtfsb0" else f"c.fpscr |= {bit};"
        return [s + (" cr1_rc(c);" if rc else "")]
    if op == "mcrfs":
        sh = 28 - 4 * f["crfS"]
        return [f"{{ uint32_t v = c.fpscr >> {sh}; cr_set(c, {f['crfD']}, v >> 3 & 1, v >> 2 & 1, v >> 1 & 1, v & 1); }}"]

    # ---- VMX ------------------------------------------------------------------------------
    if op in ("lvx", "lvxl", "stvx", "stvxl", "lvlx", "lvrx", "stvlx", "stvrx",
              "lvebx", "lvehx", "lvewx", "stvebx", "stvehx", "stvewx", "lvsl", "lvsr"):
        k = op[:-1] if op in ("lvxl", "stvxl") else op
        return [f"vmx_{k}(c, {f['D']}, {_ea_x(f)});"]
    if op in _VMX3:
        return [f"vmx_{op}(c.v[{f['D']}], c.v[{f['A']}], c.v[{f['B']}]);"]
    if op in _VMX2:
        return [f"vmx_{op}(c.v[{f['D']}], c.v[{f['B']}]);"]
    if op in _VMXCMP:
        return [f"vmx_{op}(c, c.v[{f['D']}], c.v[{f['A']}], c.v[{f['B']}], {f['Rc']});"]
    if op in ("vmaddfp", "vnmsubfp", "vperm", "vsel"):
        return [f"vmx_{op}(c.v[{f['D']}], c.v[{f['A']}], c.v[{f['B']}], c.v[{f['C']}]);"]
    if op == "vsldoi":
        return [f"vmx_vsldoi(c.v[{f['D']}], c.v[{f['A']}], c.v[{f['B']}], {f['SHB']});"]
    if op in ("vspltw", "vsplth", "vspltb"):
        return [f"vmx_{op}(c.v[{f['D']}], c.v[{f['B']}], {f['UIMM']});"]
    if op in ("vspltisw", "vspltish", "vspltisb"):
        return [f"vmx_{op}(c.v[{f['D']}], {f['SIMM']});"]
    if op in ("vctsxs", "vctuxs", "vcfsx", "vcfux"):
        return [f"vmx_{op}(c, c.v[{f['D']}], c.v[{f['B']}], {f['UIMM']});"]
    if op == "mfvscr":
        return [f"vmx_mfvscr(c, c.v[{f['D']}]);"]
    if op == "mtvscr":
        return [f"c.vscr = vmx_word(c.v[{f['B']}], 3);"]

    raise Unsupported(op)


def terminates(ins):
    """True if control never falls through to the next instruction."""
    op, f = ins.op, ins.f
    if op == "b" and not f["LK"]:
        return True
    return op in ("bclr", "bcctr") and not f["LK"] and f["BO"] & 0x14 == 0x14
