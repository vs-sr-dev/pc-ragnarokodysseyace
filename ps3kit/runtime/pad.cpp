// ps3kit runtime — cellPad and cellKb: the controller and the keyboard.
//
// One standard controller is connected to port 0, as on a PS3 that has
// booted a game. Its state comes from the host: the first SDL gamepad, by
// position (south is cross, east is circle), and the keyboard, which stands
// where a gamepad goes:
//
//   arrows  directional buttons       W A S D   left stick
//   Z X     cross, circle             I J K L   right stick
//   C V     square, triangle          Q E       L1, R1
//   Enter   start                     1 3       L2, R2
//   Backspace select                  F G       L3, R3
//
// The host's main thread samples it (pad_host_poll, from the window's loop);
// a game thread reads the last sample. cellPadGetData reports a change only
// when the state differs from what that port last returned, as the library
// does; otherwise len is 0. No keyboard is connected.
#include "rt.h"
#include <SDL3/SDL.h>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace {
constexpr uint32_t kErrAlreadyInit = 0x80121103u, kErrNotInit = 0x80121104u, kErrParam = 0x80121102u,
                   kErrNoDevice = 0x80121107u;
constexpr uint32_t kKbErrAlreadyInit = 0x80121003u, kKbErrNotInit = 0x80121004u, kKbErrNoDevice = 0x80121007u;
constexpr uint32_t kMaxPorts = 7;
constexpr uint32_t kStatusConnected = 1, kStatusAssignChanges = 2;
constexpr uint32_t kSettingPress = 2, kSettingSensor = 4;
constexpr uint32_t kCapabilities = 0x1F;          // conformity, press, sensor, HP stick, actuator
constexpr int kLenDefault = 8, kLenPress = 20, kLenSensor = 24;

// CellPadData's button words
enum : int {
    kDigital1 = 2, kDigital2, kRightX, kRightY, kLeftX, kLeftY,
    kPressRight, kPressLeft, kPressUp, kPressDown,
    kPressTriangle, kPressCircle, kPressCross, kPressSquare,
    kPressL1, kPressR1, kPressL2, kPressR2,
    kSensorX, kSensorY, kSensorZ, kSensorG,
};
// digital 1 and 2 bits
constexpr uint16_t kSelect = 0x01, kL3 = 0x02, kR3 = 0x04, kStart = 0x08,
                   kUp = 0x10, kRight = 0x20, kDown = 0x40, kLeft = 0x80;
constexpr uint16_t kL2 = 0x01, kR2 = 0x02, kL1 = 0x04, kR1 = 0x08,
                   kTriangle = 0x10, kCircle = 0x20, kCross = 0x40, kSquare = 0x80;

struct State { uint16_t b[24]; };

State neutral() {
    State s{};
    s.b[kRightX] = s.b[kRightY] = s.b[kLeftX] = s.b[kLeftY] = 128;
    s.b[kSensorX] = s.b[kSensorY] = s.b[kSensorZ] = 512;    // at rest, 1 g on Z
    s.b[kSensorG] = 512;
    return s;
}

std::mutex g_mx;
State g_host = neutral();                         // the latest sample; untouched without a window
bool g_init = false;
uint32_t g_max = 0;
uint32_t g_setting[kMaxPorts];
bool g_assigned = false;                          // the assignment change has been reported
State g_last;                                     // what port 0 last returned
bool g_last_valid = false;
bool g_kb_init = false;
uint32_t g_kb_max = 0;
SDL_Gamepad* g_pad = nullptr;

// PS3KIT_PAD_PRESS="20:cross,31.5:start+up": buttons held for a fifth of a
// second at those times (seconds from the first poll), for runs nobody plays.
struct Press { double t; uint16_t d1, d2; };
std::vector<Press> g_script;

std::vector<Press> parse_script() {
    std::vector<Press> out;
    const char* env = std::getenv("PS3KIT_PAD_PRESS");
    if (!env) return out;
    static const struct { const char* name; int word; uint16_t bit; } names[] = {
        {"up", 1, kUp}, {"down", 1, kDown}, {"left", 1, kLeft}, {"right", 1, kRight},
        {"start", 1, kStart}, {"select", 1, kSelect}, {"l3", 1, kL3}, {"r3", 1, kR3},
        {"cross", 2, kCross}, {"circle", 2, kCircle}, {"square", 2, kSquare}, {"triangle", 2, kTriangle},
        {"l1", 2, kL1}, {"r1", 2, kR1}, {"l2", 2, kL2}, {"r2", 2, kR2}};
    std::string all = env;
    for (size_t at = 0; at < all.size();) {
        size_t end = all.find(',', at);
        if (end == std::string::npos) end = all.size();
        std::string item = all.substr(at, end - at);
        at = end + 1;
        size_t colon = item.find(':');
        if (colon == std::string::npos) continue;
        Press p{std::atof(item.substr(0, colon).c_str()), 0, 0};
        for (size_t b = colon + 1; b < item.size();) {
            size_t e = item.find('+', b);
            if (e == std::string::npos) e = item.size();
            std::string n = item.substr(b, e - b);
            b = e + 1;
            for (auto& k : names)
                if (n == k.name) (k.word == 1 ? p.d1 : p.d2) |= k.bit;
        }
        out.push_back(p);
    }
    return out;
}

uint16_t axis(Sint16 v) { return (uint16_t)((v + 32768) >> 8); }

void press(State& s, int word, uint16_t bit, int press_word, uint8_t value) {
    if (!value) return;
    s.b[word] |= bit;
    if (value > s.b[press_word]) s.b[press_word] = value;
}

void stick(State& s, int xw, int yw, bool l, bool r, bool u, bool d) {
    if (l != r) s.b[xw] = l ? 0 : 255;
    if (u != d) s.b[yw] = u ? 0 : 255;
}
}  // namespace

void pad_host_poll() {
    if (!g_pad) {
        int n = 0;
        SDL_JoystickID* ids = SDL_GetGamepads(&n);
        if (ids && n > 0) {
            g_pad = SDL_OpenGamepad(ids[0]);
            if (g_pad) rt_log("pad: %s on port 0", SDL_GetGamepadName(g_pad));
        }
        SDL_free(ids);
    } else if (!SDL_GamepadConnected(g_pad)) {
        SDL_CloseGamepad(g_pad);
        g_pad = nullptr;
    }
    State s = neutral();
    if (g_pad) {
        auto btn = [&](SDL_GamepadButton b) -> uint8_t { return SDL_GetGamepadButton(g_pad, b) ? 255 : 0; };
        press(s, kDigital1, kUp, kPressUp, btn(SDL_GAMEPAD_BUTTON_DPAD_UP));
        press(s, kDigital1, kDown, kPressDown, btn(SDL_GAMEPAD_BUTTON_DPAD_DOWN));
        press(s, kDigital1, kLeft, kPressLeft, btn(SDL_GAMEPAD_BUTTON_DPAD_LEFT));
        press(s, kDigital1, kRight, kPressRight, btn(SDL_GAMEPAD_BUTTON_DPAD_RIGHT));
        press(s, kDigital2, kCross, kPressCross, btn(SDL_GAMEPAD_BUTTON_SOUTH));
        press(s, kDigital2, kCircle, kPressCircle, btn(SDL_GAMEPAD_BUTTON_EAST));
        press(s, kDigital2, kSquare, kPressSquare, btn(SDL_GAMEPAD_BUTTON_WEST));
        press(s, kDigital2, kTriangle, kPressTriangle, btn(SDL_GAMEPAD_BUTTON_NORTH));
        press(s, kDigital2, kL1, kPressL1, btn(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER));
        press(s, kDigital2, kR1, kPressR1, btn(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER));
        auto trig = [&](SDL_GamepadAxis a) -> uint8_t {
            int v = SDL_GetGamepadAxis(g_pad, a);           // 0..32767
            return v > 3277 ? (uint8_t)(v >> 7) : 0;        // a tenth of the travel before it counts
        };
        press(s, kDigital2, kL2, kPressL2, trig(SDL_GAMEPAD_AXIS_LEFT_TRIGGER));
        press(s, kDigital2, kR2, kPressR2, trig(SDL_GAMEPAD_AXIS_RIGHT_TRIGGER));
        if (btn(SDL_GAMEPAD_BUTTON_START)) s.b[kDigital1] |= kStart;
        if (btn(SDL_GAMEPAD_BUTTON_BACK)) s.b[kDigital1] |= kSelect;
        if (btn(SDL_GAMEPAD_BUTTON_LEFT_STICK)) s.b[kDigital1] |= kL3;
        if (btn(SDL_GAMEPAD_BUTTON_RIGHT_STICK)) s.b[kDigital1] |= kR3;
        s.b[kLeftX] = axis(SDL_GetGamepadAxis(g_pad, SDL_GAMEPAD_AXIS_LEFTX));
        s.b[kLeftY] = axis(SDL_GetGamepadAxis(g_pad, SDL_GAMEPAD_AXIS_LEFTY));
        s.b[kRightX] = axis(SDL_GetGamepadAxis(g_pad, SDL_GAMEPAD_AXIS_RIGHTX));
        s.b[kRightY] = axis(SDL_GetGamepadAxis(g_pad, SDL_GAMEPAD_AXIS_RIGHTY));
    }
    const bool* k = SDL_GetKeyboardState(nullptr);
    auto key = [&](SDL_Scancode sc) -> uint8_t { return k[sc] ? 255 : 0; };
    press(s, kDigital1, kUp, kPressUp, key(SDL_SCANCODE_UP));
    press(s, kDigital1, kDown, kPressDown, key(SDL_SCANCODE_DOWN));
    press(s, kDigital1, kLeft, kPressLeft, key(SDL_SCANCODE_LEFT));
    press(s, kDigital1, kRight, kPressRight, key(SDL_SCANCODE_RIGHT));
    press(s, kDigital2, kCross, kPressCross, key(SDL_SCANCODE_Z));
    press(s, kDigital2, kCircle, kPressCircle, key(SDL_SCANCODE_X));
    press(s, kDigital2, kSquare, kPressSquare, key(SDL_SCANCODE_C));
    press(s, kDigital2, kTriangle, kPressTriangle, key(SDL_SCANCODE_V));
    press(s, kDigital2, kL1, kPressL1, key(SDL_SCANCODE_Q));
    press(s, kDigital2, kR1, kPressR1, key(SDL_SCANCODE_E));
    press(s, kDigital2, kL2, kPressL2, key(SDL_SCANCODE_1));
    press(s, kDigital2, kR2, kPressR2, key(SDL_SCANCODE_3));
    if (k[SDL_SCANCODE_RETURN] && !(SDL_GetModState() & SDL_KMOD_ALT)) s.b[kDigital1] |= kStart;
    if (k[SDL_SCANCODE_BACKSPACE]) s.b[kDigital1] |= kSelect;
    if (k[SDL_SCANCODE_F]) s.b[kDigital1] |= kL3;
    if (k[SDL_SCANCODE_G]) s.b[kDigital1] |= kR3;
    stick(s, kLeftX, kLeftY, k[SDL_SCANCODE_A], k[SDL_SCANCODE_D], k[SDL_SCANCODE_W], k[SDL_SCANCODE_S]);
    stick(s, kRightX, kRightY, k[SDL_SCANCODE_J], k[SDL_SCANCODE_L], k[SDL_SCANCODE_I], k[SDL_SCANCODE_K]);
    static const auto t0 = std::chrono::steady_clock::now();
    static const bool scripted = (g_script = parse_script(), !g_script.empty());
    if (scripted) {
        double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        for (const Press& p : g_script) {
            if (t < p.t || t >= p.t + 0.2) continue;
            static const int d1_press[8] = {0, 0, 0, 0, kPressUp, kPressRight, kPressDown, kPressLeft};
            static const int d2_press[8] = {kPressL2, kPressR2, kPressL1, kPressR1,
                                            kPressTriangle, kPressCircle, kPressCross, kPressSquare};
            for (int i = 0; i < 8; ++i) {
                if (p.d1 >> i & 1) {
                    if (d1_press[i]) press(s, kDigital1, 1 << i, d1_press[i], 255);
                    else s.b[kDigital1] |= 1 << i;
                }
                if (p.d2 >> i & 1) press(s, kDigital2, 1 << i, d2_press[i], 255);
            }
        }
    }
    std::lock_guard<std::mutex> lk(g_mx);
    g_host = s;
}

// (max_connect)
PS3_HLE(cellPadInit) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (g_init) { c.r[3] = kErrAlreadyInit; return; }
    uint32_t max = arg_u32(c, 0);
    if (max == 0 || max > kMaxPorts) { c.r[3] = kErrParam; return; }
    g_init = true;
    g_max = max;
    std::memset(g_setting, 0, sizeof g_setting);
    g_assigned = false;
    g_last_valid = false;
    c.r[3] = CELL_OK;
}

PS3_HLE(cellPadEnd) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    g_init = false;
    c.r[3] = CELL_OK;
}

// (CellPadInfo2*): the first call after the controller is assigned reports
// the assignment as a change.
PS3_HLE(cellPadGetInfo2) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    uint32_t p = arg_u32(c, 0);
    if (!p) { c.r[3] = kErrParam; return; }
    std::memset(g_mem + p, 0, 12 + 4 * 4 * kMaxPorts);
    st32(p + 0, g_max);
    st32(p + 4, 1);
    st32(p + 8, 0);
    st32(p + 12, kStatusConnected | (g_assigned ? 0 : kStatusAssignChanges));
    st32(p + 12 + 4 * kMaxPorts, g_setting[0]);
    st32(p + 12 + 8 * kMaxPorts, kCapabilities);
    st32(p + 12 + 12 * kMaxPorts, 0);              // CELL_PAD_DEV_TYPE_STANDARD
    g_assigned = true;
    c.r[3] = CELL_OK;
}

// (port, CellPadData*)
PS3_HLE(cellPadGetData) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    uint32_t port = arg_u32(c, 0), p = arg_u32(c, 1);
    if (port >= kMaxPorts || !p) { c.r[3] = kErrParam; return; }
    if (port >= g_max || port != 0) { c.r[3] = kErrNoDevice; return; }
    const State& s = g_host;
    if (g_last_valid && std::memcmp(&s, &g_last, sizeof s) == 0) {
        st32(p, 0);                                // CELL_PAD_LEN_NO_CHANGE
        c.r[3] = CELL_OK;
        return;
    }
    g_last = s;
    g_last_valid = true;
    int len = (g_setting[port] & kSettingSensor) ? kLenSensor
              : (g_setting[port] & kSettingPress) ? kLenPress : kLenDefault;
    st32(p, (uint32_t)len);
    st16(p + 4, 0);
    st16(p + 6, (uint16_t)(0x70 | (len / 2)));
    for (int i = 2; i < len; ++i) st16(p + 4 + 2 * i, s.b[i]);
    c.r[3] = CELL_OK;
}

// (port, setting): press and sensor modes
PS3_HLE(cellPadSetPortSetting) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    uint32_t port = arg_u32(c, 0);
    if (port >= kMaxPorts) { c.r[3] = kErrParam; return; }
    g_setting[port] = arg_u32(c, 1) & (kSettingPress | kSettingSensor);
    c.r[3] = CELL_OK;
}

// (port, CellPadActParam*): the motors. Accepted; the host's do not turn.
PS3_HLE(cellPadSetActDirect) {
    std::lock_guard<std::mutex> lk(g_mx);
    if (!g_init) { c.r[3] = kErrNotInit; return; }
    uint32_t port = arg_u32(c, 0);
    if (port >= kMaxPorts || !arg_u32(c, 1)) { c.r[3] = kErrParam; return; }
    c.r[3] = port < g_max && port == 0 ? CELL_OK : kErrNoDevice;
}

// ---- the keyboard: none connected ------------------------------------------------------

// (max_connect)
PS3_HLE(cellKbInit) {
    if (g_kb_init) { c.r[3] = kKbErrAlreadyInit; return; }
    g_kb_init = true;
    g_kb_max = arg_u32(c, 0);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellKbEnd) {
    if (!g_kb_init) { c.r[3] = kKbErrNotInit; return; }
    g_kb_init = false;
    c.r[3] = CELL_OK;
}

// (CellKbInfo*): max_connect, now_connect, info, status[127]
PS3_HLE(cellKbGetInfo) {
    if (!g_kb_init) { c.r[3] = kKbErrNotInit; return; }
    uint32_t p = arg_u32(c, 0);
    std::memset(g_mem + p, 0, 12 + 127);
    st32(p, g_kb_max);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellKbRead) { c.r[3] = g_kb_init ? kKbErrNoDevice : kKbErrNotInit; }
PS3_HLE(cellKbClearBuf) { c.r[3] = g_kb_init ? kKbErrNoDevice : kKbErrNotInit; }
PS3_HLE(cellKbSetCodeType) { c.r[3] = g_kb_init ? CELL_OK : kKbErrNotInit; }
PS3_HLE(cellKbSetReadMode) { c.r[3] = g_kb_init ? kKbErrNoDevice : kKbErrNotInit; }
