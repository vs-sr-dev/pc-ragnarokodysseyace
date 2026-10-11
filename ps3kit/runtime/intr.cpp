// ps3kit runtime — the interrupt thread: one host thread with a guest context of
// its own that runs the game's callbacks (vblank and flip handlers, system
// event callbacks) one at a time, in the order they were posted, the way
// lv2 runs them on an interrupt PPU thread.
#include "rt.h"
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <mutex>
#include <pthread.h>
#include <utility>

namespace {
std::mutex g_mx;
std::condition_variable g_cv;
std::deque<std::pair<uint32_t, uint64_t>> g_queue;
PPUContext* g_ctx = nullptr;

void* intr_main(void*) {
    for (;;) {
        std::pair<uint32_t, uint64_t> job;
        {
            std::unique_lock<std::mutex> lk(g_mx);
            g_cv.wait(lk, [] { return !g_queue.empty(); });
            job = g_queue.front();
            g_queue.pop_front();
        }
        try {
            ppu_call_guest(*g_ctx, job.first, job.second);
        } catch (const PPUExit& e) {
            rt_log("ps3kit: the process exited with %d (from a callback)", e.code);
            std::fflush(stdout);
            std::fflush(stderr);
            std::_Exit(e.code);
        } catch (const PPUThreadExit&) {
        }
    }
    return nullptr;
}
}  // namespace

void ppu_intr_post(uint32_t desc, uint64_t arg) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_ctx) {
        g_ctx = ppu_context_new(0x10000, "_intr_thread");
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setstacksize(&attr, 64u << 20);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
        pthread_t h;
        pthread_create(&h, &attr, intr_main, nullptr);
        pthread_attr_destroy(&attr);
    }
    if (g_queue.size() > 64) return;      // a callback that never returns: drop rather than grow
    g_queue.push_back({desc, arg});
    g_cv.notify_one();
}
