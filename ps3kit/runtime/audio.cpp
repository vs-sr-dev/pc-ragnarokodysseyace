// ps3kit runtime — cellAudio and the audio output: the ports a game mixes
// into, and the clock that consumes them. The audio system reads one block
// of 256 samples per port every 256/48000 s: it takes the block at the
// port's read index, clears it, and advances the index, which the game finds
// through cellAudioGetPortConfig and reads to know how far ahead it may
// write. The game paces its mixer on that index.
//
// What the clock takes is what is heard: each started port's block, at the
// port's level, mixed down to two channels (an eight-channel port is
// L R C LFE Ls Rs Lb Rb; centre and surrounds go in at -3 dB, the LFE is
// dropped), the ports summed and sent to the host's audio device through an
// SDL3 stream once the window has started SDL's audio. When more than a
// fifth of a second is already queued there a block is dropped, so that the
// host device's clock and this one cannot drift apart into latency.
// PS3KIT_AUDIODUMP=FILE.wav also writes the mix to a WAV file.
//
// The output (cellAudioOut, a cellSysutil function) is what a PS3 on a
// television reports: HDMI, two-channel linear PCM at 48 kHz.
#include "rt.h"
#include <SDL3/SDL.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <cmath>
#include <mutex>
#include <thread>

namespace {
constexpr uint32_t kPorts = 8;
constexpr uint32_t kSamples = 256;                              // CELL_AUDIO_BLOCK_SAMPLES
constexpr uint32_t kPortArea = kSamples * 32 * 8 * 4;           // 32 blocks of 8 channels of floats
constexpr uint32_t kErrAlreadyInit = 0x80310701u, kErrNotInit = 0x80310703u, kErrParam = 0x80310704u,
                   kErrPortFull = 0x80310705u, kErrAlreadyRun = 0x80310706u, kErrNotOpen = 0x80310707u,
                   kErrNotRun = 0x80310708u, kErrPortOpen = 0x8031070Au;
constexpr uint32_t kStatusReady = 1, kStatusRun = 2, kStatusClose = 0x1010;
constexpr uint64_t kAttrInitLevel = 0x1000;

enum class Port { closed, opened, started };
struct AudioPort {
    Port state = Port::closed;
    uint32_t channels = 0, blocks = 0, size = 0;
    uint32_t addr = 0, index = 0;       // the port's buffer; its read index, a u64
    uint64_t pos = 0;
    float level = 1.0f;
};

std::mutex g_mx;
bool g_init = false;
AudioPort g_port[kPorts];
uint32_t g_area = 0, g_indices = 0;     // allocated once, kept across cellAudioQuit

uint32_t block_bytes(const AudioPort& p) { return p.channels * kSamples * 4; }

// ---- what is heard ----
SDL_AudioStream* g_stream = nullptr;
FILE* g_dump = nullptr;
uint32_t g_dump_frames = 0;

void dump_header() {
    uint32_t data = g_dump_frames * 8;
    uint8_t h[44];
    auto w32 = [&](int at, uint32_t v) { std::memcpy(h + at, &v, 4); };
    auto w16 = [&](int at, uint16_t v) { std::memcpy(h + at, &v, 2); };
    std::memcpy(h, "RIFF", 4); w32(4, 36 + data); std::memcpy(h + 8, "WAVEfmt ", 8);
    w32(16, 16); w16(20, 3); w16(22, 2); w32(24, 48000); w32(28, 48000 * 8); w16(32, 8); w16(34, 32);
    std::memcpy(h + 36, "data", 4); w32(40, data);
    std::fseek(g_dump, 0, SEEK_SET);
    std::fwrite(h, 1, sizeof h, g_dump);
    std::fseek(g_dump, 0, SEEK_END);
}

void output(const float* mix) {                                 // kSamples stereo frames
    if (!g_stream && SDL_WasInit(SDL_INIT_AUDIO)) {
        SDL_AudioSpec spec{SDL_AUDIO_F32, 2, 48000};
        g_stream = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, nullptr, nullptr);
        if (g_stream) {
            SDL_ResumeAudioStreamDevice(g_stream);
            rt_log("audio: playing on the host's default device");
        } else {
            rt_log("audio: no output device: %s", SDL_GetError());
        }
    }
    if (g_stream && SDL_GetAudioStreamQueued(g_stream) < 48000 * 8 / 5)
        SDL_PutAudioStreamData(g_stream, mix, kSamples * 8);
    if (g_dump) {
        std::fwrite(mix, 8, kSamples, g_dump);
        g_dump_frames += kSamples;
        if (g_dump_frames % 48000 < kSamples) dump_header();
    }
}

// One port's block into the stereo mix, at the port's level.
void mix_block(const AudioPort& p, const uint8_t* block, float* mix) {
    const float k = 0.70710678f;
    for (uint32_t i = 0; i < kSamples; ++i) {
        float ch[8];
        for (uint32_t c = 0; c < p.channels; ++c) {
            uint32_t u;
            std::memcpy(&u, block + 4 * (i * p.channels + c), 4);
            ch[c] = as_f32(PPU_BSWAP32(u)) * p.level;
        }
        float l = ch[0], r = ch[1];
        if (p.channels == 8) {
            l += k * (ch[2] + ch[4] + ch[6]);
            r += k * (ch[2] + ch[5] + ch[7]);
        }
        mix[2 * i] += l;
        mix[2 * i + 1] += r;
    }
}

// The audio system's period: every started port's current block is consumed
// and cleared, and its read index moves on.
void clock_main() {
    using namespace std::chrono;
    const auto t0 = steady_clock::now();
    if (const char* path = std::getenv("PS3KIT_AUDIODUMP")) {
        g_dump = std::fopen(path, "wb");
        if (g_dump) dump_header();
    }
    std::vector<float> mix(kSamples * 2);
    for (uint64_t n = 1;; ++n) {
        host_sleep_until(t0 + nanoseconds(n * kSamples * 1000000000ull / 48000));
        std::fill(mix.begin(), mix.end(), 0.0f);
        {
            std::lock_guard<std::mutex> lk(g_mx);
            if (!g_init) continue;
            for (AudioPort& p : g_port) {
                if (p.state != Port::started) continue;
                uint8_t* block = g_mem + p.addr + (uint32_t)p.pos * block_bytes(p);
                mix_block(p, block, mix.data());
                std::memset(block, 0, block_bytes(p));
                p.pos = (p.pos + 1) % p.blocks;
                st64(p.index, p.pos);
            }
        }
        for (float& v : mix) v = std::fmin(std::fmax(v, -1.0f), 1.0f);
        output(mix.data());
    }
}
}  // namespace

PS3_HLE(cellAudioInit) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (g_init) { c.r[3] = kErrAlreadyInit; return; }
    if (!g_area) {
        g_area = hle_alloc(kPortArea * kPorts, 0x10000);
        g_indices = hle_alloc(16 * kPorts, 128);                    // a u64 per port, 16 bytes apart
        std::thread(clock_main).detach();
    }
    std::memset(g_mem + g_area, 0, kPortArea * kPorts);
    std::memset(g_mem + g_indices, 0, 16 * kPorts);
    for (uint32_t i = 0; i < kPorts; ++i) {
        g_port[i] = AudioPort{};
        g_port[i].addr = g_area + kPortArea * i;
        g_port[i].index = g_indices + 16 * i;
    }
    g_init = true;
    c.r[3] = CELL_OK;
}

PS3_HLE(cellAudioQuit) {
    std::lock_guard<std::mutex> lk(g_mx);
    c.r[3] = g_init ? CELL_OK : kErrNotInit;
    g_init = false;
}

PS3_HLE(cellAudioPortOpen) {             // (CellAudioPortParam*, u32* port)
    uint32_t param = arg_u32(c, 0), out = arg_u32(c, 1);
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    if (!param || !out) { c.r[3] = kErrParam; return; }
    uint64_t channels = ld64(param), blocks = ld64(param + 8), attr = ld64(param + 16);
    float level = as_f32(ld32(param + 24));
    if (channels != 2 && channels != 8) { c.r[3] = kErrParam; return; }
    if (blocks != 8 && blocks != 16 && blocks != 32) { c.r[3] = kErrParam; return; }
    for (uint32_t i = 0; i < kPorts; ++i) {
        AudioPort& p = g_port[i];
        if (p.state != Port::closed) continue;
        p.channels = (uint32_t)channels;
        p.blocks = (uint32_t)blocks;
        p.size = p.channels * p.blocks * kSamples * 4;
        p.pos = 0;
        p.level = (attr & kAttrInitLevel) ? level : 1.0f;
        if (p.level <= -1.0f) { c.r[3] = kErrPortOpen; return; }
        std::memset(g_mem + p.addr, 0, p.size);
        st64(p.index, 0);
        p.state = Port::opened;
        st32(out, i);
        rt_log("audio: port %u open, %u channels, %u blocks, attr %llX, buffer %08X, read index %08X", i,
               p.channels, p.blocks, (unsigned long long)attr, p.addr, p.index);
        c.r[3] = CELL_OK;
        return;
    }
    c.r[3] = kErrPortFull;
}

PS3_HLE(cellAudioGetPortConfig) {        // (port, CellAudioPortConfig*)
    uint32_t n = arg_u32(c, 0), cfg = arg_u32(c, 1);
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    if (!cfg || n >= kPorts) { c.r[3] = kErrParam; return; }
    const AudioPort& p = g_port[n];
    st32(cfg, p.index);                                             // readIndexAddr
    st32(cfg + 4, p.state == Port::started ? kStatusRun : p.state == Port::opened ? kStatusReady : kStatusClose);
    st64(cfg + 8, p.channels);
    st64(cfg + 16, p.blocks);
    st32(cfg + 24, p.size);
    st32(cfg + 28, p.addr);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellAudioPortStart) {
    uint32_t n = arg_u32(c, 0);
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    if (n >= kPorts) { c.r[3] = kErrParam; return; }
    Port& s = g_port[n].state;
    c.r[3] = s == Port::closed ? kErrNotOpen : s == Port::started ? kErrAlreadyRun : CELL_OK;
    if (s == Port::opened) s = Port::started;
}

PS3_HLE(cellAudioPortStop) {
    uint32_t n = arg_u32(c, 0);
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    if (n >= kPorts) { c.r[3] = kErrParam; return; }
    Port& s = g_port[n].state;
    c.r[3] = s == Port::started ? CELL_OK : kErrNotRun;
    if (s == Port::started) s = Port::opened;
}

PS3_HLE(cellAudioPortClose) {
    uint32_t n = arg_u32(c, 0);
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    if (n >= kPorts) { c.r[3] = kErrParam; return; }
    c.r[3] = g_port[n].state == Port::closed ? kErrNotOpen : CELL_OK;
    g_port[n].state = Port::closed;
}

// Mixes one block into the block the port will be read from next.
PS3_HLE(cellAudioAddData) {              // (port, float* src, samples, f1 volume)
    uint32_t n = arg_u32(c, 0), src = arg_u32(c, 1), samples = arg_u32(c, 2);
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    if (n >= kPorts || !src || (src & 3) || samples != kSamples) { c.r[3] = kErrParam; return; }
    const AudioPort& p = g_port[n];
    float vol = std::isfinite(c.f[1]) ? std::fmin(std::fmax((float)c.f[1], -16.0f), 16.0f) : 0.0f;
    uint32_t dst = p.addr + (uint32_t)p.pos * block_bytes(p);
    for (uint32_t i = 0; i < samples * p.channels; ++i)
        st32(dst + 4 * i, as_u32(as_f32(ld32(dst + 4 * i)) + as_f32(ld32(src + 4 * i)) * vol));
    c.r[3] = CELL_OK;
}

// ---- the audio output ------------------------------------------------------------------------
namespace {
uint8_t g_out_channels = 2;
uint32_t g_downmixer = 0;               // CELL_AUDIO_OUT_DOWNMIXER_NONE

void sound_mode(uint32_t p) {           // CellAudioOutSoundMode
    st8(p, 0);                          // type: LPCM
    st8(p + 1, 2);                      // channel
    st8(p + 2, 0x04);                   // fs: 48 kHz
    st8(p + 3, 0);
    st32(p + 4, 1);                     // layout: 2ch
}
}  // namespace

PS3_HLE(cellAudioOutGetState) {          // (audio out, device index, CellAudioOutState*)
    uint32_t out = arg_u32(c, 0), p = arg_u32(c, 2);
    if (out != 0) { c.r[3] = 0x8002B245u; return; }                 // CELL_AUDIO_OUT_ERROR_UNSUPPORTED_AUDIO_OUT
    std::memset(g_mem + p, 0, 20);
    st8(p, 0);                                                      // state: enabled
    st8(p + 1, 0);                                                  // encoder: LPCM
    st32(p + 8, g_downmixer);
    sound_mode(p + 12);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellAudioOutGetConfiguration) {  // (audio out, CellAudioOutConfiguration*, option)
    uint32_t out = arg_u32(c, 0), p = arg_u32(c, 1);
    if (out != 0) { c.r[3] = 0x8002B245u; return; }
    std::memset(g_mem + p, 0, 16);
    st8(p, g_out_channels);
    st8(p + 1, 0);                                                  // encoder: LPCM
    st32(p + 12, g_downmixer);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellAudioOutConfigure) {         // (audio out, CellAudioOutConfiguration*, option, wait)
    uint32_t out = arg_u32(c, 0), p = arg_u32(c, 1);
    if (out != 0) { c.r[3] = 0x8002B245u; return; }
    if (ld8(p) != 2) { c.r[3] = 0x8002B246u; return; }             // ..._UNSUPPORTED_SOUND_MODE: the television is stereo
    g_out_channels = ld8(p);
    g_downmixer = ld32(p + 12);
    rt_log("audio: output %u channels, downmixer %u", g_out_channels, g_downmixer);
    c.r[3] = CELL_OK;
}
