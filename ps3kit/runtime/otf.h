// ps3kit runtime — OpenType fonts: the sfnt tables a renderer needs and the
// glyph outlines of CFF fonts (Type 2 charstrings), name-keyed or CID-keyed.
//
// The face reads the bytes in place; they must outlive it. Outlines come out
// in font units, y up, as the font has them: no hinting is applied.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace otf {

// A glyph outline: closed contours of lines and cubic Bézier segments.
struct Path {
    enum Op : uint8_t { Move, Line, Cubic };
    std::vector<uint8_t> ops;
    std::vector<float> pts;         // Move and Line one point, Cubic three
    void clear() { ops.clear(); pts.clear(); }
    // The control box: every point, control points included.
    bool cbox(float& x0, float& y0, float& x1, float& y1) const;
};

struct VMetrics { int ascender, descender, line_gap; };

class Face {
public:
    bool open(const uint8_t* data, size_t size, std::string* err);
    int glyph_count() const { return nglyphs_; }
    int units_per_em() const { return upem_; }
    VMetrics hhea() const { return hhea_; }
    int glyph_index(uint32_t code) const;           // through the Unicode cmap; 0 when unmapped
    int advance(int gid) const;                     // hmtx, font units
    bool vertical(int gid, int& advance, int& origin_y) const;   // vmtx and VORG; false without vhea
    bool outline(int gid, Path& out) const;         // false if the charstring is malformed

private:
    struct Range { uint32_t off = 0, size = 0; };
    struct Index { uint32_t count = 0, off_size = 0, offsets = 0, data = 0; };
    struct Private { Index subrs; int subr_bias = 0; };

    Range table(const char* tag) const;
    bool read_index(uint32_t at, Index& ix, uint32_t* end) const;
    bool index_item(const Index& ix, uint32_t i, uint32_t& off, uint32_t& size) const;
    bool read_private(uint32_t dict_off, uint32_t dict_size, Private& p) const;
    int fd_of(int gid) const;
    bool run(uint32_t off, uint32_t size, const Private& priv, struct Interp& st, int depth) const;

    const uint8_t* d_ = nullptr;
    size_t n_ = 0;
    uint32_t ntables_ = 0;
    int nglyphs_ = 0, upem_ = 1000;
    VMetrics hhea_{};
    uint32_t hmtx_ = 0, nhmetrics_ = 0, vmtx_ = 0, nvmetrics_ = 0, vorg_ = 0;
    uint32_t cmap4_ = 0, cmap12_ = 0;
    uint32_t cff_ = 0;
    Index gsubrs_, charstrings_;
    int gsubr_bias_ = 0;
    std::vector<Private> fds_;                      // one, or the FDArray of a CID-keyed font
    uint32_t fdselect_ = 0;
};

}  // namespace otf
