// ps3kit runtime — lv2 system calls: `sc` with the number in r11. The ones a
// game makes directly (its statically linked liblv2 and libc) are dispatched
// by number; one with no implementation is reported and returns CELL_ENOSYS.
#include "rt.h"
#include <cstdlib>
#include <chrono>
#include <cstdio>
#include <thread>

namespace {
struct Sys { const char* name; HleFunc fn; };
Sys g_sys[1024];
}

Lv2Reg::Lv2Reg(int num, const char* name, HleFunc f) { g_sys[num] = {name, f}; }

// The names of the calls the ports make, for reports; an implementation
// registers its own (LV2_SYSCALL), which wins.
static const struct { int num; const char* name; } kNames[] = {
    {22, "_sys_process_exit"},
    {43, "sys_ppu_thread_yield"},
    {44, "sys_ppu_thread_join"},
    {45, "sys_ppu_thread_detach"},
    {47, "sys_ppu_thread_set_priority"},
    {48, "sys_ppu_thread_get_priority"},
    {82, "sys_event_flag_create"},
    {83, "sys_event_flag_destroy"},
    {85, "sys_event_flag_wait"},
    {87, "sys_event_flag_set"},
    {90, "sys_semaphore_create"},
    {91, "sys_semaphore_destroy"},
    {92, "sys_semaphore_wait"},
    {94, "sys_semaphore_post"},
    {100, "sys_mutex_create"},
    {101, "sys_mutex_destroy"},
    {102, "sys_mutex_lock"},
    {103, "sys_mutex_trylock"},
    {104, "sys_mutex_unlock"},
    {105, "sys_cond_create"},
    {106, "sys_cond_destroy"},
    {107, "sys_cond_wait"},
    {109, "sys_cond_signal_all"},
    {118, "sys_event_flag_clear"},
    {120, "sys_rwlock_create"},
    {121, "sys_rwlock_destroy"},
    {122, "sys_rwlock_rlock"},
    {124, "sys_rwlock_runlock"},
    {125, "sys_rwlock_wlock"},
    {127, "sys_rwlock_wunlock"},
    {128, "sys_event_queue_create"},
    {129, "sys_event_queue_destroy"},
    {130, "sys_event_queue_receive"},
    {134, "sys_event_port_create"},
    {135, "sys_event_port_destroy"},
    {136, "sys_event_port_connect_local"},
    {137, "sys_event_port_disconnect"},
    {138, "sys_event_port_send"},
    {141, "sys_timer_usleep"},
    {142, "sys_timer_sleep"},
    {144, "sys_time_get_timezone"},
    {145, "sys_time_get_current_time"},
    {147, "sys_time_get_timebase_frequency"},
    {156, "sys_spu_image_open"},
    {169, "sys_spu_initialize"},
    {170, "sys_spu_thread_group_create"},
    {171, "sys_spu_thread_group_destroy"},
    {172, "sys_spu_thread_initialize"},
    {173, "sys_spu_thread_group_start"},
    {174, "sys_spu_thread_group_suspend"},
    {177, "sys_spu_thread_group_terminate"},
    {178, "sys_spu_thread_group_join"},
    {181, "sys_spu_thread_write_ls"},
    {182, "sys_spu_thread_read_ls"},
    {187, "sys_spu_thread_set_spu_cfg"},
    {190, "sys_spu_thread_write_spu_mb"},
    {191, "sys_spu_thread_connect_event"},
    {192, "sys_spu_thread_disconnect_event"},
    {193, "sys_spu_thread_bind_queue"},
    {251, "sys_spu_thread_group_connect_event_all_threads"},
    {252, "sys_spu_thread_group_disconnect_event_all_threads"},
    {324, "sys_memory_container_create"},
    {325, "sys_memory_container_destroy"},
    {348, "sys_memory_allocate"},
    {352, "sys_memory_get_user_memory_size"},
    {402, "sys_tty_read"},
    {403, "sys_tty_write"},
    {801, "sys_fs_open"},
    {802, "sys_fs_read"},
    {803, "sys_fs_write"},
    {804, "sys_fs_close"},
    {805, "sys_fs_opendir"},
    {806, "sys_fs_readdir"},
    {807, "sys_fs_closedir"},
    {808, "sys_fs_stat"},
    {809, "sys_fs_fstat"},
    {810, "sys_fs_link"},
    {811, "sys_fs_mkdir"},
    {812, "sys_fs_rename"},
    {813, "sys_fs_rmdir"},
    {814, "sys_fs_unlink"},
    {815, "sys_fs_utime"},
    {817, "sys_fs_fcntl"},
    {818, "sys_fs_lseek"},
    {820, "sys_fs_fsync"},
    {831, "sys_fs_truncate"},
    {832, "sys_fs_ftruncate"},
    {834, "sys_fs_chmod"},
};

const char* lv2_name(int num) {
    if (num >= 0 && num < 1024 && g_sys[num].name) return g_sys[num].name;
    for (const auto& n : kNames)
        if (n.num == num) return n.name;
    return "?";
}

void ppu_syscall(PPUContext& c, uint32_t addr) {
    uint64_t n = c.r[11];
    if (n < 1024 && g_sys[n].fn) { g_sys[n].fn(c); return; }
    rt_log("STUB syscall %llu (%s) at %08X (%llX, %llX, %llX, %llX)", (unsigned long long)n,
           lv2_name((int)n), addr, (unsigned long long)c.r[3], (unsigned long long)c.r[4],
           (unsigned long long)c.r[5], (unsigned long long)c.r[6]);
    c.r[3] = CELL_ENOSYS;
}

// ---- process, time, tty ------------------------------------------------------------------
LV2_SYSCALL(22, sys_process_exit) { throw PPUExit{(int)arg_u32(c, 0)}; }

// On time to a fraction of a millisecond (host_sleep_until): a middleware
// loop that sleeps out a 60 Hz period keeps its rate, and the audio it feeds
// keeps ahead of the ports.
LV2_SYSCALL(141, sys_timer_usleep) {
    using namespace std::chrono;
    uint64_t us = arg_u64(c, 0);
    auto end = steady_clock::now() + microseconds(us);
    host_sleep_until(end);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(145, sys_time_get_current_time) {        // (s64* sec, s64* nsec)
    using namespace std::chrono;
    auto ns = duration_cast<nanoseconds>(system_clock::now().time_since_epoch()).count();
    st64(arg_u32(c, 0), (uint64_t)(ns / 1000000000));
    st64(arg_u32(c, 1), (uint64_t)(ns % 1000000000));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(144, sys_time_get_timezone) {            // (s32* timezone, s32* summertime)
    st32(arg_u32(c, 0), 0);
    st32(arg_u32(c, 1), 0);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(403, sys_tty_write) {                    // (ch, buf, len, u32* written)
    uint32_t buf = arg_u32(c, 1), len = arg_u32(c, 2), out = arg_u32(c, 3);
    std::fwrite(g_mem + buf, 1, len, stdout);
    std::fflush(stdout);
    if (out) st32(out, len);
    c.r[3] = CELL_OK;
}

// ---- memory -----------------------------------------------------------------------------
LV2_SYSCALL(348, sys_memory_allocate) {              // (size, flags, u32* addr)
    uint32_t size = arg_u32(c, 0), flags = (uint32_t)arg_u64(c, 1), out = arg_u32(c, 2);
    uint32_t align = flags & 0x200 ? 0x10000u : 0x100000u;   // SYS_MEMORY_PAGE_SIZE_64K, else 1M
    uint32_t a = user_alloc(size, align);
    if (!a) { c.r[3] = CELL_ENOMEM; return; }
    st32(out, a);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(352, sys_memory_get_user_memory_size) {  // (sys_memory_info_t*: total, available)
    uint32_t p = arg_u32(c, 0);
    st32(p, mm::USER_SIZE);
    st32(p + 4, user_free_bytes());
    c.r[3] = CELL_OK;
}
