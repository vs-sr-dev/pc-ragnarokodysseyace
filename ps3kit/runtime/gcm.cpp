// ps3kit runtime — cellGcmSys and cellResc, and the RSX as far as the game's
// command stream needs one to keep going: a thread that consumes the FIFO
// between GET and PUT, follows its jumps, calls and returns, executes the
// methods that synchronise (references, semaphores, labels) and the flip,
// and a vblank clock at 59.94 Hz that paces flips and runs the handlers.
//
// Nothing is drawn yet: every other method is counted and skipped. The
// counts are what the renderer will be written against.
//
// The default FIFO is libgcm's: the command area at the start of the I/O
// region is cut into 32 KB segments, the first 4 KB reserved; when one fills,
// the callback flushes PUT, writes a jump into the next and waits for the RSX
// to have left it.
#include "rt.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <map>
#include <mutex>
#include <pthread.h>
#include <thread>

namespace {
constexpr uint32_t kFailure = 0x802100FFu;          // CELL_GCM_ERROR_FAILURE
constexpr uint32_t kLocalSize = 0x0F900000u;        // what the system gives a game of the 256 MB
constexpr uint32_t kSegment = 0x8000u;

uint32_t g_io_addr, g_io_size, g_cmd_size, g_segments;
uint32_t g_ctx;                                     // the CellGcmContextData the game writes through
uint32_t g_control;                                 // CellGcmControl: put, get, ref
uint32_t g_labels;                                  // the semaphore area, 0x10 bytes a label
uint32_t g_callback;                                // the descriptor of cellGcmCallback
uint32_t g_command_words = 0x400, g_segment_words = 0x100;

std::atomic<uint32_t> g_flip_status{0};             // CELL_GCM_DISPLAY_FLIP_STATUS_DONE
std::atomic<uint64_t> g_vblank_count{0};
std::atomic<uint32_t> g_flips{0};
std::atomic<uint32_t> g_flip_handler{0}, g_vblank_handler{0};
std::atomic<uint32_t> g_resc_flip_handler{0}, g_resc_vblank_handler{0};
uint32_t g_flip_mode = 1;                           // CELL_GCM_DISPLAY_VSYNC
struct Display { uint32_t offset, pitch, width, height; } g_display[8];

std::mutex g_vblank_mx;
std::condition_variable_any g_vblank_cv;
std::mutex g_stats_mx;
std::map<uint32_t, uint64_t> g_method_counts;

void gcm_report(int top);
uint32_t put() { return ld32(g_control); }
uint32_t get() { return ld32(g_control + 4); }

// ---- the command buffer, written from the runtime side --------------------------------------
void callback(PPUContext& c);

void write_command(PPUContext& c, uint32_t ctx, uint32_t method, std::initializer_list<uint32_t> args) {
    uint32_t n = (uint32_t)args.size();
    if (ld32(ctx + 8) + 4 * (n + 1) >= ld32(ctx + 4)) {
        PPUContext t = c;
        t.r[3] = ctx;
        t.r[4] = n + 1;
        if (ld32(ctx + 12) == g_callback) callback(t);
        else ppu_call_guest(c, ld32(ctx + 12), ctx, n + 1);
    }
    uint32_t cur = ld32(ctx + 8);
    st32(cur, (n << 18) | method);
    uint32_t k = 1;
    for (uint32_t a : args) st32(cur + 4 * k++, a);
    st32(ctx + 8, cur + 4 * (n + 1));
}

// cellGcmCallback(context, count): the current segment is full.
void callback(PPUContext& c) {
    uint32_t ctx = arg_u32(c, 0);
    uint32_t cur = ld32(ctx + 8);
    st32(g_control, cur - g_io_addr);                               // flush up to here
    uint32_t seg = (cur - g_io_addr) / kSegment, next = (seg + 1) % g_segments;
    uint32_t begin = g_io_addr + next * kSegment + (next == 0 ? 0x1000 : 0);
    uint32_t end = g_io_addr + next * kSegment + kSegment - 4;
    st32(cur, 0x20000000u | (begin - g_io_addr));                   // jump there
    st32(ctx, begin);
    st32(ctx + 4, end);
    st32(ctx + 8, begin);
    for (;;) {                                                      // until the RSX has left it
        uint32_t g = g_io_addr + get();
        if (g < begin - (next == 0 ? 0x1000 : 0) || g > end) break;
        std::this_thread::yield();
    }
    c.r[3] = CELL_OK;
}

// ---- the RSX ------------------------------------------------------------------------------------
void flip(uint32_t id) {
    if (g_flip_mode == 1) {                                         // wait for the next vblank
        std::unique_lock<std::mutex> lk(g_vblank_mx);
        uint64_t v = g_vblank_count.load();
        g_vblank_cv.wait(lk, [v] { return g_vblank_count.load() != v; });
    }
    g_flip_status = 0;
    uint32_t n = ++g_flips;
    if (n <= 5 || n % 300 == 0) {
        const Display& d = g_display[id & 7];
        rt_log("rsx: flip %u to buffer %u (offset %X, %ux%u, pitch %X)", n, id, d.offset, d.width, d.height, d.pitch);
    }
    if (n == 60 || n % 1800 == 0) gcm_report(12);
    if (uint32_t h = g_flip_handler) ppu_intr_post(h, 1);
    if (uint32_t h = g_resc_flip_handler) ppu_intr_post(h, 1);
}

void method(uint32_t m, uint32_t arg, uint32_t& sem406e, uint32_t& sem4097) {
    switch (m) {
    case 0x0050: st32(g_control + 8, arg); return;                  // NV406E_SET_REFERENCE
    case 0x0064: sem406e = arg; return;                             // NV406E_SEMAPHORE_OFFSET
    case 0x0068:                                                    // NV406E_SEMAPHORE_ACQUIRE
        while (ld32(g_labels + sem406e) != arg) std::this_thread::yield();
        return;
    case 0x006C: st32(g_labels + sem406e, arg); return;             // NV406E_SEMAPHORE_RELEASE
    case 0x1D6C: sem4097 = arg; return;                             // NV4097_SET_SEMAPHORE_OFFSET
    case 0x1D70:                                                    // NV4097_BACK_END_WRITE_SEMAPHORE_RELEASE
        st32(g_labels + sem4097, (arg & 0xFF00FF00u) | (arg & 0xFF) << 16 | (arg >> 16 & 0xFF));
        return;
    case 0x1D74: st32(g_labels + sem4097, arg); return;             // NV4097_TEXTURE_READ_SEMAPHORE_RELEASE
    case 0xFEAC: flip(arg); return;                                 // GCM_FLIP_COMMAND
    default: break;
    }
    std::lock_guard<std::mutex> lk(g_stats_mx);
    ++g_method_counts[m];
}

void* rsx_main(void*) {
    uint32_t stack[8] = {}, depth = 0, sem406e = 0, sem4097 = 0;
    for (;;) {
        uint32_t g = get();
        if (g == put()) { std::this_thread::sleep_for(std::chrono::microseconds(50)); continue; }
        uint32_t cmd = ld32(g_io_addr + g);
        if ((cmd & 0xE0000003u) == 0x20000000u) { st32(g_control + 4, cmd & 0x1FFFFFFCu); continue; }  // old jump
        if ((cmd & 3) == 1) { st32(g_control + 4, cmd & ~3u); continue; }                            // jump
        if ((cmd & 3) == 2) {                                                                         // call
            if (depth < 8) stack[depth++] = g + 4;
            st32(g_control + 4, cmd & ~3u);
            continue;
        }
        if (cmd == 0x00020000u) { st32(g_control + 4, depth ? stack[--depth] : g + 4); continue; }   // return
        uint32_t count = (cmd >> 18) & 0x7FF, m = cmd & 0xFFFC;
        bool inc = !(cmd & 0x40000000u);
        for (uint32_t i = 0; i < count; ++i)
            method(inc ? m + 4 * i : m, ld32(g_io_addr + g + 4 + 4 * i), sem406e, sem4097);
        st32(g_control + 4, g + 4 + 4 * count);
    }
    return nullptr;
}

void* vblank_main(void*) {
    using namespace std::chrono;
    auto next = steady_clock::now();
    const auto period = nanoseconds(16683350);                      // 59.94 Hz
    for (;;) {
        next += period;
        std::this_thread::sleep_until(next);
        {
            std::lock_guard<std::mutex> lk(g_vblank_mx);
            ++g_vblank_count;
        }
        g_vblank_cv.notify_all();
        if (uint32_t h = g_vblank_handler) ppu_intr_post(h, 1);
        if (uint32_t h = g_resc_vblank_handler) ppu_intr_post(h, 1);
    }
    return nullptr;
}

void start(void* (*fn)(void*)) {
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    pthread_t h;
    pthread_create(&h, &attr, fn, nullptr);
    pthread_attr_destroy(&attr);
}
}  // namespace

// ---- cellGcmSys ------------------------------------------------------------------------------
PS3_HLE(_cellGcmInitBody) {              // (CellGcmContextData** context, cmd size, io size, io address)
    uint32_t pctx = arg_u32(c, 0);
    g_cmd_size = arg_u32(c, 1);
    g_io_size = arg_u32(c, 2);
    g_io_addr = arg_u32(c, 3);
    g_segments = g_cmd_size / kSegment ? g_cmd_size / kSegment : 1;
    g_control = hle_alloc(0x1000, 0x1000) + 0x40;
    g_labels = hle_alloc(0x1000, 0x1000);
    st32(g_control, 0x1000);                                        // put
    st32(g_control + 4, 0x1000);                                    // get
    g_callback = hle_internal("cellGcmCallback", callback);
    g_ctx = hle_alloc(16, 16);
    st32(g_ctx, g_io_addr + 0x1000);                                // begin
    st32(g_ctx + 4, g_io_addr + kSegment - 4);                      // end, the last word kept for a jump
    st32(g_ctx + 8, g_io_addr + 0x1000);                            // current
    st32(g_ctx + 12, g_callback);
    st32(pctx, g_ctx);
    rt_log("gcm: io %08X+%X, command area %X (%u segments), local %08X+%X, control %08X",
           g_io_addr, g_io_size, g_cmd_size, g_segments, mm::VIDEO, kLocalSize, g_control);
    start(rsx_main);
    start(vblank_main);
    c.r[3] = CELL_OK;
}

PS3_HLE(_cellGcmFunc15) { c.r[3] = CELL_OK; }
PS3_HLE(cellGcmGetControlRegister) { c.r[3] = g_control; }
PS3_HLE(cellGcmGetDefaultCommandWordSize) { c.r[3] = g_command_words; }
PS3_HLE(cellGcmGetDefaultSegmentWordSize) { c.r[3] = g_segment_words; }
PS3_HLE(cellGcmSetDefaultFifoSize) {     // (buffer words, segment words)
    g_command_words = arg_u32(c, 0);
    g_segment_words = arg_u32(c, 1);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellGcmGetConfiguration) {       // (CellGcmConfig*)
    uint32_t p = arg_u32(c, 0);
    st32(p, mm::VIDEO);                  // localAddress
    st32(p + 4, g_io_addr);              // ioAddress
    st32(p + 8, kLocalSize);
    st32(p + 12, g_io_size);
    st32(p + 16, 650000000);             // memoryFrequency
    st32(p + 20, 500000000);             // coreFrequency
}

PS3_HLE(cellGcmAddressToOffset) {        // (address, u32* offset)
    uint32_t a = arg_u32(c, 0), out = arg_u32(c, 1);
    if (a - mm::VIDEO < kLocalSize) st32(out, a - mm::VIDEO);
    else if (a - g_io_addr < g_io_size) st32(out, a - g_io_addr);
    else { c.r[3] = kFailure; return; }
    c.r[3] = CELL_OK;
}

PS3_HLE(cellGcmGetTiledPitchSize) {
    static const uint32_t pitches[] = {
        0x0000, 0x0200, 0x0300, 0x0400, 0x0500, 0x0600, 0x0700, 0x0800, 0x0A00, 0x0C00, 0x0D00,
        0x0E00, 0x1000, 0x1400, 0x1800, 0x1A00, 0x1C00, 0x2000, 0x2800, 0x3000, 0x3400, 0x3800,
        0x4000, 0x5000, 0x6000, 0x6800, 0x7000, 0x8000, 0xA000, 0xC000, 0xD000, 0xE000, 0x10000};
    uint32_t size = arg_u32(c, 0);
    c.r[3] = 0;
    for (size_t i = 0; i + 1 < sizeof pitches / sizeof *pitches; ++i)
        if (pitches[i] < size && size <= pitches[i + 1]) { c.r[3] = pitches[i + 1]; break; }
}

PS3_HLE(cellGcmSetDisplayBuffer) {       // (id, offset, pitch, width, height)
    uint32_t id = arg_u32(c, 0);
    if (id > 7) { c.r[3] = kFailure; return; }
    g_display[id] = {arg_u32(c, 1), arg_u32(c, 2), arg_u32(c, 3), arg_u32(c, 4)};
    c.r[3] = CELL_OK;
}

PS3_HLE(cellGcmGetFlipStatus) { c.r[3] = g_flip_status.load(); }
PS3_HLE(cellGcmResetFlipStatus) { g_flip_status = 1; }
PS3_HLE(cellGcmSetFlipMode) { g_flip_mode = arg_u32(c, 0); }
PS3_HLE(cellGcmSetFlipHandler) { g_flip_handler = arg_u32(c, 0); }
PS3_HLE(cellGcmSetVBlankHandler) { g_vblank_handler = arg_u32(c, 0); }
PS3_HLE(cellGcmSetVBlankFrequency) { c.r[3] = CELL_OK; }
PS3_HLE(cellGcmGetVBlankCount) { c.r[3] = g_vblank_count.load(); }
PS3_HLE(cellGcmSetTileInfo) { c.r[3] = CELL_OK; }
PS3_HLE(cellGcmBindTile) { c.r[3] = CELL_OK; }
PS3_HLE(cellGcmUnbindTile) { c.r[3] = CELL_OK; }
PS3_HLE(cellGcmBindZcull) { c.r[3] = CELL_OK; }
PS3_HLE(cellGcmUnbindZcull) { c.r[3] = CELL_OK; }

PS3_HLE(_cellGcmSetFlipCommand) {        // (context, buffer id)
    write_command(c, arg_u32(c, 0), 0xFEAC, {arg_u32(c, 1)});
    c.r[3] = arg_u32(c, 1);
}

PS3_HLE(_cellGcmSetFlipCommandWithWaitLabel) {   // (context, buffer id, label index, label value)
    uint32_t ctx = arg_u32(c, 0), id = arg_u32(c, 1);
    write_command(c, ctx, 0x0064, {arg_u32(c, 2) * 0x10, arg_u32(c, 3)});    // then ACQUIRE: wait for it
    write_command(c, ctx, 0xFEAC, {id});
    c.r[3] = id;
}

// ---- cellResc ----------------------------------------------------------------------------------
// The scaler between the game's render size and the display. Converting is
// the renderer's job; here a "convert and flip" flips the source buffer.
//
// cellRescGetBufferSize is a reading, not the library: the colour buffers
// are sized for the largest destination the game both supports and has
// registered, times the buffers that mode needs (two; three or six at 576
// lines with PAL temporal conversion). The vertex array and fragment shader
// sizes are the runtime's own. A game sizes its local memory around the
// first number, so it is the one that matters.
namespace {
struct RescSrc { uint32_t format, pitch, width, height, offset; } g_resc_src[8];
uint32_t g_resc_mode = 4;                // CELL_RESC_1280x720
uint32_t g_resc_modes = 0, g_resc_pal = 0;
uint32_t g_resc_pitch[16], g_resc_align[16];
}

PS3_HLE(cellRescInit) {                  // (CellRescInitConfig*)
    uint32_t p = arg_u32(c, 0);
    g_resc_modes = ld32(p + 8);
    g_resc_pal = ld32(p + 16);
    c.r[3] = CELL_OK;
}
PS3_HLE(cellRescVideoOutResolutionId2RescBufferMode) {   // (resolution id, u32* mode)
    static const uint32_t mode[] = {0, 8, 4, 0, 1, 2};      // 1080, 720, -, 480, 576
    uint32_t id = arg_u32(c, 0);
    if (id == 0 || id > 5 || !mode[id]) { c.r[3] = 0x80210304u; return; }   // CELL_RESC_ERROR_BAD_ARGUMENT
    st32(arg_u32(c, 1), mode[id]);
    c.r[3] = CELL_OK;
}
PS3_HLE(cellRescSetDsts) {               // (mode, CellRescDsts*: format, pitch, heightAlign)
    uint32_t m = arg_u32(c, 0) & 15, p = arg_u32(c, 1);
    g_resc_pitch[m] = ld32(p + 4);
    g_resc_align[m] = ld32(p + 8);
    c.r[3] = CELL_OK;
}
PS3_HLE(cellRescSetDisplayMode) { g_resc_mode = arg_u32(c, 0); c.r[3] = CELL_OK; }
PS3_HLE(cellRescAdjustAspectRatio) { c.r[3] = CELL_OK; }
PS3_HLE(cellRescGetBufferSize) {         // (s32* color buffers, s32* vertex array, s32* fragment shader)
    uint32_t color = 0;
    for (uint32_t m : {1u, 2u, 4u, 8u}) {    // 480, 576, 720, 1080 lines
        if (!(g_resc_modes & m) || !g_resc_pitch[m]) continue;
        uint32_t h = m == 8 ? 1080 : m == 4 ? 720 : m == 2 ? 576 : 480, a = g_resc_align[m] ? g_resc_align[m] : 1;
        uint32_t n = m != 2 ? 2 : g_resc_pal == 1 ? 3 : g_resc_pal >= 2 && g_resc_pal <= 4 ? 6 : 2;   // PAL_60_DROP, _INTERPOLATE*
        uint32_t size = n * g_resc_pitch[m] * ((h + a - 1) / a * a);
        if (size > color) color = size;
    }
    if (arg_u32(c, 0)) st32(arg_u32(c, 0), color);
    if (arg_u32(c, 1)) st32(arg_u32(c, 1), 0x100);
    if (arg_u32(c, 2)) st32(arg_u32(c, 2), 0x400);
    c.r[3] = CELL_OK;
}
PS3_HLE(cellRescSetBufferAddress) { c.r[3] = CELL_OK; }
PS3_HLE(cellRescSetSrc) {                // (idx, CellRescSrc*: format, pitch, u16 width, u16 height, offset)
    uint32_t i = arg_u32(c, 0), p = arg_u32(c, 1);
    if (i > 7) { c.r[3] = 0x80210304u; return; }
    g_resc_src[i] = {ld32(p), ld32(p + 4), ld16(p + 8), ld16(p + 10), ld32(p + 12)};
    g_display[i] = {g_resc_src[i].offset, g_resc_src[i].pitch, g_resc_src[i].width, g_resc_src[i].height};
    c.r[3] = CELL_OK;
}
PS3_HLE(cellRescSetConvertAndFlip) {     // (context, idx)
    write_command(c, arg_u32(c, 0), 0xFEAC, {arg_u32(c, 1)});
    c.r[3] = CELL_OK;
}
PS3_HLE(cellRescResetFlipStatus) { g_flip_status = 1; }
PS3_HLE(cellRescSetFlipHandler) { g_resc_flip_handler = arg_u32(c, 0); }
PS3_HLE(cellRescSetVBlankHandler) { g_resc_vblank_handler = arg_u32(c, 0); }

// The methods seen and skipped, most frequent first: what the renderer has to do.
namespace {
void gcm_report(int top) {
    std::lock_guard<std::mutex> lk(g_stats_mx);
    std::multimap<uint64_t, uint32_t, std::greater<uint64_t>> by;
    for (auto& [m, n] : g_method_counts) by.insert({n, m});
    rt_log("rsx: %u flips, %zu distinct methods skipped", g_flips.load(), g_method_counts.size());
    for (auto& [n, m] : by) {
        if (top-- <= 0) break;
        rt_log("  %04X  %llu", m, (unsigned long long)n);
    }
}
}  // namespace
