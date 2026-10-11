// ps3kit runtime — OpenType fonts: sfnt tables and CFF outlines. See otf.h.
//
// What is read: head (units per em), hhea and hmtx (horizontal metrics),
// vhea, vmtx and VORG (vertical metrics), cmap (formats 4 and 12, Unicode
// subtables), maxp, and CFF: the INDEXes, the Top DICT, the Private DICTs
// with their local subroutines, and for a CID-keyed font the FDArray and
// FDSelect. Type 2 charstrings are run in full except that hints are
// skipped (stems are counted only to size a hint mask) and `seac`-style
// accented endchar is not supported. TrueType outlines (glyf) are not read.
#include "otf.h"
#include <cmath>
#include <cstdlib>
#include <cstring>

namespace otf {

namespace {
inline uint32_t be16(const uint8_t* p) { return (uint32_t)p[0] << 8 | p[1]; }
inline uint32_t be32(const uint8_t* p) { return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3]; }
inline int16_t s16(const uint8_t* p) { return (int16_t)be16(p); }

int subr_bias(uint32_t count) { return count < 1240 ? 107 : count < 33900 ? 1131 : 32768; }

// A DICT's operands up to its next operator.
struct DictReader {
    const uint8_t* p;
    const uint8_t* end;
    double args[48];
    int n = 0;
    // The next operator (12 xx as 1200 + xx), its operands in args; -1 at the end or on error.
    int next() {
        n = 0;
        while (p < end) {
            uint8_t b = *p++;
            if (b <= 21) {
                if (b != 12) return b;
                if (p >= end) return -1;
                return 1200 + *p++;
            }
            double v;
            if (b == 28) { if (end - p < 2) return -1; v = s16(p); p += 2; }
            else if (b == 29) { if (end - p < 4) return -1; v = (int32_t)be32(p); p += 4; }
            else if (b == 30) {
                char s[64]; int k = 0; bool done = false;
                while (!done && p < end) {
                    uint8_t byte = *p++;
                    for (int h = 0; h < 2 && !done; ++h) {
                        int nib = h ? byte & 15 : byte >> 4;
                        if (k > 60) return -1;
                        if (nib <= 9) s[k++] = (char)('0' + nib);
                        else if (nib == 0xA) s[k++] = '.';
                        else if (nib == 0xB) s[k++] = 'E';
                        else if (nib == 0xC) { s[k++] = 'E'; s[k++] = '-'; }
                        else if (nib == 0xE) s[k++] = '-';
                        else if (nib == 0xF) done = true;
                    }
                }
                s[k] = 0;
                v = std::strtod(s, nullptr);
            }
            else if (b >= 32 && b <= 246) v = (int)b - 139;
            else if (b >= 247 && b <= 250) { if (p >= end) return -1; v = ((int)b - 247) * 256 + *p++ + 108; }
            else if (b >= 251 && b <= 254) { if (p >= end) return -1; v = -((int)b - 251) * 256 - *p++ - 108; }
            else return -1;
            if (n < 48) args[n++] = v;
        }
        return -1;
    }
};
}  // namespace

bool Path::cbox(float& x0, float& y0, float& x1, float& y1) const {
    if (pts.empty()) return false;
    x0 = x1 = pts[0];
    y0 = y1 = pts[1];
    for (size_t i = 2; i + 1 < pts.size(); i += 2) {
        x0 = std::fmin(x0, pts[i]); x1 = std::fmax(x1, pts[i]);
        y0 = std::fmin(y0, pts[i + 1]); y1 = std::fmax(y1, pts[i + 1]);
    }
    return true;
}

Face::Range Face::table(const char* tag) const {
    for (uint32_t i = 0; i < ntables_; ++i) {
        const uint8_t* r = d_ + 12 + 16 * i;
        if (std::memcmp(r, tag, 4) == 0) {
            uint32_t off = be32(r + 8), size = be32(r + 12);
            if (off <= n_ && size <= n_ - off) return {off, size};
        }
    }
    return {};
}

bool Face::read_index(uint32_t at, Index& ix, uint32_t* end) const {
    if (at + 2 > n_) return false;
    ix = {};
    ix.count = be16(d_ + at);
    if (ix.count == 0) { if (end) *end = at + 2; return true; }
    if (at + 3 > n_) return false;
    ix.off_size = d_[at + 2];
    if (ix.off_size < 1 || ix.off_size > 4) return false;
    ix.offsets = at + 3;
    uint64_t last_at = ix.offsets + (uint64_t)ix.count * ix.off_size;
    if (last_at + ix.off_size > n_) return false;
    ix.data = (uint32_t)(last_at + ix.off_size - 1);
    uint32_t last = 0;
    for (uint32_t k = 0; k < ix.off_size; ++k) last = last << 8 | d_[last_at + k];
    if ((uint64_t)ix.data + last > n_) return false;
    if (end) *end = ix.data + last;
    return true;
}

bool Face::index_item(const Index& ix, uint32_t i, uint32_t& off, uint32_t& size) const {
    if (i >= ix.count) return false;
    auto at = [&](uint32_t k) {
        uint32_t v = 0;
        const uint8_t* p = d_ + ix.offsets + k * ix.off_size;
        for (uint32_t b = 0; b < ix.off_size; ++b) v = v << 8 | p[b];
        return v;
    };
    uint32_t a = at(i), b = at(i + 1);
    if (a < 1 || b < a || (uint64_t)ix.data + b > n_) return false;
    off = ix.data + a;
    size = b - a;
    return true;
}

bool Face::read_private(uint32_t dict_off, uint32_t dict_size, Private& p) const {
    p = {};
    if ((uint64_t)dict_off + dict_size > n_) return false;
    DictReader r{d_ + dict_off, d_ + dict_off + dict_size, {}};
    for (int op; (op = r.next()) >= 0;) {
        if (op == 19 && r.n >= 1) {                 // Subrs, from the Private DICT's start
            if (!read_index(dict_off + (uint32_t)r.args[0], p.subrs, nullptr)) return false;
            p.subr_bias = subr_bias(p.subrs.count);
        }
    }
    return true;
}

bool Face::open(const uint8_t* data, size_t size, std::string* err) {
    auto fail = [&](const char* why) { if (err) *err = why; return false; };
    d_ = data;
    n_ = size;
    if (n_ < 12) return fail("too short for an sfnt");
    uint32_t tag = be32(d_);
    if (tag != 0x4F54544Fu && tag != 0x00010000u && tag != 0x74727565u) return fail("not an sfnt (OTTO, 1.0 or true)");
    ntables_ = be16(d_ + 4);
    if (12 + 16ull * ntables_ > n_) return fail("table directory runs past the end");

    Range head = table("head"), hhea = table("hhea"), hmtx = table("hmtx"), maxp = table("maxp");
    if (head.size < 54 || hhea.size < 36 || !hmtx.size || maxp.size < 6) return fail("head, hhea, hmtx or maxp missing");
    upem_ = (int)be16(d_ + head.off + 18);
    if (upem_ <= 0) return fail("units per em is zero");
    nglyphs_ = (int)be16(d_ + maxp.off + 4);
    hhea_ = {s16(d_ + hhea.off + 4), s16(d_ + hhea.off + 6), s16(d_ + hhea.off + 8)};
    nhmetrics_ = be16(d_ + hhea.off + 34);
    if (!nhmetrics_ || 4ull * nhmetrics_ > hmtx.size) return fail("hmtx shorter than hhea says");
    hmtx_ = hmtx.off;

    Range vhea = table("vhea"), vmtx = table("vmtx"), vorg = table("VORG");
    if (vhea.size >= 36 && vmtx.size) {
        nvmetrics_ = be16(d_ + vhea.off + 34);
        if (nvmetrics_ && 4ull * nvmetrics_ <= vmtx.size) vmtx_ = vmtx.off;
    }
    if (vorg.size >= 8 && 8 + 4ull * be16(d_ + vorg.off + 6) <= vorg.size) vorg_ = vorg.off;

    // cmap: a full-repertoire subtable (format 12) if there is one, else the BMP one (format 4)
    Range cmap = table("cmap");
    if (cmap.size < 4) return fail("no cmap");
    for (uint32_t i = 0, nt = be16(d_ + cmap.off + 2); i < nt && cmap.off + 4 + 8 * (i + 1) <= cmap.off + cmap.size; ++i) {
        const uint8_t* rec = d_ + cmap.off + 4 + 8 * i;
        uint32_t plat = be16(rec), enc = be16(rec + 2), off = be32(rec + 4);
        bool unicode = plat == 0 || (plat == 3 && (enc == 1 || enc == 10));
        if (!unicode || off + 8 > cmap.size) continue;
        uint32_t t = cmap.off + off, fmt = be16(d_ + t);
        if (fmt == 4 && !cmap4_ && t + 14 <= n_ && t + be16(d_ + t + 2) <= n_) cmap4_ = t;
        if (fmt == 12 && !cmap12_ && t + 16 <= n_ && t + 16 + 12ull * be32(d_ + t + 12) <= n_) cmap12_ = t;
    }
    if (!cmap4_ && !cmap12_) return fail("no Unicode cmap of format 4 or 12");

    Range cff = table("CFF ");
    if (!cff.size) return fail(table("glyf").size ? "TrueType outlines (glyf) are not read yet" : "no CFF table");
    cff_ = cff.off;
    if (cff.size < 4 || d_[cff_] != 1) return fail("CFF is not version 1");
    uint32_t p = cff_ + d_[cff_ + 2];
    Index names, tops, strings;
    if (!read_index(p, names, &p) || !read_index(p, tops, &p) || !read_index(p, strings, &p) ||
        !read_index(p, gsubrs_, &p))
        return fail("CFF header INDEXes are malformed");
    gsubr_bias_ = subr_bias(gsubrs_.count);
    uint32_t top_off, top_size;
    if (!index_item(tops, 0, top_off, top_size)) return fail("no Top DICT");

    uint32_t charstrings = 0, fdarray = 0, priv_off = 0, priv_size = 0;
    bool cid = false;
    DictReader r{d_ + top_off, d_ + top_off + top_size, {}};
    for (int op; (op = r.next()) >= 0;) {
        if (op == 17 && r.n >= 1) charstrings = cff_ + (uint32_t)r.args[0];
        else if (op == 18 && r.n >= 2) { priv_size = (uint32_t)r.args[0]; priv_off = cff_ + (uint32_t)r.args[1]; }
        else if (op == 1230) cid = true;                                   // ROS
        else if (op == 1236 && r.n >= 1) fdarray = cff_ + (uint32_t)r.args[0];
        else if (op == 1237 && r.n >= 1) fdselect_ = cff_ + (uint32_t)r.args[0];
        else if (op == 1206 && r.n >= 1 && r.args[0] != 2) return fail("charstrings are not Type 2");
    }
    if (!charstrings || !read_index(charstrings, charstrings_, nullptr)) return fail("no CharStrings INDEX");
    if ((int)charstrings_.count < nglyphs_) nglyphs_ = (int)charstrings_.count;

    fds_.clear();
    if (cid) {
        Index fda;
        if (!fdarray || !fdselect_ || !read_index(fdarray, fda, nullptr)) return fail("CID-keyed without FDArray or FDSelect");
        uint32_t fmt = fdselect_ < n_ ? d_[fdselect_] : 0xFF;
        if (fmt != 0 && fmt != 3) return fail("FDSelect format is neither 0 nor 3");
        for (uint32_t i = 0; i < fda.count; ++i) {
            uint32_t fo, fs;
            if (!index_item(fda, i, fo, fs)) return fail("FDArray entry malformed");
            uint32_t po = 0, ps = 0;
            DictReader fr{d_ + fo, d_ + fo + fs, {}};
            for (int op; (op = fr.next()) >= 0;)
                if (op == 18 && fr.n >= 2) { ps = (uint32_t)fr.args[0]; po = cff_ + (uint32_t)fr.args[1]; }
            Private pr;
            if (!read_private(po, ps, pr)) return fail("a Font DICT's Private DICT is malformed");
            fds_.push_back(pr);
        }
    } else {
        Private pr;
        if (priv_off && !read_private(priv_off, priv_size, pr)) return fail("Private DICT malformed");
        fds_.push_back(pr);
    }
    if (fds_.empty()) return fail("no Private DICT");
    return true;
}

int Face::glyph_index(uint32_t code) const {
    if (cmap12_) {
        uint32_t n = be32(d_ + cmap12_ + 12), lo = 0, hi = n;
        while (lo < hi) {
            uint32_t mid = (lo + hi) / 2;
            const uint8_t* g = d_ + cmap12_ + 16 + 12 * mid;
            if (code < be32(g)) hi = mid;
            else if (code > be32(g + 4)) lo = mid + 1;
            else { uint32_t gid = be32(g + 8) + (code - be32(g)); return gid < (uint32_t)nglyphs_ ? (int)gid : 0; }
        }
        return 0;
    }
    if (code > 0xFFFF) return 0;
    uint32_t t = cmap4_, segs = be16(d_ + t + 6) / 2;
    uint32_t ends = t + 14, starts = ends + 2 * segs + 2, deltas = starts + 2 * segs, ranges = deltas + 2 * segs;
    if (ranges + 2ull * segs > n_) return 0;
    uint32_t lo = 0, hi = segs;
    while (lo < hi) {                               // the first segment whose end is >= code
        uint32_t mid = (lo + hi) / 2;
        if (be16(d_ + ends + 2 * mid) < code) lo = mid + 1; else hi = mid;
    }
    if (lo >= segs || be16(d_ + starts + 2 * lo) > code) return 0;
    uint32_t start = be16(d_ + starts + 2 * lo), delta = be16(d_ + deltas + 2 * lo), ro = be16(d_ + ranges + 2 * lo);
    uint32_t gid;
    if (ro == 0) gid = (code + delta) & 0xFFFF;
    else {
        uint64_t at = (uint64_t)ranges + 2 * lo + ro + 2 * (code - start);
        if (at + 2 > n_) return 0;
        uint32_t g = be16(d_ + at);
        gid = g ? (g + delta) & 0xFFFF : 0;
    }
    return gid < (uint32_t)nglyphs_ ? (int)gid : 0;
}

int Face::advance(int gid) const {
    uint32_t i = (uint32_t)gid < nhmetrics_ ? (uint32_t)gid : nhmetrics_ - 1;
    return (int)be16(d_ + hmtx_ + 4 * i);
}

bool Face::vertical(int gid, int& adv, int& origin_y) const {
    if (!vmtx_) return false;
    uint32_t i = (uint32_t)gid < nvmetrics_ ? (uint32_t)gid : nvmetrics_ - 1;
    adv = (int)be16(d_ + vmtx_ + 4 * i);
    origin_y = hhea_.ascender;
    if (vorg_) {
        origin_y = s16(d_ + vorg_ + 4);
        uint32_t n = be16(d_ + vorg_ + 6), lo = 0, hi = n;
        while (lo < hi) {
            uint32_t mid = (lo + hi) / 2, g = be16(d_ + vorg_ + 8 + 4 * mid);
            if (g == (uint32_t)gid) { origin_y = s16(d_ + vorg_ + 10 + 4 * mid); break; }
            if (g < (uint32_t)gid) lo = mid + 1; else hi = mid;
        }
    }
    return true;
}

int Face::fd_of(int gid) const {
    if (!fdselect_) return 0;
    uint8_t fmt = d_[fdselect_];
    int fd = 0;
    if (fmt == 0) {
        if (fdselect_ + 1 + (uint32_t)gid < n_) fd = d_[fdselect_ + 1 + gid];
    } else {
        uint32_t nr = fdselect_ + 3 <= n_ ? be16(d_ + fdselect_ + 1) : 0;
        if (fdselect_ + 3 + 3ull * nr + 2 > n_) return 0;
        for (uint32_t i = 0; i < nr; ++i) {
            const uint8_t* r = d_ + fdselect_ + 3 + 3 * i;
            if ((uint32_t)gid >= be16(r) && (uint32_t)gid < be16(r + 3)) { fd = r[2]; break; }
        }
    }
    return fd < (int)fds_.size() ? fd : 0;
}

// ---- Type 2 charstrings -------------------------------------------------------------

struct Interp {
    float s[48];
    int n = 0;
    float trans[32] = {};
    float x = 0, y = 0;
    int stems = 0;
    bool width_seen = false, ended = false, open = false;
    Path* out;

    void move(float dx, float dy) {
        x += dx; y += dy;
        out->ops.push_back(Path::Move);
        out->pts.insert(out->pts.end(), {x, y});
        open = true;
    }
    void line(float dx, float dy) {
        x += dx; y += dy;
        out->ops.push_back(Path::Line);
        out->pts.insert(out->pts.end(), {x, y});
    }
    void curve(float dx1, float dy1, float dx2, float dy2, float dx3, float dy3) {
        float x1 = x + dx1, y1 = y + dy1, x2 = x1 + dx2, y2 = y1 + dy2;
        x = x2 + dx3; y = y2 + dy3;
        out->ops.push_back(Path::Cubic);
        out->pts.insert(out->pts.end(), {x1, y1, x2, y2, x, y});
    }
    // The first stack-clearing operator may carry the advance width first.
    int first(int expected_even_or_count, bool parity) {
        int base = 0;
        if (!width_seen) {
            width_seen = true;
            if (parity ? (n & 1) : n > expected_even_or_count) base = 1;
        }
        return base;
    }
};

bool Face::run(uint32_t off, uint32_t size, const Private& priv, Interp& st, int depth) const {
    if (depth > 10) return false;
    const uint8_t* p = d_ + off;
    const uint8_t* end = p + size;
    float* s = st.s;
    int& n = st.n;
    auto need = [&](int k) { return n >= k; };
    while (p < end) {
        uint8_t b = *p++;
        if (b >= 32 || b == 28) {
            float v;
            if (b == 28) { if (end - p < 2) return false; v = s16(p); p += 2; }
            else if (b <= 246) v = (float)((int)b - 139);
            else if (b <= 250) { if (p >= end) return false; v = (float)(((int)b - 247) * 256 + *p++ + 108); }
            else if (b <= 254) { if (p >= end) return false; v = (float)(-((int)b - 251) * 256 - *p++ - 108); }
            else { if (end - p < 4) return false; v = (float)((int32_t)be32(p) / 65536.0); p += 4; }
            if (n >= 48) return false;
            s[n++] = v;
            continue;
        }
        switch (b) {
        case 1: case 3: case 18: case 23: {         // hstem vstem hstemhm vstemhm
            int i = st.first(0, true);
            st.stems += (n - i) / 2;
            n = 0;
            break;
        }
        case 19: case 20: {                         // hintmask cntrmask: an implied vstem first
            int i = st.first(0, true);
            st.stems += (n - i) / 2;
            n = 0;
            p += (st.stems + 7) / 8;
            if (p > end) return false;
            break;
        }
        case 21: {                                  // rmoveto
            int i = st.first(2, false);
            if (n - i < 2) return false;
            st.move(s[i], s[i + 1]);
            n = 0;
            break;
        }
        case 22: case 4: {                          // hmoveto vmoveto
            int i = st.first(1, false);
            if (n - i < 1) return false;
            if (b == 22) st.move(s[i], 0); else st.move(0, s[i]);
            n = 0;
            break;
        }
        case 5:                                     // rlineto
            for (int i = 0; i + 1 < n; i += 2) st.line(s[i], s[i + 1]);
            n = 0;
            break;
        case 6: case 7: {                           // hlineto vlineto: alternating
            bool h = b == 6;
            for (int i = 0; i < n; ++i, h = !h) { if (h) st.line(s[i], 0); else st.line(0, s[i]); }
            n = 0;
            break;
        }
        case 8:                                     // rrcurveto
            for (int i = 0; i + 5 < n; i += 6) st.curve(s[i], s[i + 1], s[i + 2], s[i + 3], s[i + 4], s[i + 5]);
            n = 0;
            break;
        case 24: {                                  // rcurveline
            if (n < 8) return false;
            int i = 0;
            for (; i + 5 < n - 2; i += 6) st.curve(s[i], s[i + 1], s[i + 2], s[i + 3], s[i + 4], s[i + 5]);
            st.line(s[i], s[i + 1]);
            n = 0;
            break;
        }
        case 25: {                                  // rlinecurve
            if (n < 8) return false;
            int i = 0;
            for (; i + 1 < n - 6; i += 2) st.line(s[i], s[i + 1]);
            st.curve(s[i], s[i + 1], s[i + 2], s[i + 3], s[i + 4], s[i + 5]);
            n = 0;
            break;
        }
        case 26: {                                  // vvcurveto: dx1? {dya dxb dyb dyc}+
            int i = 0;
            float dx1 = 0;
            if (n & 1) dx1 = s[i++];
            for (; i + 3 < n; i += 4, dx1 = 0) st.curve(dx1, s[i], s[i + 1], s[i + 2], 0, s[i + 3]);
            n = 0;
            break;
        }
        case 27: {                                  // hhcurveto: dy1? {dxa dxb dyb dxc}+
            int i = 0;
            float dy1 = 0;
            if (n & 1) dy1 = s[i++];
            for (; i + 3 < n; i += 4, dy1 = 0) st.curve(s[i], dy1, s[i + 1], s[i + 2], s[i + 3], 0);
            n = 0;
            break;
        }
        case 30: case 31: {                         // vhcurveto hvcurveto: alternating, a last odd argument
            bool h = b == 31;
            for (int i = 0; i + 3 < n; i += 4, h = !h) {
                float last = (n - i == 5) ? s[i + 4] : 0;
                if (h) st.curve(s[i], 0, s[i + 1], s[i + 2], last, s[i + 3]);
                else st.curve(0, s[i], s[i + 1], s[i + 2], s[i + 3], last);
            }
            n = 0;
            break;
        }
        case 10: case 29: {                         // callsubr callgsubr
            if (!need(1)) return false;
            const Index& ix = b == 10 ? priv.subrs : gsubrs_;
            int k = (int)s[--n] + (b == 10 ? priv.subr_bias : gsubr_bias_);
            uint32_t so, ss;
            if (k < 0 || !index_item(ix, (uint32_t)k, so, ss)) return false;
            if (!run(so, ss, priv, st, depth + 1)) return false;
            if (st.ended) return true;
            break;
        }
        case 11:                                    // return
            return true;
        case 14: {                                  // endchar
            int i = st.first(0, false);
            if (n - i >= 4) return false;           // seac-style accent: not supported
            st.ended = true;
            n = 0;
            return true;
        }
        case 12: {
            if (p >= end) return false;
            uint8_t e = *p++;
            switch (e) {
            case 35:                                // flex
                if (!need(13)) return false;
                st.curve(s[0], s[1], s[2], s[3], s[4], s[5]);
                st.curve(s[6], s[7], s[8], s[9], s[10], s[11]);
                n = 0;
                break;
            case 34:                                // hflex
                if (!need(7)) return false;
                st.curve(s[0], 0, s[1], s[2], s[3], 0);
                st.curve(s[4], 0, s[5], -s[2], s[6], 0);
                n = 0;
                break;
            case 36:                                // hflex1
                if (!need(9)) return false;
                st.curve(s[0], s[1], s[2], s[3], s[4], 0);
                st.curve(s[5], 0, s[6], s[7], s[8], -(s[1] + s[3] + s[7]));
                n = 0;
                break;
            case 37: {                              // flex1
                if (!need(11)) return false;
                float dx = s[0] + s[2] + s[4] + s[6] + s[8], dy = s[1] + s[3] + s[5] + s[7] + s[9];
                st.curve(s[0], s[1], s[2], s[3], s[4], s[5]);
                if (std::fabs(dx) > std::fabs(dy)) st.curve(s[6], s[7], s[8], s[9], s[10], -dy);
                else st.curve(s[6], s[7], s[8], s[9], -dx, s[10]);
                n = 0;
                break;
            }
            // arithmetic and storage
            case 3: if (!need(2)) return false; s[n - 2] = (s[n - 2] != 0 && s[n - 1] != 0); --n; break;   // and
            case 4: if (!need(2)) return false; s[n - 2] = (s[n - 2] != 0 || s[n - 1] != 0); --n; break;   // or
            case 5: if (!need(1)) return false; s[n - 1] = s[n - 1] == 0; break;                           // not
            case 9: if (!need(1)) return false; s[n - 1] = std::fabs(s[n - 1]); break;                     // abs
            case 10: if (!need(2)) return false; s[n - 2] += s[n - 1]; --n; break;                          // add
            case 11: if (!need(2)) return false; s[n - 2] -= s[n - 1]; --n; break;                          // sub
            case 12: if (!need(2)) return false; s[n - 2] = s[n - 1] != 0 ? s[n - 2] / s[n - 1] : 0; --n; break;   // div
            case 14: if (!need(1)) return false; s[n - 1] = -s[n - 1]; break;                              // neg
            case 15: if (!need(2)) return false; s[n - 2] = s[n - 2] == s[n - 1]; --n; break;              // eq
            case 18: if (!need(1)) return false; --n; break;                                               // drop
            case 20: {                                                                                     // put
                if (!need(2)) return false;
                int k = (int)s[n - 1];
                if (k >= 0 && k < 32) st.trans[k] = s[n - 2];
                n -= 2;
                break;
            }
            case 21: {                                                                                     // get
                if (!need(1)) return false;
                int k = (int)s[n - 1];
                s[n - 1] = k >= 0 && k < 32 ? st.trans[k] : 0;
                break;
            }
            case 22: if (!need(4)) return false; s[n - 4] = s[n - 2] <= s[n - 1] ? s[n - 4] : s[n - 3]; n -= 3; break;   // ifelse
            case 23: if (n >= 48) return false; s[n++] = 0.5f; break;                                      // random: fixed
            case 24: if (!need(2)) return false; s[n - 2] *= s[n - 1]; --n; break;                          // mul
            case 26: if (!need(1)) return false; s[n - 1] = std::sqrt(std::fmax(0.f, s[n - 1])); break;    // sqrt
            case 27: if (!need(1) || n >= 48) return false; s[n] = s[n - 1]; ++n; break;                   // dup
            case 28: if (!need(2)) return false; std::swap(s[n - 1], s[n - 2]); break;                     // exch
            case 29: {                                                                                     // index
                if (!need(1)) return false;
                int k = (int)s[n - 1];
                if (k < 0) k = 0;
                s[n - 1] = k < n - 1 ? s[n - 2 - k] : 0;
                break;
            }
            case 30: {                                                                                     // roll
                if (!need(2)) return false;
                int j = (int)s[n - 1], cnt = (int)s[n - 2];
                n -= 2;
                if (cnt <= 0 || cnt > n) break;
                j = ((j % cnt) + cnt) % cnt;
                float tmp[48];
                for (int i = 0; i < cnt; ++i) tmp[(i + j) % cnt] = s[n - cnt + i];
                std::memcpy(s + n - cnt, tmp, sizeof(float) * cnt);
                break;
            }
            default: return false;
            }
            break;
        }
        default:
            return false;
        }
    }
    return depth > 0;                               // a charstring must end in endchar
}

bool Face::outline(int gid, Path& out) const {
    out.clear();
    uint32_t off, size;
    if (gid < 0 || gid >= nglyphs_ || !index_item(charstrings_, (uint32_t)gid, off, size)) return false;
    Interp st;
    st.out = &out;
    if (!run(off, size, fds_[fd_of(gid)], st, 0) || !st.ended) { out.clear(); return false; }
    return true;
}

}  // namespace otf
