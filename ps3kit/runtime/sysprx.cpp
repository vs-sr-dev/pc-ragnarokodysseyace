// ps3kit runtime — sysPrxForUser: the process's start, TLS, time, thread
// identity and the lightweight mutex.
//
// One guest thread runs so far: the lightweight mutex and condition calls
// keep their structures in the shape the game reads but never block, and
// sys_ppu_thread_create reports the thread it was asked for without
// starting it. Both change when the runtime gets threads.
#include "rt.h"
#include <chrono>

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
PS3_HLE(sys_ppu_thread_exit) { throw PPUExit{(int)arg_u32(c, 0)}; }

// ---- time and identity ---------------------------------------------------------------------
PS3_HLE(sys_time_get_system_time) {      // microseconds since the system started
    using namespace std::chrono;
    static const auto t0 = steady_clock::now();
    c.r[3] = (uint64_t)duration_cast<microseconds>(steady_clock::now() - t0).count();
}

PS3_HLE(sys_ppu_thread_get_id) {         // (u64* id)
    st64(arg_u32(c, 0), c.thread_id);
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_ppu_thread_once) {           // (s32* once_ctrl, void (*init)(void))
    uint32_t once = arg_u32(c, 0), init = arg_u32(c, 1);
    if (ld32(once) == 0) {
        st32(once, 1);
        ppu_call_guest(c, init);
    }
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_ppu_thread_create) {         // (u64* id, entry, arg, prio, stacksize, flags, name)
    rt_log("ps3kit: sys_ppu_thread_create(entry %08X, arg %llX, prio %d, stack %X, flags %llX, \"%s\") "
           "-- not started: the runtime has one thread so far",
           arg_u32(c, 1), (unsigned long long)arg_u64(c, 2), (int)arg_u32(c, 3), arg_u32(c, 4),
           (unsigned long long)arg_u64(c, 5), mem_cstr(arg_u32(c, 6)).c_str());
    static uint32_t next_id = 0x01000001;
    st64(arg_u32(c, 0), next_id++);
    c.r[3] = CELL_OK;
}

// ---- the lightweight mutex -------------------------------------------------------------------
// sys_lwmutex_t: {u32 owner, u32 waiter} lock word, u32 attribute,
// u32 recursive count, u32 sleep queue id, u32 pad.
constexpr uint32_t kLwFree = 0xFFFFFFFFu;

PS3_HLE(sys_lwmutex_create) {            // (sys_lwmutex_t*, attribute*: protocol, recursive, name)
    uint32_t m = arg_u32(c, 0), attr = arg_u32(c, 1);
    st32(m, kLwFree);
    st32(m + 4, 0);
    st32(m + 8, ld32(attr) | ld32(attr + 4));
    st32(m + 12, 0);
    static uint32_t next_queue = 0x95000001;
    st32(m + 16, next_queue++);
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwmutex_lock) {              // (sys_lwmutex_t*, timeout)
    uint32_t m = arg_u32(c, 0);
    uint32_t me = c.thread_id;
    if (ld32(m) == me) st32(m + 12, ld32(m + 12) + 1);
    else st32(m, me);
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwmutex_unlock) {
    uint32_t m = arg_u32(c, 0);
    if (ld32(m + 12)) st32(m + 12, ld32(m + 12) - 1);
    else st32(m, kLwFree);
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwmutex_destroy) { c.r[3] = CELL_OK; }
