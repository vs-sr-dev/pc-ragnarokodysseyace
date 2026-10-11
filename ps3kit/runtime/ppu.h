// ps3kit runtime — the Cell PPU as seen by recompiled code.
//
// Recompiled functions have the signature `void f_XXXXXXXX(PPUContext& c)`
// and touch guest state only through this header: registers in PPUContext,
// memory through ld*/st* (big-endian guest byte order, a flat 4 GiB host
// reservation at g_mem: a game's address space is 32 bits wide even though
// its code is 64-bit), and a handful of out-of-line services the runtime
// provides (indirect calls, system calls, traps, the time base).
//
// The PPU runs in 64-bit mode: GPRs, LR and CTR are 64 bits wide, record
// forms compare all 64, carries come out of bit 63. Floating point is the
// PowerPC FPU's: fused multiply-adds round once (std::fma), single-precision
// results are rounded to float. Known approximations: fres/frsqrte return
// exact values rather than the hardware's estimates, FPSCR exception bits
// are not kept, and the rounding mode is honoured only by fctiw/fctid.
#pragma once
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>

#if defined(_MSC_VER) && !defined(__clang__)
#error "ps3kit's generated code needs clang: tail jumps are [[clang::musttail]]"
#endif
#define PPU_BSWAP16 __builtin_bswap16
#define PPU_BSWAP32 __builtin_bswap32
#define PPU_BSWAP64 __builtin_bswap64
#define PPU_UNLIKELY(x) __builtin_expect(!!(x), 0)
#define PPU_NOINLINE __attribute__((noinline))

// A tail jump to another recompiled function: guaranteed not to grow the
// host stack, so a guest loop that crosses a function boundary stays a loop.
#define PPU_TAIL(f) [[clang::musttail]] return f(c)

// A VMX register, kept in guest byte order: b[0] is the most significant
// byte, as it is in memory after lvx. Element accessors are in vmx.h.
struct alignas(16) VR { uint8_t b[16]; };

struct PPUContext {
    uint64_t r[32];
    double   f[32];
    VR       v[32];
    uint8_t  cr[32];     // one byte per CR bit: 4*field + {0 lt, 1 gt, 2 eq, 3 so}
    uint64_t lr, ctr;
    uint8_t  xer_so, xer_ov, xer_ca, xer_bc;
    uint32_t fpscr, vscr, vrsave;
    uint32_t raddr, rsize;  // the lwarx/ldarx reservation: address, 4 or 8 (0: none)
    uint64_t rval;          // and the value it saw, in guest byte order
    uint32_t thread_id;     // the lv2 id of the guest thread running this context
};

typedef void (*PPUFunc)(PPUContext&);

// The generated tables: address -> function, and the imports.
struct PPUFuncEntry { uint32_t addr; PPUFunc fn; };
struct PPUImport { const char* module; const char* name; uint32_t nid; uint32_t slot; };

// ---- services provided by the runtime ------------------------------------------------
extern uint8_t* g_mem;
void     ppu_call_indirect(PPUContext& c, uint32_t addr);  // bctrl, blrl
void     ppu_bctr(PPUContext& c);                          // an indirect tail jump to CTR
void     ppu_syscall(PPUContext& c, uint32_t addr);        // sc: lv2, the number in r11
void     ppu_trap(PPUContext& c, uint32_t addr);
void     ppu_unimplemented(PPUContext& c, uint32_t addr, const char* what);
uint64_t ppu_timebase();                                   // 79.8 MHz, as the Cell's

// ---- memory ---------------------------------------------------------------------
static inline uint8_t ld8(uint32_t a) { return g_mem[a]; }
static inline uint16_t ld16(uint32_t a) { uint16_t v; std::memcpy(&v, g_mem + a, 2); return PPU_BSWAP16(v); }
static inline uint32_t ld32(uint32_t a) { uint32_t v; std::memcpy(&v, g_mem + a, 4); return PPU_BSWAP32(v); }
static inline uint64_t ld64(uint32_t a) { uint64_t v; std::memcpy(&v, g_mem + a, 8); return PPU_BSWAP64(v); }
static inline void st8(uint32_t a, uint8_t v) { g_mem[a] = v; }
static inline void st16(uint32_t a, uint16_t v) { v = PPU_BSWAP16(v); std::memcpy(g_mem + a, &v, 2); }
static inline void st32(uint32_t a, uint32_t v) { v = PPU_BSWAP32(v); std::memcpy(g_mem + a, &v, 4); }
static inline void st64(uint32_t a, uint64_t v) { v = PPU_BSWAP64(v); std::memcpy(g_mem + a, &v, 8); }
static inline void ppu_dcbz(uint32_t ea) {                  // the Cell's cache line is 128 bytes
    std::memset(g_mem + (ea & ~127u), 0, 128);
}

// lwarx/stwcx. and ldarx/stdcx.: a compare-and-swap against the value the
// reservation saw. Another thread's store of the same value in between goes
// unnoticed (the ABA case), which lock-free code on the PPU does not rely on.
static inline uint64_t ppu_lwarx(PPUContext& c, uint32_t ea) {
    uint32_t v = __atomic_load_n(reinterpret_cast<uint32_t*>(g_mem + ea), __ATOMIC_SEQ_CST);
    c.raddr = ea; c.rsize = 4; c.rval = v;
    return PPU_BSWAP32(v);
}
static inline uint64_t ppu_ldarx(PPUContext& c, uint32_t ea) {
    uint64_t v = __atomic_load_n(reinterpret_cast<uint64_t*>(g_mem + ea), __ATOMIC_SEQ_CST);
    c.raddr = ea; c.rsize = 8; c.rval = v;
    return PPU_BSWAP64(v);
}
static inline void cr_set(PPUContext& c, int field, bool lt, bool gt, bool eq, bool so) {
    uint8_t* b = &c.cr[field * 4];
    b[0] = lt; b[1] = gt; b[2] = eq; b[3] = so;
}
static inline void ppu_stwcx(PPUContext& c, uint32_t ea, uint64_t v) {
    bool ok = false;
    if (c.rsize == 4 && c.raddr == ea) {
        uint32_t expect = (uint32_t)c.rval;
        ok = __atomic_compare_exchange_n(reinterpret_cast<uint32_t*>(g_mem + ea), &expect,
                                         PPU_BSWAP32((uint32_t)v), false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
    }
    c.rsize = 0;
    cr_set(c, 0, false, false, ok, c.xer_so);
}
static inline void ppu_stdcx(PPUContext& c, uint32_t ea, uint64_t v) {
    bool ok = false;
    if (c.rsize == 8 && c.raddr == ea) {
        uint64_t expect = c.rval;
        ok = __atomic_compare_exchange_n(reinterpret_cast<uint64_t*>(g_mem + ea), &expect,
                                         PPU_BSWAP64(v), false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
    }
    c.rsize = 0;
    cr_set(c, 0, false, false, ok, c.xer_so);
}

// ---- bit helpers ------------------------------------------------------------------
static inline uint64_t rotl64(uint64_t x, uint32_t n) { n &= 63; return n ? (x << n) | (x >> (64 - n)) : x; }
static inline uint64_t dup32(uint64_t x) { x &= 0xFFFFFFFFull; return x | (x << 32); }
static inline uint64_t cntlzw(uint32_t x) { return x ? (uint64_t)__builtin_clz(x) : 32; }
static inline uint64_t cntlzd(uint64_t x) { return x ? (uint64_t)__builtin_clzll(x) : 64; }
static inline double   as_f64(uint64_t u) { double d; std::memcpy(&d, &u, 8); return d; }
static inline uint64_t as_u64(double d)   { uint64_t u; std::memcpy(&u, &d, 8); return u; }
static inline float    as_f32(uint32_t u) { float f; std::memcpy(&f, &u, 4); return f; }
static inline uint32_t as_u32(float f)    { uint32_t u; std::memcpy(&u, &f, 4); return u; }

// ---- condition register -------------------------------------------------------------
static inline void cr_cmp_s(PPUContext& c, int field, int64_t a, int64_t b) {
    cr_set(c, field, a < b, a > b, a == b, c.xer_so);
}
static inline void cr_cmp_u(PPUContext& c, int field, uint64_t a, uint64_t b) {
    cr_set(c, field, a < b, a > b, a == b, c.xer_so);
}
static inline void cr0_rc(PPUContext& c, uint64_t v) { cr_cmp_s(c, 0, (int64_t)v, 0); }
static inline void cr1_rc(PPUContext& c) {          // FP record form: CR1 = FPSCR[FX FEX VX OX]
    uint32_t f = c.fpscr;
    cr_set(c, 1, f >> 31 & 1, f >> 30 & 1, f >> 29 & 1, f >> 28 & 1);
}
static inline uint64_t mfcr(const PPUContext& c) {
    uint32_t v = 0;
    for (int i = 0; i < 32; ++i) v |= (uint32_t)c.cr[i] << (31 - i);
    return v;
}
static inline void mtcrf(PPUContext& c, uint32_t crm, uint32_t v) {
    for (int fld = 0; fld < 8; ++fld)
        if (crm & (0x80u >> fld))
            for (int k = 0; k < 4; ++k) c.cr[fld * 4 + k] = v >> (31 - (fld * 4 + k)) & 1;
}
static inline uint64_t mfxer(const PPUContext& c) {
    return (uint32_t)c.xer_so << 31 | (uint32_t)c.xer_ov << 30 | (uint32_t)c.xer_ca << 29 | c.xer_bc;
}
static inline void mtxer(PPUContext& c, uint64_t v) {
    c.xer_so = v >> 31 & 1; c.xer_ov = v >> 30 & 1; c.xer_ca = v >> 29 & 1; c.xer_bc = v & 0x7F;
}

// ---- integer arithmetic ---------------------------------------------------------------
// Carrying forms compute a + b + cin over 64 bits; CA is the carry out of bit 63.
static inline uint64_t add_ca(PPUContext& c, uint64_t a, uint64_t b, uint64_t cin) {
    unsigned __int128 s = (unsigned __int128)a + b + cin;
    c.xer_ca = (uint8_t)(s >> 64);
    return (uint64_t)s;
}
// The word divides leave the high word undefined; zero is what is written.
static inline uint64_t divw(uint64_t a, uint64_t b) {
    int32_t sa = (int32_t)a, sb = (int32_t)b;
    if (sb == 0 || (sa == INT32_MIN && sb == -1)) return 0;
    return (uint32_t)(sa / sb);
}
static inline uint64_t divwu(uint64_t a, uint64_t b) { return (uint32_t)b ? (uint32_t)a / (uint32_t)b : 0; }
static inline uint64_t divd(uint64_t a, uint64_t b) {
    int64_t sa = (int64_t)a, sb = (int64_t)b;
    if (sb == 0 || (sa == INT64_MIN && sb == -1)) return 0;
    return (uint64_t)(sa / sb);
}
static inline uint64_t divdu(uint64_t a, uint64_t b) { return b ? a / b : 0; }
static inline uint64_t mulhd(uint64_t a, uint64_t b) { return (uint64_t)(((__int128)(int64_t)a * (int64_t)b) >> 64); }
static inline uint64_t mulhdu(uint64_t a, uint64_t b) { return (uint64_t)(((unsigned __int128)a * b) >> 64); }
static inline uint64_t slw(uint64_t a, uint64_t n) { n &= 63; return n > 31 ? 0 : (uint32_t)((uint32_t)a << n); }
static inline uint64_t srw(uint64_t a, uint64_t n) { n &= 63; return n > 31 ? 0 : (uint32_t)a >> n; }
static inline uint64_t sraw(PPUContext& c, uint64_t a, uint64_t n) {
    n &= 63;
    int32_t s = (int32_t)a;
    if (n > 31) { c.xer_ca = s < 0; return s < 0 ? ~0ull : 0; }
    c.xer_ca = s < 0 && n && ((uint32_t)a & ((1u << n) - 1)) != 0;
    return (uint64_t)(int64_t)(s >> n);
}
static inline uint64_t sld(uint64_t a, uint64_t n) { n &= 127; return n > 63 ? 0 : a << n; }
static inline uint64_t srd(uint64_t a, uint64_t n) { n &= 127; return n > 63 ? 0 : a >> n; }
static inline uint64_t srad(PPUContext& c, uint64_t a, uint64_t n) {
    n &= 127;
    int64_t s = (int64_t)a;
    if (n > 63) { c.xer_ca = s < 0; return s < 0 ? ~0ull : 0; }
    c.xer_ca = s < 0 && n && (a & ((1ull << n) - 1)) != 0;
    return (uint64_t)(s >> n);
}
static inline bool trap_cond32(uint32_t to, uint64_t a, uint64_t b) {
    int32_t sa = (int32_t)a, sb = (int32_t)b;
    uint32_t ua = (uint32_t)a, ub = (uint32_t)b;
    return ((to & 16) && sa < sb) || ((to & 8) && sa > sb) || ((to & 4) && ua == ub) ||
           ((to & 2) && ua < ub) || ((to & 1) && ua > ub);
}
static inline bool trap_cond64(uint32_t to, uint64_t a, uint64_t b) {
    int64_t sa = (int64_t)a, sb = (int64_t)b;
    return ((to & 16) && sa < sb) || ((to & 8) && sa > sb) || ((to & 4) && a == b) ||
           ((to & 2) && a < b) || ((to & 1) && a > b);
}

// ---- floating point -------------------------------------------------------------------
static inline double rs(double x) { return (double)(float)x; }     // round to single
static inline void fcmp(PPUContext& c, int field, double a, double b) {
    bool un = std::isnan(a) || std::isnan(b);
    cr_set(c, field, !un && a < b, !un && a > b, !un && a == b, un);
    c.fpscr = (c.fpscr & ~0xF000u) | ((uint32_t)(un ? 1 : a < b ? 8 : a > b ? 4 : 2) << 12);
}
static inline double round_mode(const PPUContext& c, double b) {
    switch (c.fpscr & 3) {                         // RN
    case 0: return std::nearbyint(b);
    case 1: return std::trunc(b);
    case 2: return std::ceil(b);
    default: return std::floor(b);
    }
}
static inline double fctiw_bits(PPUContext& c, double b, bool truncate) {
    int32_t v;
    if (std::isnan(b)) v = INT32_MIN;
    else if (b >= 2147483648.0) v = INT32_MAX;
    else if (b < -2147483648.0) v = INT32_MIN;
    else v = (int32_t)(truncate ? std::trunc(b) : round_mode(c, b));
    return as_f64(0xFFF8000000000000ull | (uint32_t)v);
}
static inline double fctid_bits(PPUContext& c, double b, bool truncate) {
    int64_t v;
    if (std::isnan(b)) v = INT64_MIN;
    else if (b >= 9223372036854775808.0) v = INT64_MAX;
    else if (b < -9223372036854775808.0) v = INT64_MIN;
    else v = (int64_t)(truncate ? std::trunc(b) : round_mode(c, b));
    return as_f64((uint64_t)v);
}
static inline double fres(double b) { return 1.0 / b; }
static inline double frsqrte(double b) { return 1.0 / std::sqrt(b); }
static inline void mtfsf(PPUContext& c, uint32_t fm, double b) {
    uint32_t v = (uint32_t)as_u64(b), m = 0;
    for (int i = 0; i < 8; ++i) if (fm & (0x80u >> i)) m |= 0xF0000000u >> (i * 4);
    c.fpscr = (c.fpscr & ~m) | (v & m);
}

#include "vmx.h"
