// ps3kit runtime — what the RSX (gcm.cpp, its FIFO thread) hands the
// renderer (rsxgl.cpp and video.cpp, the host's main thread).
//
// The FIFO thread runs the methods as the command stream gives them. It
// executes the ones that synchronise with the game (references, semaphores,
// labels, flips) and passes every other method write on, in order: the
// renderer keeps its own copy of the 3D engine's registers and does what a
// write does there (a clear, a program upload). What the renderer cannot
// read for itself, because it runs behind the game and guest memory moves
// on, the FIFO thread reads when a draw ends and attaches to the draw:
// the vertices, the indices, the fragment program and the textures.
//
// The record is a byte stream of commands:
//   REGS     u32 n, then n x {u32 method, u32 value}
//   DRAW     RsxDraw, then its sections (below)
//   FLIP     RsxFlip
//   TEXFLUSH the renderer's textures are forgotten (the FIFO thread's list of
//            what it has sent was full and starts again)
//
// A DRAW's sections, in order:
//   arrays:  ranges x {u32 first, u32 count}, first counted from base
//   indexed: indices x u32, rebased to base; the restart index is 0xFFFFFFFF
//   attributes: attrs x {u32 index, u32 format, u32 bytes, data}, host order,
//            at the array's stride, starting at vertex base
//   fragment program: fp_words x u32, decoded (fp_word)
//   textures: textures x {RsxTexture, data of RsxTexture::bytes bytes}
#pragma once
#include <cstdint>
#include <string>
#include <vector>

enum : uint8_t { RC_REGS = 1, RC_DRAW, RC_FLIP, RC_TEXFLUSH };

struct RsxDraw {
    uint32_t prim;                      // NV4097_SET_BEGIN_END
    uint32_t indexed;                   // 0: arrays, 1: indices
    uint32_t count;                     // ranges, or indices
    uint32_t base;                      // the first vertex the attributes hold
    uint32_t vertices;                  // vertices each attribute holds
    uint32_t attrs, fp_words, textures;
};

struct RsxTexture {
    uint32_t unit;
    uint32_t regs[8];                   // offset, format, address, control0, control1, filter, image rect, border colour
    uint32_t control3;                  // pitch and depth
    uint64_t key;                       // the layout and the bytes, hashed
    uint32_t bytes;                     // 0: the renderer has this key already
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

// rsxcap.cpp, on the FIFO thread
void rsxcap_io(uint32_t io_addr, uint32_t io_size);
void rsxcap_method(uint32_t m, uint32_t v);     // every method the FIFO thread does not execute itself
void rsxcap_flip(const RsxFlip& f);             // ends the record and hands it over

// rsxgl.cpp, on the renderer's thread
void rsxgl_init();
void rsxgl_exec(const uint8_t* rec, size_t n, void (*on_flip)(const RsxFlip&));
// The colour surface at a display buffer's offset in local memory, if one
// was drawn: its texture, framebuffer and size.
bool rsxgl_display(uint32_t offset, uint32_t& tex, uint32_t& fbo, int& w, int& h);
void rsxgl_report();
// video.cpp: 8-bit RGB (channels 3) or RGBA (4) rows, top first
void write_png(const std::string& path, int w, int h, const std::vector<uint8_t>& px, int channels);
