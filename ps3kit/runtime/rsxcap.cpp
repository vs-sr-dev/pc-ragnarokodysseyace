// ps3kit runtime — the RSX's 3D engine as the FIFO thread sees it (rsx.h):
// every method write is kept here and passed on to the renderer, and when a
// draw ends, what it reads from guest memory is copied into the record.
#include "rt.h"
#include "rsx.h"
#include "rsxprog.h"
#include "rsxtex.h"
#include <cstdlib>
#include <mutex>
#include <set>
#include <unordered_map>
#include <unordered_set>

namespace {
uint32_t reg[0x4000];                   // by method / 4
uint32_t g_io_addr = 0, g_io_size = 0;
std::vector<uint8_t> g_rec;
std::vector<uint32_t> g_pending;        // method, value pairs not yet in the record
uint32_t g_prim = 0;
bool g_indexed = false;
std::vector<std::pair<uint32_t, uint32_t>> g_ranges;   // first, count
std::unordered_set<uint64_t> g_sent;    // texture keys the renderer has
// A texture's key by its address and layout, kept while its memory goes
// unwritten (mem.cpp's write tracking), so that an unchanged texture is not
// read and hashed again on every draw that binds it.
struct KnownTexture { uint32_t addr, layout[3]; uint64_t key, stamp; };
std::unordered_map<uint64_t, KnownTexture> g_known;
// The surfaces the renderer has made, by location << 32 | offset, with their
// size: registered where it makes them (a draw; a colour or a depth clear), so
// that a texture over one is sampled on the GPU and never read, hashed or sent.
// Guest memory holds nothing the GPU drew there.
struct Target { uint32_t w, h, depth_format; };
std::unordered_map<uint64_t, Target> g_colors, g_depths;
uint64_t g_sent_bytes = 0;
uint64_t g_draws = 0;
std::set<std::string> g_reported;

void report_once(const std::string& what) {
    if (g_reported.insert(what).second) rt_log("rsx: %s", what.c_str());
}

uint32_t R(uint32_t method) { return reg[method >> 2]; }

// As rsxgl's targets(), color_dma(), color_offset(), depth_surface() and the surface size read them.
void register_targets(bool color, bool depth) {
    uint32_t w = (R(0x0200) & 0xFFFF) + (R(0x0200) >> 16), h = (R(0x0204) & 0xFFFF) + (R(0x0204) >> 16);
    if (!w || !h || w > 0xFFFF || h > 0xFFFF) return;
    uint32_t zf = R(0x0208) >> 5 & 7;
    if (depth && zf) g_depths[(uint64_t)(R(0x0198) == 0xFEED0001u) << 32 | R(0x0214)] = {w, h, zf};
    if (!color) return;
    static const uint32_t dma[] = {0x0194, 0x018C, 0x01B4, 0x01B8}, off[] = {0x0210, 0x0218, 0x0288, 0x028C};
    int t[4], n = 0;
    switch (R(0x0220)) {
    case 0x01: t[n++] = 0; break;
    case 0x02: t[n++] = 1; break;
    case 0x13: t[n++] = 0; t[n++] = 1; break;
    case 0x17: t[n++] = 0; t[n++] = 1; t[n++] = 2; break;
    case 0x1F: t[n++] = 0; t[n++] = 1; t[n++] = 2; t[n++] = 3; break;
    }
    for (int i = 0; i < n; ++i)
        g_colors[(uint64_t)(R(dma[t[i]]) == 0xFEED0001u) << 32 | R(off[t[i]])] = {w, h, 0};
}

template <typename T> void put(const T& v) {
    const uint8_t* p = reinterpret_cast<const uint8_t*>(&v);
    g_rec.insert(g_rec.end(), p, p + sizeof v);
}
void put_bytes(const void* p, size_t n) {
    g_rec.insert(g_rec.end(), (const uint8_t*)p, (const uint8_t*)p + n);
}

void flush_regs() {
    if (g_pending.empty()) return;
    g_rec.push_back(RC_REGS);
    put((uint32_t)(g_pending.size() / 2));
    put_bytes(g_pending.data(), g_pending.size() * 4);
    g_pending.clear();
}

// Guest memory the game's addresses may name, so that a bad one is reported
// rather than read.
bool readable(uint32_t a, uint32_t n) {
    auto in = [&](uint32_t base, uint32_t size) { return a >= base && n <= size && a - base <= size - n; };
    return in(mm::MAIN, mm::HLE_END - mm::MAIN) || in(mm::USER, mm::USER_SIZE) || in(mm::VIDEO, mm::VIDEO_SIZE) ||
           in(mm::STACK, mm::STACK_SIZE);
}

// An RSX offset to a guest address: location 0 is local memory, 1 main memory through the I/O map.
uint32_t address(uint32_t location, uint32_t offset) { return location ? g_io_addr + offset : mm::VIDEO + offset; }

uint64_t hash(const uint8_t* p, size_t n, uint64_t h = 0x9E3779B97F4A7C15ull) {
    size_t i = 0;
    for (; i + 8 <= n; i += 8) {
        uint64_t v;
        std::memcpy(&v, p + i, 8);
        h = (h ^ v) * 0x100000001B3ull;
        h ^= h >> 29;
    }
    for (; i < n; ++i) h = (h ^ p[i]) * 0x100000001B3ull;
    return h ^ (h >> 32);
}

// The bytes of one vertex attribute's components, by NV4097_SET_VERTEX_DATA_ARRAY_FORMAT's type.
uint32_t component_bytes(uint32_t type) {
    switch (type) {
    case 1: case 3: case 5: return 2;      // S1, SF, S32K
    case 4: case 7: return 1;              // UB, UB256
    default: return 4;                     // F, CMP
    }
}

void end_draw() {
    if (g_ranges.empty()) return;
    ProfScope prof(PROF_FIFO_CAPTURE);
    size_t rec_before = g_rec.size();
    struct Sent { size_t& from; ~Sent() { if (g_prof) prof_count(PROFC_SENT, g_rec.size() - from); } } sent{rec_before};
    if (g_prof) prof_count(PROFC_DRAWS, 1);
    ++g_draws;
    RsxDraw d{g_prim, g_indexed, 0, 0, 0, 0, 0, 0};
    std::vector<uint32_t> indices;
    uint32_t lo = 0xFFFFFFFFu, hi = 0;
    if (!g_indexed) {
        for (auto& [f, n] : g_ranges) { lo = std::min(lo, f); hi = std::max(hi, f + n); }
    } else {
        uint32_t dma = R(0x1820), size = (dma >> 4) & 1 ? 2 : 4;
        uint32_t base = address(dma & 0xF, R(0x181C));
        bool restart = R(0x1DAC) & 1;
        uint32_t restart_index = R(0x1DB0), base_index = R(0x173C);
        for (auto& [f, n] : g_ranges) {
            if (!readable(base + f * size, n * size)) { report_once("index array outside guest memory"); return; }
            for (uint32_t k = 0; k < n; ++k) {
                uint32_t a = base + (f + k) * size;
                uint32_t v = size == 2 ? ld16(a) : ld32(a);
                if (restart && v == restart_index) { indices.push_back(0xFFFFFFFFu); continue; }
                v += base_index;
                indices.push_back(v);
                lo = std::min(lo, v);
                hi = std::max(hi, v + 1);
            }
        }
        if (lo > hi) { lo = 0; hi = 0; }
        for (uint32_t& v : indices) if (v != 0xFFFFFFFFu) v -= lo;
    }
    d.base = lo;
    d.vertices = hi - lo;
    d.count = g_indexed ? (uint32_t)indices.size() : (uint32_t)g_ranges.size();

    // the attributes
    struct Attr { uint32_t index, format, bytes; std::vector<uint8_t> data; };
    std::vector<Attr> attrs;
    for (uint32_t i = 0; i < 16 && d.vertices; ++i) {
        uint32_t fmt = R(0x1740 + 4 * i), size = fmt >> 4 & 0xF, type = fmt & 0xF, stride = fmt >> 8 & 0xFF;
        if (!size) continue;
        uint32_t off = R(0x1680 + 4 * i);
        uint32_t a = address(off >> 31, (off & 0x7FFFFFFF) + R(0x1738)) + stride * d.base;
        uint32_t cb = component_bytes(type), elem = type == 6 ? 4 : size * cb;
        uint32_t bytes = stride ? (d.vertices - 1) * stride + elem : elem;
        if (!readable(a, bytes)) { report_once("vertex attribute outside guest memory"); continue; }
        Attr at{i, fmt, bytes, std::vector<uint8_t>(bytes)};
        std::memcpy(at.data.data(), g_mem + a, bytes);
        uint32_t step = stride ? stride : elem, nv = stride ? d.vertices : 1;
        if (cb > 1 || type == 6) {
            uint32_t swap = type == 6 ? 4 : cb;
            for (uint32_t v = 0; v < nv; ++v)
                for (uint32_t c = 0; c < elem; c += swap) std::reverse(&at.data[v * step + c], &at.data[v * step + c + swap]);
        }
        attrs.push_back(std::move(at));
    }
    d.attrs = (uint32_t)attrs.size();

    // the fragment program
    std::vector<uint32_t> fp;
    {
        // instruction by instruction to the one that ends it, each with its constant
        uint32_t sp = R(0x08E4), a = address((sp & 3) == 2, sp & ~3u);
        auto read4 = [&](uint32_t at) {
            if (!readable(at, 16)) return false;
            for (uint32_t k = 0; k < 4; ++k) fp.push_back(fp_word(ld32(at + 4 * k)));
            return true;
        };
        bool ok = false;
        for (uint32_t pc = 0; pc < 4096; ++pc) {
            if (!read4(a + 16 * pc)) break;
            const uint32_t* i = &fp[fp.size() - 4];
            uint32_t op = (i[0] >> 24 & 0x3F) | (i[2] >> 31) << 6;
            bool lit = !(op >= 0x40 && op <= 0x45) && ((i[1] & 3) == 2 || (i[2] & 3) == 2 || (i[3] & 3) == 2);
            bool end = i[0] & 1;
            if (lit && !read4(a + 16 * ++pc)) break;
            if (end) { ok = true; break; }
        }
        if (!ok) { report_once("fragment program without an end, or outside guest memory"); fp.clear(); }
    }
    d.fp_words = (uint32_t)fp.size();
    if (d.fp_words && d.vertices) register_targets(true, true);    // the renderer draws it, so makes them

    // the textures
    struct Tex { RsxTexture t; uint32_t addr; };
    std::vector<Tex> texs;
    for (uint32_t u = 0; u < 16; ++u) {
        uint32_t b = 0x1A00 + 0x20 * u;
        if (!(R(b + 0xC) & 0x80000000u)) continue;
        RsxTexture t{};
        t.unit = u;
        for (int k = 0; k < 8; ++k) t.regs[k] = R(b + 4 * k);
        t.control3 = R(0x1840 + 4 * u);
        TexLayout l = tex_layout(t.regs[1], t.regs[6], t.control3);
        uint64_t sk = (uint64_t)((t.regs[1] & 3) == 2) << 32 | t.regs[0];
        auto fits = [&](const Target& s) { return s.w >= l.w && s.h >= l.h && !l.cube && l.dims == 2; };
        auto ct = g_colors.find(sk), dt = g_depths.find(sk);
        if (ct != g_colors.end() && fits(ct->second)) t.target = 1;
        else if (dt != g_depths.end() && fits(dt->second)) {
            // a D24S8 buffer read as A8R8G8B8 gives its bytes; other pairings are not done yet
            if (dt->second.depth_format == 2 && l.base == 0x85) t.target = 2;
            else report_once("depth surface sampled as texture format " + std::to_string(l.base) + ", read from memory");
        }
        if (t.target) { texs.push_back({t, 0}); continue; }
        uint32_t a = address((t.regs[1] & 3) == 2, t.regs[0]);
        if (!readable(a, l.total)) { report_once("texture outside guest memory"); continue; }
        uint32_t layout[3] = {t.regs[1] & ~3u, t.regs[6], t.control3};
        uint64_t lk = hash((const uint8_t*)layout, sizeof layout, a);
        KnownTexture& kt = g_known[lk];
        if (kt.addr == a && std::memcmp(kt.layout, layout, sizeof layout) == 0 && memwatch_clean(a, l.total, kt.stamp)) {
            t.key = kt.key;
        } else {
            uint64_t stamp = memwatch_arm(a, l.total);              // before the read: a write after it is seen
            t.key = hash(g_mem + a, l.total, hash((const uint8_t*)layout, sizeof layout));
            kt = KnownTexture{a, {layout[0], layout[1], layout[2]}, t.key, stamp};
            if (g_prof) prof_count(PROFC_HASHED, l.total);
        }
        t.bytes = l.total;
        texs.push_back({t, a});
    }
    d.textures = (uint32_t)texs.size();

    flush_regs();
    g_rec.push_back(RC_DRAW);
    put(d);
    if (g_indexed) put_bytes(indices.data(), indices.size() * 4);
    else for (auto& [f, n] : g_ranges) { put(f - lo); put(n); }
    for (auto& at : attrs) { put(at.index); put(at.format); put(at.bytes); put_bytes(at.data.data(), at.bytes); }
    put_bytes(fp.data(), fp.size() * 4);
    for (auto& [t0, a] : texs) {
        RsxTexture t = t0;
        if (t.target) { put(t); continue; }
        bool have = g_sent.count(t.key);
        if (!have && g_sent_bytes + t.bytes > (512ull << 20)) {      // the renderer's textures start again
            g_rec.push_back(RC_TEXFLUSH);
            g_sent.clear();
            g_sent_bytes = 0;
        }
        if (have) t.bytes = 0;
        else { g_sent.insert(t.key); g_sent_bytes += t.bytes; }
        put(t);
        put_bytes(g_mem + a, t.bytes);
    }
}
}  // namespace

void rsxcap_io(uint32_t io_addr, uint32_t io_size) { g_io_addr = io_addr; g_io_size = io_size; }

void rsxcap_method(uint32_t m, uint32_t v) {
    reg[m >> 2] = v;
    switch (m) {
    case 0x1808:                                                    // NV4097_SET_BEGIN_END
        if (v) { g_prim = v; g_indexed = false; g_ranges.clear(); }
        else end_draw(), g_ranges.clear();
        return;
    case 0x1814:                                                    // NV4097_DRAW_ARRAYS
        if (g_indexed && !g_ranges.empty()) report_once("arrays and indices in one draw");
        g_indexed = false;
        g_ranges.push_back({v & 0xFFFFFF, (v >> 24) + 1});
        return;
    case 0x1824:                                                    // NV4097_DRAW_INDEX_ARRAY
        g_indexed = true;
        g_ranges.push_back({v & 0xFFFFFF, (v >> 24) + 1});
        return;
    case 0x1818:                                                    // NV4097_INLINE_ARRAY
        report_once("inline vertex arrays");
        return;
    case 0x1D94:                                                    // NV4097_CLEAR_SURFACE
        register_targets(v & 0xF0, v & 3);                          // a clear makes them too
        g_pending.push_back(m);
        g_pending.push_back(v);
        return;
    default:
        g_pending.push_back(m);
        g_pending.push_back(v);
        return;
    }
}

void rsxcap_flip(const RsxFlip& f) {
    flush_regs();
    g_rec.push_back(RC_FLIP);
    put(f);
    video_submit(g_rec, 1);
}

uint64_t rsxcap_draws() { return g_draws; }
