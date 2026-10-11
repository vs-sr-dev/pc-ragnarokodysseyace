// ps3kit runtime — cellGame: how the game was booted (from its disc), where its
// content is, and the strings of its PARAM.SFO, read from the disc.
#include "rt.h"
#include <cstdio>
#include <map>
#include <string>
#include <vector>

extern std::string g_dev_bdvd;

namespace {
// PARAM.SFO: a header (magic "\0PSF", version, key table, data table,
// count) and 16-byte index entries (key offset u16, format u16, length u32,
// max length u32, data offset u32), little-endian throughout.
std::map<std::string, std::string> sfo_strings() {
    std::map<std::string, std::string> out;
    std::string path = g_dev_bdvd + "/PS3_GAME/PARAM.SFO";
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return out;
    std::vector<uint8_t> d;
    uint8_t buf[4096];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) d.insert(d.end(), buf, buf + n);
    std::fclose(f);
    auto le32 = [&](size_t o) { return (uint32_t)d[o] | d[o + 1] << 8 | d[o + 2] << 16 | (uint32_t)d[o + 3] << 24; };
    auto le16 = [&](size_t o) { return (uint32_t)d[o] | d[o + 1] << 8; };
    if (d.size() < 20 || std::memcmp(d.data(), "\0PSF", 4)) return out;
    uint32_t keys = le32(8), data = le32(12), count = le32(16);
    for (uint32_t i = 0; i < count && 20 + 16 * i + 16 <= d.size(); ++i) {
        size_t e = 20 + 16 * i;
        std::string key((const char*)&d[keys + le16(e)]);
        if (le16(e + 2) != 0x0204) continue;                    // utf-8, NUL-terminated
        out[key] = std::string((const char*)&d[data + le32(e + 12)]);
    }
    return out;
}

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
    static const std::map<std::string, std::string> sfo = sfo_strings();
    auto it = key ? sfo.find(key) : sfo.end();
    if (it == sfo.end() || !size) { c.r[3] = 0x8002CB21u; return; }   // CELL_GAME_ERROR_NOTSUPPORTED
    std::string v = it->second.substr(0, size - 1);
    mem_write(buf, v.c_str(), v.size() + 1);
    c.r[3] = CELL_OK;
}
