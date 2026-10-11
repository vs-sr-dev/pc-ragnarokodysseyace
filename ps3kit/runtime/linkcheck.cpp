// Link check: every recompiled function, the dispatch table, the imports and
// the runtime link into one executable. Nothing runs.
#include "ppu.h"
#include <cstdio>
#include <cstddef>

extern const PPUFuncEntry g_ppu_funcs[];
extern const size_t g_ppu_nfuncs;
extern const size_t g_ppu_nimports;

int main() {
    std::printf("linked %zu recompiled functions (%08X-%08X) and %zu imports\n", g_ppu_nfuncs,
                g_ppu_funcs[0].addr, g_ppu_funcs[g_ppu_nfuncs - 1].addr, g_ppu_nimports);
    return 0;
}
