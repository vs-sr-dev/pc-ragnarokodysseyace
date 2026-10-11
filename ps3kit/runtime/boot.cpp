// ps3boot — the process start, as the PS3's loader does it: the executable in
// memory, every import bound, the primary thread's stack and TLS, and a call
// to the entry descriptor with the registers _start expects.
//
//     ps3boot GAME.elf [--bdvd DISC] [--hdd0 DIR]
//
// DISC is the player's extracted disc, the folder that holds PS3_GAME;
// DIR is where /dev_hdd0 lives (game data, saves), created if missing.
//
// r3 argc, r4 argv, r5 envp, r6 envc, r7 the thread's id, r8-r10 the TLS
// image (address, file size, memory size), r11 e_entry, r12 malloc's page size.
#include "rt.h"
#include <cstdio>
#include <filesystem>
#include <string>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

void tls_init(PPUContext& c, uint32_t image, uint32_t filesz, uint32_t memsz);
extern std::string g_dev_bdvd, g_dev_hdd0;

#ifdef _WIN32
// A host fault, reported with what makes it findable: the host instruction
// (nm on ps3boot names the recompiled function around it) and, when the
// access was into guest memory, the guest address.
static LONG WINAPI on_fault(EXCEPTION_POINTERS* ep) {
    const EXCEPTION_RECORD* r = ep->ExceptionRecord;
    if (r->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && r->ExceptionCode != EXCEPTION_STACK_OVERFLOW &&
        r->ExceptionCode != EXCEPTION_ILLEGAL_INSTRUCTION && r->ExceptionCode != EXCEPTION_INT_DIVIDE_BY_ZERO)
        return EXCEPTION_CONTINUE_SEARCH;
    uintptr_t rip = (uintptr_t)r->ExceptionAddress;
    uintptr_t base = (uintptr_t)GetModuleHandleA(nullptr);
    std::fprintf(stderr, "ps3kit: host exception %08lX at %p (image offset %llX)", r->ExceptionCode,
                 (void*)rip, (unsigned long long)(rip - base));
    if (r->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && r->NumberParameters >= 2) {
        uintptr_t a = (uintptr_t)r->ExceptionInformation[1];
        const char* kind = r->ExceptionInformation[0] == 1 ? "write" : "read";
        if (a >= (uintptr_t)g_mem && a < (uintptr_t)g_mem + (1ull << 32))
            std::fprintf(stderr, ", %s of guest %08llX", kind, (unsigned long long)(a - (uintptr_t)g_mem));
        else
            std::fprintf(stderr, ", %s of host %p", kind, (void*)a);
    }
    std::fprintf(stderr, "\n");
    std::fflush(stderr);
    std::fflush(stdout);
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

static const char kArgv0[] = "/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN";

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: ps3boot GAME.elf [--bdvd DISC] [--hdd0 DIR]\n");
        return 2;
    }
    g_dev_hdd0 = "hdd0";
    for (int i = 2; i + 1 < argc; i += 2) {
        std::string k = argv[i];
        if (k == "--bdvd") g_dev_bdvd = argv[i + 1];
        else if (k == "--hdd0") g_dev_hdd0 = argv[i + 1];
    }
    std::error_code ec;
    std::filesystem::create_directories(g_dev_hdd0 + "/game", ec);
    std::filesystem::create_directories(g_dev_hdd0 + "/home/00000001/savedata", ec);
    rt_log("ps3kit: /dev_bdvd -> %s, /dev_hdd0 -> %s", g_dev_bdvd.empty() ? "(none)" : g_dev_bdvd.c_str(),
           g_dev_hdd0.c_str());
#ifdef _WIN32
    AddVectoredExceptionHandler(1, on_fault);
#endif
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
    ppu_thread_register_main(c, "main");

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
    } catch (const PPUThreadExit& e) {
        rt_log("ps3kit: the primary thread exited with %lld", (long long)e.value);
    } catch (const PPUExit& e) {
        rt_log("ps3kit: the process exited with %d", e.code);
        return e.code;
    }
    // the process lives until sys_process_exit, or until nothing is left running
    ppu_thread_wait_all();
    return 0;
}
