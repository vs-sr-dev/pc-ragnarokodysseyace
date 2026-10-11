// ps3kit runtime — cellOskDialog: the system's on-screen keyboard.
//
// The protocol is the system's, as the first game reads it: LoadAsync opens
// the dialog with a message, an initial text and a length limit (UTF-16) and
// the system answers LOADED; when the user confirms or cancels it sends
// FINISHED, the game calls UnloadAsync with a buffer the system fills with
// the result and the text, and the system sends UNLOADED. Events go through
// cellSysutilCheckCallback (sysutil_post).
//
// The keyboard itself is the runtime's own, standing where the system's
// interface goes: a panel drawn over the game with its message and the text
// typed so far, typed on the host's keyboard (Enter confirms, Escape
// cancels, Backspace deletes). The panel's characters are the first font
// the game opened from memory, drawn by the runtime's rasterizer; the
// window's title carries the text as well. While the dialog is open the
// controller reports no input to the game, as the system's dialogs take it.
//
// The system dims the game behind its keyboard unless the game has called
// DisableDimmer; the runtime dims the display to half.
//
// PS3KIT_OSK=1 reports each call. PS3KIT_OSK_TYPE="text" answers every
// keyboard at once with that text, confirmed, for runs nobody types into.
#include "rt.h"
#include "otf.h"
#include "raster.h"
#include <cmath>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace {
constexpr uint32_t kErrInUse = 0x8002B501u, kErrParam = 0x8002B504u;
constexpr uint32_t kErrNotOpened = 0x8002B302u;         // the message dialog's code, as no other is known
constexpr uint64_t kLoaded = 0x0502, kFinished = 0x0503, kUnloaded = 0x0504;
constexpr int32_t kResultOk = 0, kResultCanceled = 1, kResultAbort = 2, kResultNoText = 3;
constexpr uint32_t kNoSpace = 1;                        // CELL_OSKDIALOG_NO_SPACE
constexpr size_t kMaxChars = 511;

const bool g_trace = std::getenv("PS3KIT_OSK") != nullptr;

enum class State { Closed, Open, Finished };
std::mutex g_mx;
State g_state = State::Closed;
std::u16string g_message, g_text;
uint32_t g_limit = 0, g_prohibit = 0;
int32_t g_result = kResultOk;
uint64_t g_version = 0;                                 // bumped on every change the panel shows
bool g_dimmer = true;

std::u16string read_u16(uint32_t a, size_t max) {
    std::u16string s;
    if (!a) return s;
    for (size_t i = 0; i < max; ++i) {
        char16_t ch = (char16_t)ld16(a + 2 * (uint32_t)i);
        if (!ch) break;
        s.push_back(ch);
    }
    return s;
}

std::string utf8(const std::u16string& s) {
    std::string out;
    for (size_t i = 0; i < s.size(); ++i) {
        uint32_t c = s[i];
        if (c >= 0xD800 && c < 0xDC00 && i + 1 < s.size()) c = 0x10000 + ((c - 0xD800) << 10) + (s[++i] - 0xDC00);
        if (c < 0x80) out.push_back((char)c);
        else if (c < 0x800) { out.push_back((char)(0xC0 | c >> 6)); out.push_back((char)(0x80 | (c & 0x3F))); }
        else if (c < 0x10000) {
            out.push_back((char)(0xE0 | c >> 12));
            out.push_back((char)(0x80 | (c >> 6 & 0x3F)));
            out.push_back((char)(0x80 | (c & 0x3F)));
        } else {
            out.push_back((char)(0xF0 | c >> 18));
            out.push_back((char)(0x80 | (c >> 12 & 0x3F)));
            out.push_back((char)(0x80 | (c >> 6 & 0x3F)));
            out.push_back((char)(0x80 | (c & 0x3F)));
        }
    }
    return out;
}

void finish(int32_t result, uint64_t reason) {
    g_result = result;
    g_state = State::Finished;
    ++g_version;
    sysutil_post(kFinished, reason);
    if (g_trace) rt_log("osk: finished, result %d, text \"%s\"", result, utf8(g_text).c_str());
}

// ---- the panel ---------------------------------------------------------------------------
// Drawn at the display's 1280x720 scale: 1000 x 128 pixels.
constexpr int kPanelW = 1000, kPanelH = 128;

struct Canvas {
    std::vector<uint8_t> px;
    void fill(int x0, int y0, int x1, int y1, const uint8_t c[3]) {
        for (int y = std::max(0, y0); y < std::min(kPanelH, y1); ++y)
            for (int x = std::max(0, x0); x < std::min(kPanelW, x1); ++x) {
                uint8_t* p = &px[((size_t)y * kPanelW + x) * 4];
                p[0] = c[0]; p[1] = c[1]; p[2] = c[2]; p[3] = 255;
            }
    }
};

float text_width(const otf::Face& face, const std::u16string& s, float size) {
    float w = 0;
    for (char16_t ch : s) w += face.advance(face.glyph_index(ch)) * size / face.units_per_em();
    return w;
}

void draw_text(Canvas& cv, const otf::Face& face, const std::u16string& s, float x, int baseline, float size,
               const uint8_t col[3]) {
    float scale = size / face.units_per_em();
    for (char16_t ch : s) {
        int gid = face.glyph_index(ch);
        otf::Path path;
        if (gid && face.outline(gid, path)) {
            GlyphBitmap g;
            render_glyph(path, scale, scale, g);
            int ox = (int)std::floor(x) + g.left, oy = baseline - g.top;
            for (int y = 0; y < g.h; ++y)
                for (int xx = 0; xx < g.w; ++xx) {
                    int px = ox + xx, py = oy + y;
                    if (px < 0 || py < 0 || px >= kPanelW || py >= kPanelH) continue;
                    uint8_t a = g.pix[(size_t)y * g.w + xx];
                    uint8_t* p = &cv.px[((size_t)py * kPanelW + px) * 4];
                    for (int k = 0; k < 3; ++k) p[k] = (uint8_t)((p[k] * (255 - a) + col[k] * a) / 255);
                }
        }
        x += face.advance(gid) * scale;
    }
}
}  // namespace

// ---- the window's side -------------------------------------------------------------------------

bool osk_active() {
    std::lock_guard<std::mutex> lk(g_mx);
    return g_state == State::Open;
}

bool osk_dimmed() {
    std::lock_guard<std::mutex> lk(g_mx);
    return g_state == State::Open && g_dimmer;
}

std::string osk_title() {
    std::lock_guard<std::mutex> lk(g_mx);
    if (g_state != State::Open) return "";
    return utf8(g_message) + " > " + utf8(g_text) + "_  (" + std::to_string(g_text.size()) + "/" +
           std::to_string(g_limit) + ", Enter confirms, Esc cancels)";
}

void osk_host_text(const char* s) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (g_state != State::Open) return;
    for (size_t i = 0; s[i];) {
        uint8_t b = (uint8_t)s[i];
        int n = b < 0x80 ? 1 : b < 0xE0 ? 2 : b < 0xF0 ? 3 : 4;
        uint32_t c = n == 1 ? b : b & (0x7F >> n);
        for (int k = 1; k < n && s[i + k]; ++k) c = c << 6 | ((uint8_t)s[i + k] & 0x3F);
        i += n;
        if (c < 0x20 || c == 0x7F) continue;
        if (c == 0x20 && (g_prohibit & kNoSpace)) continue;
        size_t units = c > 0xFFFF ? 2 : 1;
        if (g_text.size() + units > g_limit) continue;
        if (units == 2) {
            g_text.push_back((char16_t)(0xD800 + ((c - 0x10000) >> 10)));
            g_text.push_back((char16_t)(0xDC00 + ((c - 0x10000) & 0x3FF)));
        } else g_text.push_back((char16_t)c);
        ++g_version;
    }
}

void osk_host_key(int key) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (g_state != State::Open) return;
    if (key == 0) {
        if (g_text.empty()) return;
        g_text.pop_back();
        if (!g_text.empty() && g_text.back() >= 0xD800 && g_text.back() < 0xDC00) g_text.pop_back();
        ++g_version;
    } else if (key == 1) finish(g_text.empty() ? kResultNoText : kResultOk, 0);   // CELL_OSKDIALOG_CLOSE_CONFIRM
    else finish(kResultCanceled, 1);                                                 // CELL_OSKDIALOG_CLOSE_CANCEL
}

bool osk_panel(uint64_t& version, std::vector<uint8_t>& rgba, int& w, int& h) {
    std::u16string message, text;
    uint32_t limit;
    {
        std::lock_guard<std::mutex> lk(g_mx);
        if (g_state != State::Open) return false;
        if (version == g_version) return true;
        version = g_version;
        message = g_message;
        text = g_text;
        limit = g_limit;
    }
    static const uint8_t bg[3] = {18, 24, 38}, edge[3] = {150, 165, 190}, field[3] = {32, 40, 60},
                         white[3] = {255, 255, 255}, light[3] = {200, 210, 228}, grey[3] = {130, 140, 160};
    Canvas cv;
    cv.px.assign((size_t)kPanelW * kPanelH * 4, 0);
    cv.fill(0, 0, kPanelW, kPanelH, edge);
    cv.fill(2, 2, kPanelW - 2, kPanelH - 2, bg);
    cv.fill(20, 52, kPanelW - 20, 94, field);
    std::shared_ptr<const otf::Face> face = font_ui_face();
    if (face) {
        draw_text(cv, *face, message, 24, 38, 24, light);
        draw_text(cv, *face, text + u"_", 32, 82, 30, white);
        std::string n = std::to_string(text.size()) + "/" + std::to_string(limit);
        std::u16string count(n.begin(), n.end());
        draw_text(cv, *face, count, kPanelW - 32 - text_width(*face, count, 22), 81, 22, grey);
        std::u16string hint = u"Enter: confirm     Esc: cancel     Backspace: delete";
        draw_text(cv, *face, hint, 24, 118, 18, grey);
    }
    rgba = std::move(cv.px);
    w = kPanelW;
    h = kPanelH;
    return true;
}

// ---- the dialog ------------------------------------------------------------------------------

// (container, CellOskDialogParam*, CellOskDialogInputFieldInfo*)
PS3_HLE(cellOskDialogLoadAsync) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t param = arg_u32(c, 1), info = arg_u32(c, 2);
    if (!param || !info) { c.r[3] = kErrParam; return; }
    if (g_state != State::Closed) { c.r[3] = kErrInUse; return; }
    g_limit = std::min<uint32_t>(ld32(info + 8), kMaxChars);
    g_message = read_u16(ld32(info), kMaxChars);
    g_text = read_u16(ld32(info + 4), g_limit);
    g_prohibit = ld32(param + 16);
    g_result = kResultOk;
    g_state = State::Open;
    ++g_version;
    rt_log("osk: \"%s\" (up to %u characters, initial \"%s\")", utf8(g_message).c_str(), g_limit,
           utf8(g_text).c_str());
    sysutil_post(kLoaded, 0);
    if (const char* typed = std::getenv("PS3KIT_OSK_TYPE")) {
        g_text.clear();
        for (const char* p = typed; *p && g_text.size() < g_limit; ++p) g_text.push_back((char16_t)(uint8_t)*p);
        finish(g_text.empty() ? kResultNoText : kResultOk, 0);
    }
    c.r[3] = CELL_OK;
}

// (CellOskDialogCallbackReturnParam*): result, numCharsResultString, pResultString
PS3_HLE(cellOskDialogUnloadAsync) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t out = arg_u32(c, 0);
    if (!out || (int32_t)ld32(out + 4) < 0) { c.r[3] = kErrParam; return; }
    if (g_state == State::Closed) { c.r[3] = kErrNotOpened; return; }
    if (g_state == State::Open) g_result = kResultAbort;          // unloaded before the user finished
    st32(out, (uint32_t)g_result);
    uint32_t n = ld32(out + 4), s = ld32(out + 8);
    if (s && (g_result == kResultOk || g_result == kResultNoText)) {
        uint32_t k = std::min<uint32_t>(n, (uint32_t)g_text.size());
        for (uint32_t i = 0; i < k; ++i) st16(s + 2 * i, g_text[i]);
        st16(s + 2 * k, 0);
    }
    if (g_trace) rt_log("osk: unloaded, result %d", g_result);
    g_state = State::Closed;
    ++g_version;
    sysutil_post(kUnloaded, 0);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellOskDialogAbort) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (g_state != State::Open) { c.r[3] = kErrNotOpened; return; }
    finish(kResultAbort, 0);
    c.r[3] = CELL_OK;
}

// (CellOskDialogCallbackReturnParam*): the text so far
PS3_HLE(cellOskDialogGetInputText) {
    std::lock_guard<std::mutex> lk(g_mx);
    uint32_t out = arg_u32(c, 0);
    if (!out || (int32_t)ld32(out + 4) < 0) { c.r[3] = kErrParam; return; }
    if (g_state == State::Closed) { c.r[3] = kErrNotOpened; return; }
    st32(out, g_text.empty() ? kResultNoText : kResultOk);
    uint32_t n = ld32(out + 4), s = ld32(out + 8);
    if (s) {
        uint32_t k = std::min<uint32_t>(n, (uint32_t)g_text.size());
        for (uint32_t i = 0; i < k; ++i) st16(s + 2 * i, g_text[i]);
        st16(s + 2 * k, 0);
    }
    c.r[3] = CELL_OK;
}

// Options of the system's keyboard that the runtime's panel has no use for: accepted.
PS3_HLE(cellOskDialogSetKeyLayoutOption) { c.r[3] = CELL_OK; }
PS3_HLE(cellOskDialogDisableDimmer) {
    std::lock_guard<std::mutex> lk(g_mx);
    g_dimmer = false;
    c.r[3] = CELL_OK;
}
PS3_HLE(cellOskDialogSetSeparateWindowOption) { c.r[3] = arg_u32(c, 0) ? CELL_OK : kErrParam; }
PS3_HLE(cellOskDialogExtSetInitialScale) { c.r[3] = CELL_OK; }

// (callback, timeout): a filter the system runs over the confirmed text; never run here
PS3_HLE(cellOskDialogExtRegisterConfirmWordFilterCallback) {
    if (arg_u32(c, 0)) rt_log("osk: a confirm-word filter is registered and will not be run");
    c.r[3] = CELL_OK;
}
