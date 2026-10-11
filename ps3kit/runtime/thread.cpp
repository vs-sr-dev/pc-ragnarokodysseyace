// ps3kit runtime — PPU threads. A guest thread is a host thread with its own
// PPUContext, its own guest stack (in the stack area) and its own TLS block,
// started at its entry descriptor with r3 = the argument, as lv2 starts it.
//
// Scheduling is the host's: guest priorities are kept and reported but do
// not order anything. A game that relies on a high-priority thread never
// being preempted by a low one will show it here first.
#include "rt.h"
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <pthread.h>
#include <string>
#include <thread>

namespace {
struct Thread {
    uint32_t id = 0, entry_desc = 0;
    PPUContext* ctx = nullptr;
    std::string name;
    int prio = 0;
    bool joinable = false, done = false, joined = false;
    uint64_t exit_value = 0;
};
std::mutex g_mx;
std::condition_variable g_cv;
std::map<uint32_t, Thread*> g_threads;
uint32_t g_next_id = 0x01000001;
constexpr size_t kHostStack = 256u << 20;   // recompiled code recurses as deeply as the game does

void finish(Thread* t, uint64_t value) {
    std::lock_guard<std::mutex> lk(g_mx);
    t->exit_value = value;
    t->done = true;
    g_cv.notify_all();
}

void* thread_main(void* p) {
    Thread* t = static_cast<Thread*>(p);
    PPUContext& c = *t->ctx;
    try {
        ppu_call_indirect(c, ld32(t->entry_desc));
        finish(t, c.r[3]);
    } catch (const PPUThreadExit& e) {
        finish(t, e.value);
    } catch (const PPUExit& e) {
        rt_log("ps3kit: the process exited with %d (from thread \"%s\")", e.code, t->name.c_str());
        std::fflush(stdout);
        std::fflush(stderr);
        std::_Exit(e.code);
    }
    return nullptr;
}
}  // namespace

void ppu_thread_register_main(PPUContext& c, const char* name) {
    Thread* t = new Thread;
    t->id = c.thread_id;
    t->ctx = &c;
    t->name = name;
    std::lock_guard<std::mutex> lk(g_mx);
    g_threads[t->id] = t;
}

uint32_t ppu_thread_spawn(uint32_t entry_desc, uint64_t arg, int prio, uint32_t stacksize,
                          const char* name, bool joinable) {
    Thread* t = new Thread;
    t->entry_desc = entry_desc;
    t->name = name ? name : "";
    t->prio = prio;
    t->joinable = joinable;
    PPUContext& c = *(t->ctx = new PPUContext{});
    {
        std::lock_guard<std::mutex> lk(g_mx);
        t->id = g_next_id++;
        g_threads[t->id] = t;
    }
    c.thread_id = t->id;
    c.vscr = 0x00010000;
    if (stacksize < 0x4000) stacksize = 0x4000;
    uint32_t base = stack_alloc(stacksize);
    c.r[1] = (base + stacksize - 0x70) & ~15ull;
    st64((uint32_t)c.r[1], 0);
    c.r[2] = ld32(entry_desc + 4);
    c.r[3] = arg;
    c.r[13] = tls_new_block() + 0x7000;
    c.lr = mm::HLE_CODE - 4;

    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, kHostStack);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    pthread_t h;
    if (pthread_create(&h, &attr, thread_main, t)) {
        rt_log("ps3kit: cannot start a host thread for \"%s\"", t->name.c_str());
        std::abort();
    }
    pthread_attr_destroy(&attr);
    return t->id;
}

PPUContext* ppu_context_new(uint32_t stacksize, const char* name) {
    Thread* t = new Thread;
    t->name = name;
    PPUContext& c = *(t->ctx = new PPUContext{});
    {
        std::lock_guard<std::mutex> lk(g_mx);
        t->id = g_next_id++;
        g_threads[t->id] = t;
    }
    c.thread_id = t->id;
    c.vscr = 0x00010000;
    uint32_t base = stack_alloc(stacksize);
    c.r[1] = (base + stacksize - 0x70) & ~15ull;
    st64((uint32_t)c.r[1], 0);
    c.r[13] = tls_new_block() + 0x7000;
    return &c;
}

void ppu_thread_wait_all() {
    std::unique_lock<std::mutex> lk(g_mx);
    g_cv.wait(lk, [] {
        for (auto& [id, t] : g_threads)
            if (t->entry_desc && !t->done) return false;
        return true;
    });
}

// ---- the calls ------------------------------------------------------------------------------
PS3_HLE(sys_ppu_thread_create) {         // (u64* id, entry, arg, prio, stacksize, flags, name)
    uint32_t out = arg_u32(c, 0), entry = arg_u32(c, 1), stack = arg_u32(c, 4);
    int prio = (int)arg_u32(c, 3);
    uint64_t flags = arg_u64(c, 5);
    std::string name = mem_cstr(arg_u32(c, 6));
    uint32_t id = ppu_thread_spawn(entry, arg_u64(c, 2), prio, stack, name.c_str(), flags & 1);
    rt_log("ps3kit: thread %08X \"%s\" started (entry %08X, prio %d, stack %X%s)", id, name.c_str(),
           entry, prio, stack, flags & 1 ? ", joinable" : "");
    st64(out, id);
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_ppu_thread_exit) { throw PPUThreadExit{arg_u64(c, 0)}; }

PS3_HLE(sys_ppu_thread_get_id) {         // (u64* id)
    st64(arg_u32(c, 0), c.thread_id);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(41, _sys_ppu_thread_exit) { throw PPUThreadExit{arg_u64(c, 0)}; }

LV2_SYSCALL(43, sys_ppu_thread_yield) {
    std::this_thread::yield();
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(44, sys_ppu_thread_join) {   // (id, u64* exit value)
    uint32_t id = arg_u32(c, 0), out = arg_u32(c, 1);
    std::unique_lock<std::mutex> lk(g_mx);
    auto it = g_threads.find(id);
    if (it == g_threads.end()) { c.r[3] = CELL_ESRCH; return; }
    Thread* t = it->second;
    if (id == c.thread_id) { c.r[3] = 0x80010008u; return; }   // EDEADLK
    if (!t->joinable || t->joined) { c.r[3] = CELL_EINVAL; return; }
    t->joined = true;
    g_cv.wait(lk, [t] { return t->done; });
    if (out) st64(out, t->exit_value);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(45, sys_ppu_thread_detach) {
    std::lock_guard<std::mutex> lk(g_mx);
    auto it = g_threads.find(arg_u32(c, 0));
    if (it == g_threads.end()) { c.r[3] = CELL_ESRCH; return; }
    it->second->joinable = false;
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(47, sys_ppu_thread_set_priority) {
    std::lock_guard<std::mutex> lk(g_mx);
    auto it = g_threads.find(arg_u32(c, 0));
    if (it == g_threads.end()) { c.r[3] = CELL_ESRCH; return; }
    it->second->prio = (int)arg_u32(c, 1);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(48, sys_ppu_thread_get_priority) {   // (id, s32* prio)
    std::lock_guard<std::mutex> lk(g_mx);
    auto it = g_threads.find(arg_u32(c, 0));
    if (it == g_threads.end()) { c.r[3] = CELL_ESRCH; return; }
    st32(arg_u32(c, 1), (uint32_t)it->second->prio);
    c.r[3] = CELL_OK;
}
