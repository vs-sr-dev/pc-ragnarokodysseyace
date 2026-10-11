// ps3kit runtime — sysPrxForUser: the process's start, TLS, time and
// once-only initialisation. Its threads are in thread.cpp, its lightweight
// mutex and condition in sync.cpp.
#include "rt.h"
#include <chrono>
#include <mutex>

// ---- TLS ---------------------------------------------------------------------------------
// The block is a 0x30-byte system area followed by the image (file part
// copied, the rest cleared); r13 points 0x7000 past the image's start, so
// that the compiler's signed 16-bit offsets reach all of it.
static uint32_t g_tls_image, g_tls_filesz, g_tls_memsz;

static uint32_t tls_block() {
    uint32_t b = hle_alloc(0x30 + g_tls_memsz, 16) + 0x30;
    if (g_tls_filesz) std::memcpy(g_mem + b, g_mem + g_tls_image, g_tls_filesz);
    return b;
}

uint32_t tls_new_block() { return tls_block(); }

PS3_HLE(sys_initialize_tls) {            // (main thread id, image, file size, memory size)
    if (c.r[13] != 0) return;            // already done, by the loader
    g_tls_image = arg_u32(c, 1);
    g_tls_filesz = arg_u32(c, 2);
    g_tls_memsz = arg_u32(c, 3);
    c.r[13] = tls_block() + 0x7000;
}

void tls_init(PPUContext& c, uint32_t image, uint32_t filesz, uint32_t memsz) {
    c.r[13] = 0;
    PPUContext t = c;
    t.r[3] = c.thread_id; t.r[4] = image; t.r[5] = filesz; t.r[6] = memsz;
    hle_sys_initialize_tls(t);
    c.r[13] = t.r[13];
}

// ---- process -----------------------------------------------------------------------------
PS3_HLE(sys_process_exit) { throw PPUExit{(int)arg_u32(c, 0)}; }
PS3_HLE(sys_prx_exitspawn_with_level) { throw PPUExit{0}; }

// ---- time and once-only initialisation ---------------------------------------------------
PS3_HLE(sys_time_get_system_time) {      // microseconds since the system started
    using namespace std::chrono;
    static const auto t0 = steady_clock::now();
    c.r[3] = (uint64_t)duration_cast<microseconds>(steady_clock::now() - t0).count();
}

PS3_HLE(sys_ppu_thread_once) {           // (s32* once_ctrl, void (*init)(void))
    static std::recursive_mutex mx;      // a second caller waits until the first has finished
    std::lock_guard<std::recursive_mutex> lk(mx);
    uint32_t once = arg_u32(c, 0), init = arg_u32(c, 1);
    if (ld32(once) == 0) {
        st32(once, 1);
        ppu_call_guest(c, init);
    }
    c.r[3] = CELL_OK;
}
