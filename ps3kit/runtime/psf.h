// ps3kit runtime — PARAM.SFO, the system's key/value file: read for the
// disc's, read and written for save data.
#pragma once
#include <cstdint>
#include <map>
#include <string>
#include <vector>

struct PsfValue {
    uint16_t fmt = 0x0204;              // 0x0004 bytes, 0x0204 utf-8 with its NUL, 0x0404 u32
    uint32_t max = 0;                   // the room the data table gives it
    std::vector<uint8_t> data;          // as stored, without padding
};
using Psf = std::map<std::string, PsfValue>;    // keys in the file's order, which is sorted

Psf psf_load(const std::string& host_path);     // empty when missing or not a PARAM.SFO
bool psf_save(const std::string& host_path, const Psf& psf);

std::string psf_string(const Psf& psf, const char* key);
uint32_t psf_u32(const Psf& psf, const char* key);
void psf_set_string(Psf& psf, const char* key, const std::string& v, uint32_t max);
void psf_set_bytes(Psf& psf, const char* key, const void* v, uint32_t n);
void psf_set_u32(Psf& psf, const char* key, uint32_t v);
