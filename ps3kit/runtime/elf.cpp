// ps3kit runtime — loading the decrypted executable into guest memory: its
// PT_LOAD segments at their addresses with their bss cleared, and what the
// loader reads besides (the TLS image, the process parameters).
#include "rt.h"
#include <cstdio>
#include <vector>

static uint64_t be64(const uint8_t* p) { uint64_t v; std::memcpy(&v, p, 8); return PPU_BSWAP64(v); }
static uint32_t be32(const uint8_t* p) { uint32_t v; std::memcpy(&v, p, 4); return PPU_BSWAP32(v); }
static uint16_t be16(const uint8_t* p) { uint16_t v; std::memcpy(&v, p, 2); return PPU_BSWAP16(v); }

bool elf_load(const char* path, ElfInfo& info) {
    FILE* f = std::fopen(path, "rb");
    if (!f) { rt_log("ps3kit: cannot open %s", path); return false; }
    std::vector<uint8_t> d;
    uint8_t buf[1 << 16];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) d.insert(d.end(), buf, buf + n);
    std::fclose(f);
    if (d.size() < 64 || std::memcmp(d.data(), "\x7f" "ELF", 4) || d[4] != 2 || d[5] != 2) {
        rt_log("ps3kit: %s is not a 64-bit big-endian ELF (decrypt the SELF first)", path);
        return false;
    }
    info = ElfInfo{};
    info.entry_desc = (uint32_t)be64(&d[24]);
    uint64_t phoff = be64(&d[32]);
    uint16_t phentsize = be16(&d[54]), phnum = be16(&d[56]);
    for (int i = 0; i < phnum; ++i) {
        const uint8_t* p = &d[phoff + (size_t)i * phentsize];
        uint32_t type = be32(p);
        uint64_t off = be64(p + 8), va = be64(p + 16), filesz = be64(p + 32), memsz = be64(p + 40);
        if (type == 1 && memsz) {                                   // PT_LOAD
            if (filesz) mem_write((uint32_t)va, &d[off], filesz);
            if (memsz > filesz) std::memset(g_mem + va + filesz, 0, memsz - filesz);
        } else if (type == 7) {                                     // PT_TLS
            info.tls_addr = (uint32_t)va; info.tls_filesz = (uint32_t)filesz; info.tls_memsz = (uint32_t)memsz;
        } else if (type == 0x60000001 && filesz >= 0x1C) {         // the process parameters
            const uint8_t* q = &d[off];
            info.sdk_version = be32(q + 12);
            info.primary_prio = be32(q + 16);
            info.primary_stacksize = be32(q + 20);
            info.malloc_pagesize = be32(q + 24);
        }
    }
    return true;
}
