// ps3kit runtime — synchronisation: the lightweight mutex and condition
// (sysPrxForUser, whose structures live in guest memory and are kept in the
// shape the game reads), and the lv2 objects behind ids: mutex, condition,
// semaphore, event flag, event queue and event port.
//
// Every object is guarded by one runtime-wide lock and every wait sleeps on
// one condition variable, woken on any change. That is correct and simple,
// and wakes more threads than it needs to; protocols (FIFO, priority) are
// not honoured, waiters race. Timeouts are in microseconds, 0 = forever.
#include "rt.h"
#include <array>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <map>
#include <mutex>

namespace {
std::mutex g_mx;
std::condition_variable g_cv;

constexpr uint32_t CELL_EDEADLK = 0x80010008u, CELL_EPERM = 0x80010009u, CELL_EBUSY = 0x8001000Au,
                   CELL_ETIMEDOUT = 0x8001000Bu, CELL_ENOTCONN = 0x80010010u, CELL_EISCONN = 0x8001000Fu;
constexpr uint32_t kLwFree = 0xFFFFFFFFu;
constexpr uint32_t kSyncRecursive = 0x10;

// Wait on the shared condition until pred() holds; false on timeout.
template <class P>
bool wait_for(std::unique_lock<std::mutex>& lk, uint64_t timeout_us, P pred) {
    if (!timeout_us) { g_cv.wait(lk, pred); return true; }
    return g_cv.wait_for(lk, std::chrono::microseconds(timeout_us), pred);
}

template <class T>
struct Table {
    std::map<uint32_t, T> m;
    uint32_t next;
    explicit Table(uint32_t first) : next(first) {}
    uint32_t add(T v) { m[next] = v; return next++; }
    T* get(uint32_t id) { auto it = m.find(id); return it == m.end() ? nullptr : &it->second; }
};

struct Mutex { uint32_t owner = 0, count = 0; bool recursive = false; };
struct Cond { uint32_t mutex = 0, waiters = 0, signals = 0; };
struct Sema { int32_t value = 0, max = 0; };
struct EFlag { uint64_t pattern = 0; };
struct EQueue { std::deque<std::array<uint64_t, 4>> events; uint32_t size = 127; };
struct EPort { uint64_t name = 0; uint32_t queue = 0; };
struct LwCond { uint32_t waiters = 0, signals = 0; };

Table<Mutex> g_mutex(0x85000001);
Table<Cond> g_cond(0x86000001);
Table<Sema> g_sema(0x96000001);
Table<EFlag> g_eflag(0x98000001);
Table<EQueue> g_equeue(0x8D000001);
Table<EPort> g_eport(0x0E000001);
std::map<uint32_t, LwCond> g_lwcond;            // by the guest address of its sys_lwcond_t
uint32_t g_lw_queue = 0x95000001;

// ---- the lightweight mutex, in guest memory -----------------------------------------------
// sys_lwmutex_t: u32 owner (0xFFFFFFFF free), u32 waiter, u32 attribute,
// u32 recursive count, u32 sleep queue, u32 pad.
uint32_t lw_lock(std::unique_lock<std::mutex>& lk, uint32_t m, uint32_t me, uint64_t timeout, bool wait) {
    uint32_t owner = ld32(m);
    if (owner == me) {
        if (!(ld32(m + 8) & kSyncRecursive)) return CELL_EDEADLK;
        st32(m + 12, ld32(m + 12) + 1);
        return CELL_OK;
    }
    if (owner != kLwFree) {
        if (!wait) return CELL_EBUSY;
        st32(m + 4, ld32(m + 4) + 1);
        bool ok = wait_for(lk, timeout, [m] { return ld32(m) == kLwFree; });
        st32(m + 4, ld32(m + 4) - 1);
        if (!ok) return CELL_ETIMEDOUT;
    }
    st32(m, me);
    return CELL_OK;
}

uint32_t lw_unlock(uint32_t m, uint32_t me) {
    if (ld32(m) != me) return CELL_EPERM;
    if (ld32(m + 12)) { st32(m + 12, ld32(m + 12) - 1); return CELL_OK; }
    st32(m, kLwFree);
    g_cv.notify_all();
    return CELL_OK;
}

uint32_t mutex_lock(std::unique_lock<std::mutex>& lk, uint32_t id, uint32_t me, uint64_t timeout, bool wait) {
    Mutex* mx = g_mutex.get(id);
    if (!mx) return CELL_ESRCH;
    if (mx->owner == me) {
        if (!mx->recursive) return CELL_EDEADLK;
        ++mx->count;
        return CELL_OK;
    }
    if (mx->owner) {
        if (!wait) return CELL_EBUSY;
        if (!wait_for(lk, timeout, [id] { Mutex* m = g_mutex.get(id); return !m || !m->owner; })) return CELL_ETIMEDOUT;
        if (!(mx = g_mutex.get(id))) return CELL_ESRCH;
    }
    mx->owner = me;
    mx->count = 0;
    return CELL_OK;
}
}  // namespace

// ---- sysPrxForUser: lightweight mutex and condition ---------------------------------------
PS3_HLE(sys_lwmutex_create) {            // (sys_lwmutex_t*, attribute*: protocol, recursive, name)
    uint32_t m = arg_u32(c, 0), attr = arg_u32(c, 1);
    std::lock_guard<std::mutex> lk(g_mx);
    st32(m, kLwFree);
    st32(m + 4, 0);
    st32(m + 8, ld32(attr) | ld32(attr + 4));
    st32(m + 12, 0);
    st32(m + 16, g_lw_queue++);
    st32(m + 20, 0);
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwmutex_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t m = arg_u32(c, 0);
    if (ld32(m) != kLwFree) { c.r[3] = CELL_EBUSY; return; }
    st32(m, 0xFFFFFFFEu);                // dead
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwmutex_lock) {              // (sys_lwmutex_t*, timeout)
    std::unique_lock<std::mutex> lk(g_mx);
    c.r[3] = lw_lock(lk, arg_u32(c, 0), c.thread_id, arg_u64(c, 1), true);
}

PS3_HLE(sys_lwmutex_trylock) {
    std::unique_lock<std::mutex> lk(g_mx);
    c.r[3] = lw_lock(lk, arg_u32(c, 0), c.thread_id, 0, false);
}

PS3_HLE(sys_lwmutex_unlock) {
    std::lock_guard<std::mutex> lk(g_mx);
    c.r[3] = lw_unlock(arg_u32(c, 0), c.thread_id);
}

// sys_lwcond_t: u32 the sys_lwmutex_t it pairs with, u32 sleep queue.
PS3_HLE(sys_lwcond_create) {             // (sys_lwcond_t*, sys_lwmutex_t*, attribute*)
    uint32_t cv = arg_u32(c, 0);
    std::lock_guard<std::mutex> lk(g_mx);
    st32(cv, arg_u32(c, 1));
    st32(cv + 4, g_lw_queue++);
    g_lwcond[cv] = LwCond{};
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwcond_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    auto it = g_lwcond.find(arg_u32(c, 0));
    if (it != g_lwcond.end() && it->second.waiters) { c.r[3] = CELL_EBUSY; return; }
    if (it != g_lwcond.end()) g_lwcond.erase(it);
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwcond_wait) {               // (sys_lwcond_t*, timeout)
    uint32_t cv = arg_u32(c, 0), m = ld32(cv), me = c.thread_id;
    std::unique_lock<std::mutex> lk(g_mx);
    if (ld32(m) != me) { c.r[3] = CELL_EPERM; return; }
    uint32_t depth = ld32(m + 12);
    st32(m + 12, 0);
    st32(m, kLwFree);
    LwCond& w = g_lwcond[cv];
    ++w.waiters;
    g_cv.notify_all();
    bool ok = wait_for(lk, arg_u64(c, 1), [cv] { return g_lwcond[cv].signals > 0; });
    LwCond& w2 = g_lwcond[cv];
    --w2.waiters;
    if (ok) --w2.signals;
    wait_for(lk, 0, [m] { return ld32(m) == kLwFree; });
    st32(m, me);
    st32(m + 12, depth);
    c.r[3] = ok ? CELL_OK : CELL_ETIMEDOUT;
}

PS3_HLE(sys_lwcond_signal) {
    std::lock_guard<std::mutex> lk(g_mx);
    LwCond& w = g_lwcond[arg_u32(c, 0)];
    if (w.waiters > w.signals) { ++w.signals; g_cv.notify_all(); }
    c.r[3] = CELL_OK;
}

PS3_HLE(sys_lwcond_signal_all) {
    std::lock_guard<std::mutex> lk(g_mx);
    LwCond& w = g_lwcond[arg_u32(c, 0)];
    w.signals = w.waiters;
    g_cv.notify_all();
    c.r[3] = CELL_OK;
}

// ---- lv2: mutex ----------------------------------------------------------------------------
LV2_SYSCALL(100, sys_mutex_create) {     // (u32* id, attribute*: protocol, recursive, ...)
    std::lock_guard<std::mutex> lk(g_mx);
    Mutex mx;
    mx.recursive = ld32(arg_u32(c, 1) + 4) == kSyncRecursive;
    st32(arg_u32(c, 0), g_mutex.add(mx));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(101, sys_mutex_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    Mutex* mx = g_mutex.get(arg_u32(c, 0));
    if (!mx) { c.r[3] = CELL_ESRCH; return; }
    if (mx->owner) { c.r[3] = CELL_EBUSY; return; }
    g_mutex.m.erase(arg_u32(c, 0));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(102, sys_mutex_lock) {       // (id, timeout)
    std::unique_lock<std::mutex> lk(g_mx);
    c.r[3] = mutex_lock(lk, arg_u32(c, 0), c.thread_id, arg_u64(c, 1), true);
}

LV2_SYSCALL(103, sys_mutex_trylock) {
    std::unique_lock<std::mutex> lk(g_mx);
    c.r[3] = mutex_lock(lk, arg_u32(c, 0), c.thread_id, 0, false);
}

LV2_SYSCALL(104, sys_mutex_unlock) {
    std::lock_guard<std::mutex> lk(g_mx);
    Mutex* mx = g_mutex.get(arg_u32(c, 0));
    if (!mx) { c.r[3] = CELL_ESRCH; return; }
    if (mx->owner != c.thread_id) { c.r[3] = CELL_EPERM; return; }
    if (mx->count) --mx->count;
    else { mx->owner = 0; g_cv.notify_all(); }
    c.r[3] = CELL_OK;
}

// ---- lv2: condition --------------------------------------------------------------------------
LV2_SYSCALL(105, sys_cond_create) {      // (u32* id, mutex id, attribute*)
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_mutex.get(arg_u32(c, 1))) { c.r[3] = CELL_ESRCH; return; }
    Cond cv;
    cv.mutex = arg_u32(c, 1);
    st32(arg_u32(c, 0), g_cond.add(cv));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(106, sys_cond_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    Cond* cv = g_cond.get(arg_u32(c, 0));
    if (!cv) { c.r[3] = CELL_ESRCH; return; }
    if (cv->waiters) { c.r[3] = CELL_EBUSY; return; }
    g_cond.m.erase(arg_u32(c, 0));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(107, sys_cond_wait) {        // (id, timeout)
    uint32_t id = arg_u32(c, 0), me = c.thread_id;
    std::unique_lock<std::mutex> lk(g_mx);
    Cond* cv = g_cond.get(id);
    if (!cv) { c.r[3] = CELL_ESRCH; return; }
    uint32_t mid = cv->mutex;
    Mutex* mx = g_mutex.get(mid);
    if (!mx || mx->owner != me) { c.r[3] = CELL_EPERM; return; }
    uint32_t depth = mx->count;
    mx->owner = 0; mx->count = 0;
    ++cv->waiters;
    g_cv.notify_all();
    bool ok = wait_for(lk, arg_u64(c, 1), [id] { Cond* x = g_cond.get(id); return !x || x->signals > 0; });
    if ((cv = g_cond.get(id))) { --cv->waiters; if (ok && cv->signals) --cv->signals; }
    wait_for(lk, 0, [mid] { Mutex* m = g_mutex.get(mid); return !m || !m->owner; });
    if ((mx = g_mutex.get(mid))) { mx->owner = me; mx->count = depth; }
    c.r[3] = ok ? CELL_OK : CELL_ETIMEDOUT;
}

LV2_SYSCALL(108, sys_cond_signal) {
    std::lock_guard<std::mutex> lk(g_mx);
    Cond* cv = g_cond.get(arg_u32(c, 0));
    if (!cv) { c.r[3] = CELL_ESRCH; return; }
    if (cv->waiters > cv->signals) { ++cv->signals; g_cv.notify_all(); }
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(109, sys_cond_signal_all) {
    std::lock_guard<std::mutex> lk(g_mx);
    Cond* cv = g_cond.get(arg_u32(c, 0));
    if (!cv) { c.r[3] = CELL_ESRCH; return; }
    cv->signals = cv->waiters;
    g_cv.notify_all();
    c.r[3] = CELL_OK;
}

// ---- lv2: semaphore --------------------------------------------------------------------------
LV2_SYSCALL(90, sys_semaphore_create) {  // (u32* id, attribute*, initial, max)
    std::lock_guard<std::mutex> lk(g_mx);
    Sema s{(int32_t)arg_u32(c, 2), (int32_t)arg_u32(c, 3)};
    if (s.max <= 0 || s.value < 0 || s.value > s.max) { c.r[3] = CELL_EINVAL; return; }
    st32(arg_u32(c, 0), g_sema.add(s));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(91, sys_semaphore_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    c.r[3] = g_sema.m.erase(arg_u32(c, 0)) ? CELL_OK : CELL_ESRCH;
    g_cv.notify_all();
}

LV2_SYSCALL(92, sys_semaphore_wait) {    // (id, timeout)
    uint32_t id = arg_u32(c, 0);
    std::unique_lock<std::mutex> lk(g_mx);
    if (!g_sema.get(id)) { c.r[3] = CELL_ESRCH; return; }
    if (!wait_for(lk, arg_u64(c, 1), [id] { Sema* s = g_sema.get(id); return !s || s->value > 0; })) {
        c.r[3] = CELL_ETIMEDOUT;
        return;
    }
    Sema* s = g_sema.get(id);
    if (!s) { c.r[3] = CELL_ESRCH; return; }
    --s->value;
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(93, sys_semaphore_trywait) {
    std::lock_guard<std::mutex> lk(g_mx);
    Sema* s = g_sema.get(arg_u32(c, 0));
    if (!s) { c.r[3] = CELL_ESRCH; return; }
    if (s->value <= 0) { c.r[3] = CELL_EBUSY; return; }
    --s->value;
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(94, sys_semaphore_post) {    // (id, count)
    std::lock_guard<std::mutex> lk(g_mx);
    Sema* s = g_sema.get(arg_u32(c, 0));
    int32_t n = (int32_t)arg_u32(c, 1);
    if (!s) { c.r[3] = CELL_ESRCH; return; }
    if (n < 0 || s->value + n > s->max) { c.r[3] = CELL_EINVAL; return; }
    s->value += n;
    g_cv.notify_all();
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(114, sys_semaphore_get_value) {  // (id, s32* value)
    std::lock_guard<std::mutex> lk(g_mx);
    Sema* s = g_sema.get(arg_u32(c, 0));
    if (!s) { c.r[3] = CELL_ESRCH; return; }
    st32(arg_u32(c, 1), (uint32_t)s->value);
    c.r[3] = CELL_OK;
}

// ---- lv2: event flag -------------------------------------------------------------------------
constexpr uint32_t kWaitAnd = 0x01, kWaitOr = 0x02, kClear = 0x10, kClearAll = 0x20;

static bool eflag_match(uint64_t pattern, uint64_t bits, uint32_t mode) {
    return mode & kWaitOr ? (pattern & bits) != 0 : (pattern & bits) == bits;
}
static void eflag_take(EFlag& f, uint64_t bits, uint32_t mode, uint32_t out) {
    if (out) st64(out, f.pattern);
    if (mode & kClearAll) f.pattern = 0;
    else if (mode & kClear) f.pattern &= ~bits;
}

LV2_SYSCALL(82, sys_event_flag_create) { // (u32* id, attribute*, initial pattern)
    std::lock_guard<std::mutex> lk(g_mx);
    st32(arg_u32(c, 0), g_eflag.add(EFlag{arg_u64(c, 2)}));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(83, sys_event_flag_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    c.r[3] = g_eflag.m.erase(arg_u32(c, 0)) ? CELL_OK : CELL_ESRCH;
    g_cv.notify_all();
}

LV2_SYSCALL(85, sys_event_flag_wait) {   // (id, bits, mode, u64* result, timeout)
    uint32_t id = arg_u32(c, 0), mode = arg_u32(c, 2), out = arg_u32(c, 3);
    uint64_t bits = arg_u64(c, 1);
    std::unique_lock<std::mutex> lk(g_mx);
    if (!g_eflag.get(id)) { c.r[3] = CELL_ESRCH; return; }
    bool ok = wait_for(lk, arg_u64(c, 4), [=] { EFlag* f = g_eflag.get(id); return !f || eflag_match(f->pattern, bits, mode); });
    EFlag* f = g_eflag.get(id);
    if (!f) { c.r[3] = CELL_ESRCH; return; }
    if (!ok) { if (out) st64(out, f->pattern); c.r[3] = CELL_ETIMEDOUT; return; }
    eflag_take(*f, bits, mode, out);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(86, sys_event_flag_trywait) {    // (id, bits, mode, u64* result)
    std::lock_guard<std::mutex> lk(g_mx);
    EFlag* f = g_eflag.get(arg_u32(c, 0));
    if (!f) { c.r[3] = CELL_ESRCH; return; }
    uint64_t bits = arg_u64(c, 1);
    uint32_t mode = arg_u32(c, 2), out = arg_u32(c, 3);
    if (!eflag_match(f->pattern, bits, mode)) { if (out) st64(out, f->pattern); c.r[3] = CELL_EBUSY; return; }
    eflag_take(*f, bits, mode, out);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(87, sys_event_flag_set) {    // (id, bits)
    std::lock_guard<std::mutex> lk(g_mx);
    EFlag* f = g_eflag.get(arg_u32(c, 0));
    if (!f) { c.r[3] = CELL_ESRCH; return; }
    f->pattern |= arg_u64(c, 1);
    g_cv.notify_all();
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(118, sys_event_flag_clear) { // (id, bits): the pattern is ANDed with them
    std::lock_guard<std::mutex> lk(g_mx);
    EFlag* f = g_eflag.get(arg_u32(c, 0));
    if (!f) { c.r[3] = CELL_ESRCH; return; }
    f->pattern &= arg_u64(c, 1);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(139, sys_event_flag_get) {   // (id, u64* pattern)
    std::lock_guard<std::mutex> lk(g_mx);
    EFlag* f = g_eflag.get(arg_u32(c, 0));
    if (!f) { c.r[3] = CELL_ESRCH; return; }
    st64(arg_u32(c, 1), f->pattern);
    c.r[3] = CELL_OK;
}

// ---- lv2: event queue and port -------------------------------------------------------------------
LV2_SYSCALL(128, sys_event_queue_create) {   // (u32* id, attribute*, ipc key, size)
    std::lock_guard<std::mutex> lk(g_mx);
    EQueue q;
    int32_t size = (int32_t)arg_u32(c, 3);
    if (size > 0) q.size = (uint32_t)size;
    st32(arg_u32(c, 0), g_equeue.add(q));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(129, sys_event_queue_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    c.r[3] = g_equeue.m.erase(arg_u32(c, 0)) ? CELL_OK : CELL_ESRCH;
    g_cv.notify_all();
}

// The event comes back in registers, r4-r7: source, data1, data2, data3.
LV2_SYSCALL(130, sys_event_queue_receive) {  // (id, unused event*, timeout)
    uint32_t id = arg_u32(c, 0);
    std::unique_lock<std::mutex> lk(g_mx);
    if (!g_equeue.get(id)) { c.r[3] = CELL_ESRCH; return; }
    bool ok = wait_for(lk, arg_u64(c, 2), [id] { EQueue* q = g_equeue.get(id); return !q || !q->events.empty(); });
    EQueue* q = g_equeue.get(id);
    if (!q) { c.r[3] = 0x80010013u; return; }   // ECANCELED: destroyed while waiting
    if (!ok) { c.r[3] = CELL_ETIMEDOUT; return; }
    auto e = q->events.front();
    q->events.pop_front();
    c.r[4] = e[0]; c.r[5] = e[1]; c.r[6] = e[2]; c.r[7] = e[3];
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(133, sys_event_queue_drain) {
    std::lock_guard<std::mutex> lk(g_mx);
    EQueue* q = g_equeue.get(arg_u32(c, 0));
    if (!q) { c.r[3] = CELL_ESRCH; return; }
    q->events.clear();
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(134, sys_event_port_create) {    // (u32* id, type, name)
    std::lock_guard<std::mutex> lk(g_mx);
    EPort p;
    uint32_t id = g_eport.next;
    p.name = arg_u64(c, 2) ? arg_u64(c, 2) : (0x1ull << 32) | id;   // unnamed: the process and the port
    st32(arg_u32(c, 0), g_eport.add(p));
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(135, sys_event_port_destroy) {
    std::lock_guard<std::mutex> lk(g_mx);
    c.r[3] = g_eport.m.erase(arg_u32(c, 0)) ? CELL_OK : CELL_ESRCH;
}

LV2_SYSCALL(136, sys_event_port_connect_local) {   // (port, queue)
    std::lock_guard<std::mutex> lk(g_mx);
    EPort* p = g_eport.get(arg_u32(c, 0));
    if (!p || !g_equeue.get(arg_u32(c, 1))) { c.r[3] = CELL_ESRCH; return; }
    if (p->queue) { c.r[3] = CELL_EISCONN; return; }
    p->queue = arg_u32(c, 1);
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(137, sys_event_port_disconnect) {
    std::lock_guard<std::mutex> lk(g_mx);
    EPort* p = g_eport.get(arg_u32(c, 0));
    if (!p) { c.r[3] = CELL_ESRCH; return; }
    if (!p->queue) { c.r[3] = CELL_ENOTCONN; return; }
    p->queue = 0;
    c.r[3] = CELL_OK;
}

LV2_SYSCALL(138, sys_event_port_send) {      // (port, data1, data2, data3)
    std::lock_guard<std::mutex> lk(g_mx);
    EPort* p = g_eport.get(arg_u32(c, 0));
    if (!p) { c.r[3] = CELL_ESRCH; return; }
    EQueue* q = p->queue ? g_equeue.get(p->queue) : nullptr;
    if (!q) { c.r[3] = CELL_ENOTCONN; return; }
    if (q->events.size() >= q->size) { c.r[3] = CELL_EBUSY; return; }
    q->events.push_back({p->name, arg_u64(c, 1), arg_u64(c, 2), arg_u64(c, 3)});
    g_cv.notify_all();
    c.r[3] = CELL_OK;
}

// For the runtime's own event sources (audio, system callbacks): an event
// into a queue by id, as if a port had sent it. False if the queue is gone or full.
bool lv2_event_queue_push(uint32_t queue, uint64_t source, uint64_t d1, uint64_t d2, uint64_t d3) {
    std::lock_guard<std::mutex> lk(g_mx);
    EQueue* q = g_equeue.get(queue);
    if (!q || q->events.size() >= q->size) return false;
    q->events.push_back({source, d1, d2, d3});
    g_cv.notify_all();
    return true;
}
