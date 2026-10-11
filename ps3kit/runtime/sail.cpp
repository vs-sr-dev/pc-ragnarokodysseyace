// ps3kit runtime — cellSail, the system's movie player: PAMF files, their
// MPEG-2 video decoded by the runtime's own decoder and handed to the game
// as frames it draws itself.
//
// A player is a thread of its own that runs the game's calls in order and
// tells the game about them through its callback: the calls return at once,
// and the game polls what its callback recorded. The events, in order:
//
//   Boot         state BOOT_TRANSITION, state CLOSED, call completed (BOOT)
//   OpenStream   state OPEN_TRANSITION, stream opened (the descriptor),
//                state OPENED, call completed (OPEN_STREAM)
//   Start        state START_TRANSITION, session started, state RUNNING,
//                call completed (START); at the end of the stream, source
//                end (EOS), then state OPENED
//   Stop         state STOP_TRANSITION, state OPENED, call completed (STOP)
//   CloseStream  state CLOSE_TRANSITION, stream closed (the descriptor),
//                state CLOSED, call completed (CLOSE_STREAM)
//
// The graphics adapter is the game's: it allocates the frame buffers through
// its callback and takes each frame with GetFrame2 when it draws. Frames are
// decoded ahead into those buffers and shown at their presentation times, on
// the host's clock from the first frame decoded.
//
// PS3KIT_SAIL=1 reports every call and event.
#include "rt.h"
#include "mpeg2.h"
#include "mpegps.h"
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <map>
#include <mutex>
#include <pthread.h>
#include <string>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;

constexpr uint32_t ERR_INVALID_ARG = 0x80610701u, ERR_INVALID_STATE = 0x80610702u,
                   ERR_UNSUPPORTED = 0x80610703u, ERR_EMPTY = 0x80610705u, ERR_MEMORY = 0x806107F0u;
enum Event { EV_ERROR = 1, EV_CALL_COMPLETED, EV_STATE_CHANGED, EV_STREAM_OPENED, EV_STREAM_CLOSED,
             EV_SESSION_STARTED, EV_PAUSE_STATE_CHANGED, EV_SOURCE_EOS };
enum Call { CALL_BOOT = 1, CALL_OPEN_STREAM = 2, CALL_CLOSE_STREAM = 3, CALL_START = 10, CALL_STOP = 11 };
enum State { ST_INITIALIZED, ST_BOOT_TRANSITION, ST_CLOSED, ST_OPEN_TRANSITION, ST_OPENED,
             ST_START_TRANSITION, ST_RUNNING, ST_STOP_TRANSITION, ST_CLOSE_TRANSITION, ST_LOST };
constexpr int kFrames = 4;               // frame buffers asked of the adapter: two shown, two ahead

const bool g_trace = std::getenv("PS3KIT_SAIL") != nullptr;

struct Adapter {
    uint32_t addr = 0;
    uint32_t make_up = 0, clean_up = 0, format_changed = 0, alloc = 0, free = 0, arg = 0;
    uint8_t preferred[32];
    uint8_t format[32];                  // CellSailVideoFormat of the current session
    uint32_t format_addr = 0, frames_addr = 0;
};

struct Descriptor {
    uint32_t addr = 0;
    std::string uri, host;
    uint64_t data_offset = 0;            // where the program stream starts
    uint32_t first_pts = 0, last_pts = 0;
};

struct Slot {                            // one frame buffer
    uint32_t addr = 0;
    int64_t index = -1;                  // the frame it holds, in display order
    uint64_t pts = 0;
};

struct Player {
    uint32_t self = 0, callback = 0, callback_arg = 0;
    Adapter* gfx = nullptr;
    std::vector<Descriptor*> descriptors;
    Descriptor* stream = nullptr;
    int state = ST_INITIALIZED;
    int repeat = 0;
    bool paused = false;

    pthread_t thread{};
    PPUContext* ctx = nullptr;
    std::mutex mx;
    std::condition_variable cv;
    std::deque<int> calls;               // Call codes, plus 100 for pause and 101 for resume
    bool quit = false;

    // The session.
    uint32_t session = 0;
    bool running = false, source_done = false, eos_sent = false, frames_allocated = false;
    MpegPsReader reader;
    Mpeg2Decoder decoder;
    std::deque<std::pair<std::vector<uint8_t>, uint64_t>> decoded;   // ARGB, pts, not yet in a slot
    Slot slots[kFrames];
    uint32_t frame_size = 0;
    int64_t next_index = 0, shown = -1, last_index = -1;
    uint64_t next_pts = 0, frame_ticks = 3003, last_ticks = 3003;
    Clock::time_point t0;
    bool clock_started = false;
    Clock::time_point pause_start;
};

std::mutex g_mx;
std::map<uint32_t, Player*> g_players;                 // by the game's CellSailPlayer
std::map<uint32_t, Adapter*> g_adapters;               // by the game's CellSailGraphicsAdapter
std::map<uint32_t, Descriptor*> g_descriptors;

Player* player(uint32_t addr) {
    std::lock_guard<std::mutex> lk(g_mx);
    auto it = g_players.find(addr);
    return it == g_players.end() ? nullptr : it->second;
}
Adapter* adapter(uint32_t addr) {
    std::lock_guard<std::mutex> lk(g_mx);
    auto& a = g_adapters[addr];
    if (!a) { a = new Adapter; a->addr = addr; std::memset(a->preferred, 0xFF, 32); }
    return a;
}
Descriptor* descriptor(uint32_t addr) {
    std::lock_guard<std::mutex> lk(g_mx);
    auto it = g_descriptors.find(addr);
    return it == g_descriptors.end() ? nullptr : it->second;
}

// ---- events, on the player's thread
void notify(Player& p, uint32_t major, uint32_t minor, uint64_t arg0 = 0, uint64_t arg1 = 0) {
    if (g_trace) rt_log("sail: event %u.%u (%llX)", major, minor, (unsigned long long)arg0);
    if (p.callback) ppu_call_guest(*p.ctx, p.callback, p.callback_arg, (uint64_t)major << 32 | minor, arg0, arg1);
}
void set_state(Player& p, int s) {
    p.state = s;
    notify(p, EV_STATE_CHANGED, 0, (uint64_t)s);
}

// ---- the picture: 4:2:0 to the adapter's ARGB, BT.709 or BT.601, limited range.
// Chroma is sited as MPEG-2 sites it: with the even luma columns, between
// the luma rows; it is interpolated linearly both ways.
void to_argb(const Mpeg2Picture& pic, uint8_t* out, uint8_t alpha) {
    const bool bt601 = pic.matrix == 5 || pic.matrix == 6;
    const int crv = bt601 ? 104597 : 117489, cbu = bt601 ? 132201 : 138438;      // 16.16
    const int cgu = bt601 ? 25675 : 13975, cgv = bt601 ? 53279 : 34925, ky = 76309;
    const int W = pic.width, H = pic.height, CW = (W + 1) / 2, CH = (H + 1) / 2;
    std::vector<int> cb_row(W), cr_row(W);
    for (int y = 0; y < H; ++y) {
        int k = y >> 1, k2 = (y & 1) ? std::min(k + 1, CH - 1) : std::max(k - 1, 0);
        const uint8_t *b0 = pic.cb + (size_t)k * pic.c_stride, *b1 = pic.cb + (size_t)k2 * pic.c_stride;
        const uint8_t *r0 = pic.cr + (size_t)k * pic.c_stride, *r1 = pic.cr + (size_t)k2 * pic.c_stride;
        for (int x = 0; x < W; ++x) {
            int j = x >> 1, j2 = (x & 1) ? std::min(j + 1, CW - 1) : j;
            // vertical 3:1, then horizontal 1:1 for odd columns; kept at 4x / 8x scale
            int cb = 3 * b0[j] + b1[j], cr = 3 * r0[j] + r1[j];
            int cb2 = 3 * b0[j2] + b1[j2], cr2 = 3 * r0[j2] + r1[j2];
            cb_row[x] = cb + cb2;    // 8x
            cr_row[x] = cr + cr2;
        }
        const uint8_t* yr = pic.y + (size_t)y * pic.y_stride;
        uint8_t* o = out + (size_t)y * W * 4;
        for (int x = 0; x < W; ++x) {
            int Y = (yr[x] - 16) * ky;
            int u = cb_row[x] - 8 * 128, v = cr_row[x] - 8 * 128;   // 8x
            int r = (Y + (crv * v >> 3) + 32768) >> 16;
            int g = (Y - (cgu * u >> 3) - (cgv * v >> 3) + 32768) >> 16;
            int b = (Y + (cbu * u >> 3) + 32768) >> 16;
            o[4 * x] = alpha;
            o[4 * x + 1] = (uint8_t)std::clamp(r, 0, 255);
            o[4 * x + 2] = (uint8_t)std::clamp(g, 0, 255);
            o[4 * x + 3] = (uint8_t)std::clamp(b, 0, 255);
        }
    }
}

uint64_t ticks_of(int frame_rate_code, int fields) {   // one picture's display time, 90 kHz
    static const double fps[9] = {30000.0 / 1001, 24000.0 / 1001, 24, 25, 30000.0 / 1001, 30, 50, 60000.0 / 1001, 60};
    double f = fps[frame_rate_code >= 1 && frame_rate_code <= 8 ? frame_rate_code : 4];
    return (uint64_t)(90000.0 / f * fields / 2 + 0.5);
}

// ---- the session
bool open_descriptor(Descriptor& d) {
    FILE* f = std::fopen(d.host.c_str(), "rb");
    if (!f) return false;
    uint8_t h[0x80] = {};
    size_t n = std::fread(h, 1, sizeof h, f);
    std::fclose(f);
    if (n < 0x62 || std::memcmp(h, "PAMF", 4)) return false;
    auto be32 = [&](int o) { return (uint32_t)h[o] << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]; };
    d.data_offset = (uint64_t)be32(8) * 0x800;
    d.first_pts = be32(0x58);
    d.last_pts = be32(0x5E);
    return true;
}

void start_session(Player& p) {
    Descriptor& d = *p.stream;
    ++p.session;
    p.reader.open(d.host, d.data_offset);
    p.decoder.reset();
    p.decoded.clear();
    p.source_done = p.eos_sent = false;
    p.next_index = 0;
    p.shown = p.last_index = -1;
    p.next_pts = d.first_pts;
    p.clock_started = false;
    for (Slot& s : p.slots) s.index = -1;
    p.decoder.on_picture = [&p](const Mpeg2Picture& pic) {
        Adapter& a = *p.gfx;
        if (!p.frames_allocated) {
            // The format the frames are in: the adapter's preferred one where
            // it says, the stream's where it leaves it unspecified.
            std::memcpy(a.format, a.preferred, 32);
            if ((int8_t)a.format[0] < 0) a.format[0] = 0;                // ARGB interleaved
            a.format[1] = 0;                                              // progressive
            a.format[2] = 8;                                              // bits per colour
            a.format[3] = pic.frame_rate_code == 4 ? 3 : (int8_t)-1;      // 30000/1001 Hz
            a.format[4] = (uint8_t)(pic.width >> 8); a.format[5] = (uint8_t)pic.width;
            a.format[6] = (uint8_t)(pic.height >> 8); a.format[7] = (uint8_t)pic.height;
            uint32_t pitch = (uint32_t)pic.width * 4;
            a.format[8] = (uint8_t)(pitch >> 24); a.format[9] = (uint8_t)(pitch >> 16);
            a.format[10] = (uint8_t)(pitch >> 8); a.format[11] = (uint8_t)pitch;
            if ((int32_t)(a.preferred[12] << 24 | a.preferred[13] << 16 | a.preferred[14] << 8 | a.preferred[15]) < 0)
                std::memset(a.format + 12, 0, 3), a.format[15] = 0xFF;   // alpha
            a.format[16] = pic.matrix == 5 || pic.matrix == 6 ? 0 : 1;    // BT.601 / BT.709
            a.format[17] = 1;                                             // aspect 1:1
            a.format[18] = 0;                                             // full range out
            if (!a.format_addr) a.format_addr = hle_alloc(32);
            mem_write(a.format_addr, a.format, 32);
            if (g_trace) rt_log("sail: format %dx%d, frame rate code %d, matrix %d", pic.width, pic.height,
                                pic.frame_rate_code, pic.matrix);
            if (a.format_changed) ppu_call_guest(*p.ctx, a.format_changed, a.arg, a.format_addr, p.session);
            p.frame_size = pitch * (uint32_t)pic.height;
            if (!a.frames_addr) a.frames_addr = hle_alloc(4 * kFrames);
            int32_t r = a.alloc ? (int32_t)ppu_call_guest(*p.ctx, a.alloc, a.arg, p.frame_size, kFrames, a.frames_addr) : -1;
            if (r < 0) {
                rt_log("sail: the adapter could not allocate %d frames of %u bytes (%d)", kFrames, p.frame_size, r);
                notify(p, EV_ERROR, 0, ERR_MEMORY);
                p.source_done = true;
                return;
            }
            for (int i = 0; i < kFrames; ++i) p.slots[i].addr = ld32(a.frames_addr + 4 * i);
            if (g_trace) rt_log("sail: %d frames of %u bytes at %08X %08X %08X %08X", kFrames, p.frame_size,
                                p.slots[0].addr, p.slots[1].addr, p.slots[2].addr, p.slots[3].addr);
            p.frames_allocated = true;
        }
        std::vector<uint8_t> argb((size_t)p.frame_size);
        uint32_t alpha = a.format[12] << 24 | a.format[13] << 16 | a.format[14] << 8 | a.format[15];
        to_argb(pic, argb.data(), (uint8_t)std::min<uint32_t>(alpha, 255));
        uint64_t pts = p.next_pts;
        p.last_ticks = ticks_of(pic.frame_rate_code, pic.fields);
        p.next_pts += p.last_ticks;
        std::lock_guard<std::mutex> lk(p.mx);
        p.decoded.push_back({std::move(argb), pts});
    };
}

// Decoded frames into free buffers. A buffer is free once the frame two
// before the one shown last is behind it: the renderer may still be reading
// the one before.
void place_frames(Player& p) {
    std::lock_guard<std::mutex> lk(p.mx);
    while (!p.decoded.empty()) {
        int64_t i = p.next_index;
        Slot& s = p.slots[i % kFrames];
        if (s.index >= 0 && s.index >= p.shown - 1) break;
        mem_write(s.addr, p.decoded.front().first.data(), p.frame_size);
        s.index = i;
        s.pts = p.decoded.front().second;
        p.decoded.pop_front();
        ++p.next_index;
        if (!p.clock_started) { p.t0 = Clock::now(); p.clock_started = true; }
    }
}

bool decode_some(Player& p) {            // false at the end of the source
    std::vector<uint8_t> es;
    if (g_trace && !p.next_index && p.decoded.empty()) rt_log("sail: decoding");
    if (!p.reader.read(0xE0, es, 1 << 15)) {
        p.decoder.flush();
        return false;
    }
    p.decoder.push(es.data(), es.size());
    return true;
}

void end_session(Player& p) { p.running = false; p.reader.close(); }

void handle(Player& p, int call) {
    if (g_trace) rt_log("sail: call %d in state %d", call, p.state);
    switch (call) {
    case CALL_BOOT:
        set_state(p, ST_BOOT_TRANSITION);
        set_state(p, ST_CLOSED);
        notify(p, EV_CALL_COMPLETED, CALL_BOOT, 0);
        break;
    case CALL_OPEN_STREAM: {
        set_state(p, ST_OPEN_TRANSITION);
        p.stream = p.descriptors.empty() ? nullptr : p.descriptors.back();
        if (!p.stream || !open_descriptor(*p.stream)) {
            rt_log("sail: cannot open the stream %s", p.stream ? p.stream->uri.c_str() : "(no descriptor)");
            set_state(p, ST_CLOSED);
            notify(p, EV_CALL_COMPLETED, CALL_OPEN_STREAM, ERR_UNSUPPORTED);
            break;
        }
        rt_log("sail: open %s", p.stream->uri.c_str());
        notify(p, EV_STREAM_OPENED, 0, p.stream->addr);
        set_state(p, ST_OPENED);
        notify(p, EV_CALL_COMPLETED, CALL_OPEN_STREAM, 0);
        break;
    }
    case CALL_START:
        set_state(p, ST_START_TRANSITION);
        start_session(p);
        p.running = true;
        notify(p, EV_SESSION_STARTED, 0, p.session);
        set_state(p, ST_RUNNING);
        notify(p, EV_CALL_COMPLETED, CALL_START, 0);
        break;
    case CALL_STOP:
        set_state(p, ST_STOP_TRANSITION);
        end_session(p);
        set_state(p, ST_OPENED);
        notify(p, EV_CALL_COMPLETED, CALL_STOP, 0);
        break;
    case CALL_CLOSE_STREAM:
        set_state(p, ST_CLOSE_TRANSITION);
        end_session(p);
        if (p.stream) notify(p, EV_STREAM_CLOSED, 0, p.stream->addr);
        p.stream = nullptr;
        set_state(p, ST_CLOSED);
        notify(p, EV_CALL_COMPLETED, CALL_CLOSE_STREAM, 0);
        break;
    case 100: case 101: {
        bool pause = call == 100;
        std::lock_guard<std::mutex> lk(p.mx);
        if (pause && !p.paused) p.pause_start = Clock::now();
        if (!pause && p.paused) p.t0 += Clock::now() - p.pause_start;
        p.paused = pause;
        break;
    }
    }
    if (call == 100 || call == 101) notify(p, EV_PAUSE_STATE_CHANGED, 0, call == 100);
}

void* player_main(void* arg) {
    Player& p = *(Player*)arg;
    try {
        for (;;) {
            int call = 0;
            {
                std::unique_lock<std::mutex> lk(p.mx);
                auto work = [&] {
                    if (p.quit || !p.calls.empty()) return true;
                    if (!p.running) return false;
                    if (!p.source_done && p.decoded.size() < 2) return true;
                    if (!p.decoded.empty()) {
                        const Slot& s = p.slots[p.next_index % kFrames];
                        if (s.index < 0 || s.index < p.shown - 1) return true;
                    }
                    return p.source_done && p.decoded.empty() && !p.eos_sent && p.shown == p.last_index;
                };
                p.cv.wait_for(lk, std::chrono::milliseconds(5), work);
                if (p.quit) break;
                if (!p.calls.empty()) { call = p.calls.front(); p.calls.pop_front(); }
            }
            if (call) { handle(p, call); continue; }
            if (!p.running) continue;
            {
                std::unique_lock<std::mutex> lk(p.mx);
                bool want = !p.source_done && p.decoded.size() < 2;
                lk.unlock();
                if (want && !decode_some(p)) {
                    std::lock_guard<std::mutex> lk2(p.mx);
                    p.source_done = true;
                }
            }
            place_frames(p);
            bool end = false;
            {
                std::lock_guard<std::mutex> lk(p.mx);
                if (p.source_done && p.decoded.empty() && p.last_index < 0) p.last_index = p.next_index - 1;
                if (p.source_done && p.decoded.empty() && !p.eos_sent && p.shown >= p.last_index && p.clock_started) {
                    // The last frame has been taken; the source ends when its time is over.
                    const Slot& s = p.slots[(p.last_index < 0 ? 0 : p.last_index) % kFrames];
                    auto due = p.t0 + std::chrono::microseconds((s.pts + p.last_ticks - p.stream->first_pts) * 1000000 / 90000);
                    if (!p.paused && Clock::now() >= due) end = p.eos_sent = true;
                } else if (p.source_done && p.next_index == 0 && !p.eos_sent) {
                    end = p.eos_sent = true;             // nothing decoded at all
                }
            }
            if (end) {
                if (p.repeat) { start_session(p); continue; }
                rt_log("sail: end of %s, %lld frames", p.stream->uri.c_str(), (long long)p.next_index);
                notify(p, EV_SOURCE_EOS, 0, 0);
                end_session(p);
                set_state(p, ST_OPENED);
            }
        }
    } catch (const PPUExit& e) {
        rt_log("ps3kit: the process exited with %d (from a sail callback)", e.code);
        std::fflush(stdout);
        std::fflush(stderr);
        std::_Exit(e.code);
    }
    return nullptr;
}

void post(Player& p, int call) {
    std::lock_guard<std::mutex> lk(p.mx);
    p.calls.push_back(call);
    p.cv.notify_all();
}
}  // namespace

PS3_HLE(cellSailMemAllocatorInitialize) { c.r[3] = CELL_OK; }   // (pSelf, pCallbacks): nothing is allocated through it

PS3_HLE(cellSailPlayerInitialize2) {     // (pSelf, pAllocator, pCallback, callbackArg, pAttribute, pResource)
    uint32_t self = arg_u32(c, 0);
    Player* p = new Player;
    p->self = self;
    p->callback = arg_u32(c, 2);
    p->callback_arg = arg_u32(c, 3);
    p->ctx = ppu_context_new(0x10000, "_sail_player");
    {
        std::lock_guard<std::mutex> lk(g_mx);
        g_players[self] = p;
    }
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 64u << 20);
    pthread_create(&p->thread, &attr, player_main, p);
    pthread_attr_destroy(&attr);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerFinalize) {        // (pSelf)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    {
        std::lock_guard<std::mutex> lk(p->mx);
        p->quit = true;
        p->cv.notify_all();
    }
    pthread_join(p->thread, nullptr);
    if (p->frames_allocated && p->gfx && p->gfx->free)
        ppu_call_guest(c, p->gfx->free, p->gfx->arg, kFrames, p->gfx->frames_addr);
    {
        std::lock_guard<std::mutex> lk(g_mx);
        g_players.erase(p->self);
    }
    delete p;                            // its guest context stays: contexts are never freed
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailGraphicsAdapterInitialize) {   // (pSelf, pCallbacks, pArg)
    Adapter* a = adapter(arg_u32(c, 0));
    uint32_t f = arg_u32(c, 1);
    a->make_up = ld32(f); a->clean_up = ld32(f + 4); a->format_changed = ld32(f + 8);
    a->alloc = ld32(f + 12); a->free = ld32(f + 16);
    a->arg = arg_u32(c, 2);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailGraphicsAdapterSetPreferredFormat) {   // (pSelf, CellSailVideoFormat*)
    mem_read(arg_u32(c, 1), adapter(arg_u32(c, 0))->preferred, 32);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailGraphicsAdapterGetFormat) {   // (pSelf, CellSailVideoFormat*)
    mem_write(arg_u32(c, 1), adapter(arg_u32(c, 0))->format, 32);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerSetGraphicsAdapter) {   // (pSelf, index, pAdapter)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    p->gfx = adapter(arg_u32(c, 2));
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerBoot) {            // (pSelf, userParam)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    post(*p, CALL_BOOT);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerCreateDescriptor) {   // (pSelf, streamType, pMediaInfo, pUri, ppDesc)
    int32_t type = (int32_t)arg_u32(c, 1);
    std::string uri = mem_cstr(arg_u32(c, 3));
    if (type != 0) { rt_log("sail: stream type %d is not supported (%s)", type, uri.c_str()); c.r[3] = ERR_UNSUPPORTED; return; }
    Descriptor* d = new Descriptor;
    d->addr = hle_alloc(0x40);
    d->uri = uri;
    static const char kScheme[] = "x-cell-fs://";
    if (uri.compare(0, sizeof kScheme - 1, kScheme) == 0) d->host = fs_host_path(uri.substr(sizeof kScheme - 1));
    if (g_trace) rt_log("sail: descriptor %08X for %s -> %s", d->addr, uri.c_str(), d->host.c_str());
    {
        std::lock_guard<std::mutex> lk(g_mx);
        g_descriptors[d->addr] = d;
    }
    st32(arg_u32(c, 4), d->addr);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailDescriptorSetAutoSelection) { c.r[3] = CELL_OK; }   // (pDesc, flag): the first video stream is played

PS3_HLE(cellSailDescriptorOpen) {        // (pDesc)
    Descriptor* d = descriptor(arg_u32(c, 0));
    c.r[3] = d && open_descriptor(*d) ? CELL_OK : ERR_INVALID_ARG;
}

PS3_HLE(cellSailDescriptorSetEs) { c.r[3] = CELL_OK; }   // (pDesc, type, index, ...): as above

PS3_HLE(cellSailDescriptorGetUri) {      // (pDesc, ...)
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerAddDescriptor) {   // (pSelf, pDesc)
    Player* p = player(arg_u32(c, 0));
    Descriptor* d = descriptor(arg_u32(c, 1));
    if (!p || !d) { c.r[3] = ERR_INVALID_ARG; return; }
    std::lock_guard<std::mutex> lk(p->mx);
    p->descriptors.push_back(d);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerDestroyDescriptor) {   // (pSelf, pDesc)
    Player* p = player(arg_u32(c, 0));
    uint32_t addr = arg_u32(c, 1);
    if (p) {
        std::lock_guard<std::mutex> lk(p->mx);
        for (size_t i = 0; i < p->descriptors.size(); ++i)
            if (p->descriptors[i]->addr == addr) { p->descriptors.erase(p->descriptors.begin() + i); break; }
    }
    c.r[3] = CELL_OK;                    // the descriptor's block stays: the runtime's heap is never freed
}

PS3_HLE(cellSailPlayerOpenStream) {      // (pSelf)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    post(*p, CALL_OPEN_STREAM);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerCloseStream) {     // (pSelf)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    post(*p, CALL_CLOSE_STREAM);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerStart) {           // (pSelf, CellSailStartCommand*, userParam)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    post(*p, CALL_START);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerStop) {            // (pSelf)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    post(*p, CALL_STOP);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerSetPaused) {       // (pSelf, paused)
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    post(*p, arg_u32(c, 1) & 0xFF ? 100 : 101);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSailPlayerSetRepeatMode) {   // (pSelf, repeatMode, CellSailStartCommand*): the previous mode
    Player* p = player(arg_u32(c, 0));
    if (!p) { c.r[3] = ERR_INVALID_STATE; return; }
    std::lock_guard<std::mutex> lk(p->mx);
    int old = p->repeat;
    p->repeat = (int32_t)arg_u32(c, 1);
    c.r[3] = (uint64_t)(int64_t)old;
}

// (pSelf, CellSailGraphicsFrameInfo* info, CellSailGraphicsFrameInfo* prev,
// u64* flipTime, flags): the frame to show now, described in info. What it
// returns on success is a reading of its one caller, which takes the frame
// from info and any result above 255 (signed) as "there is one": the
// frame's size in bytes. Not its address, which is negative in local memory.
PS3_HLE(cellSailGraphicsAdapterGetFrame2) {
    uint32_t a = arg_u32(c, 0), info = arg_u32(c, 1), prev = arg_u32(c, 2), flip = arg_u32(c, 3);
    Player* p = nullptr;
    {
        std::lock_guard<std::mutex> lk(g_mx);
        for (auto& [k, v] : g_players) if (v->gfx && v->gfx->addr == a) { p = v; break; }
    }
    if (!p) { c.r[3] = ERR_EMPTY; return; }
    std::lock_guard<std::mutex> lk(p->mx);
    if (!p->clock_started || !p->stream) {
        static int n;
        if (g_trace && n++ % 120 == 0) rt_log("sail: GetFrame2 with no frame yet (clock %d, stream %p)", p->clock_started, (void*)p->stream);
        c.r[3] = ERR_EMPTY;
        return;
    }
    auto now = p->paused ? p->pause_start : Clock::now();
    const Slot* best = nullptr;
    for (const Slot& s : p->slots) {
        if (s.index < 0) continue;
        auto due = p->t0 + std::chrono::microseconds((s.pts - p->stream->first_pts) * 1000000 / 90000);
        if (due <= now && (!best || s.index > best->index)) best = &s;
    }
    if (!best) { c.r[3] = ERR_EMPTY; return; }
    if (prev && p->shown >= 0) {
        const Slot& ps = p->slots[p->shown % kFrames];
        if (ps.index == p->shown) {
            st32(prev, ps.addr); st32(prev + 4, p->session); st32(prev + 8, (uint32_t)(ps.index % kFrames));
            st32(prev + 12, 0); st64(prev + 16, ps.pts);
        }
    }
    if (best->index > p->shown) {
        if (g_trace && best->index % 30 == 0)
            rt_log("sail: frame %lld shown at %lld ms, pts %llu", (long long)best->index,
                   (long long)std::chrono::duration_cast<std::chrono::milliseconds>(now - p->t0).count(),
                   (unsigned long long)best->pts);
        p->shown = best->index;
        p->cv.notify_all();
    }
    st32(info, best->addr);
    st32(info + 4, p->session);
    st32(info + 8, (uint32_t)(best->index % kFrames));   // tag
    st32(info + 12, 0);                                  // status
    st64(info + 16, best->pts);
    if (flip) st64(flip, 0);
    c.r[3] = p->frame_size;
}

// (pSelf, pts, u64* timePosition): microseconds from the stream's first picture.
PS3_HLE(cellSailGraphicsAdapterPtsToTimePosition) {
    uint32_t a = arg_u32(c, 0);
    uint64_t pts = arg_u64(c, 1);
    uint32_t first = 0;
    {
        std::lock_guard<std::mutex> lk(g_mx);
        for (auto& [k, v] : g_players)
            if (v->gfx && v->gfx->addr == a && v->stream) first = v->stream->first_pts;
    }
    st64(arg_u32(c, 2), pts >= first ? (pts - first) * 1000000 / 90000 : 0);
    c.r[3] = CELL_OK;
}
