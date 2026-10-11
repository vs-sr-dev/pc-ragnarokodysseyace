// ps3kit runtime — what the RSX (gcm.cpp, its FIFO thread) hands the
// renderer (video.cpp, the host's main thread).
//
// The FIFO thread runs the methods as the command stream gives them and
// keeps the RSX's registers. What changes the picture it records, and on
// each flip it hands the record over: the renderer runs behind the game, at
// most frames_ahead flips.
//
// The record is a byte stream of commands:
//   SURFACE  RsxSurface: the render targets, as the surface registers name them
//   CLEAR    RsxClear: CLEAR_SURFACE, with the registers that bound it
//   FLIP     RsxFlip: the display buffer to show
#pragma once
#include <cstdint>
#include <vector>

enum : uint8_t { RC_SURFACE = 1, RC_CLEAR, RC_FLIP };

struct RsxSurface {
    uint32_t format;                    // NV4097_SET_SURFACE_FORMAT
    uint32_t target;                    // NV4097_SET_SURFACE_COLOR_TARGET
    uint16_t clip_x, clip_y, clip_w, clip_h;
    uint32_t color_dma[4], color_offset[4], color_pitch[4];
    uint32_t zeta_dma, zeta_offset, zeta_pitch;
};

struct RsxClear {
    uint32_t mask;                      // CELL_GCM_CLEAR_*, already narrowed by the colour mask
    uint32_t color;                     // A8R8G8B8
    uint32_t zstencil;                  // depth << 8 | stencil for Z24S8, depth for Z16
    uint16_t x, y, w, h;                // the scissor, within the surface's clip
};

struct RsxFlip {
    uint32_t id, offset, pitch, width, height;   // a display buffer, in local memory
};

struct VideoOptions {
    bool enabled = true;
    int frames_ahead = 2;
    double quit_after = 0;              // seconds; 0 = until the window closes
    const char* dump_dir = nullptr;     // PNGs of shown frames
    int dump_every = 60;                // one every N flips
};
void video_configure(const VideoOptions& o);
bool video_enabled();
// Takes the record and leaves it empty, waiting while the renderer has
// frames_ahead flips queued.
void video_submit(std::vector<uint8_t>& rec, int flips);
// Runs the window and the renderer on the calling thread, the process's
// main thread, until the window is closed; the game runs on its own threads.
[[noreturn]] void video_run(const char* title);
