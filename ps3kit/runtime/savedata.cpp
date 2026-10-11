// ps3kit runtime — cellSaveData: the saves in /dev_hdd0/home/00000001/savedata,
// one directory each, with a PARAM.SFO the system writes from what the game
// says in its callbacks.
//
// One operation serves the calls with no list dialog: Auto (the game names
// the directory), ListAuto and Fixed (the system lists the saves that match a
// prefix and the game's fixed callback picks one, existing or not). Then the
// stat callback sees the chosen save, or that it is new, and sets its
// parameters; the file callback is raised until it says it is done, reading,
// writing and deleting one file each time. The callbacks run on the calling
// thread, which the call blocks, as the system does.
//
// The game's files are kept as they are written: no secure file is
// encrypted, and the system's own record of them (PARAM.PFD) is not made.
// PS3KIT.LST, the runtime's, keeps their order and which ones are secure.
#include "rt.h"
#include "psf.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <map>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <system_error>
#include <vector>

namespace fs = std::filesystem;
extern std::string g_dev_hdd0;

namespace {
constexpr uint32_t ERR_CBRESULT = 0x8002B401u, ERR_ACCESS = 0x8002B402u, ERR_PARAM = 0x8002B404u,
                   ERR_BROKEN = 0x8002B406u, ERR_FAILURE = 0x8002B407u, ERR_BUSY = 0x8002B408u;
constexpr int32_t CB_OK_LAST_NOCONFIRM = 2, CB_OK_LAST = 1, CB_OK_NEXT = 0, CB_ERR_INVALID = -5;
constexpr uint32_t kSysSizeKB = 35;      // what the system reports for its own files, whatever their size
constexpr uint32_t kHddFreeKB = 40000000;    // as cellGameBootCheck reports it
const char kList[] = "PS3KIT.LST";

// The system's structures the callbacks are handed, in one block of its own.
constexpr uint32_t R = 0x000;            // CellSaveDataCBResult
constexpr uint32_t LG = 0x020;           // CellSaveDataListGet
constexpr uint32_t FX = 0x080;           // CellSaveDataFixedSet
constexpr uint32_t SG = 0x100;           // CellSaveDataStatGet, 0x6A8 bytes
constexpr uint32_t SS = 0x7C0;           // CellSaveDataStatSet
constexpr uint32_t FG = 0x7D0;           // CellSaveDataFileGet
constexpr uint32_t FS = 0x820;           // CellSaveDataFileSet
constexpr uint32_t kCtxSize = 0x850;
// CellSaveDataStatGet: hddFreeSizeKB, isNewData, dir (CellSaveDataDirStat,
// 0x38 bytes), getParam (CellSaveDataSystemFileParam, 0x610), then bind,
// sizeKB, sysSizeKB, fileNum, fileListNum, fileList.
constexpr uint32_t SG_DIR = 8, SG_PARAM = 0x40, SG_BIND = 0x650, SG_SIZE = 0x654, SG_SYSSIZE = 0x658,
                   SG_FILENUM = 0x65C, SG_FILELISTNUM = 0x660, SG_FILELIST = 0x664;
// CellSaveDataSystemFileParam: title[128], subTitle[128], detail[1024],
// attribute, reserved2 (parental level), listParam[8], reserved[256].
constexpr uint32_t P_SUBTITLE = 0x80, P_DETAIL = 0x100, P_ATTR = 0x500, P_PARENTAL = 0x504,
                   P_LISTPARAM = 0x508, P_RESERVED = 0x510;

std::mutex g_mx;
uint32_t g_ctx;
const bool g_trace = std::getenv("PS3KIT_SAVEDATA") != nullptr;

struct Times { int64_t atime = 0, mtime = 0, ctime = 0; };
Times times_of(const std::string& p) {
    struct stat st;
    if (::stat(p.c_str(), &st)) return {};
    return {(int64_t)st.st_atime, (int64_t)st.st_mtime, (int64_t)st.st_ctime};
}

std::string base_dir() { return g_dev_hdd0 + "/home/00000001/savedata/"; }

// A directory name the system accepts: A-Z, 0-9, '-' and '_', 1 to 31 characters.
bool valid_dir_name(const std::string& s) {
    if (s.empty() || s.size() >= 32) return false;
    for (char ch : s)
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '-' || ch == '_')) return false;
    return true;
}

bool system_file(const std::string& n) { return n == "PARAM.SFO" || n == "PARAM.PFD" || n == kList; }

// PS3KIT.LST: one line per file, in the order written, "S name" or "N name".
std::vector<std::pair<std::string, bool>> list_load(const std::string& dir) {
    std::vector<std::pair<std::string, bool>> out;
    FILE* f = std::fopen((dir + kList).c_str(), "rb");
    if (!f) return out;
    char line[64];
    while (std::fgets(line, sizeof line, f)) {
        std::string s(line);
        while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
        if (s.size() > 2) out.push_back({s.substr(2), s[0] == 'S'});
    }
    std::fclose(f);
    return out;
}

struct Entry { std::string dir, list_param, subtitle; int64_t mtime; };

// The saves under the prefixes ('|' between them), with their PARAM.SFO.
std::vector<Entry> list_saves(const std::string& prefixes) {
    std::vector<std::string> pre;
    for (size_t a = 0;;) {
        size_t b = prefixes.find('|', a);
        pre.push_back(prefixes.substr(a, b == std::string::npos ? std::string::npos : b - a));
        if (b == std::string::npos) break;
        a = b + 1;
    }
    std::vector<Entry> out;
    std::error_code ec;
    for (auto& e : fs::directory_iterator(base_dir(), ec)) {
        std::string name = e.path().filename().string();
        if (!e.is_directory() || !valid_dir_name(name)) continue;
        if (std::none_of(pre.begin(), pre.end(), [&](const std::string& p) { return name.compare(0, p.size(), p) == 0; }))
            continue;
        std::string dir = base_dir() + name + "/";
        Psf psf = psf_load(dir + "PARAM.SFO");
        if (psf.empty()) continue;
        out.push_back({name, psf_string(psf, "SAVEDATA_LIST_PARAM"), psf_string(psf, "SUB_TITLE"), times_of(dir).mtime});
    }
    return out;
}

void put_str(uint32_t p, const std::string& s, size_t room) {
    std::string t = s.substr(0, room - 1);
    mem_write(p, t.c_str(), t.size() + 1);
}

// What the system does when a callback reports an error: a dialog when the
// game asked for one (none is drawn yet), then the call fails.
uint32_t cb_error(int32_t res) {
    if (res < CB_ERR_INVALID || res > CB_OK_LAST_NOCONFIRM) return ERR_PARAM;
    return ERR_CBRESULT;
}

enum Kind { AUTO, LIST_AUTO, FIXED };

uint32_t savedata_op(PPUContext& c, Kind kind, uint32_t dirName, uint32_t setList,
                     uint32_t setBuf, uint32_t funcFixed, uint32_t funcStat, uint32_t funcFile,
                     uint32_t userdata) {
    std::unique_lock<std::mutex> lk(g_mx, std::try_to_lock);
    if (!lk) return ERR_BUSY;
    if (!g_ctx) g_ctx = hle_alloc(kCtxSize);
    const uint32_t x = g_ctx;
    std::memset(g_mem + x, 0, kCtxSize);
    st32(x + R + 16, userdata);
    auto raise = [&](uint32_t func, uint32_t get, uint32_t set) {
        std::memset(g_mem + x + R, 0, 16);           // all but userdata, which the game may change
        ppu_call_guest(c, func, x + R, x + get, x + set);
        int32_t res = (int32_t)ld32(x + R);
        if (g_trace) rt_log("savedata:   %s callback -> %d", get == LG ? "fixed" : get == SG ? "stat" : "file", res);
        return res;
    };
    const uint32_t buf = ld32(setBuf + 36), buf_size = ld32(setBuf + 32);
    const uint32_t dir_max = ld32(setBuf), file_max = ld32(setBuf + 4);

    std::string dir_name;
    if (kind != AUTO) {
        std::vector<Entry> saves = list_saves(mem_cstr(ld32(setList + 8), 256));
        const uint32_t order = ld32(setList + 4);    // 0 descending, 1 ascending
        const bool by_subtitle = ld32(setList) == 1;
        std::sort(saves.begin(), saves.end(), [&](const Entry& a, const Entry& b) {
            bool less = by_subtitle ? (a.subtitle != b.subtitle ? a.subtitle < b.subtitle : a.mtime < b.mtime)
                                    : (a.mtime != b.mtime ? a.mtime < b.mtime : a.subtitle < b.subtitle);
            bool more = by_subtitle ? (a.subtitle != b.subtitle ? a.subtitle > b.subtitle : a.mtime > b.mtime)
                                    : (a.mtime != b.mtime ? a.mtime > b.mtime : a.subtitle > b.subtitle);
            return order == 1 ? less : more;
        });
        if (!saves.empty()) std::memset(g_mem + buf, 0, buf_size);
        uint32_t listed = std::min<uint32_t>((uint32_t)saves.size(), dir_max);
        for (uint32_t i = 0; i < listed; ++i) {      // CellSaveDataDirList: dirName[32], listParam[8], reserved[8]
            put_str(buf + 48 * i, saves[i].dir, 32);
            put_str(buf + 48 * i + 32, saves[i].list_param, 9);
        }
        st32(x + LG, (uint32_t)saves.size());
        st32(x + LG + 4, listed);
        st32(x + LG + 8, buf);

        int32_t res = raise(funcFixed, LG, FX);
        if (res != CB_OK_NEXT) return res == CB_OK_LAST ? CELL_OK : cb_error(res);
        uint32_t name = ld32(x + FX);
        if (!name) return ERR_PARAM;
        dir_name = mem_cstr(name, 64);
        if (g_trace) rt_log("savedata:   %zu saves listed, the game picks %s", saves.size(), dir_name.c_str());
        if (!valid_dir_name(dir_name)) return ERR_PARAM;
        // option 0 asks the user to confirm a Fixed save or load; no dialog
        // is drawn yet, and the answer taken is yes.
        if (ld32(x + FX + 8) > 1) return ERR_PARAM;
        if (!saves.empty()) std::memset(g_mem + buf, 0, buf_size);
    } else {
        dir_name = mem_cstr(dirName, 64);
    }
    if (!valid_dir_name(dir_name)) return ERR_BROKEN;

    const std::string dir = base_dir() + dir_name + "/";
    Psf psf = psf_load(dir + "PARAM.SFO");
    const bool is_new = psf.empty();
    auto order = list_load(dir);

    // ---- the stat callback
    Times t = times_of(dir);
    st32(x + SG, kHddFreeKB);
    st32(x + SG + 4, is_new);
    st64(x + SG + SG_DIR, t.atime);
    st64(x + SG + SG_DIR + 8, t.mtime);
    st64(x + SG + SG_DIR + 16, t.ctime);
    put_str(x + SG + SG_DIR + 24, dir_name, 32);
    if (!is_new) {
        const uint32_t p = x + SG + SG_PARAM;
        put_str(p, psf_string(psf, "TITLE"), 128);
        put_str(p + P_SUBTITLE, psf_string(psf, "SUB_TITLE"), 128);
        put_str(p + P_DETAIL, psf_string(psf, "DETAIL"), 1024);
        st32(p + P_ATTR, psf_u32(psf, "ATTRIBUTE"));
        st32(p + P_PARENTAL, psf_u32(psf, "PARENTAL_LEVEL"));
        put_str(p + P_LISTPARAM, psf_string(psf, "SAVEDATA_LIST_PARAM"), 9);
        std::memset(g_mem + buf, 0, buf_size);
    }
    // The files in the order they were written, then any others by name.
    std::vector<std::pair<std::string, uint64_t>> files;
    {
        std::map<std::string, uint64_t> on_disk;
        std::error_code ec;
        for (auto& e : fs::directory_iterator(dir, ec)) {
            std::string n = e.path().filename().string();
            if (e.is_regular_file() && !system_file(n)) on_disk[n] = e.file_size();
        }
        for (auto& [n, secure] : order) {
            auto it = on_disk.find(n);
            if (it != on_disk.end()) { files.push_back(*it); on_disk.erase(it); }
        }
        for (auto& f : on_disk) files.push_back(f);
    }
    uint64_t total = 0;
    uint32_t listed = 0;
    for (auto& [n, size] : files) {
        total += (size + 1023) & ~1023ull;
        if (listed >= file_max) continue;
        const uint32_t p = buf + 56 * listed++;  // CellSaveDataFileStat
        uint32_t type = 1;                       // NORMALFILE
        if (n == "ICON0.PNG") type = 2;
        else if (n == "ICON1.PAM") type = 3;
        else if (n == "PIC1.PNG") type = 4;
        else if (n == "SND0.AT3") type = 5;
        else for (auto& [m, secure] : order) if (m == n && secure) type = 0;
        Times ft = times_of(dir + n);
        st32(p, type);
        st64(p + 8, size);
        st64(p + 16, ft.atime);
        st64(p + 24, ft.mtime);
        st64(p + 32, ft.ctime);
        put_str(p + 40, n, 13);
    }
    st32(x + SG + SG_BIND, 0);
    st32(x + SG + SG_SIZE, is_new ? 0 : (uint32_t)(total / 1024) + kSysSizeKB);
    st32(x + SG + SG_SYSSIZE, kSysSizeKB);
    st32(x + SG + SG_FILENUM, (uint32_t)files.size());
    st32(x + SG + SG_FILELISTNUM, listed);
    st32(x + SG + SG_FILELIST, buf);

    int32_t res = raise(funcStat, SG, SS);
    if (res != CB_OK_NEXT) return res == CB_OK_LAST ? CELL_OK : cb_error(res);
    bool modified = false, recreate = false;
    if (uint32_t p = ld32(x + SS)) {
        if (ld32(p + P_ATTR) > 1 || ld32(p + P_PARENTAL) > 11) return ERR_PARAM;
        for (uint32_t i = 0; i < 256; ++i) if (ld8(p + P_RESERVED + i)) return ERR_PARAM;
        std::string lp = mem_cstr(p + P_LISTPARAM, 8);
        for (char ch : lp)
            if (!((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '-' || ch == '_')) return ERR_PARAM;
        // The keys a save's PARAM.SFO has. ACCOUNT_ID and PARAMS carry the
        // console's and the user's ids, which this system does not have.
        static const uint8_t zeros[1024] = {};
        psf_set_bytes(psf, "ACCOUNT_ID", zeros, 16);
        psf_set_u32(psf, "ATTRIBUTE", ld32(p + P_ATTR));
        psf_set_string(psf, "CATEGORY", "SD", 4);
        psf_set_string(psf, "DETAIL", mem_cstr(p + P_DETAIL, 1023), 1024);
        psf_set_bytes(psf, "PARAMS", zeros, 1024);
        psf_set_bytes(psf, "PARAMS2", zeros, 12);
        psf_set_u32(psf, "PARENTAL_LEVEL", ld32(p + P_PARENTAL));
        psf_set_string(psf, "SAVEDATA_DIRECTORY", dir_name, 64);
        psf_set_string(psf, "SAVEDATA_LIST_PARAM", lp, 8);
        psf_set_string(psf, "SUB_TITLE", mem_cstr(p + P_SUBTITLE, 127), 128);
        psf_set_string(psf, "TITLE", mem_cstr(p, 127), 128);
        modified = true;
    } else if (is_new) {
        return ERR_PARAM;
    }
    switch (ld32(x + SS + 4) & 0xFFFEFFFFu) {   // reCreateMode, without the trophy-ownership bit
    case 0: case 1: break;
    case 2: case 3:
        if (!ld32(x + SS)) return ERR_PARAM;
        recreate = modified = true;
        order.clear();
        break;
    default: return ERR_PARAM;
    }

    // ---- the file callback, on the files held in memory until the end
    std::map<std::string, std::vector<uint8_t>> data;
    if (!recreate)
        for (auto& [n, size] : files) {
            std::vector<uint8_t> v(size);
            if (FILE* f = std::fopen((dir + n).c_str(), "rb")) {
                v.resize(std::fread(v.data(), 1, v.size(), f));
                std::fclose(f);
            }
            data[n] = std::move(v);
        }
    uint32_t result = CELL_OK;
    while (funcFile) {
        std::memset(g_mem + x + FS, 0, 48);
        std::memset(g_mem + x + FG + 4, 0, 64);
        res = raise(funcFile, FG, FS);
        if (res == CB_OK_LAST || res == CB_OK_LAST_NOCONFIRM) break;
        if (res != CB_OK_NEXT) { result = cb_error(res); break; }
        const uint32_t s = x + FS;
        const uint32_t op = ld32(s), type = ld32(s + 8), name = ld32(s + 28), off = ld32(s + 32),
                       size = ld32(s + 36), bsize = ld32(s + 40), fbuf = ld32(s + 44);
        if (g_trace) rt_log("savedata:   file op %u type %u \"%s\" offset %u size %u", op, type,
                            name ? mem_cstr(name, 13).c_str() : "", off, size);
        std::string n;
        switch (type) {
        case 0: case 1: {
            if (!name) { result = ERR_PARAM; break; }
            n = mem_cstr(name, 13);
            if (n.size() >= 13 || n.empty() || system_file(n)) { result = ERR_PARAM; break; }
            break;
        }
        case 2: n = "ICON0.PNG"; break;
        case 3: n = "ICON1.PAM"; break;
        case 4: n = "PIC1.PNG"; break;
        case 5: n = "SND0.AT3"; break;
        default: result = ERR_PARAM;
        }
        if (result) break;
        if (op != 2 && (bsize < size || (!fbuf && bsize))) { result = ERR_PARAM; break; }
        auto mark = [&] {
            bool secure = type == 0;
            auto it = std::find_if(order.begin(), order.end(), [&](auto& e) { return e.first == n; });
            if (it == order.end()) order.push_back({n, secure});
            else it->second = secure;
        };
        if (op == 0) {                           // READ
            auto it = data.find(n);
            if (it == data.end() || it->second.size() <= off) { result = ERR_FAILURE; break; }
            uint32_t got = (uint32_t)std::min<uint64_t>(size, it->second.size() - off);
            mem_write(fbuf, it->second.data() + off, got);
            st32(x + FG, got);
        } else if (op == 1 || op == 3) {         // WRITE, WRITE_NOTRUNC
            auto& v = data[n];
            if (v.size() < (size_t)off + size) v.resize((size_t)off + size);
            mem_read(fbuf, v.data() + off, size);
            if (op == 1) v.resize((size_t)off + size);
            st32(x + FG, size);
            mark();
            modified = true;
        } else if (op == 2) {                    // DELETE
            if (!data.erase(n)) { result = ERR_FAILURE; break; }
            order.erase(std::remove_if(order.begin(), order.end(), [&](auto& e) { return e.first == n; }), order.end());
            st32(x + FG, 0);
            modified = true;
        } else {
            result = ERR_PARAM;
            break;
        }
    }

    // ---- the save, made whole in a working directory and then put in place
    if (!psf.empty() && modified) {
        std::error_code ec;
        const std::string work = base_dir() + ".working_" + dir_name + "/", old = base_dir() + ".backup_" + dir_name;
        fs::remove_all(work, ec);
        fs::create_directories(work, ec);
        bool ok = psf_save(work + "PARAM.SFO", psf);
        for (auto& [n, v] : data) {
            FILE* f = std::fopen((work + n).c_str(), "wb");
            ok = ok && f && std::fwrite(v.data(), 1, v.size(), f) == v.size();
            if (f) std::fclose(f);
        }
        if (FILE* f = std::fopen((work + kList).c_str(), "wb")) {
            for (auto& [n, secure] : order) if (data.count(n)) std::fprintf(f, "%c %s\n", secure ? 'S' : 'N', n.c_str());
            std::fclose(f);
        }
        fs::remove_all(old, ec);
        if (fs::exists(dir, ec)) fs::rename(dir, old, ec);
        if (ok) fs::rename(work, base_dir() + dir_name, ec);
        if (!ok || ec) { rt_log("savedata: could not write %s", dir.c_str()); return ERR_ACCESS; }
        fs::remove_all(old, ec);
    }
    return result;
}

// The ninth argument and after are in the caller's parameter save area.
uint32_t arg_stack(const PPUContext& c, int i) { return (uint32_t)ld64((uint32_t)c.r[1] + 0x70 + 8 * (i - 8)); }

void report(const char* call, uint32_t r, const std::string& what) {
    rt_log("savedata: %s %s -> %08X", call, what.c_str(), r);
}
}  // namespace

PS3_HLE(cellSaveDataListAutoLoad) {      // (version, errDialog, setList, setBuf, funcFixed, funcStat, funcFile, container, userdata)
    uint32_t r = savedata_op(c, LIST_AUTO, 0, arg_u32(c, 2), arg_u32(c, 3), arg_u32(c, 4), arg_u32(c, 5),
                             arg_u32(c, 6), arg_stack(c, 8));
    report("ListAutoLoad", r, mem_cstr(ld32(arg_u32(c, 2) + 8)));
    c.r[3] = r;
}

PS3_HLE(cellSaveDataListAutoSave) {
    uint32_t r = savedata_op(c, LIST_AUTO, 0, arg_u32(c, 2), arg_u32(c, 3), arg_u32(c, 4), arg_u32(c, 5),
                             arg_u32(c, 6), arg_stack(c, 8));
    report("ListAutoSave", r, mem_cstr(ld32(arg_u32(c, 2) + 8)));
    c.r[3] = r;
}

PS3_HLE(cellSaveDataAutoLoad2) {         // (version, dirName, errDialog, setBuf, funcStat, funcFile, container, userdata)
    uint32_t r = savedata_op(c, AUTO, arg_u32(c, 1), 0, arg_u32(c, 3), 0, arg_u32(c, 4), arg_u32(c, 5),
                             arg_u32(c, 7));
    report("AutoLoad2", r, mem_cstr(arg_u32(c, 1)));
    c.r[3] = r;
}

PS3_HLE(cellSaveDataAutoSave2) {
    uint32_t r = savedata_op(c, AUTO, arg_u32(c, 1), 0, arg_u32(c, 3), 0, arg_u32(c, 4), arg_u32(c, 5),
                             arg_u32(c, 7));
    report("AutoSave2", r, mem_cstr(arg_u32(c, 1)));
    c.r[3] = r;
}

PS3_HLE(cellSaveDataFixedLoad2) {        // (version, setList, setBuf, funcFixed, funcStat, funcFile, container, userdata)
    uint32_t r = savedata_op(c, FIXED, 0, arg_u32(c, 1), arg_u32(c, 2), arg_u32(c, 3), arg_u32(c, 4),
                             arg_u32(c, 5), arg_u32(c, 7));
    report("FixedLoad2", r, mem_cstr(ld32(arg_u32(c, 1) + 8)));
    c.r[3] = r;
}

PS3_HLE(cellSaveDataFixedSave2) {
    uint32_t r = savedata_op(c, FIXED, 0, arg_u32(c, 1), arg_u32(c, 2), arg_u32(c, 3), arg_u32(c, 4),
                             arg_u32(c, 5), arg_u32(c, 7));
    report("FixedSave2", r, mem_cstr(ld32(arg_u32(c, 1) + 8)));
    c.r[3] = r;
}
