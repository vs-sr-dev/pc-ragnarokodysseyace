// ps3kit runtime — an MPEG-2 video decoder, written from ISO/IEC 13818-2.
//
// The variable-length codes are the standard's tables, written out as bit
// strings so that they can be checked against it line by line, and turned
// into lookup tables on first use; building them checks that no code is a
// prefix of another. The inverse DCT is the separable floating-point
// transform, rounded once at the end, which is what the standard's accuracy
// requirement is measured against.
//
// Supported: frame pictures (progressive or interlaced), 4:2:0, I/P/B, frame
// and field motion compensation, frame and field DCT, both coefficient
// tables and both scans, the non-linear quantiser scale, quantiser matrix
// extensions. Not supported, and reported once when met: field pictures,
// dual-prime prediction, 4:2:2 and 4:4:4, MPEG-1 streams, scalability.
#include "mpeg2.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

namespace {

// ---- variable-length codes ------------------------------------------------------------
struct Code { const char* bits; int a, b; };
struct Entry { int16_t a, b; uint8_t len; };

// A table indexed by the next `width` bits of the stream.
struct Lut {
    int width = 0;
    std::vector<Entry> e;
    void build(const Code* c, size_t n, int w, const char* name) {
        width = w;
        e.assign((size_t)1 << w, Entry{0, 0, 0});
        for (size_t i = 0; i < n; ++i) {
            uint32_t v = 0; int len = 0;
            for (const char* p = c[i].bits; *p; ++p) v = v << 1 | (uint32_t)(*p - '0'), ++len;
            uint32_t lo = v << (w - len), hi = lo + (1u << (w - len));
            for (uint32_t k = lo; k < hi; ++k) {
                if (e[k].len) std::fprintf(stderr, "mpeg2: table %s: code %s overlaps another\n", name, c[i].bits);
                e[k] = Entry{(int16_t)c[i].a, (int16_t)c[i].b, (uint8_t)len};
            }
        }
    }
};

// B.1 macroblock_address_increment; 34 is the escape (+33), 35 MPEG-1 stuffing.
const Code kMba[] = {
    {"1", 1}, {"011", 2}, {"010", 3}, {"0011", 4}, {"0010", 5}, {"00011", 6}, {"00010", 7},
    {"0000111", 8}, {"0000110", 9}, {"00001011", 10}, {"00001010", 11}, {"00001001", 12},
    {"00001000", 13}, {"00000111", 14}, {"00000110", 15}, {"0000010111", 16}, {"0000010110", 17},
    {"0000010101", 18}, {"0000010100", 19}, {"0000010011", 20}, {"0000010010", 21},
    {"00000100011", 22}, {"00000100010", 23}, {"00000100001", 24}, {"00000100000", 25},
    {"00000011111", 26}, {"00000011110", 27}, {"00000011101", 28}, {"00000011100", 29},
    {"00000011011", 30}, {"00000011010", 31}, {"00000011001", 32}, {"00000011000", 33},
    {"00000001000", 34}, {"00000001111", 35},
};

// B.2-B.4 macroblock_type, as flags.
enum { MB_QUANT = 1, MB_FWD = 2, MB_BWD = 4, MB_PATTERN = 8, MB_INTRA = 16 };
const Code kMbI[] = {{"1", MB_INTRA}, {"01", MB_INTRA | MB_QUANT}};
const Code kMbP[] = {
    {"1", MB_FWD | MB_PATTERN}, {"01", MB_PATTERN}, {"001", MB_FWD}, {"00011", MB_INTRA},
    {"00010", MB_QUANT | MB_FWD | MB_PATTERN}, {"00001", MB_QUANT | MB_PATTERN}, {"000001", MB_QUANT | MB_INTRA},
};
const Code kMbB[] = {
    {"10", MB_FWD | MB_BWD}, {"11", MB_FWD | MB_BWD | MB_PATTERN}, {"010", MB_BWD},
    {"011", MB_BWD | MB_PATTERN}, {"0010", MB_FWD}, {"0011", MB_FWD | MB_PATTERN}, {"00011", MB_INTRA},
    {"00010", MB_QUANT | MB_FWD | MB_BWD | MB_PATTERN}, {"000011", MB_QUANT | MB_FWD | MB_PATTERN},
    {"000010", MB_QUANT | MB_BWD | MB_PATTERN}, {"000001", MB_QUANT | MB_INTRA},
};

// B.9 coded_block_pattern (4:2:0).
const Code kCbp[] = {
    {"111", 60}, {"1101", 4}, {"1100", 8}, {"1011", 16}, {"1010", 32}, {"10011", 12}, {"10010", 48},
    {"10001", 20}, {"10000", 40}, {"01111", 28}, {"01110", 44}, {"01101", 52}, {"01100", 56},
    {"01011", 1}, {"01010", 61}, {"01001", 2}, {"01000", 62}, {"001111", 24}, {"001110", 36},
    {"001101", 3}, {"001100", 63}, {"0010111", 5}, {"0010110", 9}, {"0010101", 17}, {"0010100", 33},
    {"0010011", 6}, {"0010010", 10}, {"0010001", 18}, {"0010000", 34}, {"00011111", 7},
    {"00011110", 11}, {"00011101", 19}, {"00011100", 35}, {"00011011", 13}, {"00011010", 49},
    {"00011001", 21}, {"00011000", 41}, {"00010111", 14}, {"00010110", 50}, {"00010101", 22},
    {"00010100", 42}, {"00010011", 15}, {"00010010", 51}, {"00010001", 23}, {"00010000", 43},
    {"00001111", 25}, {"00001110", 37}, {"00001101", 26}, {"00001100", 38}, {"00001011", 29},
    {"00001010", 45}, {"00001001", 53}, {"00001000", 57}, {"00000111", 30}, {"00000110", 46},
    {"00000101", 54}, {"00000100", 58}, {"000000111", 31}, {"000000110", 47}, {"000000101", 55},
    {"000000100", 59}, {"000000011", 27}, {"000000010", 39}, {"000000001", 0},
};

// B.10 motion_code, the magnitude; a sign bit follows every code but "1".
const Code kMotion[] = {
    {"1", 0}, {"01", 1}, {"001", 2}, {"0001", 3}, {"000011", 4}, {"0000101", 5}, {"0000100", 6},
    {"0000011", 7}, {"000001011", 8}, {"000001010", 9}, {"000001001", 10}, {"0000010001", 11},
    {"0000010000", 12}, {"0000001111", 13}, {"0000001110", 14}, {"0000001101", 15}, {"0000001100", 16},
};

// B.12, B.13 dct_dc_size.
const Code kDcLuma[] = {
    {"100", 0}, {"00", 1}, {"01", 2}, {"101", 3}, {"110", 4}, {"1110", 5}, {"11110", 6},
    {"111110", 7}, {"1111110", 8}, {"11111110", 9}, {"111111110", 10}, {"111111111", 11},
};
const Code kDcChroma[] = {
    {"00", 0}, {"01", 1}, {"10", 2}, {"110", 3}, {"1110", 4}, {"11110", 5}, {"111110", 6},
    {"1111110", 7}, {"11111110", 8}, {"111111110", 9}, {"1111111110", 10}, {"1111111111", 11},
};

// B.14 and B.15, the DCT coefficients: run, level; a sign bit follows.
constexpr int EOB = 64, ESC = 65;
#define DCT_LONG_CODES \
    {"00000000011111", 0, 16}, {"00000000011110", 0, 17}, {"00000000011101", 0, 18}, \
    {"00000000011100", 0, 19}, {"00000000011011", 0, 20}, {"00000000011010", 0, 21}, \
    {"00000000011001", 0, 22}, {"00000000011000", 0, 23}, {"00000000010111", 0, 24}, \
    {"00000000010110", 0, 25}, {"00000000010101", 0, 26}, {"00000000010100", 0, 27}, \
    {"00000000010011", 0, 28}, {"00000000010010", 0, 29}, {"00000000010001", 0, 30}, \
    {"00000000010000", 0, 31}, {"000000000011000", 0, 32}, {"000000000010111", 0, 33}, \
    {"000000000010110", 0, 34}, {"000000000010101", 0, 35}, {"000000000010100", 0, 36}, \
    {"000000000010011", 0, 37}, {"000000000010010", 0, 38}, {"000000000010001", 0, 39}, \
    {"000000000010000", 0, 40}, {"000000000011111", 1, 8}, {"000000000011110", 1, 9}, \
    {"000000000011101", 1, 10}, {"000000000011100", 1, 11}, {"000000000011011", 1, 12}, \
    {"000000000011010", 1, 13}, {"000000000011001", 1, 14}, {"0000000000010011", 1, 15}, \
    {"0000000000010010", 1, 16}, {"0000000000010001", 1, 17}, {"0000000000010000", 1, 18}, \
    {"0000000000010100", 6, 3}, {"0000000000011010", 11, 2}, {"0000000000011001", 12, 2}, \
    {"0000000000011000", 13, 2}, {"0000000000010111", 14, 2}, {"0000000000010110", 15, 2}, \
    {"0000000000010101", 16, 2}, {"0000000000011111", 27, 1}, {"0000000000011110", 28, 1}, \
    {"0000000000011101", 29, 1}, {"0000000000011100", 30, 1}, {"0000000000011011", 31, 1}
#define DCT_13BIT_CODES \
    {"0000000010110", 1, 6}, {"0000000010101", 1, 7}, {"0000000010100", 2, 5}, \
    {"0000000010011", 3, 4}, {"0000000010010", 5, 3}, {"0000000010001", 9, 2}, \
    {"0000000010000", 10, 2}, {"0000000011111", 22, 1}, {"0000000011110", 23, 1}, \
    {"0000000011101", 24, 1}, {"0000000011100", 25, 1}, {"0000000011011", 26, 1}
#define DCT_12BIT_CODES \
    {"000000011100", 3, 3}, {"000000010010", 4, 3}, {"000000011110", 6, 2}, \
    {"000000010101", 7, 2}, {"000000010001", 8, 2}, {"000000011111", 17, 1}, \
    {"000000011010", 18, 1}, {"000000011001", 19, 1}, {"000000010111", 20, 1}, \
    {"000000010110", 21, 1}

// Table zero. Its first code, "1s" for (0, 1), is only read as the first
// coefficient of a non-intra block; elsewhere "10" is the end of block.
const Code kDct0[] = {
    {"10", EOB, 0}, {"000001", ESC, 0},
    {"11", 0, 1}, {"011", 1, 1}, {"0100", 0, 2}, {"0101", 2, 1}, {"00101", 0, 3}, {"00111", 3, 1},
    {"00110", 4, 1}, {"000110", 1, 2}, {"000111", 5, 1}, {"000101", 6, 1}, {"000100", 7, 1},
    {"0000110", 0, 4}, {"0000100", 2, 2}, {"0000111", 8, 1}, {"0000101", 9, 1},
    {"00100110", 0, 5}, {"00100001", 0, 6}, {"00100101", 1, 3}, {"00100100", 3, 2},
    {"00100111", 10, 1}, {"00100011", 11, 1}, {"00100010", 12, 1}, {"00100000", 13, 1},
    {"0000001010", 0, 7}, {"0000001100", 1, 4}, {"0000001011", 2, 3}, {"0000001111", 4, 2},
    {"0000001001", 5, 2}, {"0000001110", 14, 1}, {"0000001101", 15, 1}, {"0000001000", 16, 1},
    {"000000011101", 0, 8}, {"000000011000", 0, 9}, {"000000010011", 0, 10}, {"000000010000", 0, 11},
    {"000000011011", 1, 5}, {"000000010100", 2, 4},
    DCT_12BIT_CODES,
    {"0000000011010", 0, 12}, {"0000000011001", 0, 13}, {"0000000011000", 0, 14}, {"0000000010111", 0, 15},
    DCT_13BIT_CODES,
    DCT_LONG_CODES,
};

// Table one, for intra blocks when intra_vlc_format is set.
const Code kDct1[] = {
    {"0110", EOB, 0}, {"000001", ESC, 0},
    {"10", 0, 1}, {"010", 1, 1}, {"110", 0, 2}, {"00101", 2, 1}, {"0111", 0, 3}, {"00111", 3, 1},
    {"000110", 4, 1}, {"00110", 1, 2}, {"000111", 5, 1}, {"0000110", 6, 1}, {"0000100", 7, 1},
    {"11100", 0, 4}, {"0000111", 2, 2}, {"0000101", 8, 1}, {"1111000", 9, 1}, {"11101", 0, 5},
    {"000101", 0, 6}, {"1111001", 1, 3}, {"00100110", 3, 2}, {"1111010", 10, 1}, {"00100001", 11, 1},
    {"00100101", 12, 1}, {"00100100", 13, 1}, {"000100", 0, 7}, {"00100111", 1, 4},
    {"11111100", 2, 3}, {"11111101", 4, 2}, {"000000100", 5, 2}, {"000000101", 14, 1},
    {"000000111", 15, 1}, {"0000001101", 16, 1}, {"1111011", 0, 8}, {"1111100", 0, 9},
    {"00100011", 0, 10}, {"00100010", 0, 11}, {"00100000", 1, 5}, {"0000001100", 2, 4},
    DCT_12BIT_CODES,
    {"11111010", 0, 12}, {"11111011", 0, 13}, {"11111110", 0, 14}, {"11111111", 0, 15},
    DCT_13BIT_CODES,
    DCT_LONG_CODES,
};

struct Tables {
    Lut mba, mb[4], cbp, motion, dc_luma, dc_chroma, dct[2];
    Tables() {
        mba.build(kMba, std::size(kMba), 11, "B.1");
        mb[1].build(kMbI, std::size(kMbI), 2, "B.2");
        mb[2].build(kMbP, std::size(kMbP), 6, "B.3");
        mb[3].build(kMbB, std::size(kMbB), 6, "B.4");
        cbp.build(kCbp, std::size(kCbp), 9, "B.9");
        motion.build(kMotion, std::size(kMotion), 10, "B.10");
        dc_luma.build(kDcLuma, std::size(kDcLuma), 9, "B.12");
        dc_chroma.build(kDcChroma, std::size(kDcChroma), 10, "B.13");
        dct[0].build(kDct0, std::size(kDct0), 16, "B.14");
        dct[1].build(kDct1, std::size(kDct1), 16, "B.15");
    }
};
const Tables& tables() { static const Tables t; return t; }

// ---- scans, matrices, the quantiser scale --------------------------------------------
const uint8_t kScan[2][64] = {
    {0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6,
     7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31,
     39, 46, 53, 60, 61, 54, 47, 55, 62, 63},
    {0, 8, 16, 24, 1, 9, 2, 10, 17, 25, 32, 40, 48, 56, 57, 49, 41, 33, 26, 18, 3, 11, 4, 12, 19, 27, 34, 42,
     50, 58, 35, 43, 51, 59, 20, 28, 5, 13, 6, 14, 21, 29, 36, 44, 52, 60, 37, 45, 53, 61, 22, 30, 7, 15,
     23, 31, 38, 46, 54, 62, 39, 47, 55, 63},
};
const uint8_t kDefaultIntra[64] = {   // in raster order
    8, 16, 19, 22, 26, 27, 29, 34, 16, 16, 22, 24, 27, 29, 34, 37, 19, 22, 26, 27, 29, 34, 34, 38,
    22, 22, 26, 27, 29, 34, 37, 40, 22, 26, 27, 29, 32, 35, 40, 48, 26, 27, 29, 32, 35, 40, 48, 58,
    26, 27, 29, 34, 38, 46, 56, 69, 27, 29, 35, 38, 46, 56, 69, 83,
};
const uint8_t kNonLinearQ[32] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 22,
                                 24, 28, 32, 36, 40, 44, 48, 52, 56, 64, 72, 80, 88, 96, 104, 112};

// ---- the inverse DCT ---------------------------------------------------------------------
constexpr double kPi = 3.14159265358979323846;

struct Idct {
    float c[8][8];                       // c[u][x] = C(u)/2 cos((2x+1)u pi/16)
    Idct() {
        for (int u = 0; u < 8; ++u)
            for (int x = 0; x < 8; ++x)
                c[u][x] = (float)((u ? 0.5 : 0.5 / std::sqrt(2.0)) * std::cos((2 * x + 1) * u * kPi / 16));
    }
    // F in raster order (v rows, u columns) to f, rounded, clamped to [-256, 255].
    void run(const int32_t* F, int16_t* f) const {
        float t[64];
        for (int v = 0; v < 8; ++v) {    // rows: over u, for each x
            const int32_t* r = F + 8 * v;
            float* o = t + 8 * v;
            if (!(r[0] | r[1] | r[2] | r[3] | r[4] | r[5] | r[6] | r[7])) {
                for (int x = 0; x < 8; ++x) o[x] = 0;
                continue;
            }
            for (int x = 0; x < 8; ++x) {
                float s = 0;
                for (int u = 0; u < 8; ++u) s += c[u][x] * (float)r[u];
                o[x] = s;
            }
        }
        for (int x = 0; x < 8; ++x)      // columns: over v, for each y
            for (int y = 0; y < 8; ++y) {
                float s = 0;
                for (int v = 0; v < 8; ++v) s += c[v][y] * t[8 * v + x];
                float r = std::floor(s + 0.5f);
                f[8 * y + x] = (int16_t)std::clamp(r, -256.0f, 255.0f);
            }
    }
};
const Idct& idct() { static const Idct t; return t; }

uint8_t clip8(int v) { return (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v); }

// ---- the bit reader -------------------------------------------------------------------
// Over a buffer with at least 8 zero bytes past its end.
struct Bits {
    const uint8_t* p;
    size_t pos = 0;                      // in bits
    uint32_t peek(int n) const {
        const uint8_t* q = p + (pos >> 3);
        uint64_t w = (uint64_t)q[0] << 56 | (uint64_t)q[1] << 48 | (uint64_t)q[2] << 40 | (uint64_t)q[3] << 32 |
                     (uint64_t)q[4] << 24 | (uint64_t)q[5] << 16 | (uint64_t)q[6] << 8 | q[7];
        return (uint32_t)((w << (pos & 7)) >> (64 - n));
    }
    void skip(int n) { pos += n; }
    uint32_t get(int n) { uint32_t v = peek(n); pos += n; return v; }
    bool get1() { return get(1) != 0; }
    const Entry& vlc(const Lut& t) {
        const Entry& e = t.e[peek(t.width)];
        pos += e.len;
        return e;
    }
};

struct Frame {
    std::vector<uint8_t> y, cb, cr;
    int type = 0, fields = 2;
};

}  // namespace

// ---- the decoder ---------------------------------------------------------------------------
struct Mpeg2Decoder::Impl {
    uint32_t err_mask = 0, err_count = 0;
    void error(int kind, const char* what) {
        if (!(err_mask & (1u << kind))) {
            err_mask |= 1u << kind;
            std::fprintf(stderr, "mpeg2: %s\n", what);
        }
        ++err_count;
    }

    // The stream, split into start-code units.
    std::vector<uint8_t> buf, unit;
    size_t start = std::string::npos, scanned = 0;

    // Sequence.
    bool have_seq = false;
    int width = 0, height = 0, frame_rate_code = 4, matrix = 1;
    bool progressive_seq = true;
    int mb_w = 0, mb_h = 0, ystride = 0, cstride = 0;
    uint8_t q_intra[64], q_inter[64], q_cintra[64], q_cinter[64];   // raster order

    // Picture.
    int last_header = 0;                 // 0xB3 or 0x00: what an extension belongs to
    bool in_picture = false, decoded_any = false, skip_picture = false;
    int ptype = 0, f_code[2][2] = {{15, 15}, {15, 15}};
    int dc_precision = 0, structure = 3, tff = 0, frame_pred_frame_dct = 1, concealment = 0;
    int q_scale_type = 0, intra_vlc = 0, alt_scan = 0, rff = 0, progressive_frame = 1;
    bool have_pce = false;

    Frame frames[3];
    Frame* fwd = &frames[0];
    Frame* bwd = &frames[1];
    Frame* cur = nullptr;
    bool fwd_valid = false, bwd_valid = false;

    // Slice state.
    int qscale = 0, dc_pred[3] = {0, 0, 0};
    int pmv[2][2][2] = {};               // [r][s][t]
    struct Mc { int flags = 0, motion_type = 2; int mv[2][2][2] = {}; int sel[2][2] = {}; } last_mc;

    Impl() {
        tables();
        idct();
        default_matrices();
    }

    void default_matrices() {
        std::memcpy(q_intra, kDefaultIntra, 64);
        std::memset(q_inter, 16, 64);
        std::memcpy(q_cintra, kDefaultIntra, 64);
        std::memset(q_cinter, 16, 64);
    }

    void load_matrix(Bits& b, uint8_t* m) {
        for (int i = 0; i < 64; ++i) m[kScan[0][i]] = (uint8_t)b.get(8);
    }

    // ---- splitting into units
    void push(const uint8_t* data, size_t n) {
        buf.insert(buf.end(), data, data + n);
        size_t i = std::max(scanned, start == std::string::npos ? (size_t)0 : start + 4);
        while (i + 3 <= buf.size()) {
            const uint8_t* q = (const uint8_t*)std::memchr(&buf[i], 0, buf.size() - i);
            if (!q) { i = buf.size(); break; }
            i = q - buf.data();
            if (i + 3 > buf.size()) break;
            if (buf[i + 1] == 0 && buf[i + 2] == 1) {
                if (start != std::string::npos) run_unit(start, i);
                start = i;
                i += 4;
            } else {
                ++i;
            }
        }
        scanned = i;
        if (start != std::string::npos && start > (1u << 20)) {   // keep the buffer from growing
            buf.erase(buf.begin(), buf.begin() + start);
            scanned -= start;
            start = 0;
        }
    }

    void flush() {
        if (start != std::string::npos && start + 3 < buf.size()) run_unit(start, buf.size());
        buf.clear();
        start = std::string::npos;
        scanned = 0;
        finish_picture();
        if (bwd_valid) output(*bwd);
        fwd_valid = bwd_valid = false;
    }

    void reset() {
        buf.clear();
        start = std::string::npos;
        scanned = 0;
        in_picture = false;
        fwd_valid = bwd_valid = false;
        have_seq = false;
    }

    void run_unit(size_t a, size_t b) {
        unit.assign(buf.begin() + a + 3, buf.begin() + b);
        size_t n = unit.size();
        unit.resize(n + 16, 0);
        if (n == 0) return;
        Bits bits{unit.data()};
        uint8_t code = bits.get(8);
        if (code >= 0x01 && code <= 0xAF) {
            if (in_picture && !skip_picture) slice(bits, code, n);
        } else if (code == 0x00) {
            finish_picture();
            picture_header(bits);
        } else if (code == 0xB3) {
            finish_picture();
            sequence_header(bits);
        } else if (code == 0xB5) {
            extension(bits);
        } else if (code == 0xB8) {
            finish_picture();
        } else if (code == 0xB7) {
            finish_picture();
        }
    }

    // ---- headers
    void sequence_header(Bits& b) {
        int w = b.get(12), h = b.get(12);
        b.skip(4);                       // aspect ratio
        frame_rate_code = b.get(4);
        b.skip(18 + 1 + 10 + 1);         // bit rate, marker, vbv buffer size, constrained
        std::memcpy(q_intra, kDefaultIntra, 64);
        std::memcpy(q_cintra, kDefaultIntra, 64);
        std::memset(q_inter, 16, 64);
        std::memset(q_cinter, 16, 64);
        if (b.get1()) { load_matrix(b, q_intra); std::memcpy(q_cintra, q_intra, 64); }
        if (b.get1()) { load_matrix(b, q_inter); std::memcpy(q_cinter, q_inter, 64); }
        if (w != width || h != height || !have_seq) {
            width = w; height = h;
            fwd_valid = bwd_valid = false;
        }
        have_seq = true;
        last_header = 0xB3;
    }

    void layout() {
        mb_w = (width + 15) / 16;
        mb_h = progressive_seq ? (height + 15) / 16 : 2 * ((height + 31) / 32);
        ystride = mb_w * 16;
        cstride = mb_w * 8;
        for (Frame& f : frames) {
            f.y.resize((size_t)ystride * mb_h * 16);
            f.cb.resize((size_t)cstride * mb_h * 8);
            f.cr.resize((size_t)cstride * mb_h * 8);
        }
    }

    void extension(Bits& b) {
        int id = b.get(4);
        if (id == 1 && last_header == 0xB3) {          // sequence extension
            b.skip(8);                   // profile and level
            progressive_seq = b.get1();
            int chroma = b.get(2);
            if (chroma != 1) error(0, "4:2:2 and 4:4:4 are not supported");
            width |= b.get(2) << 12;
            height |= b.get(2) << 12;
            layout();
        } else if (id == 2 && last_header == 0xB3) {   // sequence display extension
            b.skip(3);                   // video format
            if (b.get1()) {
                b.skip(8 + 8);           // colour primaries, transfer characteristics
                matrix = b.get(8);
            }
        } else if (id == 3) {            // quant matrix extension
            if (b.get1()) { load_matrix(b, q_intra); std::memcpy(q_cintra, q_intra, 64); }
            if (b.get1()) { load_matrix(b, q_inter); std::memcpy(q_cinter, q_inter, 64); }
            if (b.get1()) load_matrix(b, q_cintra);
            if (b.get1()) load_matrix(b, q_cinter);
        } else if (id == 8 && last_header == 0x00) {   // picture coding extension
            f_code[0][0] = b.get(4); f_code[0][1] = b.get(4);
            f_code[1][0] = b.get(4); f_code[1][1] = b.get(4);
            dc_precision = b.get(2);
            structure = b.get(2);
            tff = b.get1();
            frame_pred_frame_dct = b.get1();
            concealment = b.get1();
            q_scale_type = b.get1();
            intra_vlc = b.get1();
            alt_scan = b.get1();
            rff = b.get1();
            b.skip(1);                   // chroma_420_type
            progressive_frame = b.get1();
            have_pce = true;
            if (structure != 3) {
                error(1, "field pictures are not supported");
                skip_picture = true;
            }
        } else if (id >= 5 && id <= 10 && id != 8) {
            error(2, "scalable and other extensions are not supported");
        }
    }

    void picture_header(Bits& b) {
        last_header = 0x00;
        have_pce = false;
        skip_picture = false;
        if (!have_seq || !mb_w) { in_picture = false; return; }
        b.skip(10);                      // temporal reference
        ptype = b.get(3);
        b.skip(16);                      // vbv delay
        if (ptype < 1 || ptype > 3) { in_picture = false; return; }
        in_picture = true;
        decoded_any = false;
        // A P picture needs one reference, a B picture two: at the start of a
        // stream, or after a broken link, the pictures that lack them are dropped.
        if (ptype == 2 && !bwd_valid) skip_picture = true;
        if (ptype == 3 && !(fwd_valid && bwd_valid)) skip_picture = true;
        if (ptype == 3) {
            cur = &frames[0];
            while (cur == fwd || cur == bwd) ++cur;
        } else {
            std::swap(fwd, bwd);         // the old forward reference was output already
            fwd_valid = bwd_valid;
            bwd_valid = false;
            cur = bwd;
        }
        cur->type = ptype;
    }

    void finish_picture() {
        if (!in_picture) return;
        in_picture = false;
        if (!have_pce) { error(3, "MPEG-1 streams are not supported"); return; }
        if (skip_picture || !decoded_any) return;
        cur->fields = progressive_seq ? (rff ? (tff ? 6 : 4) : 2) : (rff ? 3 : 2);
        if (ptype == 3) {
            output(*cur);
        } else {
            bwd_valid = true;
            if (fwd_valid) output(*fwd);
        }
    }

    Mpeg2Decoder* owner = nullptr;
    void output(const Frame& f) {
        if (!owner->on_picture) return;
        Mpeg2Picture p;
        p.width = width; p.height = height;
        p.y = f.y.data(); p.cb = f.cb.data(); p.cr = f.cr.data();
        p.y_stride = ystride; p.c_stride = cstride;
        p.type = f.type; p.fields = f.fields;
        p.frame_rate_code = frame_rate_code;
        p.matrix = matrix;
        owner->on_picture(p);
    }

    // ---- slices and macroblocks
    int motion_delta(Bits& b, int fcode) {
        const Entry& e = b.vlc(tables().motion);
        if (!e.len) return 0x7FFF;
        int code = e.a;
        if (code && b.get1()) code = -code;
        int r_size = fcode - 1;
        if (r_size == 0 || code == 0) return code;
        int residual = b.get(r_size);
        int delta = ((std::abs(code) - 1) << r_size) + residual + 1;
        return code < 0 ? -delta : delta;
    }

    // One motion vector component, predicted from pmv; field vectors in frame
    // pictures are kept in frame units and predicted in field units.
    bool motion_vector(Bits& b, int r, int s, bool field, int out[2]) {
        for (int t = 0; t < 2; ++t) {
            int fcode = f_code[s][t];
            int delta = motion_delta(b, fcode);
            if (delta == 0x7FFF) return false;
            int r_size = fcode - 1, f = 1 << r_size;
            int low = -16 * f, high = 16 * f - 1, range = 32 * f;
            int pred = pmv[r][s][t];
            if (field && t == 1) pred >>= 1;
            int v = pred + delta;
            if (v < low) v += range;
            if (v > high) v -= range;
            out[t] = v;
            pmv[r][s][t] = (field && t == 1) ? v * 2 : v;
        }
        return true;
    }

    // Read the vectors of direction s for this macroblock's motion type.
    bool motion_vectors(Bits& b, int s, int motion_type, Mc& mc) {
        if (motion_type == 1) {          // field: two vectors, each with a field select
            for (int r = 0; r < 2; ++r) {
                mc.sel[r][s] = b.get1();
                if (!motion_vector(b, r, s, true, mc.mv[r][s])) return false;
            }
        } else {                         // frame (or dual prime, rejected earlier)
            if (!motion_vector(b, 0, s, false, mc.mv[0][s])) return false;
            pmv[1][s][0] = pmv[0][s][0];
            pmv[1][s][1] = pmv[0][s][1];
        }
        return true;
    }

    // Predict a w x h block of one plane. ref lines are taken every `step`
    // lines from line `ofs` (a field when step is 2); half-sample vectors.
    static void predict(uint8_t* dst, int dstride, const uint8_t* ref, int rstride, int pw, int ph,
                        int x, int y, int mvx, int mvy, int w, int h, bool avg) {
        int ix = x + (mvx >> 1), iy = y + (mvy >> 1), hx = mvx & 1, hy = mvy & 1;
        auto px = [&](int xx, int yy) -> int {
            xx = xx < 0 ? 0 : xx >= pw ? pw - 1 : xx;
            yy = yy < 0 ? 0 : yy >= ph ? ph - 1 : yy;
            return ref[(size_t)yy * rstride + xx];
        };
        bool inside = ix >= 0 && iy >= 0 && ix + w + hx <= pw && iy + h + hy <= ph;
        for (int j = 0; j < h; ++j) {
            uint8_t* o = dst + (size_t)j * dstride;
            if (inside) {
                const uint8_t* a = ref + (size_t)(iy + j) * rstride + ix;
                const uint8_t* c = a + rstride;
                for (int i = 0; i < w; ++i) {
                    int v;
                    if (!hx && !hy) v = a[i];
                    else if (hx && !hy) v = (a[i] + a[i + 1] + 1) >> 1;
                    else if (!hx) v = (a[i] + c[i] + 1) >> 1;
                    else v = (a[i] + a[i + 1] + c[i] + c[i + 1] + 2) >> 2;
                    o[i] = avg ? (uint8_t)((o[i] + v + 1) >> 1) : (uint8_t)v;
                }
            } else {
                for (int i = 0; i < w; ++i) {
                    int xx = ix + i, yy = iy + j, v;
                    if (!hx && !hy) v = px(xx, yy);
                    else if (hx && !hy) v = (px(xx, yy) + px(xx + 1, yy) + 1) >> 1;
                    else if (!hx) v = (px(xx, yy) + px(xx, yy + 1) + 1) >> 1;
                    else v = (px(xx, yy) + px(xx + 1, yy) + px(xx, yy + 1) + px(xx + 1, yy + 1) + 2) >> 2;
                    o[i] = avg ? (uint8_t)((o[i] + v + 1) >> 1) : (uint8_t)v;
                }
            }
        }
    }

    // The prediction of a macroblock into cur, from the references it names.
    void motion_compensate(int mbx, int mby, const Mc& mc) {
        bool avg = false;
        const int H = mb_h * 16;
        for (int s = 0; s < 2; ++s) {
            if (!(mc.flags & (s ? MB_BWD : MB_FWD))) continue;
            const Frame& r = s ? *bwd : *fwd;
            if (mc.motion_type == 2) {   // frame prediction
                int mvx = mc.mv[0][s][0], mvy = mc.mv[0][s][1];
                predict(&cur->y[(size_t)mby * 16 * ystride + mbx * 16], ystride, r.y.data(), ystride,
                        ystride, H, mbx * 16, mby * 16, mvx, mvy, 16, 16, avg);
                int cx = mvx / 2, cy = mvy / 2;
                predict(&cur->cb[(size_t)mby * 8 * cstride + mbx * 8], cstride, r.cb.data(), cstride,
                        cstride, H / 2, mbx * 8, mby * 8, cx, cy, 8, 8, avg);
                predict(&cur->cr[(size_t)mby * 8 * cstride + mbx * 8], cstride, r.cr.data(), cstride,
                        cstride, H / 2, mbx * 8, mby * 8, cx, cy, 8, 8, avg);
            } else {                     // field prediction: each field of the macroblock on its own
                for (int f = 0; f < 2; ++f) {
                    int sel = mc.sel[f][s];
                    int mvx = mc.mv[f][s][0], mvy = mc.mv[f][s][1];
                    predict(&cur->y[(size_t)(mby * 16 + f) * ystride + mbx * 16], 2 * ystride,
                            r.y.data() + (size_t)sel * ystride, 2 * ystride, ystride, H / 2,
                            mbx * 16, mby * 8, mvx, mvy, 16, 8, avg);
                    int cx = mvx / 2, cy = mvy / 2;
                    predict(&cur->cb[(size_t)(mby * 8 + f) * cstride + mbx * 8], 2 * cstride,
                            r.cb.data() + (size_t)sel * cstride, 2 * cstride, cstride, H / 4,
                            mbx * 8, mby * 4, cx, cy, 8, 4, avg);
                    predict(&cur->cr[(size_t)(mby * 8 + f) * cstride + mbx * 8], 2 * cstride,
                            r.cr.data() + (size_t)sel * cstride, 2 * cstride, cstride, H / 4,
                            mbx * 8, mby * 4, cx, cy, 8, 4, avg);
                }
            }
            avg = true;
        }
    }

    // One block's coefficients, dequantised into F (raster order).
    bool block(Bits& b, int i, bool intra, int32_t* F) {
        std::memset(F, 0, 64 * sizeof(int32_t));
        const uint8_t* scan = kScan[alt_scan];
        const bool chroma = i >= 4;
        const uint8_t* W = intra ? (chroma ? q_cintra : q_intra) : (chroma ? q_cinter : q_inter);
        int n = 0;
        int32_t sum = 0;
        if (intra) {
            const Entry& e = b.vlc(chroma ? tables().dc_chroma : tables().dc_luma);
            if (!e.len) return false;
            int size = e.a, diff = 0;
            if (size) {
                diff = b.get(size);
                if (!(diff >> (size - 1))) diff -= (1 << size) - 1;
            }
            int cc = chroma ? i - 3 : 0;
            dc_pred[cc] += diff;
            F[0] = dc_pred[cc] * (8 >> dc_precision);
            sum = F[0];
            n = 1;
        }
        const Lut& t = tables().dct[intra && intra_vlc];
        bool first = !intra;
        for (;;) {
            int run, level;
            if (first && b.peek(1)) {    // "1s": (0, 1) as a non-intra block's first coefficient
                b.skip(1);
                run = 0; level = b.get1() ? -1 : 1;
            } else {
                const Entry& e = b.vlc(t);
                if (!e.len) return false;
                if (e.a == EOB) break;
                if (e.a == ESC) {
                    run = b.get(6);
                    level = b.get(12);
                    if (level >= 2048) level -= 4096;
                    if (level == 0 || level == -2048) return false;
                } else {
                    run = e.a;
                    level = b.get1() ? -e.b : e.b;
                }
            }
            first = false;
            n += run;
            if (n > 63) return false;
            int pos = scan[n++];
            int32_t v = intra ? (2 * level * W[pos] * qscale) / 32
                              : ((2 * level + (level > 0 ? 1 : -1)) * W[pos] * qscale) / 32;
            v = std::clamp(v, -2048, 2047);
            F[pos] = v;
            sum += v;
        }
        if (!(sum & 1)) F[63] += (F[63] & 1) ? -1 : 1;
        return true;
    }

    // Write or add a block's samples into cur.
    void put_block(int i, int mbx, int mby, bool field_dct, const int16_t* f, bool add) {
        uint8_t* dst;
        int stride;
        if (i < 4) {
            int bx = mbx * 16 + (i & 1) * 8;
            if (field_dct) {
                dst = &cur->y[(size_t)(mby * 16 + (i >> 1)) * ystride + bx];
                stride = 2 * ystride;
            } else {
                dst = &cur->y[(size_t)(mby * 16 + (i >> 1) * 8) * ystride + bx];
                stride = ystride;
            }
        } else {
            dst = &(i == 4 ? cur->cb : cur->cr)[(size_t)mby * 8 * cstride + mbx * 8];
            stride = cstride;
        }
        for (int y = 0; y < 8; ++y)
            for (int x = 0; x < 8; ++x) {
                uint8_t* o = dst + (size_t)y * stride + x;
                *o = clip8((add ? *o : 0) + f[8 * y + x]);
            }
    }

    void reset_dc() { dc_pred[0] = dc_pred[1] = dc_pred[2] = 1 << (7 + dc_precision); }

    void skipped(int mbx, int mby) {
        reset_dc();
        Mc mc;
        if (ptype == 2) {                // P: forward, zero vector, frame prediction
            std::memset(pmv, 0, sizeof pmv);
            mc.flags = MB_FWD;
            mc.motion_type = 2;
            std::memset(mc.mv, 0, sizeof mc.mv);
        } else {                         // B: the previous macroblock's directions, frame
            mc.flags = last_mc.flags & (MB_FWD | MB_BWD);   // prediction with the vector predictors
            mc.motion_type = 2;
            for (int s = 0; s < 2; ++s) {
                mc.mv[0][s][0] = pmv[0][s][0];
                mc.mv[0][s][1] = pmv[0][s][1];
            }
        }
        motion_compensate(mbx, mby, mc);
    }

    void slice(Bits& b, int code, size_t n) {
        const size_t end = n * 8;
        int mb_row = code - 1;
        if (mb_row >= mb_h) { error(4, "a slice below the picture"); return; }
        int qsc = b.get(5);
        qscale = q_scale_type ? kNonLinearQ[qsc] : 2 * qsc;
        if (b.peek(1)) {                 // intra_slice_flag, intra_slice, reserved; then extra information
            b.skip(9);
            while (b.get1()) b.skip(8);
        } else {
            b.skip(1);
        }
        reset_dc();
        std::memset(pmv, 0, sizeof pmv);
        last_mc = Mc();
        int addr = mb_row * mb_w - 1;
        bool first = true;
        alignas(16) int32_t F[64];
        alignas(16) int16_t f[64];
        while (b.pos < end && b.peek(23) != 0) {
            int inc = 0;
            for (;;) {
                const Entry& e = b.vlc(tables().mba);
                if (!e.len) { error(5, "damaged data: macroblock address"); return; }
                if (e.a == 34) { inc += 33; continue; }
                if (e.a == 35) continue;
                inc += e.a;
                break;
            }
            if (first) { addr += inc; first = false; }
            else {
                for (int k = 1; k < inc; ++k) {
                    ++addr;
                    if (addr >= mb_w * mb_h) return;
                    skipped(addr % mb_w, addr / mb_w);
                }
                ++addr;
            }
            if (addr >= mb_w * mb_h) { error(4, "a macroblock past the picture"); return; }
            int mbx = addr % mb_w, mby = addr / mb_w;
            const Entry& te = b.vlc(tables().mb[ptype]);
            if (!te.len) { error(5, "damaged data: macroblock type"); return; }
            Mc mc;
            mc.flags = te.a;
            mc.motion_type = 2;
            const bool intra = mc.flags & MB_INTRA;
            if (mc.flags & (MB_FWD | MB_BWD)) {
                if (!frame_pred_frame_dct) mc.motion_type = b.get(2);
                if (mc.motion_type == 3) { error(6, "dual-prime prediction is not supported"); return; }
                if (mc.motion_type == 0) { error(5, "damaged data: motion type"); return; }
            }
            bool field_dct = false;
            if (!frame_pred_frame_dct && (intra || (mc.flags & MB_PATTERN))) field_dct = b.get1();
            if (mc.flags & MB_QUANT) {
                int c = b.get(5);
                qscale = q_scale_type ? kNonLinearQ[c] : 2 * c;
            }
            if ((mc.flags & MB_FWD) || (intra && concealment)) {
                if (!motion_vectors(b, 0, intra ? 2 : mc.motion_type, mc)) { error(5, "damaged data: motion vector"); return; }
            }
            if (mc.flags & MB_BWD) {
                if (!motion_vectors(b, 1, mc.motion_type, mc)) { error(5, "damaged data: motion vector"); return; }
            }
            if (intra && concealment) b.skip(1);
            int cbp = 0;
            if (mc.flags & MB_PATTERN) {
                const Entry& e = b.vlc(tables().cbp);
                if (!e.len) { error(5, "damaged data: coded block pattern"); return; }
                cbp = e.a;
            } else if (intra) {
                cbp = 63;
            }
            if (intra) {
                if (!concealment) std::memset(pmv, 0, sizeof pmv);
            } else {
                reset_dc();
                if (ptype == 2 && !(mc.flags & MB_FWD)) {   // P, no motion: forward, zero vector
                    std::memset(pmv, 0, sizeof pmv);
                    mc.flags |= MB_FWD;
                    mc.motion_type = 2;
                    std::memset(mc.mv, 0, sizeof mc.mv);
                }
                motion_compensate(mbx, mby, mc);
                last_mc = mc;
            }
            for (int i = 0; i < 6; ++i) {
                if (!(cbp & (32 >> i))) continue;
                if (!block(b, i, intra, F)) { error(5, "damaged data: DCT coefficients"); return; }
                idct().run(F, f);
                put_block(i, mbx, mby, field_dct && i < 4, f, !intra);
            }
            decoded_any = true;
        }
    }
};

Mpeg2Decoder::Mpeg2Decoder() : d(new Impl) { d->owner = this; }
Mpeg2Decoder::~Mpeg2Decoder() { delete d; }
void Mpeg2Decoder::push(const uint8_t* data, size_t n) { d->push(data, n); }
void Mpeg2Decoder::flush() { d->flush(); }
void Mpeg2Decoder::reset() { d->reset(); }
uint32_t Mpeg2Decoder::errors() const { return d->err_count; }
