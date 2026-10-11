// ps3kit runtime — fragment programs to GLSL (rsxprog.h).
//
// An instruction is four words: the destination and opcode, then three
// sources. A source of type constant reads the 128-bit literal stored in the
// slot after the instruction. Flow control (IFE, LOOP, REP) names its
// targets as instruction addresses, and is translated back into GLSL's own
// blocks. The R registers are 32-bit, the H registers 16-bit; both are kept
// as separate full-precision variables.
#include "rsxprog.h"
#include <cstdio>
#include <set>

namespace {
uint32_t bits(uint32_t v, int lo, int n) { return (v >> lo) & ((1u << n) - 1); }

enum : uint32_t {
    NOP = 0x00, MOV, MUL, ADD, MAD, DP3, DP4, DST, MIN, MAX, SLT, SGE, SLE, SGT, SNE, SEQ, FRC, FLR, KIL, PK4,
    UP4, DDX, DDY, TEX, TXP, TXD, RCP, RSQ, EX2, LG2, LIT, LRP, STR, SFL, COS, SIN, PK2, UP2, POW, PKB, UPB, PK16,
    UP16, BEM, PKG, UPG, DP2A, TXL, TXB = 0x31, TEXBEM = 0x33, TXPBEM, BEMLUM, REFL, TIMESWTEX, DP2, NRM, DIV,
    DIVSQ, LIF, FENCT, FENCB, BRK = 0x40, CAL, IFE, LOOP, REP, RET
};

const char* kInputs[] = {"wpos", "fp_col0", "fp_col1", "fp_fog", "fp_tc0", "fp_tc1", "fp_tc2", "fp_tc3",
                         "fp_tc4", "fp_tc5", "fp_tc6", "fp_tc7", "fp_tc8", "fp_tc9", "ssa"};
// where each input arrives: the vertex program's output register
const int kInputLocation[] = {0, 1, 2, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 6, 0};

struct Ins {
    uint32_t d, s0, s1, s2;
    uint32_t pc;                        // address, in 16-byte slots
    int literal = -1;                   // index into fc[], when a source reads the constant
};

struct Gen {
    const uint32_t* w;
    uint32_t nwords;
    const FPConfig& cfg;
    ProgramText out;
    std::vector<Ins> ins;               // in address order
    std::set<std::string> regs;         // r0, h3, ...
    std::set<int> inputs;
    std::set<int> samplers;
    std::string body;
    int depth = 1, loops = 0;
    bool kill = false;

    Gen(const uint32_t* w_, uint32_t n_, const FPConfig& c) : w(w_), nwords(n_), cfg(c) {}

    void problem(const std::string& p) {
        for (auto& q : out.problems) if (q == p) return;
        out.problems.push_back(p);
    }
    void line(const std::string& s) { body.append(depth * 4, ' ') += s + "\n"; }

    static uint32_t opcode(const Ins& i) { return bits(i.d, 24, 6) | (bits(i.s1, 31, 1) << 6); }
    static bool reads_constant(const Ins& i) {
        return bits(i.s0, 0, 2) == 2 || bits(i.s1, 0, 2) == 2 || bits(i.s2, 0, 2) == 2;
    }
    static bool is_flow(uint32_t op) { return op >= BRK && op <= RET; }

    bool parse() {
        for (uint32_t pc = 0; pc * 4 + 3 < nwords; ++pc) {
            Ins i{w[pc * 4], w[pc * 4 + 1], w[pc * 4 + 2], w[pc * 4 + 3], pc};
            uint32_t op = opcode(i);
            bool lit = !is_flow(op) && reads_constant(i);
            if (lit) {
                i.literal = (int)out.literals.size();
                out.literals.push_back((pc + 1) * 4);
            }
            ins.push_back(i);
            if (bits(i.d, 0, 1)) return true;           // end
            if (lit) ++pc;
        }
        return false;
    }

    const Ins* at(uint32_t pc) const {
        for (auto& i : ins) if (i.pc == pc) return &i;
        return nullptr;
    }

    std::string reg(uint32_t index, bool half) {
        std::string n = std::string(half ? "h" : "r") + std::to_string(index);
        regs.insert(n);
        return n;
    }

    std::string clamp_prec(const std::string& v, uint32_t prec) {
        switch (prec) {
        case 2: return "clamp(" + v + ", -2.0, 2.0)";   // fixed12
        case 3: return "clamp(" + v + ", -1.0, 1.0)";   // fixed9
        case 4: return "clamp(" + v + ", 0.0, 1.0)";
        default: return v;
        }
    }

    std::string src(const Ins& i, int n) {
        uint32_t s = n == 0 ? i.s0 : n == 1 ? i.s1 : i.s2;
        uint32_t prec_mod = bits(i.s1, 19 + 3 * n, 3);
        bool abs = n == 0 ? bits(i.s0, 29, 1) : bits(s, 18, 1);
        std::string v;
        switch (bits(s, 0, 2)) {
        case 0: v = reg(bits(s, 2, 6), bits(s, 8, 1)); break;
        case 1: {
            uint32_t id = bits(i.s2, 30, 1) ? bits(i.s2, 19, 11) + 4 : bits(i.d, 13, 4);
            if (bits(i.s2, 30, 1)) problem("indexed input");
            if (id > 14) { problem("input register " + std::to_string(id)); v = "vec4(0.0)"; break; }
            inputs.insert((int)id);
            if (id == 1 || id == 2) { v = "clamp(" + std::string(kInputs[id]) + ", 0.0, 1.0)"; prec_mod = 0; }
            else if (id >= 4 && id <= 13) {
                std::string tc = kInputs[id];
                bool flat2d = (cfg.tc_2d >> (id - 4)) & 1;
                if (bits(i.s2, 31, 1)) tc = flat2d ? "vec4(" + tc + ".xy * gl_FragCoord.w, 0.0, 1.0)"
                                                  : "(" + tc + " * gl_FragCoord.w)";
                else if (flat2d) tc = "vec4(" + tc + ".xy, 0.0, 1.0)";
                v = tc;
            } else v = kInputs[id];
            break;
        }
        case 2: v = "fc[" + std::to_string(i.literal) + "]"; break;
        default: problem("source type 3"); v = "vec4(0.0)"; break;
        }
        static const char xyzw[] = "xyzw";
        std::string sw = ".";
        for (int k = 0; k < 4; ++k) sw += xyzw[bits(s, 9 + 2 * k, 2)];
        if (sw != ".xyzw") v += sw;
        if (abs) v = "abs(" + v + ")";
        if (prec_mod) v = clamp_prec(v, prec_mod);
        if (bits(s, 17, 1)) v = "-" + v;
        return v;
    }

    // The condition an instruction executes under, per component, or "" for always.
    std::string cond(const Ins& i, bool& never) {
        bool lt = bits(i.s0, 18, 1), eq = bits(i.s0, 19, 1), gt = bits(i.s0, 20, 1);
        never = !lt && !eq && !gt;
        if (lt && eq && gt) return "";
        static const char xyzw[] = "xyzw";
        std::string sw = ".";
        for (int k = 0; k < 4; ++k) sw += xyzw[bits(i.s0, 21 + 2 * k, 2)];
        std::string cc = "cc" + std::to_string(bits(i.s0, 31, 1)) + (sw == ".xyzw" ? "" : sw);
        const char* f = gt && eq ? "greaterThanEqual" : lt && eq ? "lessThanEqual" : gt && lt ? "notEqual"
                        : gt ? "greaterThan" : lt ? "lessThan" : "equal";
        return std::string(f) + "(" + cc + ", vec4(0.0))";
    }

    std::string mask(const Ins& i) {
        std::string m = ".";
        if (bits(i.d, 9, 1)) m += 'x';
        if (bits(i.d, 10, 1)) m += 'y';
        if (bits(i.d, 11, 1)) m += 'z';
        if (bits(i.d, 12, 1)) m += 'w';
        return m == "." || m == ".xyzw" ? "" : m;
    }

    // The result of an instruction, written as the hardware writes it:
    // scaled, clamped, masked, under its condition, and to CC if asked.
    void set_dst(const Ins& i, std::string v) {
        bool never;
        std::string c = cond(i, never);
        if (never) return;
        switch (bits(i.s1, 28, 3)) {
        case 1: v = "(" + v + " * 2.0)"; break;
        case 2: v = "(" + v + " * 4.0)"; break;
        case 3: v = "(" + v + " * 8.0)"; break;
        case 5: v = "(" + v + " / 2.0)"; break;
        case 6: v = "(" + v + " / 4.0)"; break;
        case 7: v = "(" + v + " / 8.0)"; break;
        default: break;
        }
        if (bits(i.d, 31, 1)) v = "clamp(" + v + ", 0.0, 1.0)";
        else if (bits(i.d, 22, 2) >= 2) v = clamp_prec(v, bits(i.d, 22, 2));
        std::string m = mask(i);
        std::string value = "vec4(" + v + ")";
        auto assign = [&](const std::string& lhs) {
            if (c.empty()) line(lhs + m + " = " + value + m + ";");
            else line(lhs + m + " = mix(" + lhs + ", " + value + ", bvec4(" + c + "))" + m + ";");
        };
        std::string lhs;
        if (!bits(i.d, 30, 1)) {
            lhs = reg(bits(i.d, 1, 6), bits(i.d, 7, 1));
            assign(lhs);
        }
        if (bits(i.d, 8, 1)) {
            std::string cc = "cc" + std::to_string(bits(i.s0, 30, 1));
            if (!lhs.empty()) line(cc + m + " = " + lhs + m + ";");
            else assign(cc);
        }
    }

    std::string sampler(const Ins& i) {
        int t = (int)bits(i.d, 17, 4);
        samplers.insert(t);
        return "tex" + std::to_string(t);
    }
    int tex_dim(const Ins& i) { return (int)((cfg.tex_dims >> (2 * bits(i.d, 17, 4))) & 3); }
    std::string coord(const Ins& i, const std::string& a) {
        switch (tex_dim(i)) {
        case 0: return a + ".x";
        case 1: return a + ".xy";
        default: return a + ".xyz";
        }
    }

    void op(const Ins& i) {
        uint32_t o = opcode(i);
        auto s = [&](int n) { return src(i, n); };
        switch (o) {
        case NOP: case FENCT: case FENCB: return;
        case MOV: set_dst(i, s(0)); return;
        case MUL: set_dst(i, "(" + s(0) + " * " + s(1) + ")"); return;
        case ADD: set_dst(i, "(" + s(0) + " + " + s(1) + ")"); return;
        case MAD: set_dst(i, "fma(" + s(0) + ", " + s(1) + ", " + s(2) + ")"); return;
        case DP2: set_dst(i, "dot((" + s(0) + ").xy, (" + s(1) + ").xy)"); return;
        case DP3: set_dst(i, "dot((" + s(0) + ").xyz, (" + s(1) + ").xyz)"); return;
        case DP4: set_dst(i, "dot(" + s(0) + ", " + s(1) + ")"); return;
        case DP2A: set_dst(i, "(dot((" + s(0) + ").xy, (" + s(1) + ").xy) + (" + s(2) + ").z)"); return;
        case DST: set_dst(i, "vec4(1.0, (" + s(0) + ").y * (" + s(1) + ").y, (" + s(0) + ").z, (" + s(1) + ").w)"); return;
        case MIN: set_dst(i, "min(" + s(0) + ", " + s(1) + ")"); return;
        case MAX: set_dst(i, "max(" + s(0) + ", " + s(1) + ")"); return;
        case SLT: set_dst(i, "vec4(lessThan(" + s(0) + ", " + s(1) + "))"); return;
        case SGE: set_dst(i, "vec4(greaterThanEqual(" + s(0) + ", " + s(1) + "))"); return;
        case SLE: set_dst(i, "vec4(lessThanEqual(" + s(0) + ", " + s(1) + "))"); return;
        case SGT: set_dst(i, "vec4(greaterThan(" + s(0) + ", " + s(1) + "))"); return;
        case SNE: set_dst(i, "vec4(notEqual(" + s(0) + ", " + s(1) + "))"); return;
        case SEQ: set_dst(i, "vec4(equal(" + s(0) + ", " + s(1) + "))"); return;
        case STR: set_dst(i, "vec4(1.0)"); return;
        case SFL: set_dst(i, "vec4(0.0)"); return;
        case FRC: set_dst(i, "fract(" + s(0) + ")"); return;
        case FLR: set_dst(i, "floor(" + s(0) + ")"); return;
        case RCP: set_dst(i, "(1.0 / (" + s(0) + ").x)"); return;
        case RSQ: set_dst(i, "inversesqrt(abs((" + s(0) + ").x))"); return;
        case EX2: set_dst(i, "exp2((" + s(0) + ").x)"); return;
        case LG2: set_dst(i, "log2((" + s(0) + ").x)"); return;
        case COS: set_dst(i, "cos((" + s(0) + ").x)"); return;
        case SIN: set_dst(i, "sin((" + s(0) + ").x)"); return;
        case POW: set_dst(i, "pow((" + s(0) + ").x, (" + s(1) + ").x)"); return;
        case DIV: set_dst(i, "(" + s(0) + " / (" + s(1) + ").x)"); return;
        case DIVSQ: set_dst(i, "(" + s(0) + " * inversesqrt((" + s(1) + ").x))"); return;
        case LRP: set_dst(i, "mix(" + s(2) + ", " + s(1) + ", " + s(0) + ")"); return;
        case NRM: set_dst(i, "vec4(normalize((" + s(0) + ").xyz), 0.0).xyzz"); return;
        case REFL: {
            std::string a = s(0), b = s(1);
            set_dst(i, "(2.0 * dot(" + a + ".xyz, " + b + ".xyz) / dot(" + a + ".xyz, " + a + ".xyz) * " + a + " - " + b + ")");
            return;
        }
        case LIT: {
            std::string a = s(0);
            set_dst(i, "vec4(1.0, max(" + a + ".x, 0.0), (" + a + ".x > 0.0) ? exp2(" + a + ".w * log2(max(" + a +
                           ".y, 1.0e-10))) : 0.0, 1.0)");
            return;
        }
        case DDX: set_dst(i, "dFdx(" + s(0) + ")"); return;
        case DDY: set_dst(i, "dFdy(" + s(0) + ")"); return;
        case PK2: set_dst(i, "uintBitsToFloat(packHalf2x16((" + s(0) + ").xy))"); return;
        case UP2: set_dst(i, "unpackHalf2x16(floatBitsToUint((" + s(0) + ").x)).xyxy"); return;
        case PK4: set_dst(i, "uintBitsToFloat(packSnorm4x8(" + s(0) + "))"); return;
        case UP4: set_dst(i, "unpackSnorm4x8(floatBitsToUint((" + s(0) + ").x))"); return;
        case PKB: set_dst(i, "uintBitsToFloat(packUnorm4x8(" + s(0) + "))"); return;
        case UPB: set_dst(i, "unpackUnorm4x8(floatBitsToUint((" + s(0) + ").x))"); return;
        case PK16: set_dst(i, "uintBitsToFloat(packUnorm2x16((" + s(0) + ").xy))"); return;
        case UP16: set_dst(i, "unpackUnorm2x16(floatBitsToUint((" + s(0) + ").x)).xyxy"); return;
        case TEX: {
            if (bits(i.d, 21, 1)) problem("texture expand (_bx2)");
            std::string t = sampler(i);
            set_dst(i, "texture(" + t + ", " + coord(i, "(" + s(0) + ")") + ")");
            return;
        }
        case TXP: {
            std::string t = sampler(i), a = "(" + s(0) + ")";
            if (tex_dim(i) == 1) set_dst(i, "textureProj(" + t + ", " + a + ".xyw)");
            else set_dst(i, "texture(" + t + ", " + coord(i, a) + " / " + a + ".w)");
            return;
        }
        case TXL: {
            std::string t = sampler(i);
            set_dst(i, "textureLod(" + t + ", " + coord(i, "(" + s(0) + ")") + ", (" + s(1) + ").x)");
            return;
        }
        case TXB: {
            std::string t = sampler(i);
            set_dst(i, "texture(" + t + ", " + coord(i, "(" + s(0) + ")") + ", (" + s(1) + ").x)");
            return;
        }
        case TXD: {
            std::string t = sampler(i);
            set_dst(i, "textureGrad(" + t + ", " + coord(i, "(" + s(0) + ")") + ", " + coord(i, "(" + s(1) + ")") +
                           ", " + coord(i, "(" + s(2) + ")") + ")");
            return;
        }
        case KIL: {
            bool never;
            std::string c = cond(i, never);
            if (never) return;
            kill = true;
            line(c.empty() ? "discard;" : "if (any(" + c + ")) discard;");
            return;
        }
        default: {
            char b[48];
            std::snprintf(b, sizeof b, "opcode %02X", o);
            problem(b);
            line(std::string("// ") + b);
            return;
        }
        }
    }

    // Instructions from address pc up to (not including) end, or to the program's end.
    void range(uint32_t pc, uint32_t end) {
        while (pc < end) {
            const Ins* p = at(pc);
            if (!p) return;
            const Ins& i = *p;
            uint32_t o = opcode(i);
            if (o == IFE) {
                uint32_t els = bits(i.s1, 0, 31) >> 2, fin = i.s2 >> 2;
                bool never;
                std::string c = cond(i, never);
                line("if (" + (never ? std::string("false") : c.empty() ? std::string("true") : "any(" + c + ")") + ") {");
                ++depth;
                range(pc + 1, std::min(els, fin));
                --depth;
                if (els < fin) {
                    line("} else {");
                    ++depth;
                    range(els, fin);
                    --depth;
                }
                line("}");
                pc = fin;
                continue;
            }
            if (o == LOOP || o == REP) {
                uint32_t fin = i.s2 >> 2, count = bits(i.s1, 2, 8);
                int init = (int)bits(i.s1, 10, 8), inc = (int8_t)bits(i.s1, 19, 8);
                bool never;
                std::string c = cond(i, never);
                std::string n = "i" + std::to_string(loops++);
                line((c.empty() ? std::string() : "if (any(" + c + ")) ") + "for (int " + n + " = 0; " + n + " < " +
                     std::to_string(count) + "; " + n + "++) {    // " + (o == LOOP ? "LOOP" : "REP") + " init " +
                     std::to_string(init) + " step " + std::to_string(inc));
                ++depth;
                range(pc + 1, fin);
                --depth;
                line("}");
                pc = fin;
                continue;
            }
            if (o == BRK || o == RET) {
                bool never;
                std::string c = cond(i, never);
                const char* what = o == BRK ? "break;" : "return;";
                if (!never) line(c.empty() ? what : "if (any(" + c + ")) " + std::string(what));
            } else if (o == CAL) {
                problem("CAL");
            } else {
                op(i);
            }
            if (bits(i.d, 0, 1)) return;
            pc += i.literal >= 0 ? 2 : 1;
        }
    }

    std::string build() {
        bool fp32 = cfg.ctrl & 0x40;                    // CELL_GCM_SHADER_CONTROL_32_BITS_EXPORTS
        bool depth_export = cfg.ctrl & 0xE;
        const char* outs[4] = {fp32 ? "r0" : "h0", fp32 ? "r2" : "h4", fp32 ? "r3" : "h6", fp32 ? "r4" : "h8"};
        for (auto* o : outs) regs.insert(o);
        if (depth_export) regs.insert("r1");
        std::string s = "#version 450\n";
        for (int id : inputs) {
            if (id == 0 || id == 14) continue;
            s += "layout(location = " + std::to_string(kInputLocation[id]) + ") in vec4 " + kInputs[id] + ";\n";
        }
        if (!out.literals.empty()) s += "uniform vec4 fc[" + std::to_string(out.literals.size()) + "];\n";
        static const char* kind[] = {"sampler1D", "sampler2D", "sampler3D", "samplerCube"};
        for (int t : samplers)
            s += "layout(binding = " + std::to_string(t) + ") uniform " + kind[(cfg.tex_dims >> (2 * t)) & 3] + " tex" +
                 std::to_string(t) + ";\n";
        s += "uniform vec4 fp_wpos;\nuniform ivec4 fp_alpha;\nuniform float fp_alpha_ref;\n";
        for (int k = 0; k < 4; ++k) s += "layout(location = " + std::to_string(k) + ") out vec4 ocol" + std::to_string(k) + ";\n";
        s += "vec4 cc0 = vec4(0.0), cc1 = vec4(0.0);\n";
        for (auto& r : regs) s += "vec4 " + r + " = vec4(0.0);\n";
        if (inputs.count(0)) s += "vec4 wpos;\n";
        if (inputs.count(14)) s += "vec4 ssa;\n";
        s += "void body() {\n" + body + "}\n";
        s += "void main() {\n";
        if (inputs.count(0))
            s += "    wpos = vec4(gl_FragCoord.x + fp_wpos.z, gl_FragCoord.y * fp_wpos.x + fp_wpos.y, gl_FragCoord.zw);\n";
        if (inputs.count(14)) s += "    ssa = vec4(gl_FrontFacing ? 1.0 : -1.0);\n";
        if (depth_export) s += "    r1.z = gl_FragCoord.z;\n";
        s += "    body();\n";
        // the alpha test, against the first colour output (CELL_GCM_NEVER..ALWAYS = 0x200..0x207)
        s += std::string("    if (fp_alpha.x != 0) {\n") +
             "        float a = " + outs[0] + ".a; bool pass;\n"
             "        switch (fp_alpha.y) {\n"
             "        case 0x200: pass = false; break;\n"
             "        case 0x201: pass = a < fp_alpha_ref; break;\n"
             "        case 0x202: pass = a == fp_alpha_ref; break;\n"
             "        case 0x203: pass = a <= fp_alpha_ref; break;\n"
             "        case 0x204: pass = a > fp_alpha_ref; break;\n"
             "        case 0x205: pass = a != fp_alpha_ref; break;\n"
             "        case 0x206: pass = a >= fp_alpha_ref; break;\n"
             "        default: pass = true; break;\n"
             "        }\n"
             "        if (!pass) discard;\n"
             "    }\n";
        for (int k = 0; k < 4; ++k) s += "    ocol" + std::to_string(k) + " = " + outs[k] + ";\n";
        if (depth_export) s += "    gl_FragDepth = r1.z;\n";
        s += "}\n";
        return s;
    }
};
}  // namespace

uint32_t fp_length(const uint32_t* w, uint32_t max_words) {
    for (uint32_t pc = 0; pc * 4 + 3 < max_words; ++pc) {
        uint32_t d = w[pc * 4], s0 = w[pc * 4 + 1], s1 = w[pc * 4 + 2], s2 = w[pc * 4 + 3];
        uint32_t op = bits(d, 24, 6) | (bits(s1, 31, 1) << 6);
        bool lit = !(op >= BRK && op <= RET) && (bits(s0, 0, 2) == 2 || bits(s1, 0, 2) == 2 || bits(s2, 0, 2) == 2);
        if (bits(d, 0, 1)) return (pc + 1 + lit) * 4 <= max_words ? (pc + 1 + lit) * 4 : 0;
        if (lit) ++pc;
    }
    return 0;
}

std::vector<uint32_t> fp_literal_words(const uint32_t* w, uint32_t nwords) {
    std::vector<uint32_t> out;
    for (uint32_t pc = 0; pc * 4 + 3 < nwords; ++pc) {
        uint32_t d = w[pc * 4], s0 = w[pc * 4 + 1], s1 = w[pc * 4 + 2], s2 = w[pc * 4 + 3];
        uint32_t op = bits(d, 24, 6) | (bits(s1, 31, 1) << 6);
        bool lit = !(op >= BRK && op <= RET) && (bits(s0, 0, 2) == 2 || bits(s1, 0, 2) == 2 || bits(s2, 0, 2) == 2);
        if (lit) out.push_back((pc + 1) * 4);
        if (bits(d, 0, 1)) break;
        if (lit) ++pc;
    }
    return out;
}

ProgramText fp_translate(const uint32_t* words, uint32_t nwords, const FPConfig& cfg) {
    Gen g(words, nwords, cfg);
    if (!g.parse()) g.problem("no end");
    g.range(0, 0xFFFFFFFFu);
    g.out.glsl = g.build();
    return g.out;
}
