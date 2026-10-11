// ps3boot — the process start, as the PS3's loader does it: the executable in
// memory, every import bound, the primary thread's stack and TLS, and a call
// to the entry descriptor with the registers _start expects.
//
//     ps3boot GAME.elf
//
// r3 argc, r4 argv, r5 envp, r6 envc, r7 the thread's id, r8-r10 the TLS
// image (address, file size, memory size), r11 e_entry, r12 malloc's page size.
#include "rt.h"
#include <cstdio>

void tls_init(PPUContext& c, uint32_t image, uint32_t filesz, uint32_t memsz);

static const char kArgv0[] = "/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN";

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: ps3boot GAME.elf   (the decrypted executable)\n");
        return 2;
    }
    if (!mem_init()) { std::fprintf(stderr, "ps3kit: cannot reserve guest memory\n"); return 1; }
    ElfInfo info;
    if (!elf_load(argv[1], info)) return 1;
    rt_log("ps3kit: entry descriptor %08X, sdk %08X, primary thread prio %d stack %X, malloc page %X",
           info.entry_desc, info.sdk_version, (int)info.primary_prio, info.primary_stacksize,
           info.malloc_pagesize);
    hle_bind_imports();

    static PPUContext ctx{};
    PPUContext& c = ctx;
    c.thread_id = 0x01000000;
    c.vscr = 0x00010000;                                 // NJ: non-Java mode, as the Cell starts

    uint32_t stack_size = info.primary_stacksize ? info.primary_stacksize : 0x100000;
    uint32_t base = stack_alloc(stack_size), top = base + stack_size;
    // argv[0], then argv[] and envp[] as 64-bit pointers, at the top of the stack
    uint32_t s = (top - sizeof kArgv0 - 16) & ~15u;
    mem_write(s, kArgv0, sizeof kArgv0);
    uint32_t args = (s - 32) & ~15u;
    st64(args, s);
    st64(args + 8, 0);                                   // argv's end
    st64(args + 16, 0);                                  // envp: empty
    c.r[1] = (args - 0x80) & ~15ull;
    st64((uint32_t)c.r[1], 0);                           // the back chain ends here

    tls_init(c, info.tls_addr, info.tls_filesz, info.tls_memsz);

    c.r[3] = 1;
    c.r[4] = args;
    c.r[5] = args + 16;
    c.r[6] = 0;
    c.r[7] = c.thread_id;
    c.r[8] = info.tls_addr;
    c.r[9] = info.tls_filesz;
    c.r[10] = info.tls_memsz;
    c.r[11] = info.entry_desc;
    c.r[12] = info.malloc_pagesize;
    c.r[2] = ld32(info.entry_desc + 4);
    c.lr = mm::HLE_CODE - 4;
    uint32_t entry = ld32(info.entry_desc);
    rt_log("ps3kit: _start at %08X, toc %08llX, sp %08llX, r13 %08llX", entry,
           (unsigned long long)c.r[2], (unsigned long long)c.r[1], (unsigned long long)c.r[13]);
    try {
        ppu_call_indirect(c, entry);
        rt_log("ps3kit: _start returned %lld", (long long)c.r[3]);
    } catch (const PPUExit& e) {
        rt_log("ps3kit: the process exited with %d", e.code);
        return e.code;
    }
    return 0;
}
