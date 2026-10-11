// ps3kit runtime — imported functions. The loader's job, done the loader's way:
// every slot of the executable's stub table gets the address of a descriptor,
// and the descriptor's entry is an address in the runtime's own range that no
// code lives at. A call through it lands in ppu_call_indirect, which hands it
// here: the import's C++ implementation if one is registered by name, or a
// stub that reports the call and returns CELL_OK.
//
// PS3KIT_TRACE=1 reports every call; by default each import's first calls are.
#include "rt.h"
#include <cstdlib>
#include <map>
#include <mutex>
#include <string>
#include <vector>

extern const PPUImport g_ppu_imports[];
extern const size_t g_ppu_nimports;

namespace {
std::map<std::string, HleFunc>& registry() { static std::map<std::string, HleFunc> m; return m; }
struct Bound { HleFunc fn; uint32_t calls; };
std::vector<Bound> g_bound;
std::mutex g_trace_mx;
const bool g_trace_all = std::getenv("PS3KIT_TRACE") != nullptr;
constexpr uint32_t kTraceFirst = 3;
}

HleReg::HleReg(const char* name, HleFunc f) { registry()[name] = f; }

void hle_bind_imports() {
    g_bound.assign(g_ppu_nimports, Bound{nullptr, 0});
    size_t bound = 0;
    for (size_t i = 0; i < g_ppu_nimports; ++i) {
        const PPUImport& im = g_ppu_imports[i];
        uint32_t code = mm::HLE_CODE + 4 * (uint32_t)i, desc = mm::HLE_DESC + 8 * (uint32_t)i;
        st32(desc, code);
        st32(desc + 4, 0);
        st32(im.slot, desc);
        auto it = registry().find(im.name);
        if (it != registry().end()) { g_bound[i].fn = it->second; ++bound; }
    }
    rt_log("ps3kit: %zu imports, %zu implemented, %zu stubbed", g_ppu_nimports, bound, g_ppu_nimports - bound);
}

bool hle_dispatch(PPUContext& c, uint32_t addr) {
    if (addr < mm::HLE_CODE || addr >= mm::HLE_CODE + 4 * g_ppu_nimports) return false;
    size_t i = (addr - mm::HLE_CODE) / 4;
    const PPUImport& im = g_ppu_imports[i];
    Bound& b = g_bound[i];
    uint32_t n = __atomic_fetch_add(&b.calls, 1, __ATOMIC_RELAXED);
    if (g_trace_all || n < kTraceFirst) {
        std::lock_guard<std::mutex> lk(g_trace_mx);
        rt_log("%s %s.%s(%llX, %llX, %llX, %llX)  lr=%08llX", b.fn ? "hle " : "STUB", im.module, im.name,
               (unsigned long long)c.r[3], (unsigned long long)c.r[4], (unsigned long long)c.r[5],
               (unsigned long long)c.r[6], (unsigned long long)c.lr);
    }
    if (b.fn) b.fn(c);
    else c.r[3] = CELL_OK;
    return true;
}
