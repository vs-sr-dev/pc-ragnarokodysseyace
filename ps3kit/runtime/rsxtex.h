// ps3kit runtime — an RSX texture's layout in memory, from its registers:
// what the FIFO thread copies (rsxcap.cpp) and the renderer decodes
// (rsxgl.cpp) agree on through this.
//
// A texture is its mipmap levels in order, largest first; a cube map is six
// faces of those, each face starting on a 128-byte boundary. A level is
// swizzled (texels in Morton order) unless the format's LN bit (0x20) says
// it is linear, rows at the pitch NV4097_SET_TEXTURE_CONTROL3 gives;
// compressed formats are rows of 4x4 blocks.
#pragma once
#include <algorithm>
#include <cstdint>

struct TexLayout {
    uint32_t base;                      // the format without its LN and UN bits
    bool linear, unnormalized, cube, compressed;
    uint32_t dims;                      // 1, 2 or 3
    uint32_t w, h, d, levels, pitch;
    uint32_t bpp;                       // bytes a texel, or a 4x4 block when compressed
    uint32_t level_offset[16], level_bytes[16];
    uint32_t face_bytes, total;
};

static inline uint32_t tex_bpp(uint32_t base, bool& compressed) {
    compressed = false;
    switch (base) {
    case 0x81: return 1;                                        // B8
    case 0x82: case 0x83: case 0x84: case 0x8B: case 0x8F: case 0x92: case 0x93: case 0x94: case 0x97:
    case 0x98: case 0x99: case 0x9D: case 0x8D: case 0x8E: return 2;
    case 0x85: case 0x90: case 0x91: case 0x95: case 0x9C: case 0x9E: case 0x9F: return 4;
    case 0x9A: return 8;
    case 0x9B: return 16;
    case 0x86: compressed = true; return 8;                     // DXT1
    case 0x87: case 0x88: compressed = true; return 16;         // DXT2/3, DXT4/5
    default: return 4;
    }
}

static inline TexLayout tex_layout(uint32_t format, uint32_t rect, uint32_t control3) {
    TexLayout t{};
    uint32_t f = format >> 8 & 0xFF;
    t.base = f & ~0x60u;
    t.linear = f & 0x20;
    t.unnormalized = f & 0x40;
    t.cube = format & 4;
    t.dims = format >> 4 & 0xF;
    t.levels = std::clamp<uint32_t>(format >> 16, 1, 13);
    t.w = std::max<uint32_t>(rect >> 16, 1);
    t.h = std::max<uint32_t>(rect & 0xFFFF, 1);
    t.d = std::max<uint32_t>(control3 >> 20, 1);
    t.pitch = control3 & 0xFFFFF;
    t.bpp = tex_bpp(t.base, t.compressed);
    uint32_t at = 0;
    for (uint32_t l = 0; l < t.levels; ++l) {
        uint32_t lw = std::max(t.w >> l, 1u), lh = std::max(t.h >> l, 1u), ld = t.dims == 3 ? std::max(t.d >> l, 1u) : 1;
        uint32_t n;
        if (t.compressed) n = ((lw + 3) / 4) * ((lh + 3) / 4) * t.bpp;
        else if (t.linear && t.pitch) n = t.pitch * lh;
        else n = lw * lh * t.bpp;
        n *= ld;
        t.level_offset[l] = at;
        t.level_bytes[l] = n;
        at += n;
    }
    t.face_bytes = t.cube ? (at + 127) & ~127u : at;
    t.total = t.cube ? t.face_bytes * 6 : at;
    return t;
}
