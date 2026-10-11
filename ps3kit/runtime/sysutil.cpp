// ps3kit runtime — cellSysutil: the video output as the game asks about it,
// and the system callbacks. The output is one HDMI display at 1280x720,
// progressive, 16:9, 59.94 Hz, RGB: what a PS3 on a television reports.
#include "rt.h"
#include <cstring>
#include <deque>
#include <mutex>

namespace {
constexpr uint8_t kRes720 = 2;           // CELL_VIDEO_OUT_RESOLUTION_720
uint8_t g_res = kRes720;
uint32_t g_pitch = 1280 * 4;

void display_mode(uint32_t p) {          // CellVideoOutDisplayMode
    st8(p, g_res);                       // resolutionId
    st8(p + 1, 1);                       // scanMode: progressive
    st8(p + 2, 0);                       // conversion: none
    st8(p + 3, 2);                       // aspect: 16:9
    st16(p + 6, 0x0001);                 // refreshRates: 59.94 Hz
}
}  // namespace

PS3_HLE(cellVideoOutGetState) {          // (video out, device index, CellVideoOutState*)
    uint32_t p = arg_u32(c, 2);
    std::memset(g_mem + p, 0, 16);
    st8(p, 0);                           // state: enabled
    st8(p + 1, 1);                       // colorSpace: RGB
    display_mode(p + 8);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellVideoOutGetResolution) {     // (resolution id, CellVideoOutResolution*)
    static const uint16_t wh[][2] = {{0, 0}, {1920, 1080}, {1280, 720}, {0, 0}, {720, 480}, {720, 576}};
    uint32_t id = arg_u32(c, 0), p = arg_u32(c, 1);
    if (id == 0 || id > 5 || !wh[id][0]) { c.r[3] = 0x8002B222u; return; }   // CELL_VIDEO_OUT_ERROR_ILLEGAL_PARAMETER
    st16(p, wh[id][0]);
    st16(p + 2, wh[id][1]);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellVideoOutConfigure) {         // (video out, CellVideoOutConfiguration*, option, wait)
    uint32_t p = arg_u32(c, 1);
    if (ld8(p)) g_res = ld8(p);
    g_pitch = ld32(p + 12);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellVideoOutGetConfiguration) {  // (video out, CellVideoOutConfiguration*, option)
    uint32_t p = arg_u32(c, 1);
    std::memset(g_mem + p, 0, 16);
    st8(p, g_res);
    st8(p + 1, 0);                       // format: X8R8G8B8
    st8(p + 2, 2);                       // aspect: 16:9
    st32(p + 12, g_pitch);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellVideoOutGetNumberOfDevice) { c.r[3] = 1; }

PS3_HLE(cellVideoOutGetDeviceInfo) {     // (video out, device index, CellVideoOutDeviceInfo*)
    uint32_t p = arg_u32(c, 2);
    std::memset(g_mem + p, 0, 0x100);
    st8(p, 2);                           // portType: HDMI
    st8(p + 1, 1);                       // colorSpace: RGB
    st8(p + 4, 1);                       // one available mode
    st8(p + 5, 0);                       // state: enabled
    display_mode(p + 0x20);              // availableModes[0], after the 20-byte colour info at +12
    c.r[3] = CELL_OK;
}

// System callbacks: registered in four slots. An event the runtime posts
// (sysutil_post: so far the on-screen keyboard's) is raised to every
// registered callback, (status, param, userdata), on the thread that next
// checks for callbacks; events posted while those run wait for the next check.
namespace {
std::mutex g_cb_mx;
uint32_t g_sys_cb[4], g_sys_cb_arg[4];
std::deque<std::pair<uint64_t, uint64_t>> g_events;
}

void sysutil_post(uint64_t status, uint64_t param) {
    std::lock_guard<std::mutex> lk(g_cb_mx);
    g_events.push_back({status, param});
}

PS3_HLE(cellSysutilRegisterCallback) {   // (slot, func, userdata)
    uint32_t slot = arg_u32(c, 0);
    if (slot > 3) { c.r[3] = 0x8002B102u; return; }   // CELL_SYSUTIL_ERROR_VALUE
    std::lock_guard<std::mutex> lk(g_cb_mx);
    g_sys_cb[slot] = arg_u32(c, 1);
    g_sys_cb_arg[slot] = arg_u32(c, 2);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellSysutilCheckCallback) {
    std::deque<std::pair<uint64_t, uint64_t>> events;
    uint32_t cb[4], arg[4];
    {
        std::lock_guard<std::mutex> lk(g_cb_mx);
        events.swap(g_events);
        std::memcpy(cb, g_sys_cb, sizeof cb);
        std::memcpy(arg, g_sys_cb_arg, sizeof arg);
    }
    for (auto& [status, param] : events) {
        rt_log("sysutil: event %llX (param %llX)", (unsigned long long)status, (unsigned long long)param);
        for (int i = 0; i < 4; ++i)
            if (cb[i]) ppu_call_guest(c, cb[i], status, param, arg[i]);
    }
    c.r[3] = CELL_OK;
}

// ---- the system's background music ----------------------------------------------------
// The user can play their own music over a game from the XMB; a game that
// allows it (EnableBgmPlayback) asks whether it is playing and lowers its own
// music while it is. Nothing is ever playing here: the player is stopped and
// at no volume. PLAY is 0 in this structure, so an unwritten status reads as
// music playing, and the game mutes itself.
namespace {
uint8_t g_bgm_enable = 1;               // CELL_SYSUTIL_BGMPLAYBACK_STATUS_DISABLE until enabled
}

PS3_HLE(cellSysutilEnableBgmPlayback) { g_bgm_enable = 0; c.r[3] = CELL_OK; }
PS3_HLE(cellSysutilDisableBgmPlayback) { g_bgm_enable = 1; c.r[3] = CELL_OK; }

// (CellSysutilBgmPlaybackStatus*): playerState, enableState, contentId[16],
// currentFadeRatio, reserved[13]
PS3_HLE(cellSysutilGetBgmPlaybackStatus) {
    uint32_t p = arg_u32(c, 0);
    if (!p) { c.r[3] = 0x8002B101u; return; }   // CELL_SYSUTIL_BGMPLAYBACK_ERROR_PARAM
    std::memset(g_mem + p, 0, 32);
    st8(p, 1);                                  // CELL_SYSUTIL_BGMPLAYBACK_STATUS_STOP
    st8(p + 1, g_bgm_enable);
    c.r[3] = CELL_OK;
}
