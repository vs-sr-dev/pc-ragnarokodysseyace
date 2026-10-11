// ps3kit runtime — the PPU's VMX (AltiVec) unit, one helper per operation.
//
// A VR holds its 16 bytes in guest order (vector element 0 first), exactly
// as lvx leaves them, so loads and stores are copies and the element views
// byte-swap on access. The Cell's VMX runs in non-Java mode (VSCR[NJ] = 1):
// denormal inputs and results of the float operations are flushed to zero,
// and that is done here. Estimates (vrefp, vrsqrtefp, vexptefp, vlogefp)
// return exact values. Included by ppu.h.
#pragma once
#include <algorithm>
#include <cfloat>

static inline uint32_t vmx_word(const VR& v, int i) { uint32_t w; std::memcpy(&w, v.b + 4 * i, 4); return PPU_BSWAP32(w); }
static inline void vmx_setword(VR& v, int i, uint32_t w) { w = PPU_BSWAP32(w); std::memcpy(v.b + 4 * i, &w, 4); }
static inline uint16_t vmx_half(const VR& v, int i) { uint16_t h; std::memcpy(&h, v.b + 2 * i, 2); return PPU_BSWAP16(h); }
static inline void vmx_sethalf(VR& v, int i, uint16_t h) { h = PPU_BSWAP16(h); std::memcpy(v.b + 2 * i, &h, 2); }
static inline float vmx_ftz(float x) { return std::fabs(x) < FLT_MIN ? std::copysign(0.0f, x) : x; }
static inline float vmx_float(const VR& v, int i) { return vmx_ftz(as_f32(vmx_word(v, i))); }
static inline void vmx_setfloat(VR& v, int i, float f) { vmx_setword(v, i, as_u32(vmx_ftz(f))); }

// ---- loads and stores ---------------------------------------------------------------
static inline void vmx_lvx(PPUContext& c, int d, uint32_t ea) { std::memcpy(c.v[d].b, g_mem + (ea & ~15u), 16); }
static inline void vmx_stvx(PPUContext& c, int s, uint32_t ea) { std::memcpy(g_mem + (ea & ~15u), c.v[s].b, 16); }
static inline void vmx_lvlx(PPUContext& c, int d, uint32_t ea) {      // from ea to the block's end, left-justified
    uint32_t n = 16 - (ea & 15);
    VR r{}; std::memcpy(r.b, g_mem + ea, n); c.v[d] = r;
}
static inline void vmx_lvrx(PPUContext& c, int d, uint32_t ea) {      // from the block's start to ea, right-justified
    uint32_t n = ea & 15;
    VR r{}; if (n) std::memcpy(r.b + 16 - n, g_mem + (ea & ~15u), n); c.v[d] = r;
}
static inline void vmx_stvlx(PPUContext& c, int s, uint32_t ea) {
    std::memcpy(g_mem + ea, c.v[s].b, 16 - (ea & 15));
}
static inline void vmx_stvrx(PPUContext& c, int s, uint32_t ea) {
    uint32_t n = ea & 15;
    if (n) std::memcpy(g_mem + (ea & ~15u), c.v[s].b + 16 - n, n);
}
static inline void vmx_lvebx(PPUContext& c, int d, uint32_t ea) { c.v[d].b[ea & 15] = g_mem[ea]; }
static inline void vmx_lvehx(PPUContext& c, int d, uint32_t ea) { ea &= ~1u; std::memcpy(c.v[d].b + (ea & 15), g_mem + ea, 2); }
static inline void vmx_lvewx(PPUContext& c, int d, uint32_t ea) { ea &= ~3u; std::memcpy(c.v[d].b + (ea & 15), g_mem + ea, 4); }
static inline void vmx_stvebx(PPUContext& c, int s, uint32_t ea) { g_mem[ea] = c.v[s].b[ea & 15]; }
static inline void vmx_stvehx(PPUContext& c, int s, uint32_t ea) { ea &= ~1u; std::memcpy(g_mem + ea, c.v[s].b + (ea & 15), 2); }
static inline void vmx_stvewx(PPUContext& c, int s, uint32_t ea) { ea &= ~3u; std::memcpy(g_mem + ea, c.v[s].b + (ea & 15), 4); }
static inline void vmx_lvsl(PPUContext& c, int d, uint32_t ea) { for (int i = 0; i < 16; ++i) c.v[d].b[i] = (uint8_t)((ea & 15) + i); }
static inline void vmx_lvsr(PPUContext& c, int d, uint32_t ea) { for (int i = 0; i < 16; ++i) c.v[d].b[i] = (uint8_t)(16 - (ea & 15) + i); }

// ---- float arithmetic ---------------------------------------------------------------
#define VMX_F2(name, expr) \
    static inline void vmx_##name(VR& d, const VR& a, const VR& b) { \
        VR r; for (int i = 0; i < 4; ++i) { float x = vmx_float(a, i), y = vmx_float(b, i); (void)x; (void)y; vmx_setfloat(r, i, (expr)); } d = r; }
VMX_F2(vaddfp, x + y)
VMX_F2(vsubfp, x - y)
VMX_F2(vmaxfp, std::isnan(x) || std::isnan(y) ? (std::isnan(x) ? x : y) : std::max(x, y))
VMX_F2(vminfp, std::isnan(x) || std::isnan(y) ? (std::isnan(x) ? x : y) : std::min(x, y))
#undef VMX_F2
static inline void vmx_vmaddfp(VR& d, const VR& a, const VR& b, const VR& c) {
    VR r; for (int i = 0; i < 4; ++i) vmx_setfloat(r, i, std::fma(vmx_float(a, i), vmx_float(c, i), vmx_float(b, i))); d = r;
}
static inline void vmx_vnmsubfp(VR& d, const VR& a, const VR& b, const VR& c) {
    VR r; for (int i = 0; i < 4; ++i) vmx_setfloat(r, i, -std::fma(vmx_float(a, i), vmx_float(c, i), -vmx_float(b, i))); d = r;
}
#define VMX_F1(name, expr) \
    static inline void vmx_##name(VR& d, const VR& b) { \
        VR r; for (int i = 0; i < 4; ++i) { float x = vmx_float(b, i); vmx_setfloat(r, i, (expr)); } d = r; }
VMX_F1(vrefp, 1.0f / x)
VMX_F1(vrsqrtefp, 1.0f / std::sqrt(x))
VMX_F1(vrfiz, std::trunc(x))
VMX_F1(vrfin, std::nearbyint(x))
VMX_F1(vrfip, std::ceil(x))
VMX_F1(vrfim, std::floor(x))
VMX_F1(vexptefp, std::exp2(x))
VMX_F1(vlogefp, std::log2(x))
#undef VMX_F1

// ---- conversions --------------------------------------------------------------------
static inline void vmx_vctsxs(PPUContext& c, VR& d, const VR& b, uint32_t sh) {
    VR r;
    for (int i = 0; i < 4; ++i) {
        float x = vmx_float(b, i);
        double v = std::isnan(x) ? 0.0 : std::ldexp((double)x, (int)sh);
        int32_t o;
        if (v >= 2147483647.0) { o = INT32_MAX; c.vscr |= 1; }
        else if (v < -2147483648.0) { o = INT32_MIN; c.vscr |= 1; }
        else o = (int32_t)std::trunc(v);
        vmx_setword(r, i, (uint32_t)o);
    }
    d = r;
}
static inline void vmx_vctuxs(PPUContext& c, VR& d, const VR& b, uint32_t sh) {
    VR r;
    for (int i = 0; i < 4; ++i) {
        float x = vmx_float(b, i);
        double v = std::isnan(x) ? 0.0 : std::ldexp((double)x, (int)sh);
        uint32_t o;
        if (v >= 4294967295.0) { o = UINT32_MAX; c.vscr |= 1; }
        else if (v < 0) { o = 0; if (v <= -1.0) c.vscr |= 1; }
        else o = (uint32_t)std::trunc(v);
        vmx_setword(r, i, o);
    }
    d = r;
}
static inline void vmx_vcfsx(PPUContext&, VR& d, const VR& b, uint32_t sh) {
    VR r; for (int i = 0; i < 4; ++i) vmx_setfloat(r, i, (float)std::ldexp((double)(int32_t)vmx_word(b, i), -(int)sh)); d = r;
}
static inline void vmx_vcfux(PPUContext&, VR& d, const VR& b, uint32_t sh) {
    VR r; for (int i = 0; i < 4; ++i) vmx_setfloat(r, i, (float)std::ldexp((double)vmx_word(b, i), -(int)sh)); d = r;
}

// ---- compares: all ones or all zeros per element; Rc sets CR6 ---------------------------
static inline void vmx_cr6(PPUContext& c, const VR& r, int rc) {
    if (!rc) return;
    bool all = true, none = true;
    for (int i = 0; i < 16; ++i) { all = all && r.b[i] == 0xFF; none = none && r.b[i] == 0; }
    cr_set(c, 6, all, false, none, false);
}
#define VMX_CMPW(name, expr) \
    static inline void vmx_##name(PPUContext& c, VR& d, const VR& a, const VR& b, int rc) { \
        VR r; for (int i = 0; i < 4; ++i) { uint32_t x = vmx_word(a, i), y = vmx_word(b, i); float fx = as_f32(x), fy = as_f32(y); \
            (void)fx; (void)fy; vmx_setword(r, i, (expr) ? 0xFFFFFFFFu : 0); } d = r; vmx_cr6(c, d, rc); }
VMX_CMPW(vcmpequw, x == y)
VMX_CMPW(vcmpgtuw, x > y)
VMX_CMPW(vcmpgtsw, (int32_t)x > (int32_t)y)
VMX_CMPW(vcmpeqfp, vmx_ftz(fx) == vmx_ftz(fy))
VMX_CMPW(vcmpgefp, vmx_ftz(fx) >= vmx_ftz(fy))
VMX_CMPW(vcmpgtfp, vmx_ftz(fx) > vmx_ftz(fy))
#undef VMX_CMPW
static inline void vmx_vcmpbfp(PPUContext& c, VR& d, const VR& a, const VR& b, int rc) {
    VR r; bool in = true;
    for (int i = 0; i < 4; ++i) {
        float x = vmx_float(a, i), y = vmx_float(b, i);
        uint32_t o = (!(x <= y) ? 0x80000000u : 0) | (!(x >= -y) ? 0x40000000u : 0);
        in = in && !o;
        vmx_setword(r, i, o);
    }
    d = r;
    if (rc) cr_set(c, 6, false, false, in, false);
}
#define VMX_CMPH(name, expr) \
    static inline void vmx_##name(PPUContext& c, VR& d, const VR& a, const VR& b, int rc) { \
        VR r; for (int i = 0; i < 8; ++i) { uint16_t x = vmx_half(a, i), y = vmx_half(b, i); vmx_sethalf(r, i, (expr) ? 0xFFFF : 0); } \
        d = r; vmx_cr6(c, d, rc); }
VMX_CMPH(vcmpequh, x == y)
VMX_CMPH(vcmpgtuh, x > y)
VMX_CMPH(vcmpgtsh, (int16_t)x > (int16_t)y)
#undef VMX_CMPH
#define VMX_CMPB(name, expr) \
    static inline void vmx_##name(PPUContext& c, VR& d, const VR& a, const VR& b, int rc) { \
        VR r; for (int i = 0; i < 16; ++i) { uint8_t x = a.b[i], y = b.b[i]; r.b[i] = (expr) ? 0xFF : 0; } d = r; vmx_cr6(c, d, rc); }
VMX_CMPB(vcmpequb, x == y)
VMX_CMPB(vcmpgtub, x > y)
VMX_CMPB(vcmpgtsb, (int8_t)x > (int8_t)y)
#undef VMX_CMPB

// ---- logic and integers -------------------------------------------------------------
#define VMX_B(name, expr) \
    static inline void vmx_##name(VR& d, const VR& a, const VR& b) { VR r; for (int i = 0; i < 16; ++i) { uint8_t x = a.b[i], y = b.b[i]; r.b[i] = (uint8_t)(expr); } d = r; }
VMX_B(vand, x & y)
VMX_B(vandc, x & ~y)
VMX_B(vor, x | y)
VMX_B(vxor, x ^ y)
VMX_B(vnor, ~(x | y))
VMX_B(vaddubm, x + y)
VMX_B(vsububm, x - y)
VMX_B(vavgub, (x + y + 1) >> 1)
VMX_B(vslb, x << (y & 7))
VMX_B(vsrb, x >> (y & 7))
VMX_B(vsrab, (int8_t)x >> (y & 7))
#undef VMX_B
#define VMX_H(name, expr) \
    static inline void vmx_##name(VR& d, const VR& a, const VR& b) { VR r; for (int i = 0; i < 8; ++i) { uint16_t x = vmx_half(a, i), y = vmx_half(b, i); vmx_sethalf(r, i, (uint16_t)(expr)); } d = r; }
VMX_H(vadduhm, x + y)
VMX_H(vsubuhm, x - y)
VMX_H(vslh, x << (y & 15))
VMX_H(vsrh, x >> (y & 15))
VMX_H(vsrah, (int16_t)x >> (y & 15))
VMX_H(vmaxsh, std::max((int16_t)x, (int16_t)y))
VMX_H(vminsh, std::min((int16_t)x, (int16_t)y))
#undef VMX_H
#define VMX_W(name, expr) \
    static inline void vmx_##name(VR& d, const VR& a, const VR& b) { VR r; for (int i = 0; i < 4; ++i) { uint32_t x = vmx_word(a, i), y = vmx_word(b, i); vmx_setword(r, i, (uint32_t)(expr)); } d = r; }
VMX_W(vadduwm, x + y)
VMX_W(vsubuwm, x - y)
VMX_W(vslw, x << (y & 31))
VMX_W(vsrw, x >> (y & 31))
VMX_W(vsraw, (int32_t)x >> (y & 31))
VMX_W(vrlw, (y & 31) ? (x << (y & 31)) | (x >> (32 - (y & 31))) : x)
VMX_W(vmaxsw, std::max((int32_t)x, (int32_t)y))
VMX_W(vminsw, std::min((int32_t)x, (int32_t)y))
VMX_W(vmaxuw, std::max(x, y))
VMX_W(vminuw, std::min(x, y))
#undef VMX_W

// ---- permutes ------------------------------------------------------------------------
static inline void vmx_vperm(VR& d, const VR& a, const VR& b, const VR& c) {
    VR r; for (int i = 0; i < 16; ++i) { uint8_t k = c.b[i] & 31; r.b[i] = k < 16 ? a.b[k] : b.b[k - 16]; } d = r;
}
static inline void vmx_vsel(VR& d, const VR& a, const VR& b, const VR& c) {
    VR r; for (int i = 0; i < 16; ++i) r.b[i] = (uint8_t)((b.b[i] & c.b[i]) | (a.b[i] & ~c.b[i])); d = r;
}
static inline void vmx_vsldoi(VR& d, const VR& a, const VR& b, int sh) {
    uint8_t t[32]; std::memcpy(t, a.b, 16); std::memcpy(t + 16, b.b, 16);
    VR r; std::memcpy(r.b, t + sh, 16); d = r;
}
static inline void vmx_vslo(VR& d, const VR& a, const VR& b) {
    int sh = (b.b[15] >> 3) & 15; VR r{}; std::memcpy(r.b, a.b + sh, 16 - sh); d = r;
}
static inline void vmx_vsro(VR& d, const VR& a, const VR& b) {
    int sh = (b.b[15] >> 3) & 15; VR r{}; std::memcpy(r.b + sh, a.b, 16 - sh); d = r;
}
static inline void vmx_vsl(VR& d, const VR& a, const VR& b) {
    int sh = b.b[15] & 7; VR r;
    for (int i = 0; i < 16; ++i) r.b[i] = (uint8_t)((a.b[i] << sh) | (sh && i < 15 ? a.b[i + 1] >> (8 - sh) : 0));
    d = r;
}
static inline void vmx_vsr(VR& d, const VR& a, const VR& b) {
    int sh = b.b[15] & 7; VR r;
    for (int i = 0; i < 16; ++i) r.b[i] = (uint8_t)((a.b[i] >> sh) | (sh && i > 0 ? a.b[i - 1] << (8 - sh) : 0));
    d = r;
}
#define VMX_MERGE(name, T, n, get, set, lo) \
    static inline void vmx_##name(VR& d, const VR& a, const VR& b) { \
        VR r; for (int i = 0; i < n / 2; ++i) { set(r, 2 * i, get(a, lo + i)); set(r, 2 * i + 1, get(b, lo + i)); } d = r; }
static inline uint8_t vmx_byte(const VR& v, int i) { return v.b[i]; }
static inline void vmx_setbyte(VR& v, int i, uint8_t x) { v.b[i] = x; }
VMX_MERGE(vmrghw, uint32_t, 4, vmx_word, vmx_setword, 0)
VMX_MERGE(vmrglw, uint32_t, 4, vmx_word, vmx_setword, 2)
VMX_MERGE(vmrghh, uint16_t, 8, vmx_half, vmx_sethalf, 0)
VMX_MERGE(vmrglh, uint16_t, 8, vmx_half, vmx_sethalf, 4)
VMX_MERGE(vmrghb, uint8_t, 16, vmx_byte, vmx_setbyte, 0)
VMX_MERGE(vmrglb, uint8_t, 16, vmx_byte, vmx_setbyte, 8)
#undef VMX_MERGE
static inline void vmx_vpkuwum(VR& d, const VR& a, const VR& b) {
    VR r; for (int i = 0; i < 4; ++i) { vmx_sethalf(r, i, (uint16_t)vmx_word(a, i)); vmx_sethalf(r, i + 4, (uint16_t)vmx_word(b, i)); } d = r;
}
static inline void vmx_vpkuhum(VR& d, const VR& a, const VR& b) {
    VR r; for (int i = 0; i < 8; ++i) { r.b[i] = (uint8_t)vmx_half(a, i); r.b[i + 8] = (uint8_t)vmx_half(b, i); } d = r;
}
static inline void vmx_vupkhsh(VR& d, const VR& b) { VR r; for (int i = 0; i < 4; ++i) vmx_setword(r, i, (uint32_t)(int32_t)(int16_t)vmx_half(b, i)); d = r; }
static inline void vmx_vupklsh(VR& d, const VR& b) { VR r; for (int i = 0; i < 4; ++i) vmx_setword(r, i, (uint32_t)(int32_t)(int16_t)vmx_half(b, i + 4)); d = r; }
static inline void vmx_vupkhsb(VR& d, const VR& b) { VR r; for (int i = 0; i < 8; ++i) vmx_sethalf(r, i, (uint16_t)(int16_t)(int8_t)b.b[i]); d = r; }
static inline void vmx_vupklsb(VR& d, const VR& b) { VR r; for (int i = 0; i < 8; ++i) vmx_sethalf(r, i, (uint16_t)(int16_t)(int8_t)b.b[i + 8]); d = r; }
static inline void vmx_vspltw(VR& d, const VR& b, uint32_t k) { uint32_t w = vmx_word(b, k & 3); VR r; for (int i = 0; i < 4; ++i) vmx_setword(r, i, w); d = r; }
static inline void vmx_vsplth(VR& d, const VR& b, uint32_t k) { uint16_t h = vmx_half(b, k & 7); VR r; for (int i = 0; i < 8; ++i) vmx_sethalf(r, i, h); d = r; }
static inline void vmx_vspltb(VR& d, const VR& b, uint32_t k) { uint8_t x = b.b[k & 15]; VR r; std::memset(r.b, x, 16); d = r; }
static inline void vmx_vspltisw(VR& d, int32_t s) { for (int i = 0; i < 4; ++i) vmx_setword(d, i, (uint32_t)s); }
static inline void vmx_vspltish(VR& d, int32_t s) { for (int i = 0; i < 8; ++i) vmx_sethalf(d, i, (uint16_t)s); }
static inline void vmx_vspltisb(VR& d, int32_t s) { std::memset(d.b, (uint8_t)s, 16); }
static inline void vmx_mfvscr(PPUContext& c, VR& d) { VR r{}; vmx_setword(r, 3, c.vscr); d = r; }
