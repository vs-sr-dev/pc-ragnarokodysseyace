// ps3kit runtime — cellFont and cellFontFT: fonts opened from memory, read
// by the runtime's own OpenType reader (otf.cpp) and drawn by its own
// rasterizer (raster.cpp).
//
// The system's library is FreeType behind Sony's interface. What it does is
// reproduced from the interface's meaning: a font has a scale in pixels per
// em (SetScalePixel) and a render scale (SetupRenderScalePixel); metrics are
// the glyph outline's control box and its hmtx advance at that scale,
// unhinted and unrounded; RenderCharGlyphImage draws the glyph into its
// renderer's buffer as 8-bit coverage, the image of its control box rounded
// out to whole pixels, and reports where it falls on the surface in a
// CellFontImageTransInfo clipped to the surface's scissor. The pen is at x,
// and y is one em above the baseline: the baseline is the render scale's
// height below it. That is read from the first game's arithmetic, not from
// the library: it passes a glyph cell's top less the font's descent, and
// draws the cell from the baseline less the ascent to the baseline plus the
// descent, so its font (ascent 880, descent 120 of 1000) lands in the cell
// only if the baseline is a whole em below y. Whether the library adds the
// em or the font's ascent-to-descent height is not decided by that font. A surface of one byte per pixel is drawn into as well;
// one of wider pixels is left for the caller to fill from that report.
//
// The system's own font sets (cellFontOpenFontset) are not installed: such a
// font opens, and every glyph asked of it is reported and refused with
// NO_SUPPORT_GLYPH, so that a run says which text wanted them.
//
// CellFont and CellFontRenderer are the game's memory, opaque to it; the
// runtime keeps its state by their address. PS3KIT_FONT=1 reports each call.
#include "rt.h"
#include "otf.h"
#include "raster.h"
#include <cmath>
#include <cstdlib>
#include <map>
#include <memory>
#include <mutex>
#include <set>

namespace {
constexpr uint32_t kErrInvalid = 0x80540002u, kErrUninit = 0x80540003u, kErrAlreadyInit = 0x80540006u,
                   kErrFontOpen = 0x8054000Bu, kErrNoGlyph = 0x80540012u, kErrUnbind = 0x80540021u,
                   kErrRendererInvalid = 0x80540022u;

const bool g_trace = std::getenv("PS3KIT_FONT") != nullptr;

struct Face {
    otf::Face face;
};

struct Font {
    std::shared_ptr<Face> face;     // null for a system font set
    uint32_t fontset = 0;
    float sx = 0, sy = 0;           // SetScalePixel
    float rsx = 0, rsy = 0;         // SetupRenderScalePixel
    uint32_t renderer = 0;
};

struct Renderer {
    uint32_t buffer = 0, size = 0;
};

std::mutex g_mx;
bool g_init = false;
std::map<uint64_t, std::shared_ptr<Face>> g_faces;    // by (address, size) of the font's bytes
std::map<uint32_t, Font> g_fonts;                     // by CellFont address
std::map<uint32_t, Renderer> g_renderers;             // by CellFontRenderer address
std::set<std::pair<uint32_t, uint32_t>> g_reported;   // (font set, code) already reported

float arg_f32(const PPUContext& c, int i) { return (float)c.f[1 + i]; }

void stf(uint32_t a, float v) { st32(a, as_u32(v)); }

Font* font_at(uint32_t a) {
    auto it = g_fonts.find(a);
    return it == g_fonts.end() ? nullptr : &it->second;
}

// The glyph a font maps `code` to, and its outline; 0 when it has none.
int glyph(Font& f, uint32_t code, otf::Path& path) {
    if (!f.face) {
        if (g_reported.insert({f.fontset, code}).second)
            rt_log("font: system font set %X asked for U+%04X; no system fonts are installed", f.fontset, code);
        return 0;
    }
    int gid = f.face->face.glyph_index(code);
    if (gid && !f.face->face.outline(gid, path)) {
        rt_log("font: U+%04X (glyph %d) has a malformed charstring", code, gid);
        path.clear();
    }
    return gid;
}

void write_metrics(uint32_t m, const Font& f, int gid, const otf::Path& path, float sx, float sy) {
    const otf::Face& face = f.face->face;
    float x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    path.cbox(x0, y0, x1, y1);
    float w = (x1 - x0) * sx, h = (y1 - y0) * sy, adv = face.advance(gid) * sx;
    stf(m + 0, w);
    stf(m + 4, h);
    stf(m + 8, x0 * sx);
    stf(m + 12, y1 * sy);
    stf(m + 16, adv);
    int vadv, vorg;
    if (!face.vertical(gid, vadv, vorg)) { vadv = face.units_per_em(); vorg = face.hhea().ascender; }
    stf(m + 20, -w / 2);                            // centred on the vertical pen
    stf(m + 24, (vorg - y1) * sy);
    stf(m + 28, vadv * sy);
}
}  // namespace

// ---- the library ---------------------------------------------------------------------

// (revisionFlags, CellFontConfig*)
PS3_HLE(cellFontInitializeWithRevision) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (g_trace) rt_log("font: Initialize revision %llX", (unsigned long long)arg_u64(c, 0));
    if (!arg_u32(c, 1)) { c.r[3] = kErrInvalid; return; }
    if (g_init) { c.r[3] = kErrAlreadyInit; return; }
    g_init = true;
    c.r[3] = CELL_OK;
}

PS3_HLE(cellFontEnd) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrUninit; return; }
    g_init = false;
    c.r[3] = CELL_OK;
}

// (revisionFlags, CellFontLibraryConfigFT*, const CellFontLibrary**)
PS3_HLE(cellFontInitLibraryFreeTypeWithRevision) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t lib = arg_u32(c, 2);
    if (!lib || !arg_u32(c, 1)) { c.r[3] = kErrInvalid; return; }
    if (!g_init) { c.r[3] = kErrUninit; return; }
    uint32_t p = hle_alloc(16, 16);                 // libraryType, libraryVersion, SystemClosed: all zero
    st32(lib, p);
    if (g_trace) rt_log("font: library at %08X", p);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellFontEndLibrary) { c.r[3] = CELL_OK; }

// ---- fonts -----------------------------------------------------------------------------

// (library, fontAddr, fontSize, subNum, uniqueId, CellFont*)
PS3_HLE(cellFontOpenFontMemory) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t addr = arg_u32(c, 1), size = arg_u32(c, 2), font = arg_u32(c, 5);
    if (!arg_u32(c, 0) || !addr || !font) { c.r[3] = kErrInvalid; return; }
    uint64_t key = (uint64_t)addr << 32 | size;
    auto& face = g_faces[key];
    if (!face) {
        auto f = std::make_shared<Face>();
        std::string err;
        if (!f->face.open(g_mem + addr, size, &err)) {
            rt_log("font: the font at %08X (%u bytes) does not open: %s", addr, size, err.c_str());
            g_faces.erase(key);
            c.r[3] = kErrFontOpen;
            return;
        }
        face = f;
        rt_log("font: opened the font at %08X: %u bytes, %d glyphs, %d units per em", addr, size,
               face->face.glyph_count(), face->face.units_per_em());
    }
    Font f;
    f.face = face;
    g_fonts[font] = f;
    c.r[3] = CELL_OK;
}

// (library, const CellFontType*, CellFont*)
PS3_HLE(cellFontOpenFontset) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t type = arg_u32(c, 1), font = arg_u32(c, 2);
    if (!arg_u32(c, 0) || !type || !font) { c.r[3] = kErrInvalid; return; }
    Font f;
    f.fontset = ld32(type);
    g_fonts[font] = f;
    rt_log("font: system font set %X (map %u) opened at %08X; no system fonts are installed", f.fontset,
           ld32(type + 4), font);
    c.r[3] = CELL_OK;
}

// (CellFont*, w, h): pixels per em
PS3_HLE(cellFontSetScalePixel) {
    std::lock_guard<std::mutex> lk(g_mx);
    Font* f = font_at(arg_u32(c, 0));
    if (!f) { c.r[3] = kErrInvalid; return; }
    f->sx = arg_f32(c, 0);
    f->sy = arg_f32(c, 1);
    if (g_trace) rt_log("font: %08X scale %g x %g", arg_u32(c, 0), f->sx, f->sy);
    c.r[3] = CELL_OK;
}

// (CellFont*, CellFontHorizontalLayout*)
PS3_HLE(cellFontGetHorizontalLayout) {
    std::lock_guard<std::mutex> lk(g_mx);
    Font* f = font_at(arg_u32(c, 0));
    uint32_t out = arg_u32(c, 1);
    if (!f || !out) { c.r[3] = kErrInvalid; return; }
    float base = 0, line = 0;
    if (f->face) {
        otf::VMetrics v = f->face->face.hhea();
        float s = f->sy / f->face->face.units_per_em();
        base = v.ascender * s;
        line = (v.ascender - v.descender + v.line_gap) * s;
    }
    stf(out + 0, base);
    stf(out + 4, line);
    stf(out + 8, line);                             // effectHeight: no weight effect applied
    c.r[3] = CELL_OK;
}

// (CellFont*, code, CellFontGlyphMetrics*): at the font's scale
PS3_HLE(cellFontGetCharGlyphMetrics) {
    std::lock_guard<std::mutex> lk(g_mx);
    Font* f = font_at(arg_u32(c, 0));
    uint32_t code = arg_u32(c, 1), m = arg_u32(c, 2);
    if (!f || !m) { c.r[3] = kErrInvalid; return; }
    otf::Path path;
    int gid = glyph(*f, code, path);
    if (!gid) { c.r[3] = kErrNoGlyph; return; }
    float upem = (float)f->face->face.units_per_em();
    write_metrics(m, *f, gid, path, f->sx / upem, f->sy / upem);
    c.r[3] = CELL_OK;
}

// ---- renderers and surfaces ---------------------------------------------------------------

// (library, CellFontRendererConfig*, CellFontRenderer*)
PS3_HLE(cellFontCreateRenderer) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t cfg = arg_u32(c, 1), r = arg_u32(c, 2);
    if (!arg_u32(c, 0) || !cfg || !r) { c.r[3] = kErrInvalid; return; }
    Renderer ren;
    ren.buffer = ld32(cfg);
    ren.size = ld32(cfg + 4);
    if (!ren.buffer) {
        ren.size = std::max(ren.size, 0x1000u);
        ren.buffer = hle_alloc(ren.size, 128);
    }
    g_renderers[r] = ren;
    if (g_trace) rt_log("font: renderer %08X, buffer %08X (%u bytes)", r, ren.buffer, ren.size);
    c.r[3] = CELL_OK;
}

// (CellFont*, CellFontRenderer*)
PS3_HLE(cellFontBindRenderer) {
    std::lock_guard<std::mutex> lk(g_mx);
    Font* f = font_at(arg_u32(c, 0));
    uint32_t r = arg_u32(c, 1);
    if (!f || !r) { c.r[3] = kErrInvalid; return; }
    if (!g_renderers.count(r)) { c.r[3] = kErrRendererInvalid; return; }
    f->renderer = r;
    c.r[3] = CELL_OK;
}

// (CellFont*, w, h)
PS3_HLE(cellFontSetupRenderScalePixel) {
    std::lock_guard<std::mutex> lk(g_mx);
    Font* f = font_at(arg_u32(c, 0));
    if (!f) { c.r[3] = kErrInvalid; return; }
    if (!f->renderer) { c.r[3] = kErrUnbind; return; }
    f->rsx = arg_f32(c, 0);
    f->rsy = arg_f32(c, 1);
    c.r[3] = CELL_OK;
}

// (CellFont*, code, CellFontGlyphMetrics*): at the render scale
PS3_HLE(cellFontGetRenderCharGlyphMetrics) {
    std::lock_guard<std::mutex> lk(g_mx);
    Font* f = font_at(arg_u32(c, 0));
    uint32_t code = arg_u32(c, 1), m = arg_u32(c, 2);
    if (!f || !m) { c.r[3] = kErrInvalid; return; }
    if (!f->renderer) { c.r[3] = kErrUnbind; return; }
    otf::Path path;
    int gid = glyph(*f, code, path);
    if (!gid) { c.r[3] = kErrNoGlyph; return; }
    float upem = (float)f->face->face.units_per_em();
    write_metrics(m, *f, gid, path, f->rsx / upem, f->rsy / upem);
    c.r[3] = CELL_OK;
}

// CellFontRenderSurface: buffer, widthByte, pixelSizeByte, width, height, sc_x0, sc_y0, sc_x1, sc_y1
// (surface*, buffer, bufferWidthByte, pixelSizeByte, w, h)
PS3_HLE(cellFontRenderSurfaceInit) {
    uint32_t s = arg_u32(c, 0);
    if (!s) { c.r[3] = kErrInvalid; return; }
    uint32_t w = arg_u32(c, 4), h = arg_u32(c, 5);
    st32(s + 0, arg_u32(c, 1));
    st32(s + 4, arg_u32(c, 2));
    st32(s + 8, arg_u32(c, 3));
    st32(s + 12, w);
    st32(s + 16, h);
    st32(s + 20, 0);
    st32(s + 24, 0);
    st32(s + 28, w);
    st32(s + 32, h);
    c.r[3] = CELL_OK;
}

// (surface*, x0, y0, w, h): clipped to the surface
PS3_HLE(cellFontRenderSurfaceSetScissor) {
    uint32_t s = arg_u32(c, 0);
    if (!s) { c.r[3] = kErrInvalid; return; }
    uint32_t sw = ld32(s + 12), sh = ld32(s + 16);
    uint32_t x0 = std::min(arg_u32(c, 1), sw), y0 = std::min(arg_u32(c, 2), sh);
    uint64_t x1 = std::min<uint64_t>((uint64_t)x0 + arg_u32(c, 3), sw), y1 = std::min<uint64_t>((uint64_t)y0 + arg_u32(c, 4), sh);
    st32(s + 20, x0);
    st32(s + 24, y0);
    st32(s + 28, (uint32_t)x1);
    st32(s + 32, (uint32_t)y1);
    c.r[3] = CELL_OK;
}

// (CellFont*, code, surface*, x, y, CellFontGlyphMetrics*, CellFontImageTransInfo*): the pen at
// x, the baseline an em below y. The floats take f1 and f2 and their argument slots, so the two
// pointers arrive in r8 and r9.
PS3_HLE(cellFontRenderCharGlyphImage) {
    std::lock_guard<std::mutex> lk(g_mx);
    Font* f = font_at(arg_u32(c, 0));
    uint32_t code = arg_u32(c, 1), s = arg_u32(c, 2), m = arg_u32(c, 5), ti = arg_u32(c, 6);
    float x = arg_f32(c, 0), y = arg_f32(c, 1);
    if (!f || !s) { c.r[3] = kErrInvalid; return; }
    if (!f->renderer) { c.r[3] = kErrUnbind; return; }
    otf::Path path;
    int gid = glyph(*f, code, path);
    if (!gid) { c.r[3] = kErrNoGlyph; return; }
    float upem = (float)f->face->face.units_per_em(), sx = f->rsx / upem, sy = f->rsy / upem;
    if (m) write_metrics(m, *f, gid, path, sx, sy);
    GlyphBitmap g;
    render_glyph(path, sx, sy, g);

    Renderer& ren = g_renderers[f->renderer];
    uint32_t need = (uint32_t)(g.w * g.h);
    if (need > ren.size) {                          // the old buffer is the heap's for good
        ren.size = (need + 0xFFF) & ~0xFFFu;
        ren.buffer = hle_alloc(ren.size, 128);
    }
    if (need) mem_write(ren.buffer, g.pix.data(), need);

    // the image's place on the surface, clipped to the scissor
    uint32_t buf = ld32(s), wb = ld32(s + 4), px = ld32(s + 8);
    int64_t sc_x0 = ld32(s + 20), sc_y0 = ld32(s + 24), sc_x1 = ld32(s + 28), sc_y1 = ld32(s + 32);
    int64_t gx = (int64_t)std::floor(x) + g.left, gy = (int64_t)std::floor(y + f->rsy) - g.top;
    int64_t cx0 = std::max(gx, sc_x0), cy0 = std::max(gy, sc_y0);
    int64_t cx1 = std::min(gx + g.w, sc_x1), cy1 = std::min(gy + g.h, sc_y1);
    uint32_t iw = 0, ih = 0, image = ren.buffer, surf = buf;
    if (cx1 > cx0 && cy1 > cy0) {
        iw = (uint32_t)(cx1 - cx0);
        ih = (uint32_t)(cy1 - cy0);
        image = ren.buffer + (uint32_t)((cy0 - gy) * g.w + (cx0 - gx));
        surf = buf + (uint32_t)(cy0 * wb + cx0 * px);
        if (px == 1)
            for (uint32_t row = 0; row < ih; ++row) mem_write(surf + row * wb, g_mem + image + row * g.w, iw);
    }
    if (ti) {
        st32(ti + 0, image);
        st32(ti + 4, (uint32_t)g.w);
        st32(ti + 8, iw);
        st32(ti + 12, ih);
        st32(ti + 16, surf);
        st32(ti + 20, wb);
    }
    if (g_trace)
        rt_log("font: U+%04X at (%g, %g): %dx%d image, placed %ux%u at (%lld, %lld)", code, x, y, g.w, g.h, iw, ih,
               (long long)cx0, (long long)cy0);
    c.r[3] = CELL_OK;
}
