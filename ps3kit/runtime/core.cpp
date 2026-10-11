// ps3kit runtime — the part every build shares: the guest memory pointer, the
// address -> function dispatch, guest calls from C++, traps, the time base
// and the reports a run dies with.
#include "rt.h"
#include <chrono>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif
#endif
#include <cstdarg>
#include <cstdio>
#include <cstdlib>

extern const PPUFuncEntry g_ppu_funcs[];
extern const size_t g_ppu_nfuncs;

uint8_t* g_mem = nullptr;

PPUFunc ppu_lookup(uint32_t addr) {
    size_t lo = 0, hi = g_ppu_nfuncs;
    while (lo < hi) {
        size_t mid = (lo + hi) / 2;
        if (g_ppu_funcs[mid].addr < addr) lo = mid + 1; else hi = mid;
    }
    if (lo < g_ppu_nfuncs && g_ppu_funcs[lo].addr == addr) return g_ppu_funcs[lo].fn;
    return nullptr;
}

void ppu_call_indirect(PPUContext& c, uint32_t addr) {
    if (hle_dispatch(c, addr)) return;
    PPUFunc f = ppu_lookup(addr);
    if (!f) rt_fatal(c, "indirect call to %08X, which is not a function", addr);
    f(c);
}

void ppu_bctr(PPUContext& c) {
    ppu_call_indirect(c, (uint32_t)c.ctr);
}

uint64_t ppu_call_guest(PPUContext& c, uint32_t desc, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3) {
    PPUContext saved = c;
    uint32_t entry = ld32(desc), toc = ld32(desc + 4);
    c.r[2] = toc;
    c.r[3] = a0; c.r[4] = a1; c.r[5] = a2; c.r[6] = a3;
    c.lr = mm::HLE_CODE - 4;                     // a return address no code lives at
    ppu_call_indirect(c, entry);
    uint64_t r = c.r[3];
    c = saved;
    return r;
}

void ppu_trap(PPUContext& c, uint32_t addr) {
    rt_fatal(c, "trap at %08X", addr);
}

void ppu_unimplemented(PPUContext& c, uint32_t addr, const char* what) {
    rt_fatal(c, "unimplemented at %08X: %s", addr, what);
}

void host_sleep_until(std::chrono::steady_clock::time_point t) {
    using namespace std::chrono;
#ifdef _WIN32
    thread_local HANDLE timer = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION,
                                                       TIMER_ALL_ACCESS);
    auto now = steady_clock::now();
    if (t <= now) return;
    LARGE_INTEGER due;
    due.QuadPart = -(LONGLONG)(duration_cast<nanoseconds>(t - now).count() / 100);   // relative, 100 ns units
    if (timer && SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE)) {
        WaitForSingleObject(timer, INFINITE);
        return;
    }
#endif
    std::this_thread::sleep_until(t);
}

uint64_t ppu_timebase() {
    using namespace std::chrono;
    static const auto t0 = steady_clock::now();
    auto ns = duration_cast<nanoseconds>(steady_clock::now() - t0).count();
    return (uint64_t)((unsigned __int128)ns * 79800000 / 1000000000);
}

// ---- reports --------------------------------------------------------------------------
void rt_log(const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    std::vfprintf(stderr, fmt, ap);
    va_end(ap);
    std::fputc('\n', stderr);
}

void rt_dump(PPUContext& c) {
    std::fprintf(stderr, "  lr %08llX  ctr %08llX  cr ", (unsigned long long)c.lr, (unsigned long long)c.ctr);
    for (int i = 0; i < 8; ++i)
        std::fprintf(stderr, "%X", c.cr[4 * i] << 3 | c.cr[4 * i + 1] << 2 | c.cr[4 * i + 2] << 1 | c.cr[4 * i + 3]);
    std::fputc('\n', stderr);
    for (int i = 0; i < 32; ++i)
        std::fprintf(stderr, "  r%-2d %016llX%s", i, (unsigned long long)c.r[i], i % 4 == 3 ? "\n" : "");
}

void rt_fatal(PPUContext& c, const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    std::fprintf(stderr, "ps3kit: ");
    std::vfprintf(stderr, fmt, ap);
    va_end(ap);
    std::fputc('\n', stderr);
    rt_dump(c);
    std::fflush(stderr);
    std::exit(1);
}
