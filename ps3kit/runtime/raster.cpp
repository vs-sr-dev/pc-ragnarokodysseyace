// ps3kit runtime — the coverage rasterizer. See raster.h.
//
// An edge adds, to every cell it crosses, the signed area of that cell to
// its right, and the rest of its height to the next cell; a running sum
// along the row then carries each edge's full height to every cell beyond
// it. The sum in a cell is the outline's winding weighted by area, which is
// what the nonzero rule needs: |sum| clamped to one is the coverage. A
// piece of an edge inside one cell is a trapezoid, so splitting the edge at
// every row and column boundary makes the area exact.
//
// Curves are cut into uniform-parameter segments, enough of them that the
// chords stay within 1/20 of a pixel of the curve.
#include "raster.h"
#include <algorithm>
#include <cmath>

namespace {
constexpr float kTolerance = 0.05f;
constexpr int kMaxSegments = 100;
}

void Raster::reset(int w, int h) {
    w_ = std::max(w, 0);
    h_ = std::max(h, 0);
    acc_.assign((size_t)(w_ + 2) * h_, 0.f);
    open_ = false;
}

void Raster::close() {
    if (open_ && (x_ != sx_ || y_ != sy_)) edge(x_, y_, sx_, sy_);
    x_ = sx_;
    y_ = sy_;
    open_ = false;
}

void Raster::move_to(float x, float y) {
    close();
    sx_ = x_ = x;
    sy_ = y_ = y;
    open_ = true;
}

void Raster::line_to(float x, float y) {
    edge(x_, y_, x, y);
    x_ = x;
    y_ = y;
    open_ = true;
}

void Raster::quad_to(float x1, float y1, float x, float y) {
    float ddx = x_ - 2 * x1 + x, ddy = y_ - 2 * y1 + y;
    float dd = std::sqrt(ddx * ddx + ddy * ddy);
    int n = std::clamp((int)std::ceil(std::sqrt(dd / (4 * kTolerance))), 1, kMaxSegments);
    float x0 = x_, y0 = y_;
    for (int i = 1; i <= n; ++i) {
        float t = (float)i / n, u = 1 - t;
        line_to(u * u * x0 + 2 * u * t * x1 + t * t * x, u * u * y0 + 2 * u * t * y1 + t * t * y);
    }
}

void Raster::cubic_to(float x1, float y1, float x2, float y2, float x, float y) {
    float ax = x_ - 2 * x1 + x2, ay = y_ - 2 * y1 + y2;
    float bx = x1 - 2 * x2 + x, by = y1 - 2 * y2 + y;
    float dd = std::sqrt(std::max(ax * ax + ay * ay, bx * bx + by * by));
    int n = std::clamp((int)std::ceil(std::sqrt(0.75f * dd / kTolerance)), 1, kMaxSegments);
    float x0 = x_, y0 = y_;
    for (int i = 1; i <= n; ++i) {
        float t = (float)i / n, u = 1 - t;
        float a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
        line_to(a * x0 + b * x1 + c * x2 + d * x, a * y0 + b * y1 + c * y2 + d * y);
    }
}

void Raster::edge(float x0, float y0, float x1, float y1) {
    if (y0 == y1) return;
    float dir = 1;
    if (y0 > y1) { std::swap(x0, x1); std::swap(y0, y1); dir = -1; }
    if (y1 <= 0 || y0 >= h_) return;
    float dxdy = (x1 - x0) / (y1 - y0);
    int r0 = std::max(0, (int)std::floor(y0)), r1 = std::min(h_, (int)std::ceil(y1));
    for (int row = r0; row < r1; ++row) {
        float ya = std::max(y0, (float)row), yb = std::min(y1, (float)row + 1);
        if (yb <= ya) continue;
        float xa = x0 + (ya - y0) * dxdy, xb = x0 + (yb - y0) * dxdy;
        float d = (yb - ya) * dir;
        float* a = acc_.data() + (size_t)row * (w_ + 2);
        // one cell's piece: its height dh, its mean x
        auto piece = [&](int cell, float dh, float xm) {
            if (cell >= w_) return;                 // right of every pixel: seen by none
            if (cell < 0) { a[0] += dh; return; }   // left of every pixel: covers the whole row
            float f = xm - cell;
            a[cell] += dh * (1 - f);
            a[cell + 1] += dh * f;
        };
        float xl = std::min(xa, xb), xr = std::max(xa, xb);
        int cl = (int)std::floor(xl), cr = (int)std::floor(xr);
        if (cl == cr || xr - xl < 1e-6f) { piece(cl, d, 0.5f * (xl + xr)); continue; }
        float span = xr - xl;
        for (int cell = cl; cell <= cr; ++cell) {
            float pl = std::max(xl, (float)cell), pr = std::min(xr, (float)cell + 1);
            if (pr <= pl) continue;
            piece(cell, d * (pr - pl) / span, 0.5f * (pl + pr));
        }
    }
}

void Raster::finish(uint8_t* out, int pitch) {
    close();
    for (int row = 0; row < h_; ++row) {
        const float* a = acc_.data() + (size_t)row * (w_ + 2);
        float s = 0;
        for (int x = 0; x < w_; ++x) {
            s += a[x];
            float c = std::min(1.f, std::fabs(s));
            out[(size_t)row * pitch + x] = (uint8_t)std::min(255, (int)(c * 256));
        }
    }
}

void render_glyph(const otf::Path& path, float sx, float sy, GlyphBitmap& out) {
    out = {};
    float x0, y0, x1, y1;
    if (!path.cbox(x0, y0, x1, y1)) return;
    int l = (int)std::floor(x0 * sx), r = (int)std::ceil(x1 * sx);
    int b = (int)std::floor(y0 * sy), t = (int)std::ceil(y1 * sy);
    if (r <= l || t <= b) return;
    out.left = l;
    out.top = t;
    out.w = r - l;
    out.h = t - b;
    out.pix.assign((size_t)out.w * out.h, 0);
    Raster ras;
    ras.reset(out.w, out.h);
    const float* p = path.pts.data();
    auto X = [&](float x) { return x * sx - l; };
    auto Y = [&](float y) { return t - y * sy; };
    for (uint8_t op : path.ops) {
        if (op == otf::Path::Move) { ras.move_to(X(p[0]), Y(p[1])); p += 2; }
        else if (op == otf::Path::Line) { ras.line_to(X(p[0]), Y(p[1])); p += 2; }
        else { ras.cubic_to(X(p[0]), Y(p[1]), X(p[2]), Y(p[3]), X(p[4]), Y(p[5])); p += 6; }
    }
    ras.finish(out.pix.data(), out.w);
}
