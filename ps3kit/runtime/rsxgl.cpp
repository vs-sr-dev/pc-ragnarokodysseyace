// ps3kit runtime — the RSX's 3D engine on OpenGL 4.5, on the renderer's
// thread (rsx.h).
//
// It keeps its own copy of the 3D engine's registers from the record and
// does what the hardware does on the writes that act: a clear, a word of
// the vertex program or a vertex constant uploaded. A draw is turned into
// GL state from those registers, a program pair translated from the RSX's
// own (rsxprog.h) and cached, the vertices and textures the record carries,
// and one GL draw.
//
// Render targets live on the host GPU: each colour or depth surface is a
// texture found by its location, offset, size and format, with rows stored
// top first as in RSX memory. The viewport maps the RSX's window rows onto
// those rows directly, so the picture's winding is mirrored and the front
// face is inverted to match.
#include "rsx.h"
#include "gl.h"
#include "rsxprog.h"
#include "rsxtex.h"
#include "rt.h"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <map>
#include <set>
#include <string>
#include <unordered_map>

namespace {
uint32_t reg[0x4000];                   // by method / 4
uint32_t R(uint32_t m) { return reg[m >> 2]; }
float RF(uint32_t m) { float f; std::memcpy(&f, &reg[m >> 2], 4); return f; }

// the transform program memory and constants, as the uploads fill them
constexpr uint32_t kVPSlots = 544;
uint32_t vpmem[kVPSlots * 4];
uint32_t vp_load = 0, vp_word = 0, vp_version = 0;
float vc[468 * 4];
uint32_t vc_load = 0, vc_word = 0;

std::set<std::string> reported;
void report_once(const std::string& s) {
    if (reported.insert(s).second) rt_log("rsxgl: %s", s.c_str());
}

struct Counters { uint64_t draws, clears, programs, textures, skipped_draws; } cnt;

// ---- surfaces ---------------------------------------------------------------------------------
struct Surface { GLuint tex = 0, fbo = 0; int w = 0, h = 0; GLenum fmt = 0; uint64_t version = 0; };   // version: its last write
std::unordered_map<uint64_t, Surface> colors, depths;     // by location << 32 | offset

uint64_t skey(uint32_t dma, uint32_t offset) { return (uint64_t)(dma == 0xFEED0001u) << 32 | offset; }

GLenum color_format(uint32_t f) {
    switch (f & 0x1F) {
    case 3: return GL_RGB565;
    case 9: return GL_R8;
    case 10: return GL_RG8;
    case 11: return GL_RGBA16F;
    case 12: return GL_RGBA32F;
    case 13: return GL_R32F;
    default: return GL_RGBA8;                             // the 5551s, the 8888s
    }
}

void forget_fbos();
void forget_depth_color(GLuint depth);
uint64_t g_surface_writes = 0;

Surface& surface(std::unordered_map<uint64_t, Surface>& m, uint64_t k, int w, int h, GLenum fmt, GLenum attach) {
    Surface& s = m[k];
    if (s.tex && s.w == w && s.h == h && s.fmt == fmt) return s;
    if (s.tex) { forget_depth_color(s.tex); glDeleteTextures(1, &s.tex); glDeleteFramebuffers(1, &s.fbo); forget_fbos(); }
    s = Surface{0, 0, w, h, fmt};
    glCreateTextures(GL_TEXTURE_2D, 1, &s.tex);
    glTextureStorage2D(s.tex, 1, fmt, w, h);
    glCreateFramebuffers(1, &s.fbo);
    glNamedFramebufferTexture(s.fbo, attach, s.tex, 0);
    rt_log("rsxgl: %s surface %s:%X, %dx%d, format %X", attach == GL_COLOR_ATTACHMENT0 ? "colour" : "depth",
           (k >> 32) ? "main" : "local", (uint32_t)k, w, h, fmt);
    return s;
}

int surf_w() { return (int)((R(0x0200) & 0xFFFF) + (R(0x0200) >> 16)); }
int surf_h() { return (int)((R(0x0204) & 0xFFFF) + (R(0x0204) >> 16)); }

// The colour targets the surface registers enable, as indices 0..3 (A..D).
int targets(int out[4]) {
    switch (R(0x0220)) {
    case 0x01: out[0] = 0; return 1;
    case 0x02: out[0] = 1; return 1;
    case 0x13: out[0] = 0; out[1] = 1; return 2;
    case 0x17: out[0] = 0; out[1] = 1; out[2] = 2; return 3;
    case 0x1F: out[0] = 0; out[1] = 1; out[2] = 2; out[3] = 3; return 4;
    default: return 0;
    }
}
uint32_t color_dma(int t) { static const uint32_t m[] = {0x0194, 0x018C, 0x01B4, 0x01B8}; return R(m[t]); }
uint32_t color_offset(int t) { static const uint32_t m[] = {0x0210, 0x0218, 0x0288, 0x028C}; return R(m[t]); }

Surface* color_surface(int t) {
    int w = surf_w(), h = surf_h();
    if (w <= 0 || h <= 0) return nullptr;
    return &surface(colors, skey(color_dma(t), color_offset(t)), w, h, color_format(R(0x0208)), GL_COLOR_ATTACHMENT0);
}
Surface* depth_surface() {
    int w = surf_w(), h = surf_h();
    uint32_t zf = R(0x0208) >> 5 & 7;
    if (w <= 0 || h <= 0 || !zf) return nullptr;
    bool z16 = zf == 1;
    return &surface(depths, skey(R(0x0198), R(0x0214)), w, h, z16 ? GL_DEPTH_COMPONENT16 : GL_DEPTH24_STENCIL8,
                    z16 ? GL_DEPTH_ATTACHMENT : GL_DEPTH_STENCIL_ATTACHMENT);
}

// The scissor within the surface's clip: x, y, w, h.
void scissor_rect(int r[4]) {
    auto span = [](uint32_t clip, uint32_t sc, int& at, int& n) {
        uint32_t cx = clip & 0xFFFF, cw = clip >> 16;
        uint32_t a = std::max(cx, sc & 0xFFFF), b = std::min(cx + cw, (sc & 0xFFFF) + (sc >> 16));
        at = (int)a;
        n = b > a ? (int)(b - a) : 0;
    };
    span(R(0x0200), R(0x08C0), r[0], r[2]);
    span(R(0x0204), R(0x08C4), r[1], r[3]);
}

// CLEAR_SURFACE: the channels the colour mask lets through, inside the scissor.
void clear(uint32_t arg) {
    ++cnt.clears;
    uint32_t mask = arg & 0xF3, cm = R(0x0324);
    if (!(cm & 0x00010000u)) mask &= ~0x10u;
    if (!(cm & 0x00000100u)) mask &= ~0x20u;
    if (!(cm & 0x00000001u)) mask &= ~0x40u;
    if (!(cm & 0x01000000u)) mask &= ~0x80u;
    int r[4];
    scissor_rect(r);
    if (!mask || r[2] <= 0 || r[3] <= 0) return;
    glEnable(GL_SCISSOR_TEST);
    glScissor(r[0], r[1], r[2], r[3]);
    if (mask & 0xF0) {
        uint32_t c = R(0x1D90);
        float col[4] = {(c >> 16 & 0xFF) / 255.0f, (c >> 8 & 0xFF) / 255.0f, (c & 0xFF) / 255.0f, (c >> 24) / 255.0f};
        int t[4], n = targets(t);
        for (int i = 0; i < n; ++i) {
            glColorMaski(0, (mask & 0x10) != 0, (mask & 0x20) != 0, (mask & 0x40) != 0, (mask & 0x80) != 0);
            if (Surface* s = color_surface(t[i])) glClearNamedFramebufferfv(s->fbo, GL_COLOR, 0, col);
        }
        glColorMaski(0, 1, 1, 1, 1);
    }
    if (mask & 3) {
        if (Surface* s = depth_surface()) {
            uint32_t zs = R(0x1D8C);
            bool z16 = s->fmt == GL_DEPTH_COMPONENT16;
            float depth = z16 ? (zs & 0xFFFF) / 65535.0f : (zs >> 8) / 16777215.0f;
            glDepthMask(mask & 1);
            glStencilMask((mask & 2) ? 0xFF : 0);
            s->version = ++g_surface_writes;
            if (z16) glClearNamedFramebufferfv(s->fbo, GL_DEPTH, 0, &depth);
            else glClearNamedFramebufferfi(s->fbo, GL_DEPTH_STENCIL, 0, depth, (GLint)(zs & 0xFF));
            glDepthMask(1);
            glStencilMask(0xFF);
        }
    }
    glDisable(GL_SCISSOR_TEST);
}

// A register write, and what it does on the 3D engine.
void write(uint32_t m, uint32_t v) {
    reg[m >> 2] = v;
    if (m >= 0x0B80 && m < 0x0C00) {                                    // NV4097_SET_TRANSFORM_PROGRAM
        if (vp_load < kVPSlots) vpmem[vp_load * 4 + vp_word] = v;
        if (++vp_word == 4) { vp_word = 0; ++vp_load; }
        ++vp_version;
        return;
    }
    if (m >= 0x1F00 && m < 0x1F80) {                                    // NV4097_SET_TRANSFORM_CONSTANT
        if (vc_load < 468) std::memcpy(&vc[vc_load * 4 + vc_word], &v, 4);
        if (++vc_word == 4) { vc_word = 0; ++vc_load; }
        return;
    }
    switch (m) {
    case 0x1E9C: vp_load = v; vp_word = 0; return;                      // NV4097_SET_TRANSFORM_PROGRAM_LOAD
    case 0x1EFC: vc_load = v; vc_word = 0; return;                      // NV4097_SET_TRANSFORM_CONSTANT_LOAD
    case 0x1D94: clear(v); return;                                      // NV4097_CLEAR_SURFACE
    default: return;
    }
}

uint64_t fnv(const void* p, size_t n, uint64_t h = 0xCBF29CE484222325ull) {
    const uint8_t* b = (const uint8_t*)p;
    for (size_t i = 0; i < n; ++i) h = (h ^ b[i]) * 0x100000001B3ull;
    return h;
}

// ---- programs ---------------------------------------------------------------------------------
struct Program {
    GLuint prog = 0;
    GLint vc, vp_scale, vp_offset, vp_clip, vp_branch, fc, wpos, alpha, alpha_ref;
    std::vector<uint32_t> literals;
    bool ok = false;
};
std::unordered_map<uint64_t, Program> programs;
uint64_t vp_hash_version = ~0ull, vp_hash = 0;

GLuint compile(GLenum type, const std::string& src, const char* what) {
    GLuint sh = glCreateShader(type);
    const char* p = src.c_str();
    glShaderSource(sh, 1, &p, nullptr);
    glCompileShader(sh);
    GLint ok = 0;
    glGetShaderiv(sh, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetShaderInfoLog(sh, sizeof log, nullptr, log);
        rt_log("rsxgl: %s program does not compile:\n%s\n%s", what, log, src.c_str());
        glDeleteShader(sh);
        return 0;
    }
    return sh;
}

const bool g_dump = std::getenv("PS3KIT_SHADERDUMP") != nullptr;

Program& program(const uint32_t* fp, uint32_t fp_words, const FPConfig& fc) {
    if (vp_hash_version != vp_version) { vp_hash = fnv(vpmem, sizeof vpmem); vp_hash_version = vp_version; }
    // the fragment program's key leaves its constants out: they are uniforms
    std::vector<uint32_t> code(fp, fp + fp_words);
    for (uint32_t at : fp_literal_words(fp, fp_words)) for (int k = 0; k < 4 && at + k < code.size(); ++k) code[at + k] = 0;
    uint32_t start = R(0x1EA0);
    uint64_t key = fnv(code.data(), code.size() * 4, fnv(&fc, sizeof fc, vp_hash ^ start));
    auto it = programs.find(key);
    if (it != programs.end()) return it->second;
    Program& p = programs[key];
    ++cnt.programs;
    ProgramText ft = fp_translate(fp, fp_words, fc);
    VPConfig vcfg;
    vcfg.start = start;
    ProgramText vt = vp_translate(vpmem, kVPSlots, vcfg);
    for (auto& q : vt.problems) report_once("vertex program: " + q);
    for (auto& q : ft.problems) report_once("fragment program: " + q);
    if (g_dump) rt_log("rsxgl: program %016llX\n--- vertex\n%s--- fragment\n%s", (unsigned long long)key, vt.glsl.c_str(),
                       ft.glsl.c_str());
    GLuint vs = compile(GL_VERTEX_SHADER, vt.glsl, "vertex"), fs = compile(GL_FRAGMENT_SHADER, ft.glsl, "fragment");
    if (!vs || !fs) return p;
    p.prog = glCreateProgram();
    glAttachShader(p.prog, vs);
    glAttachShader(p.prog, fs);
    glLinkProgram(p.prog);
    glDeleteShader(vs);
    glDeleteShader(fs);
    GLint ok = 0;
    glGetProgramiv(p.prog, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetProgramInfoLog(p.prog, sizeof log, nullptr, log);
        rt_log("rsxgl: programs do not link: %s", log);
        return p;
    }
    p.vc = glGetUniformLocation(p.prog, "vc");
    p.vp_scale = glGetUniformLocation(p.prog, "vp_scale");
    p.vp_offset = glGetUniformLocation(p.prog, "vp_offset");
    p.vp_clip = glGetUniformLocation(p.prog, "vp_clip");
    p.vp_branch = glGetUniformLocation(p.prog, "vp_branch_bits");
    p.fc = glGetUniformLocation(p.prog, "fc");
    p.wpos = glGetUniformLocation(p.prog, "fp_wpos");
    p.alpha = glGetUniformLocation(p.prog, "fp_alpha");
    p.alpha_ref = glGetUniformLocation(p.prog, "fp_alpha_ref");
    p.literals = ft.literals;
    p.ok = true;
    return p;
}

// ---- textures ---------------------------------------------------------------------------------
struct Texture { GLuint tex = 0; GLenum target = 0; GLenum src[4]; };   // src: the GL channel holding A, R, G, B
std::unordered_map<uint64_t, Texture> textures;
GLuint samplers[16];

uint32_t log2up(uint32_t v) { uint32_t l = 0; while ((1u << l) < v) ++l; return l; }

// The texel at (x, y) of a swizzled level: x and y's bits interleaved, x first,
// over the smaller dimension, then the larger one's remaining bits.
uint32_t swizzle(uint32_t x, uint32_t y, uint32_t lw, uint32_t lh) {
    uint32_t off = 0, s = 0, lmin = std::min(lw, lh);
    for (uint32_t i = 0; i < lmin; ++i) {
        off |= ((x >> i) & 1) << s++;
        off |= ((y >> i) & 1) << s++;
    }
    off |= (lw > lh ? x >> lmin : y >> lmin) << s;
    return off;
}

struct GLFmt { GLenum internal, format, type; uint32_t swap; GLenum src[4]; bool compressed; };
GLFmt gl_format(uint32_t base) {
    switch (base) {
    case 0x85: case 0x9E: return {GL_RGBA8, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8, 0, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, false};
    case 0x84: return {GL_RGB565, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, 2, {GL_ONE, GL_RED, GL_GREEN, GL_BLUE}, false};
    case 0x82: case 0x9D: return {GL_RGB5_A1, GL_BGRA, GL_UNSIGNED_SHORT_1_5_5_5_REV, 2, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, false};
    case 0x83: return {GL_RGBA4, GL_BGRA, GL_UNSIGNED_SHORT_4_4_4_4_REV, 2, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, false};
    case 0x97: return {GL_RGB5_A1, GL_RGBA, GL_UNSIGNED_SHORT_5_5_5_1, 2, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, false};
    case 0x81: return {GL_R8, GL_RED, GL_UNSIGNED_BYTE, 0, {GL_RED, GL_RED, GL_RED, GL_RED}, false};
    case 0x8B: return {GL_RG8, GL_RG, GL_UNSIGNED_BYTE, 0, {GL_RED, GL_GREEN, GL_RED, GL_GREEN}, false};
    case 0x94: return {GL_R16, GL_RED, GL_UNSIGNED_SHORT, 2, {GL_ONE, GL_RED, GL_RED, GL_RED}, false};
    case 0x95: return {GL_RG16, GL_RG, GL_UNSIGNED_SHORT, 2, {GL_ONE, GL_RED, GL_GREEN, GL_ZERO}, false};
    case 0x9F: return {GL_RG16F, GL_RG, GL_HALF_FLOAT, 2, {GL_ONE, GL_RED, GL_GREEN, GL_ZERO}, false};
    case 0x9A: return {GL_RGBA16F, GL_RGBA, GL_HALF_FLOAT, 2, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, false};
    case 0x9B: return {GL_RGBA32F, GL_RGBA, GL_FLOAT, 4, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, false};
    case 0x9C: return {GL_R32F, GL_RED, GL_FLOAT, 4, {GL_ONE, GL_RED, GL_RED, GL_RED}, false};
    case 0x86: return {0x83F1, 0, 0, 0, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, true};   // COMPRESSED_RGBA_S3TC_DXT1
    case 0x87: return {0x83F2, 0, 0, 0, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, true};   // DXT3
    case 0x88: return {0x83F3, 0, 0, 0, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, true};   // DXT5
    default: return {0, 0, 0, 0, {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE}, false};   // not a format the renderer knows
    }
}

// PS3KIT_TEXDUMP=DIR: every texture as it is first decoded, level 0, with its remap applied, as a PNG.
const char* g_texdump = std::getenv("PS3KIT_TEXDUMP");

void dump_texture(const Texture& x, const RsxTexture& t, const TexLayout& l) {
    std::vector<uint8_t> gl((size_t)l.w * l.h * 4), px(gl.size());
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glGetTextureImage(x.tex, 0, GL_RGBA, GL_UNSIGNED_BYTE, (GLsizei)gl.size(), gl.data());
    auto pick = [&](const uint8_t* p, GLenum c) -> uint8_t {
        switch (c) {
        case GL_RED: return p[0];
        case GL_GREEN: return p[1];
        case GL_BLUE: return p[2];
        case GL_ALPHA: return p[3];
        case GL_ONE: return 255;
        default: return 0;
        }
    };
    uint32_t remap = t.regs[4];
    static const int to_rgba[4] = {3, 0, 1, 2};                 // A R G B into RGBA
    for (size_t i = 0; i < (size_t)l.w * l.h; ++i)
        for (int c = 0; c < 4; ++c) {
            uint32_t ctl = remap >> (8 + 2 * c) & 3, from = remap >> (2 * c) & 3;
            px[i * 4 + to_rgba[c]] = ctl == 0 ? 0 : ctl == 1 ? 255 : pick(&gl[i * 4], x.src[from]);
        }
    char name[64];
    std::snprintf(name, sizeof name, "/tex_%016llX_%02X.png", (unsigned long long)t.key, l.base);
    std::filesystem::create_directories(g_texdump);
    write_png(std::string(g_texdump) + name, (int)l.w, (int)l.h, px, 4);
}

Texture& texture(const RsxTexture& t, const uint8_t* data) {
    auto it = textures.find(t.key);
    if (it != textures.end() || !t.bytes) return textures[t.key];
    Texture& x = textures[t.key];
    ++cnt.textures;
    TexLayout l = tex_layout(t.regs[1], t.regs[6], t.control3);
    GLFmt f = gl_format(l.base);
    char what[64];
    std::snprintf(what, sizeof what, "texture format %02X%s%s", l.base, l.linear ? " linear" : "", l.cube ? " cube" : "");
    report_once(what);
    if (l.unnormalized) report_once("unnormalised texture coordinates");
    // A format the renderer does not know, or rows longer than their pitch:
    // reported with the unit's registers, and the unit left without an image.
    if (!f.internal || (l.linear && !f.compressed && l.pitch && l.pitch < l.w * l.bpp)) {
        char bad[160];
        std::snprintf(bad, sizeof bad, "%s not drawn: offset %08X format %08X rect %08X control3 %08X",
                      what, t.regs[0], t.regs[1], t.regs[6], t.control3);
        report_once(bad);
        return x;
    }
    x.target = l.cube ? GL_TEXTURE_CUBE_MAP : l.dims == 3 ? GL_TEXTURE_3D : l.dims == 1 ? GL_TEXTURE_1D : GL_TEXTURE_2D;
    std::memcpy(x.src, f.src, sizeof x.src);
    glCreateTextures(x.target, 1, &x.tex);
    if (x.target == GL_TEXTURE_1D) glTextureStorage1D(x.tex, l.levels, f.internal, l.w);
    else if (x.target == GL_TEXTURE_3D) glTextureStorage3D(x.tex, l.levels, f.internal, l.w, l.h, l.d);
    else glTextureStorage2D(x.tex, l.levels, f.internal, l.w, l.h);
    glTextureParameteri(x.tex, GL_TEXTURE_MAX_LEVEL, (GLint)l.levels - 1);
    std::vector<uint8_t> buf;
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    for (uint32_t face = 0; face < (l.cube ? 6u : 1u); ++face) {
        for (uint32_t lv = 0; lv < l.levels; ++lv) {
            uint32_t lw = std::max(l.w >> lv, 1u), lh = std::max(l.h >> lv, 1u);
            uint32_t ld = l.dims == 3 ? std::max(l.d >> lv, 1u) : 1;
            const uint8_t* src = data + face * l.face_bytes + l.level_offset[lv];
            if (f.compressed) {
                if (x.target == GL_TEXTURE_CUBE_MAP)
                    glCompressedTextureSubImage3D(x.tex, lv, 0, 0, face, lw, lh, 1, f.internal, l.level_bytes[lv], src);
                else glCompressedTextureSubImage2D(x.tex, lv, 0, 0, lw, lh, f.internal, l.level_bytes[lv], src);
                continue;
            }
            // to rows, top first, host order
            uint32_t row = lw * l.bpp;
            buf.resize((size_t)row * lh * ld);
            if (l.linear) {
                uint32_t pitch = l.pitch ? l.pitch : row;
                for (uint32_t z = 0; z < ld; ++z)
                    for (uint32_t y = 0; y < lh; ++y)
                        std::memcpy(&buf[((size_t)z * lh + y) * row], src + ((size_t)z * lh + y) * pitch, row);
            } else {
                uint32_t a = log2up(lw), b = log2up(lh);
                for (uint32_t z = 0; z < ld; ++z)
                    for (uint32_t y = 0; y < lh; ++y)
                        for (uint32_t xx = 0; xx < lw; ++xx)
                            std::memcpy(&buf[(((size_t)z * lh + y) * lw + xx) * l.bpp],
                                        src + ((size_t)z * lw * lh + swizzle(xx, y, a, b)) * l.bpp, l.bpp);
            }
            if (f.swap == 2) for (size_t i = 0; i + 1 < buf.size(); i += 2) std::swap(buf[i], buf[i + 1]);
            if (f.swap == 4) for (size_t i = 0; i + 3 < buf.size(); i += 4) { std::swap(buf[i], buf[i + 3]); std::swap(buf[i + 1], buf[i + 2]); }
            if (x.target == GL_TEXTURE_1D) glTextureSubImage1D(x.tex, lv, 0, lw, f.format, f.type, buf.data());
            else if (x.target == GL_TEXTURE_3D) glTextureSubImage3D(x.tex, lv, 0, 0, 0, lw, lh, ld, f.format, f.type, buf.data());
            else if (x.target == GL_TEXTURE_CUBE_MAP)
                glTextureSubImage3D(x.tex, lv, 0, 0, face, lw, lh, 1, f.format, f.type, buf.data());
            else glTextureSubImage2D(x.tex, lv, 0, 0, lw, lh, f.format, f.type, buf.data());
        }
    }
    if (g_texdump && x.target == GL_TEXTURE_2D) dump_texture(x, t, l);
    return x;
}

GLenum wrap(uint32_t w) {
    switch (w) {
    case 1: return GL_REPEAT;
    case 2: return GL_MIRRORED_REPEAT;
    case 4: return GL_CLAMP_TO_BORDER;
    case 6: case 7: case 8: return GL_MIRROR_CLAMP_TO_EDGE;
    default: return GL_CLAMP_TO_EDGE;
    }
}

// A D24S8 surface as the RSX reads it through an A8R8G8B8 texture: each texel
// the word depth << 8 | stencil, so A, R and G are the depth's bytes from the
// top and B is the stencil. Made on the GPU from the surface, again only when
// the surface has been written since.
struct DepthColor { GLuint view = 0, tex = 0; uint64_t version = ~0ull; };
std::unordered_map<GLuint, DepthColor> depth_colors;              // by the depth surface's texture
GLuint depth_color_prog = 0;

void forget_depth_color(GLuint depth) {
    auto it = depth_colors.find(depth);
    if (it == depth_colors.end()) return;
    glDeleteTextures(1, &it->second.view);
    glDeleteTextures(1, &it->second.tex);
    depth_colors.erase(it);
}

GLuint depth_color(Surface& s) {
    if (!depth_color_prog) {
        static const char* src =
            "#version 450\n"
            "layout(local_size_x = 8, local_size_y = 8) in;\n"
            "layout(binding = 30) uniform sampler2D depth;\n"
            "layout(binding = 31) uniform usampler2D stencil;\n"
            "layout(binding = 0, rgba8) writeonly uniform image2D outimg;\n"
            "void main() {\n"
            "    ivec2 p = ivec2(gl_GlobalInvocationID.xy);\n"
            "    if (any(greaterThanEqual(p, imageSize(outimg)))) return;\n"
            "    uint d = uint(round(texelFetch(depth, p, 0).r * 16777215.0)), st = texelFetch(stencil, p, 0).r;\n"
            "    imageStore(outimg, p, vec4(float(d >> 8 & 255u), float(d & 255u), float(st & 255u), float(d >> 16 & 255u)) / 255.0);\n"
            "}\n";
        GLuint cs = compile(GL_COMPUTE_SHADER, src, "depth conversion");
        if (!cs) return 0;
        depth_color_prog = glCreateProgram();
        glAttachShader(depth_color_prog, cs);
        glLinkProgram(depth_color_prog);
        glDeleteShader(cs);
    }
    DepthColor& c = depth_colors[s.tex];
    if (!c.tex) {
        glCreateTextures(GL_TEXTURE_2D, 1, &c.tex);
        glTextureStorage2D(c.tex, 1, GL_RGBA8, s.w, s.h);
        glGenTextures(1, &c.view);
        glTextureView(c.view, GL_TEXTURE_2D, s.tex, GL_DEPTH24_STENCIL8, 0, 1, 0, 1);
        glTextureParameteri(c.view, GL_DEPTH_STENCIL_TEXTURE_MODE, GL_STENCIL_INDEX);
    }
    if (c.version == s.version) return c.tex;
    c.version = s.version;
    glUseProgram(depth_color_prog);
    glBindTextureUnit(30, s.tex);
    glBindSampler(30, 0);
    glBindTextureUnit(31, c.view);
    glBindSampler(31, 0);
    glBindImageTexture(0, c.tex, 0, GL_FALSE, 0, GL_WRITE_ONLY, GL_RGBA8);
    glDispatchCompute((GLuint)(s.w + 7) / 8, (GLuint)(s.h + 7) / 8, 1);
    glMemoryBarrier(GL_TEXTURE_FETCH_BARRIER_BIT);
    glBindTextureUnit(30, 0);
    glBindTextureUnit(31, 0);
    return c.tex;
}

// Binds a texture unit as the registers describe it: the image, the remap
// of its channels, and the sampler.
void bind_texture(const RsxTexture& t, const uint8_t* data, uint32_t& dims) {
    uint32_t u = t.unit;
    TexLayout l = tex_layout(t.regs[1], t.regs[6], t.control3);
    GLuint name = 0;
    GLenum src[4] = {GL_ALPHA, GL_RED, GL_GREEN, GL_BLUE};
    // a render target the game samples is sampled on the GPU (the capture side decided which)
    if (t.target == 1) {
        auto sit = colors.find((uint64_t)((t.regs[1] & 3) == 2) << 32 | t.regs[0]);
        if (sit == colors.end()) { report_once("a sampled render target the renderer never made"); return; }
        name = sit->second.tex;
        dims |= 1u << (2 * u);
    } else if (t.target == 2) {
        auto sit = depths.find((uint64_t)((t.regs[1] & 3) == 2) << 32 | t.regs[0]);
        if (sit == depths.end() || sit->second.fmt != GL_DEPTH24_STENCIL8) {
            report_once("a sampled depth surface the renderer never made as D24S8");
            return;
        }
        name = depth_color(sit->second);
        if (!name) return;
        dims |= 1u << (2 * u);
    } else {
        Texture& x = texture(t, data);
        if (!x.tex) return;
        name = x.tex;
        std::memcpy(src, x.src, sizeof src);
        uint32_t d = x.target == GL_TEXTURE_1D ? 0 : x.target == GL_TEXTURE_3D ? 2 : x.target == GL_TEXTURE_CUBE_MAP ? 3 : 1;
        dims |= d << (2 * u);
    }
    // the remap (NV4097_SET_TEXTURE_CONTROL1): for each of A, R, G, B a source channel, or 0, or 1
    uint32_t remap = t.regs[4];
    GLenum out[4];
    for (int c = 0; c < 4; ++c) {
        uint32_t ctl = remap >> (8 + 2 * c) & 3, from = remap >> (2 * c) & 3;
        out[c] = ctl == 0 ? GL_ZERO : ctl == 1 ? GL_ONE : src[from];
    }
    glTextureParameteri(name, GL_TEXTURE_SWIZZLE_A, (GLint)out[0]);
    glTextureParameteri(name, GL_TEXTURE_SWIZZLE_R, (GLint)out[1]);
    glTextureParameteri(name, GL_TEXTURE_SWIZZLE_G, (GLint)out[2]);
    glTextureParameteri(name, GL_TEXTURE_SWIZZLE_B, (GLint)out[3]);
    glBindTextureUnit(u, name);
    GLuint s = samplers[u];
    uint32_t addr = t.regs[2], filter = t.regs[5], ctl0 = t.regs[3];
    glSamplerParameteri(s, GL_TEXTURE_WRAP_S, (GLint)wrap(addr & 0xF));
    glSamplerParameteri(s, GL_TEXTURE_WRAP_T, (GLint)wrap(addr >> 8 & 0xF));
    glSamplerParameteri(s, GL_TEXTURE_WRAP_R, (GLint)wrap(addr >> 16 & 0xF));
    static const GLenum mins[] = {GL_NEAREST, GL_NEAREST, GL_LINEAR, GL_NEAREST_MIPMAP_NEAREST, GL_LINEAR_MIPMAP_NEAREST,
                                  GL_NEAREST_MIPMAP_LINEAR, GL_LINEAR_MIPMAP_LINEAR, GL_LINEAR};
    uint32_t mn = filter >> 16 & 0xFF, mg = filter >> 24 & 7;
    glSamplerParameteri(s, GL_TEXTURE_MIN_FILTER, (GLint)(mn < 8 ? mins[mn] : GL_LINEAR));
    glSamplerParameteri(s, GL_TEXTURE_MAG_FILTER, mg == 1 ? GL_NEAREST : GL_LINEAR);
    glSamplerParameterf(s, GL_TEXTURE_MIN_LOD, (ctl0 >> 19 & 0xFFF) / 256.0f);
    glSamplerParameterf(s, GL_TEXTURE_MAX_LOD, (ctl0 >> 7 & 0xFFF) / 256.0f);
    uint32_t bc = t.regs[7];
    float border[4] = {(bc >> 16 & 0xFF) / 255.0f, (bc >> 8 & 0xFF) / 255.0f, (bc & 0xFF) / 255.0f, (bc >> 24) / 255.0f};
    glSamplerParameterfv(s, GL_TEXTURE_BORDER_COLOR, border);
    glBindSampler(u, s);
}

// ---- draws ------------------------------------------------------------------------------------
GLuint vao = 0, vbo = 0, ibo = 0;
constexpr size_t kRing = 64u << 20;
size_t vbo_at = 0, ibo_at = 0;
std::map<std::vector<GLuint>, GLuint> fbos;            // the draw framebuffers, by their attachments
void forget_fbos() {
    for (auto& [k, f] : fbos) glDeleteFramebuffers(1, &f);
    fbos.clear();
}

size_t ring(GLuint buf, size_t& at, const void* data, size_t n) {
    n = (n + 15) & ~(size_t)15;
    if (at + n > kRing) { glInvalidateBufferData(buf); at = 0; }
    size_t o = at;
    glNamedBufferSubData(buf, (GLintptr)o, (GLsizeiptr)n, data);
    at += n;
    return o;
}

GLenum gl_prim(uint32_t p) {
    static const GLenum m[] = {GL_POINTS, GL_POINTS, GL_LINES, GL_LINE_LOOP, GL_LINE_STRIP, GL_TRIANGLES,
                               GL_TRIANGLE_STRIP, GL_TRIANGLE_FAN, GL_TRIANGLES, GL_TRIANGLE_STRIP, GL_TRIANGLE_FAN};
    return p <= 10 ? m[p] : GL_POINTS;
}

// Quads as two triangles each: the indices of a list of vertices.
void quads(std::vector<uint32_t>& out, const uint32_t* v, size_t n) {
    for (size_t q = 0; q + 3 < n; q += 4) {
        uint32_t a = v[q], b = v[q + 1], c = v[q + 2], d = v[q + 3];
        out.insert(out.end(), {a, b, c, a, c, d});
    }
}

void set_state() {
    // blending
    bool blend = R(0x0310) & 1;
    uint32_t mrt = R(0x036C);
    for (int i = 0; i < 4; ++i) {
        bool on = i == 0 ? blend : (mrt >> i) & 1;
        if (on) glEnablei(GL_BLEND, i); else glDisablei(GL_BLEND, i);
    }
    uint32_t sf = R(0x0314), df = R(0x0318), eq = R(0x0320);
    auto factor = [](uint32_t f) { return f ? (GLenum)f : GL_ZERO; };
    auto equation = [](uint32_t e) { return e >= 0x8006 && e <= 0x800B ? (GLenum)e : GL_FUNC_ADD; };
    glBlendFuncSeparate(factor(sf & 0xFFFF), factor(df & 0xFFFF), factor(sf >> 16), factor(df >> 16));
    glBlendEquationSeparate(equation(eq & 0xFFFF), equation(eq >> 16));
    uint32_t bc = R(0x031C);
    glBlendColor((bc >> 16 & 0xFF) / 255.0f, (bc >> 8 & 0xFF) / 255.0f, (bc & 0xFF) / 255.0f, (bc >> 24) / 255.0f);
    // colour masks
    uint32_t cm = R(0x0324), cmm = R(0x0370);
    glColorMaski(0, (cm & 0x00010000u) != 0, (cm & 0x00000100u) != 0, (cm & 0x00000001u) != 0, (cm & 0x01000000u) != 0);
    for (int i = 1; i < 4; ++i) {
        uint32_t b = cmm >> (4 * i);
        glColorMaski(i, (b & 2) != 0, (b & 4) != 0, (b & 8) != 0, (b & 1) != 0);
    }
    // depth and stencil
    if (R(0x0A74) & 1) glEnable(GL_DEPTH_TEST); else glDisable(GL_DEPTH_TEST);
    glDepthFunc(R(0x0A6C) >= 0x200 && R(0x0A6C) <= 0x207 ? R(0x0A6C) : GL_LESS);
    glDepthMask((R(0x0A70) & 1) != 0);
    if (R(0x0328) & 1) glEnable(GL_STENCIL_TEST); else glDisable(GL_STENCIL_TEST);
    auto sop = [](uint32_t o) { return o ? (GLenum)o : GL_ZERO; };
    bool two = R(0x0348) & 1;
    glStencilFuncSeparate(GL_FRONT, R(0x0330) ? R(0x0330) : GL_ALWAYS, (GLint)(R(0x0334) & 0xFF), R(0x0338) & 0xFF);
    glStencilOpSeparate(GL_FRONT, sop(R(0x033C)), sop(R(0x0340)), sop(R(0x0344)));
    glStencilMaskSeparate(GL_FRONT, R(0x032C) & 0xFF);
    uint32_t bfunc = two ? 0x0350 : 0x0330, bref = two ? 0x0354 : 0x0334, bmask = two ? 0x0358 : 0x0338;
    glStencilFuncSeparate(GL_BACK, R(bfunc) ? R(bfunc) : GL_ALWAYS, (GLint)(R(bref) & 0xFF), R(bmask) & 0xFF);
    glStencilOpSeparate(GL_BACK, sop(R(two ? 0x035C : 0x033C)), sop(R(two ? 0x0360 : 0x0340)), sop(R(two ? 0x0364 : 0x0344)));
    glStencilMaskSeparate(GL_BACK, R(two ? 0x034C : 0x032C) & 0xFF);
    // culling: the rows are mirrored, so the front face is the other winding
    if (R(0x183C) & 1) glEnable(GL_CULL_FACE); else glDisable(GL_CULL_FACE);
    uint32_t cf = R(0x1830);
    glCullFace(cf == 0x404 || cf == 0x405 || cf == 0x408 ? cf : GL_BACK);
    glFrontFace(R(0x1834) == 0x900 ? GL_CCW : GL_CW);
    // logic op
    if (R(0x0374) & 1) { glEnable(GL_COLOR_LOGIC_OP); glLogicOp(R(0x0378)); } else glDisable(GL_COLOR_LOGIC_OP);
    // scissor
    int r[4];
    scissor_rect(r);
    glEnable(GL_SCISSOR_TEST);
    glScissor(r[0], r[1], std::max(r[2], 0), std::max(r[3], 0));
}

// PS3KIT_DRAWDUMP=N: the Nth draw's vertices, the constants its programs see and its state.
const uint64_t g_drawdump = std::getenv("PS3KIT_DRAWDUMP") ? std::strtoull(std::getenv("PS3KIT_DRAWDUMP"), nullptr, 0) : 0;
// PS3KIT_GLSYNC=N: from draw N on, each draw is reported and waited for, so
// that a draw which brings the driver down is the last one reported.
const uint64_t g_glsync = std::getenv("PS3KIT_GLSYNC") ? std::strtoull(std::getenv("PS3KIT_GLSYNC"), nullptr, 0) : 0;

template <typename F>
void dump_draw(const RsxDraw& d, size_t nattrs, F attr, const std::vector<uint32_t>& fp, size_t ntex) {
    rt_log("rsxgl: draw %llu: primitive %u, %s %u, base %u, %u vertices, %zu attributes, %u fp words, %zu textures",
           (unsigned long long)cnt.draws, d.prim, d.indexed ? "indices" : "ranges", d.count, d.base, d.vertices, nattrs,
           d.fp_words, ntex);
    for (size_t i = 0; i < nattrs; ++i) {
        uint32_t idx, fmt;
        const uint8_t* data;
        attr(i, idx, fmt, data);
        uint32_t type = fmt & 0xF, size = fmt >> 4 & 0xF, stride = fmt >> 8 & 0xFF;
        for (uint32_t v = 0; v < std::min(d.vertices, 6u); ++v) {
            std::string s;
            for (uint32_t c = 0; c < size; ++c) {
                char b[32];
                const uint8_t* e = data + v * stride;
                if (type == 2) { float f; std::memcpy(&f, e + 4 * c, 4); std::snprintf(b, sizeof b, " %g", f); }
                else if (type == 4 || type == 7) std::snprintf(b, sizeof b, " %u", e[c]);
                else { int16_t h; std::memcpy(&h, e + 2 * c, 2); std::snprintf(b, sizeof b, " %d", h); }
                s += b;
            }
            rt_log("  in%u[%u]:%s", idx, v, s.c_str());
        }
    }
    for (uint32_t i = 256; i < 272; ++i) rt_log("  vc[%u] = %g %g %g %g", i, vc[i * 4], vc[i * 4 + 1], vc[i * 4 + 2], vc[i * 4 + 3]);
    for (uint32_t i = 460; i < 468; ++i) rt_log("  vc[%u] = %g %g %g %g", i, vc[i * 4], vc[i * 4 + 1], vc[i * 4 + 2], vc[i * 4 + 3]);
    std::vector<uint32_t> lit = fp_literal_words(fp.data(), (uint32_t)fp.size());
    for (size_t i = 0; i < lit.size(); ++i) {
        float f[4];
        std::memcpy(f, &fp[lit[i]], 16);
        rt_log("  fc[%zu] = %g %g %g %g", i, f[0], f[1], f[2], f[3]);
    }
    rt_log("  viewport scale %g %g %g offset %g %g %g, clip %08X %08X, scissor %08X %08X, window %08X", RF(0x0A30), RF(0x0A34),
           RF(0x0A38), RF(0x0A20), RF(0x0A24), RF(0x0A28), R(0x0200), R(0x0204), R(0x08C0), R(0x08C4), R(0x1D88));
    rt_log("  blend %X %08X %08X %08X, colour mask %08X, depth %X func %X mask %X, cull %X face %X front %X, alpha test %X %X %X, "
           "shader control %08X", R(0x0310), R(0x0314), R(0x0318), R(0x0320), R(0x0324), R(0x0A74), R(0x0A6C), R(0x0A70),
           R(0x183C), R(0x1830), R(0x1834), R(0x0304), R(0x0308), R(0x030C), R(0x1D60));
}

void draw(const uint8_t*& p) {
    RsxDraw d;
    std::memcpy(&d, p, sizeof d);
    p += sizeof d;
    std::vector<std::pair<uint32_t, uint32_t>> ranges;
    std::vector<uint32_t> indices;
    if (d.indexed) { indices.resize(d.count); std::memcpy(indices.data(), p, d.count * 4); p += d.count * 4; }
    else for (uint32_t i = 0; i < d.count; ++i) {
        uint32_t f, n;
        std::memcpy(&f, p, 4); std::memcpy(&n, p + 4, 4);
        p += 8;
        ranges.push_back({f, n});
    }
    struct Attr { uint32_t index, format, bytes; const uint8_t* data; };
    std::vector<Attr> attrs(d.attrs);
    for (auto& a : attrs) {
        std::memcpy(&a.index, p, 4); std::memcpy(&a.format, p + 4, 4); std::memcpy(&a.bytes, p + 8, 4);
        a.data = p + 12;
        p += 12 + a.bytes;
    }
    const uint32_t* fp = reinterpret_cast<const uint32_t*>(p);
    std::vector<uint32_t> fpw(d.fp_words);
    std::memcpy(fpw.data(), p, d.fp_words * 4);
    p += d.fp_words * 4;
    (void)fp;
    struct Tex { RsxTexture t; const uint8_t* data; };
    std::vector<Tex> texs(d.textures);
    for (auto& t : texs) { std::memcpy(&t.t, p, sizeof t.t); t.data = p + sizeof t.t; p += sizeof t.t + t.t.bytes; }

    ++cnt.draws;
    if (g_drawdump && cnt.draws == g_drawdump) dump_draw(d, attrs.size(), [&](size_t i, uint32_t& idx, uint32_t& fmt,
                                                                                 const uint8_t*& data) {
        idx = attrs[i].index; fmt = attrs[i].format; data = attrs[i].data;
    }, fpw, texs.size());
    if (!d.fp_words || !d.vertices) { ++cnt.skipped_draws; return; }

    // the render targets
    int t[4], nt = targets(t);
    std::vector<GLuint> key;
    std::vector<Surface*> cs;
    for (int i = 0; i < nt; ++i) if (Surface* s = color_surface(t[i])) { cs.push_back(s); key.push_back(s->tex); }
    Surface* ds = depth_surface();
    if (ds) ds->version = ++g_surface_writes;
    key.push_back(ds ? ds->tex : 0);
    GLuint& fbo = fbos[key];
    if (!fbo) {
        glCreateFramebuffers(1, &fbo);
        GLenum bufs[4];
        for (size_t i = 0; i < cs.size(); ++i) {
            glNamedFramebufferTexture(fbo, GL_COLOR_ATTACHMENT0 + (GLenum)i, cs[i]->tex, 0);
            bufs[i] = GL_COLOR_ATTACHMENT0 + (GLenum)i;
        }
        glNamedFramebufferDrawBuffers(fbo, (GLsizei)cs.size(), bufs);
        if (ds) glNamedFramebufferTexture(fbo, ds->fmt == GL_DEPTH_COMPONENT16 ? GL_DEPTH_ATTACHMENT : GL_DEPTH_STENCIL_ATTACHMENT,
                                          ds->tex, 0);
    }
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, fbo);
    int cw = (int)(R(0x0200) >> 16), ch = (int)(R(0x0204) >> 16);
    glViewport(0, 0, cw, ch);

    // textures first: the fragment program is translated for their kinds
    uint32_t dims = 0x55555555u;                                    // 2D unless bound otherwise
    for (auto& x : texs) {
        dims &= ~(3u << (2 * x.t.unit));
        bind_texture(x.t, x.data, dims);
    }
    FPConfig fc;
    fc.ctrl = R(0x1D60);
    fc.tex_dims = dims;
    for (int i = 0; i < 10; ++i) fc.tc_2d |= (R(0x0B40 + 4 * i) & 1) << i;
    Program& pr = program(fpw.data(), d.fp_words, fc);
    if (!pr.ok) { ++cnt.skipped_draws; return; }
    glUseProgram(pr.prog);
    glProgramUniform4fv(pr.prog, pr.vc, 468, vc);
    glProgramUniform4f(pr.prog, pr.vp_scale, RF(0x0A30), RF(0x0A34), RF(0x0A38), RF(0x0A3C));
    glProgramUniform4f(pr.prog, pr.vp_offset, RF(0x0A20), RF(0x0A24), RF(0x0A28), RF(0x0A2C));
    glProgramUniform4f(pr.prog, pr.vp_clip, 2.0f / (float)std::max(cw, 1), 2.0f / (float)std::max(ch, 1), 0, 0);
    if (pr.vp_branch >= 0) glProgramUniform1ui(pr.prog, pr.vp_branch, R(0x1E98));
    if (!pr.literals.empty()) {
        std::vector<float> lit(pr.literals.size() * 4);
        for (size_t i = 0; i < pr.literals.size(); ++i)
            for (int k = 0; k < 4; ++k) std::memcpy(&lit[i * 4 + k], &fpw[pr.literals[i] + k], 4);
        glProgramUniform4fv(pr.prog, pr.fc, (GLsizei)pr.literals.size(), lit.data());
    }
    uint32_t win = R(0x1D88);
    bool bottom = (win >> 12 & 0xF) == 1;
    float center = (win >> 16 & 0xF) == 1 ? -0.5f : 0.0f;
    glProgramUniform4f(pr.prog, pr.wpos, bottom ? -1.0f : 1.0f, bottom ? (float)(win & 0xFFF) : 0.0f, center, center);
    glProgramUniform4i(pr.prog, pr.alpha, R(0x0304) & 1, (GLint)R(0x0308), 0, 0);
    glProgramUniform1f(pr.prog, pr.alpha_ref, (R(0x030C) & 0xFF) / 255.0f);

    // the vertices
    glBindVertexArray(vao);
    bool have[16] = {};
    for (auto& a : attrs) {
        uint32_t type = a.format & 0xF, size = a.format >> 4 & 0xF, stride = a.format >> 8 & 0xFF;
        GLenum gt;
        bool norm = false;
        switch (type) {
        case 1: gt = GL_SHORT; norm = true; break;
        case 3: gt = GL_HALF_FLOAT; break;
        case 4: gt = GL_UNSIGNED_BYTE; norm = true; break;
        case 5: gt = GL_SHORT; break;
        case 7: gt = GL_UNSIGNED_BYTE; break;
        case 6: report_once("CMP vertex attributes"); continue;
        default: gt = GL_FLOAT; break;
        }
        size_t o = ring(vbo, vbo_at, a.data, a.bytes);
        glVertexArrayVertexBuffer(vao, a.index, vbo, (GLintptr)o, (GLsizei)stride);
        // a stride of 0 is one element for every vertex, where GL would read the
        // elements packed: as a per-instance attribute, every vertex reads element 0
        glVertexArrayBindingDivisor(vao, a.index, stride ? 0 : 1);
        glVertexArrayAttribFormat(vao, a.index, (GLint)std::min(size, 4u), gt, norm, 0);
        glVertexArrayAttribBinding(vao, a.index, a.index);
        glEnableVertexArrayAttrib(vao, a.index);
        have[a.index] = true;
    }
    for (uint32_t i = 0; i < 16; ++i) {
        if (have[i]) continue;
        glDisableVertexArrayAttrib(vao, i);
        uint32_t b = 0x1C00 + 16 * i;                               // NV4097_SET_VERTEX_DATA4F_M
        glVertexAttrib4f(i, RF(b), RF(b + 4), RF(b + 8), RF(b + 12));
    }
    set_state();

    GLenum prim = gl_prim(d.prim);
    bool is_quads = d.prim == 8;
    if (d.indexed || is_quads) {
        std::vector<uint32_t> list;
        if (!d.indexed) for (auto& [f, n] : ranges) for (uint32_t k = 0; k < n; ++k) list.push_back(f + k);
        else list = std::move(indices);
        if (is_quads) {
            std::vector<uint32_t> tri;
            size_t s = 0;
            for (size_t i = 0; i <= list.size(); ++i)
                if (i == list.size() || list[i] == 0xFFFFFFFFu) { quads(tri, &list[s], i - s); s = i + 1; }
            list = std::move(tri);
        }
        if (list.empty()) return;
        size_t o = ring(ibo, ibo_at, list.data(), list.size() * 4);
        glVertexArrayElementBuffer(vao, ibo);
        glDrawElements(prim, (GLsizei)list.size(), GL_UNSIGNED_INT, (const void*)o);
    } else {
        std::vector<GLint> first;
        std::vector<GLsizei> count;
        for (auto& [f, n] : ranges) { first.push_back((GLint)f); count.push_back((GLsizei)n); }
        glMultiDrawArrays(prim, first.data(), count.data(), (GLsizei)first.size());
    }
    glDisable(GL_SCISSOR_TEST);
    if (g_glsync && cnt.draws >= g_glsync) {
        std::string at;
        for (auto& a : attrs) {
            char b[40];
            std::snprintf(b, sizeof b, " %u:%03X/%u", a.index, a.format & 0xFFF, a.bytes);
            at += b;
        }
        rt_log("rsxgl: draw %llu prim %u %s %u, %u vertices, program %u, %zu textures, attrs%s",
               (unsigned long long)cnt.draws, d.prim, d.indexed ? "indices" : "ranges", d.count, d.vertices, pr.prog,
               texs.size(), at.c_str());
        glFinish();
    }
}
}  // namespace

void rsxgl_init() {
    glCreateVertexArrays(1, &vao);
    glCreateBuffers(1, &vbo);
    glNamedBufferStorage(vbo, kRing, nullptr, GL_DYNAMIC_STORAGE_BIT);
    glCreateBuffers(1, &ibo);
    glNamedBufferStorage(ibo, kRing, nullptr, GL_DYNAMIC_STORAGE_BIT);
    glCreateSamplers(16, samplers);
    glClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE);
    glEnable(GL_PRIMITIVE_RESTART_FIXED_INDEX);
    glEnable(GL_PROGRAM_POINT_SIZE);
    reg[0x0324 >> 2] = 0x01010101u;
    reg[0x08C0 >> 2] = reg[0x08C4 >> 2] = 4096u << 16;
}

void rsxgl_exec(const uint8_t* rec, size_t n, void (*on_flip)(const RsxFlip&)) {
    const uint8_t* p = rec;
    const uint8_t* end = rec + n;
    while (p < end) {
        uint8_t op = *p++;
        switch (op) {
        case RC_REGS: {
            uint32_t k;
            std::memcpy(&k, p, 4);
            p += 4;
            for (uint32_t i = 0; i < k; ++i, p += 8) {
                uint32_t m, v;
                std::memcpy(&m, p, 4);
                std::memcpy(&v, p + 4, 4);
                write(m, v);
            }
            break;
        }
        case RC_DRAW: draw(p); break;
        case RC_FLIP: { RsxFlip f; std::memcpy(&f, p, sizeof f); p += sizeof f; on_flip(f); break; }
        case RC_TEXFLUSH:
            for (auto& [k, t] : textures) if (t.tex) glDeleteTextures(1, &t.tex);
            textures.clear();
            break;
        default: rt_log("rsxgl: bad record byte %02X", op); return;
        }
    }
}

bool rsxgl_display(uint32_t offset, uint32_t& tex, uint32_t& fbo, int& w, int& h) {
    auto it = colors.find(skey(0xFEED0000u, offset));
    if (it == colors.end()) return false;
    tex = it->second.tex; fbo = it->second.fbo; w = it->second.w; h = it->second.h;
    return true;
}

void rsxgl_report() {
    rt_log("rsxgl: %llu draws (%llu skipped), %llu clears, %llu programs, %llu textures, %zu surfaces",
           (unsigned long long)cnt.draws, (unsigned long long)cnt.skipped_draws, (unsigned long long)cnt.clears,
           (unsigned long long)cnt.programs, (unsigned long long)cnt.textures, colors.size() + depths.size());
}
