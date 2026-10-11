// ps3kit runtime — vertex programs to GLSL (rsxprog.h).
//
// An instruction is four words and issues two operations at once: a vector
// one, reading sources 0 and 1 (and 2 for ADD and MAD), and a scalar one,
// reading source 2. Either can write a temporary, an output register or the
// condition code, under a condition. A program runs from its start slot to
// the instruction whose end bit is set; one that branches is translated as
// a loop over a program counter and its basic blocks, one without as
// straight code.
//
// The viewport is applied after the program, as the RSX does: the output
// position is taken to window coordinates by NV4097_SET_VIEWPORT_SCALE and
// _OFFSET, then to the render target's own coordinates (vp_clip: 2/width,
// 2/height), rows counted from the top as RSX memory stores them.
#include "rsxprog.h"
#include <cstdio>
#include <set>
#include <vector>

namespace {
uint32_t bits(uint32_t v, int lo, int n) { return (v >> lo) & ((1u << n) - 1); }

enum : uint32_t { V_NOP, V_MOV, V_MUL, V_ADD, V_MAD, V_DP3, V_DPH, V_DP4, V_DST, V_MIN, V_MAX, V_SLT, V_SGE, V_ARL, V_FRC,
                  V_FLR, V_SEQ, V_SFL, V_SGT, V_SLE, V_SNE, V_STR, V_SSG, V_TXL = 0x19 };
enum : uint32_t { S_NOP, S_MOV, S_RCP, S_RCC, S_RSQ, S_EXP, S_LOG, S_LIT, S_BRA, S_BRI, S_CAL, S_CLI, S_RET, S_LG2, S_EX2,
                  S_SIN, S_COS, S_BRB, S_CLB, S_PSH, S_POP };

struct Gen {
    const uint32_t* p;
    uint32_t n;
    const VPConfig& cfg;
    ProgramText out;
    std::set<int> inputs, temps;
    std::string body;
    bool dispatch = false;
    uint32_t d0 = 0, d1 = 0, d2 = 0, d3 = 0, src[3] = {};

    Gen(const uint32_t* p_, uint32_t n_, const VPConfig& c) : p(p_), n(n_), cfg(c) {}

    void problem(const std::string& s) {
        for (auto& q : out.problems) if (q == s) return;
        out.problems.push_back(s);
    }
    void line(const std::string& s) { body += (dispatch ? "        " : "    ") + s + "\n"; }

    void load(uint32_t i) {
        d0 = p[i * 4]; d1 = p[i * 4 + 1]; d2 = p[i * 4 + 2]; d3 = p[i * 4 + 3];
        src[0] = bits(d2, 23, 9) | bits(d1, 0, 8) << 9;
        src[1] = bits(d2, 6, 17);
        src[2] = bits(d3, 21, 11) | bits(d2, 0, 6) << 11;
    }

    std::string addr_reg() { return std::string("a") + (bits(d0, 24, 1) ? "1" : "0") + "." + "xyzw"[bits(d0, 0, 2)]; }

    std::string source(int k) {
        uint32_t s = src[k];
        std::string v;
        switch (bits(s, 0, 2)) {
        case 1: temps.insert((int)bits(s, 2, 6)); v = "r" + std::to_string(bits(s, 2, 6)); break;
        case 2: {
            int id = (int)bits(d1, 8, 4);
            if (bits(d0, 27, 1)) problem("indexed input");
            inputs.insert(id);
            v = "in" + std::to_string(id);
            break;
        }
        case 3: {
            std::string idx = std::to_string(bits(d1, 12, 10));
            if (bits(d3, 1, 1)) idx = "clamp(" + idx + " + " + addr_reg() + ", 0, 467)";
            v = "vc[" + idx + "]";
            break;
        }
        default: v = "vec4(0.0)"; break;
        }
        static const char xyzw[] = "xyzw";
        std::string sw = ".";
        sw += xyzw[bits(s, 14, 2)];
        sw += xyzw[bits(s, 12, 2)];
        sw += xyzw[bits(s, 10, 2)];
        sw += xyzw[bits(s, 8, 2)];
        if (sw != ".xyzw") v += sw;
        if (bits(d0, 21 + k, 1)) v = "abs(" + v + ")";
        if (bits(s, 16, 1)) v = "-" + v;
        return v;
    }

    std::string cc() { return std::string("cc") + (bits(d0, 25, 1) ? "1" : "0"); }

    // The comparison of the condition code a conditional write or branch tests.
    std::string condition() {
        uint32_t c = bits(d0, 10, 3);
        static const char xyzw[] = "xyzw";
        std::string sw = ".";
        sw += xyzw[bits(d0, 8, 2)];
        sw += xyzw[bits(d0, 6, 2)];
        sw += xyzw[bits(d0, 4, 2)];
        sw += xyzw[bits(d0, 2, 2)];
        std::string r = cc() + (sw == ".xyzw" ? "" : sw);
        static const char* f[] = {"", "lessThan", "equal", "lessThanEqual", "greaterThan", "notEqual", "greaterThanEqual", ""};
        return std::string(f[c]) + "(" + r + ", vec4(0.0))";
    }
    bool always() { return !bits(d0, 13, 1) || bits(d0, 10, 3) == 7; }

    std::string mask(bool sca) {
        int base = sca ? 17 : 13;                       // w, z, y, x
        std::string m = ".";
        if (bits(d3, base + 3, 1)) m += 'x';
        if (bits(d3, base + 2, 1)) m += 'y';
        if (bits(d3, base + 1, 1)) m += 'z';
        if (bits(d3, base, 1)) m += 'w';
        return m == ".xyzw" ? "" : m;
    }

    void write(bool sca, std::string value, bool address = false) {
        if (bits(d0, 10, 3) == 0) return;               // condition: never
        std::string m = mask(sca);
        if (m == ".") return;
        if (bits(d0, 26, 1)) value = "clamp(" + value + ", 0.0, 1.0)";
        value = (address ? "ivec4(floor(" : "vec4(") + value + (address ? "))" : ")");
        std::vector<std::string> dsts;
        bool result = sca ? !bits(d0, 30, 1) : bits(d0, 30, 1);
        if (result && bits(d3, 2, 5) != 0x1F) dsts.push_back("o" + std::to_string(bits(d3, 2, 5)));
        uint32_t tmp = sca ? bits(d3, 7, 6) : bits(d0, 15, 6);
        if (tmp != 0x3F) {
            if (address) dsts.push_back("a" + std::to_string(tmp & 1));
            else { temps.insert((int)tmp); dsts.push_back("r" + std::to_string(tmp)); }
        }
        if (bits(d0, 14, 1) || bits(d0, 29, 1) || dsts.empty()) dsts.push_back(cc());
        bool cond = !always();
        for (auto& d : dsts) {
            std::string v = value;
            if (address && d[0] != 'a') v = "vec4(" + value + ")";
            if (cond) v = "mix(" + d + ", " + v + ", " + condition() + ")";
            line(d + m + " = " + v + m + ";");
        }
    }

    void vector_op() {
        auto s = [&](int k) { return source(k); };
        switch (bits(d1, 22, 5)) {
        case V_NOP: return;
        case V_MOV: write(false, s(0)); return;
        case V_MUL: write(false, "(" + s(0) + " * " + s(1) + ")"); return;
        case V_ADD: write(false, "(" + s(0) + " + " + s(2) + ")"); return;
        case V_MAD: write(false, "fma(" + s(0) + ", " + s(1) + ", " + s(2) + ")"); return;
        case V_DP3: write(false, "dot((" + s(0) + ").xyz, (" + s(1) + ").xyz)"); return;
        case V_DPH: write(false, "dot(vec4((" + s(0) + ").xyz, 1.0), " + s(1) + ")"); return;
        case V_DP4: write(false, "dot(" + s(0) + ", " + s(1) + ")"); return;
        case V_DST: write(false, "vec4(1.0, (" + s(0) + ").y * (" + s(1) + ").y, (" + s(0) + ").z, (" + s(1) + ").w)"); return;
        case V_MIN: write(false, "min(" + s(0) + ", " + s(1) + ")"); return;
        case V_MAX: write(false, "max(" + s(0) + ", " + s(1) + ")"); return;
        case V_SLT: write(false, "vec4(lessThan(" + s(0) + ", " + s(1) + "))"); return;
        case V_SGE: write(false, "vec4(greaterThanEqual(" + s(0) + ", " + s(1) + "))"); return;
        case V_SEQ: write(false, "vec4(equal(" + s(0) + ", " + s(1) + "))"); return;
        case V_SGT: write(false, "vec4(greaterThan(" + s(0) + ", " + s(1) + "))"); return;
        case V_SLE: write(false, "vec4(lessThanEqual(" + s(0) + ", " + s(1) + "))"); return;
        case V_SNE: write(false, "vec4(notEqual(" + s(0) + ", " + s(1) + "))"); return;
        case V_SFL: write(false, "vec4(0.0)"); return;
        case V_STR: write(false, "vec4(1.0)"); return;
        case V_SSG: write(false, "sign(" + s(0) + ")"); return;
        case V_FRC: write(false, "fract(" + s(0) + ")"); return;
        case V_FLR: write(false, "floor(" + s(0) + ")"); return;
        case V_ARL: write(false, s(0), true); return;
        case V_TXL: problem("vertex texture fetch"); write(false, "vec4(0.0)"); return;
        default: {
            char b[32];
            std::snprintf(b, sizeof b, "vector opcode %02X", bits(d1, 22, 5));
            problem(b);
            return;
        }
        }
    }

    uint32_t target() { return bits(d0, 23, 1) << 9 | bits(d2, 0, 6) << 3 | bits(d3, 29, 3); }

    void scalar_op(uint32_t pc) {
        std::string s2 = source(2);
        switch (bits(d1, 27, 5)) {
        case S_NOP: return;
        case S_MOV: write(true, s2); return;
        case S_RCP: write(true, "(1.0 / " + s2 + ")"); return;
        case S_RCC: write(true, "clamp(1.0 / " + s2 + ", 5.42101e-20, 1.884467e19)"); return;
        case S_RSQ: write(true, "inversesqrt(max(abs((" + s2 + ").x), 1.0e-38))"); return;
        case S_EXP: write(true, "exp2(" + s2 + ")"); return;
        case S_LOG: write(true, "log2(" + s2 + ")"); return;
        case S_EX2: write(true, "exp2(" + s2 + ")"); return;
        case S_LG2: write(true, "log2(max(" + s2 + ", 1.0e-38))"); return;
        case S_SIN: write(true, "sin(" + s2 + ")"); return;
        case S_COS: write(true, "cos(" + s2 + ")"); return;
        case S_LIT: {
            std::string a = "(" + s2 + ")";
            write(true, "vec4(1.0, max(" + a + ".x, 0.0), (" + a + ".x > 0.0) ? exp2(clamp(" + a + ".w, -128.0, 128.0) * log2(max(" + a +
                            ".y, 1.0e-38))) : 0.0, 1.0)");
            return;
        }
        case S_BRI: case S_BRA: case S_BRB: case S_CAL: case S_CLI: case S_CLB: case S_RET: {
            uint32_t op = bits(d1, 27, 5);
            // a branch tests its condition whether or not the test-enable bit is set
            uint32_t cond = bits(d0, 10, 3);
            std::string c = cond == 7 ? "true" : cond == 0 ? "false" : "any(" + condition() + ")";
            if (op == S_BRB || op == S_CLB) {
                c = std::string("((vp_branch_bits >> ") + std::to_string(bits(d3, 23, 5)) + "u) & 1u) " +
                    (bits(d3, 28, 1) ? "!=" : "==") + " 0u";
            }
            std::string to = std::to_string(target());
            if (op == S_BRA) { problem("BRA"); to = std::to_string(target()); }
            if (op == S_RET) line("if (" + c + ") { if (sp == 0) { pc = -1; continue; } pc = stack[--sp]; continue; }");
            else if (op == S_CAL || op == S_CLI || op == S_CLB)
                line("if (" + c + ") { stack[sp++] = " + std::to_string(pc + 1) + "; pc = " + to + "; continue; }");
            else line("if (" + c + ") { pc = " + to + "; continue; }");
            return;
        }
        default: {
            char b[32];
            std::snprintf(b, sizeof b, "scalar opcode %02X", bits(d1, 27, 5));
            problem(b);
            return;
        }
        }
    }

    bool is_branch(uint32_t sop) { return sop == S_BRA || sop == S_BRI || sop == S_BRB || sop == S_CAL || sop == S_CLI ||
                                          sop == S_CLB || sop == S_RET; }

    void run() {
        // straight code unless something in the reachable stretch branches
        for (uint32_t i = cfg.start; i < n; ++i) {
            load(i);
            if (is_branch(bits(d1, 27, 5))) dispatch = true;
            if (bits(d3, 0, 1) && !dispatch) break;
        }
        // A program that branches is cut into basic blocks, each entered by
        // its first instruction: the start, every branch target, and whatever
        // follows a branch or an ending. A block falls through to the next one
        // within the same pass of the loop; a branch sets pc and starts a pass.
        // Only what the start reaches is translated.
        std::set<uint32_t> leaders = {cfg.start}, reach;
        if (dispatch) {
            std::vector<uint32_t> work = {cfg.start};
            while (!work.empty()) {
                uint32_t i = work.back();
                work.pop_back();
                for (; i < n && reach.insert(i).second; ++i) {
                    load(i);
                    uint32_t sop = bits(d1, 27, 5);
                    if (!valid() || bits(d3, 0, 1)) { leaders.insert(i + 1); break; }
                    if (!is_branch(sop)) continue;
                    leaders.insert(i + 1);
                    if (sop != S_RET && target() < n) { leaders.insert(target()); work.push_back(target()); }
                    if (bits(d0, 10, 3) == 7 && (sop == S_BRA || sop == S_BRI || sop == S_RET)) break;
                }
            }
        }
        bool open = false;
        for (uint32_t i = dispatch ? 0 : cfg.start; i < n; ++i) {
            if (dispatch && !reach.count(i)) continue;
            load(i);
            if (dispatch && leaders.count(i)) {
                if (open) body += "    }\n";
                body += "    if (pc == " + std::to_string(i) + ") {\n";
                open = true;
            }
            bool last = dispatch && leaders.count(i + 1);
            if (!valid()) {
                problem("invalid source type");
                if (!dispatch) break;
                line("pc = -1; continue;");
                continue;
            }
            vector_op();
            scalar_op(i);
            if (bits(d3, 0, 1)) {
                if (!dispatch) break;
                line("pc = -1; continue;");
                continue;
            }
            if (last) line("pc = " + std::to_string(i + 1) + ";");
        }
        if (open) body += "    }\n";
        if (dispatch) body += "    pc = -1;\n";
    }

    bool valid() { return bits(src[0], 0, 2) && bits(src[1], 0, 2) && bits(src[2], 0, 2); }

    std::string build() {
        std::string s = "#version 450\n";
        for (int i : inputs) s += "layout(location = " + std::to_string(i) + ") in vec4 in" + std::to_string(i) + ";\n";
        s += "uniform vec4 vc[468];\nuniform vec4 vp_scale, vp_offset, vp_clip;\nuniform uint vp_branch_bits;\n";
        for (int k = 1; k < 16; ++k) s += "layout(location = " + std::to_string(k) + ") out vec4 vo" + std::to_string(k) + ";\n";
        s += "void main() {\n";
        for (int k = 0; k < 16; ++k) s += "    vec4 o" + std::to_string(k) + " = vec4(0.0, 0.0, 0.0, 1.0);\n";
        for (int t : temps) s += "    vec4 r" + std::to_string(t) + " = vec4(0.0);\n";
        s += "    vec4 cc0 = vec4(0.0), cc1 = vec4(0.0);\n    ivec4 a0 = ivec4(0), a1 = ivec4(0);\n";
        if (dispatch) {
            s += "    int pc = " + std::to_string(cfg.start) + ", sp = 0, guard = 0;\n    int stack[8];\n";
            s += "    while (pc >= 0 && ++guard < 65536) {\n" + body + "    }\n";
        } else {
            s += body;
        }
        // the viewport, then the render target's coordinates
        s += "    vec3 win = o0.xyz * vp_scale.xyz + vp_offset.xyz * o0.w;\n";
        s += "    gl_Position = vec4(win.x * vp_clip.x - o0.w, win.y * vp_clip.y - o0.w, win.z, o0.w);\n";
        for (int k = 1; k < 16; ++k) s += "    vo" + std::to_string(k) + " = o" + std::to_string(k) + ";\n";
        s += "}\n";
        return s;
    }
};
}  // namespace

ProgramText vp_translate(const uint32_t* prog, uint32_t ninstr, const VPConfig& cfg) {
    Gen g(prog, ninstr, cfg);
    g.run();
    g.out.glsl = g.build();
    return g.out;
}
