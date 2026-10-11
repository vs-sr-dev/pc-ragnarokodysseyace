// ps3kit runtime — cellGame: how the game was booted (from its disc), where its
// content is, and the strings of its PARAM.SFO, read from the disc.
#include "rt.h"
#include "psf.h"
#include <string>

extern std::string g_dev_bdvd;

namespace {
const char* param_key(uint32_t id) {
    switch (id) {
    case 0: case 1: return "TITLE";          // CELL_GAME_PARAMID_TITLE, _DEFAULT
    case 100: return "TITLE_ID";
    case 101: return "VERSION";
    case 106: return "APP_VER";
    default: return nullptr;
    }
}
}  // namespace

PS3_HLE(cellGameBootCheck) {             // (u32* type, u32* attributes, CellGameContentSize*, char* dirName)
    st32(arg_u32(c, 0), 1);              // CELL_GAME_GAMETYPE_DISC
    st32(arg_u32(c, 1), 0);
    if (uint32_t s = arg_u32(c, 2)) {
        st32(s, 40000000);               // hddFreeSizeKB
        st32(s + 4, 0xFFFFFFFFu);        // sizeKB: not computed
        st32(s + 8, 4);                  // sysSizeKB
    }
    c.r[3] = CELL_OK;
}

PS3_HLE(cellGameContentPermit) {         // (char contentInfoPath[128], char usrdirPath[128])
    static const char info[] = "/dev_bdvd/PS3_GAME", usrdir[] = "/dev_bdvd/PS3_GAME/USRDIR";
    mem_write(arg_u32(c, 0), info, sizeof info);
    mem_write(arg_u32(c, 1), usrdir, sizeof usrdir);
    c.r[3] = CELL_OK;
}

PS3_HLE(cellGameGetParamString) {        // (id, char* buf, size)
    uint32_t id = arg_u32(c, 0), buf = arg_u32(c, 1), size = arg_u32(c, 2);
    const char* key = param_key(id);
    static const Psf sfo = psf_load(g_dev_bdvd + "/PS3_GAME/PARAM.SFO");
    if (!key || !sfo.count(key) || !size) { c.r[3] = 0x8002CB21u; return; }   // CELL_GAME_ERROR_NOTSUPPORTED
    std::string v = psf_string(sfo, key).substr(0, size - 1);
    mem_write(buf, v.c_str(), v.size() + 1);
    c.r[3] = CELL_OK;
}
