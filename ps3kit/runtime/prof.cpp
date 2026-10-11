// ps3kit runtime — where the time goes, in wall-clock terms per thread role:
// PS3KIT_PROF=1 reports, every 30 flips, how long each part spent in each
// state over that stretch, so that a frame-rate drop can be put on the game,
// the FIFO capture, the renderer or the GPU without guessing.
//
//   fifo idle      the RSX thread waiting for the game to put commands
//   fifo sema      it waiting on a semaphore the game or the GPU releases
//   fifo capture   it copying and hashing what draws read (rsxcap end_draw)
//   fifo vblank    a flip waiting for the vertical blank
//   fifo submit    a flip waiting for the renderer to have room
//   render exec    the window's thread running records on the GL context
//   render swap    its share of that spent presenting
//   render idle    it waiting for a record
//   render compile its share of exec spent translating and linking new programs
//   render upload  its share spent making new textures
//   spu jobs       SPURS jobs, run on the threads that push them
#include "rt.h"
#include <atomic>
#include <chrono>
#include <cstdlib>

namespace {
std::atomic<uint64_t> g_ns[PROF_N];
std::atomic<uint64_t> g_count[PROFC_N];
const char* const kNames[PROF_N] = {"fifo idle", "fifo sema", "fifo capture", "fifo vblank", "fifo submit",
                                    "render exec", "render swap", "render idle", "render compile", "render upload",
                                    "spu jobs"};
std::chrono::steady_clock::time_point g_since = std::chrono::steady_clock::now();
uint32_t g_flips = 0;
}  // namespace

const bool g_prof = std::getenv("PS3KIT_PROF") != nullptr;

uint64_t prof_now() {
    return (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(
               std::chrono::steady_clock::now().time_since_epoch()).count();
}

void prof_add(int slot, uint64_t ns) { g_ns[slot].fetch_add(ns, std::memory_order_relaxed); }
void prof_count(int slot, uint64_t n) { g_count[slot].fetch_add(n, std::memory_order_relaxed); }

void prof_flip() {
    if (!g_prof || ++g_flips % 30) return;
    auto now = std::chrono::steady_clock::now();
    double wall = std::chrono::duration<double, std::milli>(now - g_since).count();
    g_since = now;
    char line[768];
    int n = std::snprintf(line, sizeof line, "prof: 30 flips in %.0f ms (%.1f fps) |", wall, 30000.0 / wall);
    for (int i = 0; i < PROF_N && n < (int)sizeof line; ++i)
        n += std::snprintf(line + n, sizeof line - n, " %s %.0f", kNames[i], g_ns[i].exchange(0) / 1e6);
    uint64_t draws = g_count[PROFC_DRAWS].exchange(0), hashed = g_count[PROFC_HASHED].exchange(0),
             sent = g_count[PROFC_SENT].exchange(0), progs = g_count[PROFC_PROGRAMS].exchange(0),
             texs = g_count[PROFC_TEXTURES].exchange(0);
    if (n < (int)sizeof line)
        std::snprintf(line + n, sizeof line - n, " | %llu draws, %.1f MB hashed, %.1f MB sent, %llu new programs, %llu new textures",
                      (unsigned long long)draws, hashed / 1e6, sent / 1e6, (unsigned long long)progs,
                      (unsigned long long)texs);
    rt_log("%s", line);
}
