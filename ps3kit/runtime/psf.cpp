// ps3kit runtime — PARAM.SFO. A header (magic "\0PSF", version 1.1, key
// table offset, data table offset, entry count), 16-byte index entries (key
// offset u16, format u16, length u32, max length u32, data offset u32), the
// NUL-terminated keys padded to 4 bytes, then each entry's data in max length
// bytes. Little-endian throughout, entries sorted by key.
#include "psf.h"
#include <cstdio>
#include <cstring>

namespace {
uint32_t le32(const std::vector<uint8_t>& d, size_t o) {
    return (uint32_t)d[o] | d[o + 1] << 8 | d[o + 2] << 16 | (uint32_t)d[o + 3] << 24;
}
uint32_t le16(const std::vector<uint8_t>& d, size_t o) { return (uint32_t)d[o] | d[o + 1] << 8; }
void put32(std::vector<uint8_t>& d, size_t o, uint32_t v) {
    for (int i = 0; i < 4; ++i) d[o + i] = (uint8_t)(v >> 8 * i);
}
}  // namespace

Psf psf_load(const std::string& host_path) {
    Psf out;
    FILE* f = std::fopen(host_path.c_str(), "rb");
    if (!f) return out;
    std::vector<uint8_t> d;
    uint8_t buf[4096];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) d.insert(d.end(), buf, buf + n);
    std::fclose(f);
    if (d.size() < 20 || std::memcmp(d.data(), "\0PSF", 4)) return out;
    uint32_t keys = le32(d, 8), data = le32(d, 12), count = le32(d, 16);
    for (uint32_t i = 0; i < count && 20 + 16 * (size_t)i + 16 <= d.size(); ++i) {
        size_t e = 20 + 16 * (size_t)i;
        size_t k = keys + le16(d, e), v = data + le32(d, e + 12);
        uint32_t len = le32(d, e + 4);
        if (k >= d.size() || v + len > d.size()) break;
        PsfValue pv;
        pv.fmt = (uint16_t)le16(d, e + 2);
        pv.max = le32(d, e + 8);
        pv.data.assign(d.begin() + v, d.begin() + v + len);
        out[std::string((const char*)&d[k], strnlen((const char*)&d[k], d.size() - k))] = std::move(pv);
    }
    return out;
}

bool psf_save(const std::string& host_path, const Psf& psf) {
    size_t keys_len = 0, data_len = 0;
    for (auto& [k, v] : psf) { keys_len += k.size() + 1; data_len += v.max; }
    size_t keys = 20 + 16 * psf.size(), data = (keys + keys_len + 3) & ~(size_t)3;
    std::vector<uint8_t> d(data + data_len);
    std::memcpy(d.data(), "\0PSF", 4);
    put32(d, 4, 0x101);
    put32(d, 8, (uint32_t)keys);
    put32(d, 12, (uint32_t)data);
    put32(d, 16, (uint32_t)psf.size());
    size_t e = 20, ko = 0, dof = 0;
    for (auto& [k, v] : psf) {
        d[e] = (uint8_t)ko; d[e + 1] = (uint8_t)(ko >> 8);
        d[e + 2] = (uint8_t)v.fmt; d[e + 3] = (uint8_t)(v.fmt >> 8);
        put32(d, e + 4, (uint32_t)v.data.size());
        put32(d, e + 8, v.max);
        put32(d, e + 12, (uint32_t)dof);
        std::memcpy(&d[keys + ko], k.c_str(), k.size() + 1);
        std::memcpy(&d[data + dof], v.data.data(), v.data.size());
        e += 16; ko += k.size() + 1; dof += v.max;
    }
    FILE* f = std::fopen(host_path.c_str(), "wb");
    if (!f) return false;
    bool ok = std::fwrite(d.data(), 1, d.size(), f) == d.size();
    return std::fclose(f) == 0 && ok;
}

std::string psf_string(const Psf& psf, const char* key) {
    auto it = psf.find(key);
    if (it == psf.end() || it->second.fmt == 0x0404) return "";
    const auto& v = it->second.data;
    return std::string(v.begin(), v.end()).c_str();    // up to the NUL
}

uint32_t psf_u32(const Psf& psf, const char* key) {
    auto it = psf.find(key);
    if (it == psf.end() || it->second.fmt != 0x0404 || it->second.data.size() < 4) return 0;
    return le32(it->second.data, 0);
}

void psf_set_string(Psf& psf, const char* key, const std::string& v, uint32_t max) {
    PsfValue& pv = psf[key];
    pv.fmt = 0x0204;
    pv.max = max;
    std::string s = v.substr(0, max - 1);
    pv.data.assign(s.begin(), s.end());
    pv.data.push_back(0);
}

void psf_set_bytes(Psf& psf, const char* key, const void* v, uint32_t n) {
    PsfValue& pv = psf[key];
    pv.fmt = 0x0004;
    pv.max = n;
    pv.data.assign((const uint8_t*)v, (const uint8_t*)v + n);
}

void psf_set_u32(Psf& psf, const char* key, uint32_t v) {
    PsfValue& pv = psf[key];
    pv.fmt = 0x0404;
    pv.max = 4;
    pv.data = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
}
