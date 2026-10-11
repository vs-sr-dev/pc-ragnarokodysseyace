// ps3kit runtime — a coverage rasterizer for outlines: lines, quadratic and
// cubic Bézier curves, filled by the nonzero rule into 8-bit coverage.
//
// Each pixel gets the exact area the outline covers in it (curves are
// flattened first): the signed area of every edge is accumulated per cell
// and summed along the row, and the coverage is that sum's magnitude,
// clamped to one. Coordinates are pixels, y down, (0, 0) the top-left
// corner of the top-left pixel. Contours are closed implicitly.
#pragma once
#include "otf.h"
#include <cstdint>
#include <vector>

class Raster {
public:
    void reset(int w, int h);
    void move_to(float x, float y);
    void line_to(float x, float y);
    void quad_to(float x1, float y1, float x, float y);
    void cubic_to(float x1, float y1, float x2, float y2, float x, float y);
    // Closes the last contour and writes w x h bytes, 0 to 255, rows `pitch` apart.
    void finish(uint8_t* out, int pitch);

private:
    void edge(float x0, float y0, float x1, float y1);
    void close();
    int w_ = 0, h_ = 0;
    std::vector<float> acc_;                // (w + 2) per row: an edge's area spills one cell right
    float sx_ = 0, sy_ = 0, x_ = 0, y_ = 0;
    bool open_ = false;
};

// A glyph's coverage image: `w` x `h` bytes, its top-left pixel `left`
// pixels right of the pen and `top` pixels above the baseline.
struct GlyphBitmap {
    int left = 0, top = 0, w = 0, h = 0;
    std::vector<uint8_t> pix;
};
// The outline scaled by (sx, sy) pixels per font unit, in a bitmap that is
// its control box rounded out to whole pixels, as FreeType's renderer
// places one. An empty outline gives an empty bitmap.
void render_glyph(const otf::Path& path, float sx, float sy, GlyphBitmap& out);
