// ps3kit runtime — the file system: guest paths on the PS3's devices mapped to
// host directories, and one implementation behind both of the game's ways
// in, the cellFs library calls and the lv2 sys_fs_* system calls.
//
//   /dev_bdvd/...   the player's disc, extracted (the folder holding PS3_GAME)
//   /app_home/...   the same disc's PS3_GAME/USRDIR, as a disc game sees it
//   /dev_hdd0/...   a writable directory: game data, save data, the cache
//
// PS3KIT_FS=1 reports every open.
#include "rt.h"
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <map>
#include <mutex>
#include <string>
#include <system_error>
#include <vector>

namespace fs = std::filesystem;

std::string g_dev_bdvd, g_dev_hdd0;

namespace {
constexpr uint32_t ENOENT_ = 0x80010006u, EISDIR_ = 0x80010012u, EEXIST_ = 0x80010014u,
                   EBADF_ = 0x8001002Au, EIO_ = 0x8001002Bu, ENOTDIR_ = 0x8001002Eu,
                   ENOTEMPTY_ = 0x80010036u, EACCES_ = 0x80010029u;
constexpr uint32_t O_ACCMODE_ = 3, O_WRONLY_ = 1, O_RDWR_ = 2, O_CREAT_ = 0x40, O_EXCL_ = 0x80,
                   O_TRUNC_ = 0x200, O_APPEND_ = 0x400;

struct File {
    FILE* f = nullptr;
    bool dir = false;
    std::vector<std::pair<std::string, bool>> entries;   // name, is a directory
    size_t next = 0;
    std::string host;
};
std::mutex g_mx;
std::map<uint32_t, File> g_files;
uint32_t g_next_fd = 3;
const bool g_trace = std::getenv("PS3KIT_FS") != nullptr;

// The host path of a guest path, or "" when it names nothing the runtime maps.
std::string host_path(const std::string& p) {
    auto under = [&](const char* dev, const std::string& root, const char* sub) -> std::string {
        size_t n = std::strlen(dev);
        if (p.compare(0, n, dev) || (p.size() > n && p[n] != '/')) return "";
        if (root.empty()) return "";
        return root + sub + p.substr(n);
    };
    std::string h;
    if (!(h = under("/dev_bdvd", g_dev_bdvd, "")).empty()) return h;
    if (!(h = under("/app_home", g_dev_bdvd, "/PS3_GAME/USRDIR")).empty()) return h;
    if (!(h = under("/dev_hdd0", g_dev_hdd0, "")).empty()) return h;
    return "";
}

void stat_out(uint32_t p, const fs::path& h, bool dir, uint64_t size) {
    std::memset(g_mem + p, 0, 0x34);
    st32(p, dir ? 0040777 : 0100666);            // mode: S_IFDIR or S_IFREG, and rw for everyone
    st64(p + 0x24, size);
    st64(p + 0x2C, 4096);                        // blksize
    (void)h;
}

uint32_t do_open(const std::string& guest, uint32_t flags, uint32_t& fd) {
    std::string h = host_path(guest);
    if (h.empty()) return ENOENT_;
    std::error_code ec;
    bool exists = fs::exists(h, ec);
    if (exists && fs::is_directory(h, ec)) return EISDIR_;
    if ((flags & O_CREAT_) && (flags & O_EXCL_) && exists) return EEXIST_;
    if (!exists && !(flags & O_CREAT_)) return ENOENT_;
    const char* mode;
    uint32_t acc = flags & O_ACCMODE_;
    if (acc == 0) mode = "rb";
    else if (flags & O_APPEND_) mode = acc == O_RDWR_ ? "a+b" : "ab";
    else if ((flags & O_TRUNC_) || !exists) mode = acc == O_RDWR_ ? "w+b" : "wb";
    else mode = "r+b";
    if (acc != 0 && h.rfind(g_dev_bdvd, 0) == 0 && !g_dev_bdvd.empty()) return EACCES_;   // the disc is read-only
    FILE* f = std::fopen(h.c_str(), mode);
    if (!f) return EIO_;
    std::lock_guard<std::mutex> lk(g_mx);
    fd = g_next_fd++;
    File& e = g_files[fd];
    e.f = f;
    e.host = h;
    return CELL_OK;
}

File* get(uint32_t fd) {
    auto it = g_files.find(fd);
    return it == g_files.end() ? nullptr : &it->second;
}

uint32_t do_read(uint32_t fd, uint32_t buf, uint64_t n, uint64_t& done) {
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(fd);
    if (!e || e->dir) return EBADF_;
    done = std::fread(g_mem + buf, 1, n, e->f);
    return CELL_OK;
}

uint32_t do_write(uint32_t fd, uint32_t buf, uint64_t n, uint64_t& done) {
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(fd);
    if (!e || e->dir) return EBADF_;
    done = std::fwrite(g_mem + buf, 1, n, e->f);
    return CELL_OK;
}

uint32_t do_lseek(uint32_t fd, int64_t off, uint32_t whence, uint64_t& pos) {
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(fd);
    if (!e || e->dir) return EBADF_;
    if (whence > 2 || _fseeki64(e->f, off, (int)whence)) return 0x80010002u;   // EINVAL
    pos = (uint64_t)_ftelli64(e->f);
    return CELL_OK;
}

uint32_t do_close(uint32_t fd) {
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(fd);
    if (!e) return EBADF_;
    if (e->f) std::fclose(e->f);
    g_files.erase(fd);
    return CELL_OK;
}

uint32_t do_stat(const std::string& guest, uint32_t out) {
    std::string h = host_path(guest);
    if (h.empty()) return ENOENT_;
    std::error_code ec;
    fs::file_status s = fs::status(h, ec);
    if (ec || !fs::exists(s)) return ENOENT_;
    bool dir = fs::is_directory(s);
    stat_out(out, h, dir, dir ? 0 : fs::file_size(h, ec));
    return CELL_OK;
}

uint32_t do_fstat(uint32_t fd, uint32_t out) {
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(fd);
    if (!e) return EBADF_;
    std::error_code ec;
    if (e->f) std::fflush(e->f);
    stat_out(out, e->host, e->dir, e->dir ? 0 : fs::file_size(e->host, ec));
    return CELL_OK;
}

uint32_t do_opendir(const std::string& guest, uint32_t& fd) {
    std::string h = host_path(guest);
    if (h.empty()) return ENOENT_;
    std::error_code ec;
    if (!fs::exists(h, ec)) return ENOENT_;
    if (!fs::is_directory(h, ec)) return ENOTDIR_;
    File e;
    e.dir = true;
    e.host = h;
    e.entries = {{".", true}, {"..", true}};
    for (const auto& d : fs::directory_iterator(h, ec))
        e.entries.push_back({d.path().filename().string(), d.is_directory()});
    std::lock_guard<std::mutex> lk(g_mx);
    fd = g_next_fd++;
    g_files[fd] = std::move(e);
    return CELL_OK;
}

void dirent_out(uint32_t p, const std::string& name, bool dir) {   // CellFsDirent
    std::memset(g_mem + p, 0, 0x102);
    st8(p, dir ? 1 : 2);
    size_t n = name.size() < 255 ? name.size() : 255;
    st8(p + 1, (uint8_t)n);
    std::memcpy(g_mem + p + 2, name.data(), n);
}

uint32_t do_readdir(uint32_t fd, uint32_t out, uint64_t& nread) {
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(fd);
    if (!e || !e->dir) return EBADF_;
    if (e->next >= e->entries.size()) { nread = 0; return CELL_OK; }
    dirent_out(out, e->entries[e->next].first, e->entries[e->next].second);
    ++e->next;
    nread = 0x102;
    return CELL_OK;
}

void trace_open(const char* how, const std::string& guest, uint32_t r, uint32_t fd) {
    if (g_trace || r != CELL_OK)
        rt_log("fs: %s %s -> %s", how, guest.c_str(),
               r == CELL_OK ? ("fd " + std::to_string(fd)).c_str() : (r == ENOENT_ ? "ENOENT" : "error"));
}
}  // namespace

// ---- cellFs ----------------------------------------------------------------------------------
PS3_HLE(cellFsOpen) {                    // (path, flags, u32* fd, arg, size)
    std::string p = mem_cstr(arg_u32(c, 0));
    uint32_t fd = 0, r = do_open(p, arg_u32(c, 1), fd);
    trace_open("open", p, r, fd);
    if (r == CELL_OK) st32(arg_u32(c, 2), fd);
    c.r[3] = r;
}
PS3_HLE(cellFsRead) {                    // (fd, buf, nbytes, u64* nread)
    uint64_t n = 0;
    c.r[3] = do_read(arg_u32(c, 0), arg_u32(c, 1), arg_u64(c, 2), n);
    if (arg_u32(c, 3)) st64(arg_u32(c, 3), n);
}
PS3_HLE(cellFsWrite) {
    uint64_t n = 0;
    c.r[3] = do_write(arg_u32(c, 0), arg_u32(c, 1), arg_u64(c, 2), n);
    if (arg_u32(c, 3)) st64(arg_u32(c, 3), n);
}
PS3_HLE(cellFsLseek) {                   // (fd, offset, whence, u64* pos)
    uint64_t pos = 0;
    c.r[3] = do_lseek(arg_u32(c, 0), (int64_t)arg_u64(c, 1), arg_u32(c, 2), pos);
    if (c.r[3] == CELL_OK && arg_u32(c, 3)) st64(arg_u32(c, 3), pos);
}
PS3_HLE(cellFsClose) { c.r[3] = do_close(arg_u32(c, 0)); }
PS3_HLE(cellFsStat) {
    std::string p = mem_cstr(arg_u32(c, 0));
    c.r[3] = do_stat(p, arg_u32(c, 1));
    if (g_trace) rt_log("fs: stat %s -> %s", p.c_str(), c.r[3] ? "ENOENT" : "ok");
}
PS3_HLE(cellFsFstat) { c.r[3] = do_fstat(arg_u32(c, 0), arg_u32(c, 1)); }
PS3_HLE(cellFsOpendir) {
    std::string p = mem_cstr(arg_u32(c, 0));
    uint32_t fd = 0, r = do_opendir(p, fd);
    trace_open("opendir", p, r, fd);
    if (r == CELL_OK) st32(arg_u32(c, 1), fd);
    c.r[3] = r;
}
PS3_HLE(cellFsReaddir) {                 // (fd, CellFsDirent*, u64* nread)
    uint64_t n = 0;
    c.r[3] = do_readdir(arg_u32(c, 0), arg_u32(c, 1), n);
    if (arg_u32(c, 2)) st64(arg_u32(c, 2), n);
}
PS3_HLE(cellFsClosedir) { c.r[3] = do_close(arg_u32(c, 0)); }
PS3_HLE(cellFsGetDirectoryEntries) {     // (fd, CellFsDirectoryEntry*, bytes, u32* count)
    uint32_t fd = arg_u32(c, 0), out = arg_u32(c, 1), bytes = arg_u32(c, 2), count = 0;
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(fd);
    if (!e || !e->dir) { c.r[3] = EBADF_; return; }
    while (e->next < e->entries.size() && (count + 1) * 0x136 <= bytes) {
        const auto& [name, dir] = e->entries[e->next++];
        uint32_t p = out + count * 0x136;
        std::error_code ec;
        fs::path h = fs::path(e->host) / name;
        stat_out(p, h, dir, dir ? 0 : fs::file_size(h, ec));
        dirent_out(p + 0x34, name, dir);
        ++count;
    }
    st32(arg_u32(c, 3), count);
    c.r[3] = CELL_OK;
}
PS3_HLE(cellFsMkdir) {
    std::string h = host_path(mem_cstr(arg_u32(c, 0)));
    std::error_code ec;
    if (h.empty()) { c.r[3] = ENOENT_; return; }
    if (fs::exists(h, ec)) { c.r[3] = EEXIST_; return; }
    c.r[3] = fs::create_directory(h, ec) ? CELL_OK : ENOENT_;
}
PS3_HLE(cellFsUnlink) {
    std::string h = host_path(mem_cstr(arg_u32(c, 0)));
    std::error_code ec;
    if (h.empty() || !fs::exists(h, ec)) { c.r[3] = ENOENT_; return; }
    if (fs::is_directory(h, ec)) { c.r[3] = EISDIR_; return; }
    c.r[3] = fs::remove(h, ec) ? CELL_OK : EIO_;
}
PS3_HLE(cellFsRename) {
    std::string a = host_path(mem_cstr(arg_u32(c, 0))), b = host_path(mem_cstr(arg_u32(c, 1)));
    std::error_code ec;
    if (a.empty() || b.empty() || !fs::exists(a, ec)) { c.r[3] = ENOENT_; return; }
    fs::rename(a, b, ec);
    c.r[3] = ec ? EIO_ : CELL_OK;
}
PS3_HLE(cellFsFsync) {
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(arg_u32(c, 0));
    if (e && e->f) std::fflush(e->f);
    c.r[3] = e ? CELL_OK : EBADF_;
}
PS3_HLE(cellFsFtruncate) {               // (fd, size)
    std::lock_guard<std::mutex> lk(g_mx);
    File* e = get(arg_u32(c, 0));
    if (!e || !e->f) { c.r[3] = EBADF_; return; }
    std::fflush(e->f);
    std::error_code ec;
    fs::resize_file(e->host, arg_u64(c, 1), ec);
    c.r[3] = ec ? EIO_ : CELL_OK;
}
PS3_HLE(cellFsAioInit) { c.r[3] = CELL_OK; }
PS3_HLE(cellFsAioFinish) { c.r[3] = CELL_OK; }

// ---- lv2 sys_fs: the same, by number -----------------------------------------------------------
LV2_SYSCALL(801, sys_fs_open) {          // (path, flags, u32* fd, mode, arg, size)
    std::string p = mem_cstr(arg_u32(c, 0));
    uint32_t fd = 0, r = do_open(p, arg_u32(c, 1), fd);
    trace_open("open", p, r, fd);
    if (r == CELL_OK) st32(arg_u32(c, 2), fd);
    c.r[3] = r;
}
LV2_SYSCALL(802, sys_fs_read) {
    uint64_t n = 0;
    c.r[3] = do_read(arg_u32(c, 0), arg_u32(c, 1), arg_u64(c, 2), n);
    if (arg_u32(c, 3)) st64(arg_u32(c, 3), n);
}
LV2_SYSCALL(803, sys_fs_write) {
    uint64_t n = 0;
    c.r[3] = do_write(arg_u32(c, 0), arg_u32(c, 1), arg_u64(c, 2), n);
    if (arg_u32(c, 3)) st64(arg_u32(c, 3), n);
}
LV2_SYSCALL(804, sys_fs_close) { c.r[3] = do_close(arg_u32(c, 0)); }
LV2_SYSCALL(805, sys_fs_opendir) {
    std::string p = mem_cstr(arg_u32(c, 0));
    uint32_t fd = 0, r = do_opendir(p, fd);
    trace_open("opendir", p, r, fd);
    if (r == CELL_OK) st32(arg_u32(c, 1), fd);
    c.r[3] = r;
}
LV2_SYSCALL(806, sys_fs_readdir) {
    uint64_t n = 0;
    c.r[3] = do_readdir(arg_u32(c, 0), arg_u32(c, 1), n);
    if (arg_u32(c, 2)) st64(arg_u32(c, 2), n);
}
LV2_SYSCALL(807, sys_fs_closedir) { c.r[3] = do_close(arg_u32(c, 0)); }
LV2_SYSCALL(808, sys_fs_stat) { c.r[3] = do_stat(mem_cstr(arg_u32(c, 0)), arg_u32(c, 1)); }
LV2_SYSCALL(809, sys_fs_fstat) { c.r[3] = do_fstat(arg_u32(c, 0), arg_u32(c, 1)); }
LV2_SYSCALL(818, sys_fs_lseek) {
    uint64_t pos = 0;
    c.r[3] = do_lseek(arg_u32(c, 0), (int64_t)arg_u64(c, 1), arg_u32(c, 2), pos);
    if (c.r[3] == CELL_OK && arg_u32(c, 3)) st64(arg_u32(c, 3), pos);
}
LV2_SYSCALL(820, sys_fs_fsync) { c.r[3] = CELL_OK; }
LV2_SYSCALL(813, sys_fs_rmdir) {
    std::string h = host_path(mem_cstr(arg_u32(c, 0)));
    std::error_code ec;
    if (h.empty() || !fs::exists(h, ec)) { c.r[3] = ENOENT_; return; }
    if (!fs::is_empty(h, ec)) { c.r[3] = ENOTEMPTY_; return; }
    c.r[3] = fs::remove(h, ec) ? CELL_OK : EIO_;
}

// The host path of a guest path, for the system libraries that open files themselves.
std::string fs_host_path(const std::string& guest) { return host_path(guest); }
