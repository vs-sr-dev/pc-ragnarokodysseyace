// fonttest FONT SIZE TEXT OUT.pgm: the font reader and the
// rasterizer alone. Lays TEXT (UTF-8) out on one line at SIZE pixels per em,
// pen advanced by each glyph's hmtx advance, baseline at the ascender, and
// writes the coverage as a binary PGM, so that it can be set beside another
// renderer's image of the same string.
#include "otf.h"
#include "raster.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

static std::vector<uint32_t> utf8(const std::string& s) {
    std::vector<uint32_t> out;
    for (size_t i = 0; i < s.size();) {
        uint8_t b = (uint8_t)s[i];
        int n = b < 0x80 ? 1 : b < 0xE0 ? 2 : b < 0xF0 ? 3 : 4;
        uint32_t c = n == 1 ? b : b & (0x7F >> n);
        for (int k = 1; k < n && i + k < s.size(); ++k) c = c << 6 | ((uint8_t)s[i + k] & 0x3F);
        out.push_back(c);
        i += n;
    }
    return out;
}

int main(int argc, char** argv) {
    if (argc < 5) {
        std::fprintf(stderr, "usage: fonttest FONT SIZE TEXT OUT.pgm\n");
        return 2;
    }
    FILE* f = std::fopen(argv[1], "rb");
    if (!f) { std::perror(argv[1]); return 1; }
    std::vector<uint8_t> data;
    for (uint8_t buf[65536]; size_t k = std::fread(buf, 1, sizeof buf, f);) data.insert(data.end(), buf, buf + k);
    std::fclose(f);
    otf::Face face;
    std::string err;
    if (!face.open(data.data(), data.size(), &err)) { std::fprintf(stderr, "%s: %s\n", argv[1], err.c_str()); return 1; }
    float size = (float)std::atof(argv[2]);
    float scale = size / face.units_per_em();
    std::vector<uint32_t> text = utf8(argv[3]);

    int asc = (int)std::ceil(face.hhea().ascender * scale), desc = (int)std::ceil(-face.hhea().descender * scale);
    int width = 4, height = asc + desc + 4;
    for (uint32_t c : text) width += (int)std::ceil(face.advance(face.glyph_index(c)) * scale) + 1;
    std::vector<uint8_t> img((size_t)width * height, 0);
    float pen = 2;
    int base = 2 + asc;
    for (uint32_t c : text) {
        int gid = face.glyph_index(c);
        otf::Path path;
        if (!face.outline(gid, path)) std::fprintf(stderr, "U+%04X (glyph %d): malformed charstring\n", c, gid);
        GlyphBitmap g;
        render_glyph(path, scale, scale, g);
        int ox = (int)std::floor(pen) + g.left, oy = base - g.top;
        for (int y = 0; y < g.h; ++y)
            for (int x = 0; x < g.w; ++x) {
                int px = ox + x, py = oy + y;
                if (px < 0 || py < 0 || px >= width || py >= height) continue;
                uint8_t& d = img[(size_t)py * width + px];
                d = std::max(d, g.pix[(size_t)y * g.w + x]);
            }
        std::printf("U+%04X glyph %5d  advance %4d  bitmap %2dx%-2d at (%d, %d)\n", c, gid, face.advance(gid), g.w, g.h,
                    g.left, g.top);
        pen += face.advance(gid) * scale;
    }
    FILE* o = std::fopen(argv[4], "wb");
    if (!o) { std::perror(argv[4]); return 1; }
    std::fprintf(o, "P5\n%d %d\n255\n", width, height);
    std::fwrite(img.data(), 1, img.size(), o);
    std::fclose(o);
    return 0;
}
