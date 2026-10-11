// ps3kit runtime — guest memory: the 4 GiB reservation, its committed areas,
// and the three allocators the system side needs.
#include "rt.h"
#include <atomic>
#include <cstdio>
#include <memory>
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

// ---- write tracking ------------------------------------------------------------------------
// Per 4 KiB page: whether it is armed (read-only) and the clock at its last
// recorded write. Arming and the fault handler both take the lock, so that a
// page is never armed with its flag clear or left writable with it set; the
// stamp is taken inside the lock before the range is armed and the caller
// reads the range after, so a write either lands before the read or faults
// and is recorded after the stamp.
namespace {
constexpr uint32_t kPageBits = 12, kPages = 1u << (32 - kPageBits);
std::mutex g_watch_mx;
std::atomic<uint64_t> g_clock{1};
std::unique_ptr<std::atomic<uint64_t>[]> g_last_write;
std::unique_ptr<uint8_t[]> g_armed;

void watch_init() {
    if (g_armed) return;
    g_last_write.reset(new std::atomic<uint64_t>[kPages]());
    g_armed.reset(new uint8_t[kPages]());
}

#ifdef _WIN32
void protect(uint32_t first, uint32_t count, bool read_only) {
    DWORD old;
    VirtualProtect(g_mem + ((size_t)first << kPageBits), (size_t)count << kPageBits,
                   read_only ? PAGE_READONLY : PAGE_READWRITE, &old);
}
#endif
}  // namespace

uint64_t memwatch_arm(uint32_t addr, uint32_t n) {
#ifdef _WIN32
    if (!n) return 0;
    std::lock_guard<std::mutex> lk(g_watch_mx);
    watch_init();
    uint64_t stamp = g_clock.fetch_add(1) + 1;
    uint32_t p0 = addr >> kPageBits, p1 = (uint32_t)(((uint64_t)addr + n - 1) >> kPageBits);
    for (uint32_t p = p0; p <= p1;) {
        if (g_armed[p]) { ++p; continue; }
        uint32_t q = p;
        while (q <= p1 && !g_armed[q]) g_armed[q++] = 1;
        protect(p, q - p, true);
        p = q;
    }
    return stamp;
#else
    (void)addr; (void)n;
    return 0;
#endif
}

bool memwatch_clean(uint32_t addr, uint32_t n, uint64_t stamp) {
    if (!stamp || !g_last_write) return false;
    uint32_t p0 = addr >> kPageBits, p1 = (uint32_t)(((uint64_t)addr + n - 1) >> kPageBits);
    for (uint32_t p = p0; p <= p1; ++p)
        if (g_last_write[p].load(std::memory_order_acquire) >= stamp) return false;
    return true;
}

void memwatch_write(uint32_t addr, uint32_t n) {
#ifdef _WIN32
    if (!n) return;
    std::lock_guard<std::mutex> lk(g_watch_mx);
    if (!g_armed) return;
    uint32_t p0 = addr >> kPageBits, p1 = (uint32_t)(((uint64_t)addr + n - 1) >> kPageBits);
    for (uint32_t p = p0; p <= p1; ++p) {
        if (g_armed[p]) { protect(p, 1, false); g_armed[p] = 0; }
        g_last_write[p].store(g_clock.fetch_add(1) + 1, std::memory_order_release);
    }
#else
    (void)addr; (void)n;
#endif
}

bool memwatch_fault(uintptr_t host_addr) {
#ifdef _WIN32
    uintptr_t base = (uintptr_t)g_mem;
    if (host_addr < base || host_addr >= base + (1ull << 32)) return false;
    uint32_t p = (uint32_t)((host_addr - base) >> kPageBits);
    std::lock_guard<std::mutex> lk(g_watch_mx);
    if (!g_armed || !g_armed[p]) return false;
    protect(p, 1, false);
    g_armed[p] = 0;
    g_last_write[p].store(g_clock.fetch_add(1) + 1, std::memory_order_release);
    return true;
#else
    (void)host_addr;
    return false;
#endif
}

std::string mem_cstr(uint32_t addr, size_t max) {
    std::string s;
    if (!addr) return s;
    for (size_t i = 0; i < max && g_mem[addr + i]; ++i) s += (char)g_mem[addr + i];
    return s;
}
