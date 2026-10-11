// ps3kit runtime — guest memory: the 4 GiB reservation, its committed areas,
// and the three allocators the system side needs.
#include "rt.h"
#include <cstdio>
#include <mutex>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <sys/mman.h>
#endif

struct Region { uint32_t base, size; };
static const Region kRegions[] = {
    {mm::MAIN, mm::HLE_END - mm::MAIN},         // the executable, the main area, the runtime's own
    {mm::USER, mm::USER_SIZE},
    {mm::VIDEO, mm::VIDEO_SIZE},
    {mm::STACK, mm::STACK_SIZE},
};

static std::mutex g_alloc_mx;
static uint32_t g_hle_top = mm::HLE_HEAP;
static uint32_t g_stack_top = mm::STACK + mm::STACK_SIZE;
static uint32_t g_user_top = mm::USER;

bool mem_init() {
    const size_t span = size_t(1) << 32;
#ifdef _WIN32
    void* base = VirtualAlloc(nullptr, span, MEM_RESERVE, PAGE_NOACCESS);
    if (!base) return false;
    g_mem = static_cast<uint8_t*>(base);
    for (const Region& r : kRegions)
        if (!VirtualAlloc(g_mem + r.base, r.size, MEM_COMMIT, PAGE_READWRITE)) return false;
#else
    void* base = mmap(nullptr, span, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (base == MAP_FAILED) return false;
    g_mem = static_cast<uint8_t*>(base);
    for (const Region& r : kRegions)
        if (mprotect(g_mem + r.base, r.size, PROT_READ | PROT_WRITE)) return false;
#endif
    return true;
}

static uint32_t align_up(uint32_t v, uint32_t a) { return (v + a - 1) & ~(a - 1); }

uint32_t hle_alloc(uint32_t size, uint32_t align) {
    std::lock_guard<std::mutex> lk(g_alloc_mx);
    uint32_t a = align_up(g_hle_top, align);
    if (a + size > mm::HLE_END) { std::fprintf(stderr, "ps3kit: runtime heap exhausted\n"); std::abort(); }
    g_hle_top = a + size;
    std::memset(g_mem + a, 0, size);
    return a;
}

uint32_t stack_alloc(uint32_t size) {
    std::lock_guard<std::mutex> lk(g_alloc_mx);
    size = align_up(size, 0x1000);
    if (g_stack_top - mm::STACK < size + 0x1000) { std::fprintf(stderr, "ps3kit: stack area exhausted\n"); std::abort(); }
    g_stack_top -= size + 0x1000;                // a guard page's worth of gap below each
    std::memset(g_mem + g_stack_top, 0, size);
    return g_stack_top;
}

uint32_t user_alloc(uint32_t size, uint32_t align) {
    std::lock_guard<std::mutex> lk(g_alloc_mx);
    uint32_t a = align_up(g_user_top, align);
    if (a + size > mm::USER + mm::USER_SIZE) return 0;
    g_user_top = a + size;
    return a;
}

uint32_t user_free_bytes() { return mm::USER + mm::USER_SIZE - g_user_top; }

void mem_write(uint32_t addr, const void* src, size_t n) { std::memcpy(g_mem + addr, src, n); }
void mem_read(uint32_t addr, void* dst, size_t n) { std::memcpy(dst, g_mem + addr, n); }

std::string mem_cstr(uint32_t addr, size_t max) {
    std::string s;
    if (!addr) return s;
    for (size_t i = 0; i < max && g_mem[addr + i]; ++i) s += (char)g_mem[addr + i];
    return s;
}
