// ps3kit runtime — what the runtime's own files share: the memory map, logging,
// guest calls, and the registries that bind imported functions and lv2
// system calls to C++.
#pragma once
#include "ppu.h"
#include <cstddef>
#include <string>

// ---- the address space ------------------------------------------------------------
// Laid out as the PS3 lays out a game process: the executable and the
// "main" area below 0x10000000, user memory (sys_memory_allocate) at
// 0x30000000, RSX local memory at 0xC0000000, thread stacks at 0xD0000000.
// The top 16 MiB of the main area belong to the runtime: the descriptors and
// code addresses it hands the game for imported functions, and its own heap
// (TLS blocks, structures the system owns).
namespace mm {
constexpr uint32_t MAIN      = 0x00010000u;
constexpr uint32_t HLE_CODE  = 0x0F000000u;   // 4 bytes per import: never executed, only dispatched
constexpr uint32_t HLE_DESC  = 0x0F010000u;   // 8 bytes per import: {HLE_CODE + 4i, 0}
constexpr uint32_t HLE_HEAP  = 0x0F100000u;
constexpr uint32_t HLE_END   = 0x10000000u;
constexpr uint32_t USER      = 0x30000000u;
constexpr uint32_t USER_SIZE = 0x0D500000u;   // the 213 MiB a game is given
constexpr uint32_t VIDEO     = 0xC0000000u;
constexpr uint32_t VIDEO_SIZE= 0x10000000u;
constexpr uint32_t STACK     = 0xD0000000u;
constexpr uint32_t STACK_SIZE= 0x04000000u;
}

bool     mem_init();
uint32_t hle_alloc(uint32_t size, uint32_t align = 16);    // the runtime's heap; never freed
uint32_t stack_alloc(uint32_t size);                       // a thread stack; returns its base
uint32_t user_alloc(uint32_t size, uint32_t align);        // sys_memory_allocate; 0 when full
uint32_t user_free_bytes();
void     mem_write(uint32_t addr, const void* src, size_t n);
void     mem_read(uint32_t addr, void* dst, size_t n);
std::string mem_cstr(uint32_t addr, size_t max = 1024);

// ---- the executable ----------------------------------------------------------------
struct ElfInfo {
    uint32_t entry_desc;                // e_entry: a descriptor, not code
    uint32_t tls_addr, tls_filesz, tls_memsz;
    uint32_t sdk_version, primary_prio, primary_stacksize, malloc_pagesize;
};
bool elf_load(const char* path, ElfInfo& info);

// ---- logging -------------------------------------------------------------------------
void rt_log(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
[[noreturn]] void rt_fatal(PPUContext& c, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
void rt_dump(PPUContext& c);

// ---- calls ---------------------------------------------------------------------------
PPUFunc ppu_lookup(uint32_t addr);
// Call a guest function through its descriptor, as the game's own code
// would: r2 from the descriptor, arguments in r3..., result in r3. The
// caller's registers are saved around it except r3.
uint64_t ppu_call_guest(PPUContext& c, uint32_t desc, uint64_t a0 = 0, uint64_t a1 = 0,
                        uint64_t a2 = 0, uint64_t a3 = 0);
// Thrown by sys_process_exit and friends; caught by the boot.
struct PPUExit { int code; };
// Thrown by sys_ppu_thread_exit; ends the guest thread, not the process.
struct PPUThreadExit { uint64_t value; };

// ---- threads -------------------------------------------------------------------------
void     ppu_thread_register_main(PPUContext& c, const char* name);
uint32_t ppu_thread_spawn(uint32_t entry_desc, uint64_t arg, int prio, uint32_t stacksize,
                          const char* name, bool joinable);
void     ppu_thread_wait_all();                     // until every spawned thread has ended
// A guest context of the runtime's own (stack, TLS, a thread id), for a host
// thread that runs guest callbacks.
PPUContext* ppu_context_new(uint32_t stacksize, const char* name);
// Run a guest callback (a descriptor) with one argument on the runtime's
// interrupt thread, in order, as lv2 runs vblank and flip handlers.
void     ppu_intr_post(uint32_t desc, uint64_t arg);
uint32_t tls_new_block();                           // a thread's TLS block; r13 = it + 0x7000
bool     lv2_event_queue_push(uint32_t queue, uint64_t source, uint64_t d1, uint64_t d2, uint64_t d3);

// ---- imported functions (HLE) ----------------------------------------------------------
typedef void (*HleFunc)(PPUContext&);
struct HleReg { HleReg(const char* name, HleFunc f); };
// PS3_HLE(cellFsOpen) { ... c.r[3] = result; }
#define PS3_HLE(name) \
    static void hle_##name(PPUContext& c); \
    static HleReg hle_reg_##name(#name, hle_##name); \
    static void hle_##name(PPUContext& c)
void hle_bind_imports();
// A function of the runtime's own that the game will call through a pointer:
// returns the descriptor to hand it.
uint32_t hle_internal(const char* name, HleFunc f);
bool hle_dispatch(PPUContext& c, uint32_t addr);    // false if addr is not an import's

// ---- lv2 system calls ------------------------------------------------------------------
struct Lv2Reg { Lv2Reg(int num, const char* name, HleFunc f); };
#define LV2_SYSCALL(num, name) \
    static void lv2_##name(PPUContext& c); \
    static Lv2Reg lv2_reg_##name(num, #name, lv2_##name); \
    static void lv2_##name(PPUContext& c)
const char* lv2_name(int num);

// ---- arguments ----------------------------------------------------------------------
static inline uint32_t arg_u32(const PPUContext& c, int i) { return (uint32_t)c.r[3 + i]; }
static inline uint64_t arg_u64(const PPUContext& c, int i) { return c.r[3 + i]; }

// Error codes the runtime returns, as the system does.
constexpr uint32_t CELL_OK      = 0;
constexpr uint32_t CELL_EAGAIN  = 0x80010001u;
constexpr uint32_t CELL_EINVAL  = 0x80010002u;
constexpr uint32_t CELL_ENOSYS  = 0x80010003u;
constexpr uint32_t CELL_ENOMEM  = 0x80010004u;
constexpr uint32_t CELL_ESRCH   = 0x80010005u;
constexpr uint32_t CELL_ENOENT  = 0x80010006u;
constexpr uint32_t CELL_EFAULT  = 0x8001000Du;
