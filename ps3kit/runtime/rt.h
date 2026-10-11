// ps3kit runtime — what the runtime's own files share: the memory map, logging,
// guest calls, and the registries that bind imported functions and lv2
// system calls to C++.
#pragma once
#include "ppu.h"
#include <chrono>
#include <cstddef>
#include <memory>
#include <string>
#include <vector>

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

// Write tracking, for caches of what guest memory holds (the renderer's
// texture keys). memwatch_arm write-protects a range and returns a stamp
// (0 where the host cannot track writes); memwatch_clean says whether the
// range has gone unwritten since that stamp. A write into an armed page
// faults once, and the fault handler (memwatch_fault) records it and lets it
// through. Writes the host's kernel makes into guest memory (a file read)
// do not fault but fail, so their callers announce them (memwatch_write).
uint64_t memwatch_arm(uint32_t addr, uint32_t n);
bool     memwatch_clean(uint32_t addr, uint32_t n, uint64_t stamp);
void     memwatch_write(uint32_t addr, uint32_t n);
bool     memwatch_fault(uintptr_t host_addr);

std::string fs_host_path(const std::string& guest);        // "" when the runtime maps nothing there

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

// ---- host time -------------------------------------------------------------------------
// Sleeps to a point of the steady clock, to within a fraction of a millisecond
// on Windows too (a high-resolution waitable timer, which needs no global
// timer resolution and is not throttled with the window in the background).
void host_sleep_until(std::chrono::steady_clock::time_point t);

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
void     ppu_thread_register_main(PPUContext& c, const char* name, int prio);
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

// ---- where the time goes (prof.cpp, PS3KIT_PROF=1) ------------------------------------------
enum ProfSlot { PROF_FIFO_IDLE, PROF_FIFO_SEMA, PROF_FIFO_CAPTURE, PROF_FIFO_VBLANK, PROF_FIFO_SUBMIT,
                PROF_RENDER_EXEC, PROF_RENDER_SWAP, PROF_RENDER_IDLE, PROF_RENDER_COMPILE, PROF_RENDER_UPLOAD,
                PROF_SPU_JOBS, PROF_N };
enum ProfCount { PROFC_DRAWS, PROFC_HASHED, PROFC_SENT, PROFC_PROGRAMS, PROFC_TEXTURES, PROFC_N };
extern const bool g_prof;
uint64_t prof_now();
void prof_add(int slot, uint64_t ns);
void prof_count(int slot, uint64_t n);
void prof_flip();                                   // the report, every 30 flips
struct ProfScope {
    int slot;
    uint64_t t;
    explicit ProfScope(int s) : slot(s), t(g_prof ? prof_now() : 0) {}
    ~ProfScope() { if (g_prof) prof_add(slot, prof_now() - t); }
};

// ---- system events and dialogs ----------------------------------------------------------
// A system event (status, param) for the game's registered callbacks, raised
// on the thread that next calls cellSysutilCheckCallback.
void sysutil_post(uint64_t status, uint64_t param);
// The on-screen keyboard (osk.cpp) as the window shows and types it.
bool osk_active();
bool osk_dimmed();                                  // open, and the system's dimmer not disabled
std::string osk_title();                            // "" while closed
void osk_host_text(const char* utf8);
void osk_host_key(int key);                         // 0 backspace, 1 confirm, 2 cancel
// The panel as RGBA when `version` is stale; false while closed.
bool osk_panel(uint64_t& version, std::vector<uint8_t>& rgba, int& w, int& h);
namespace otf { class Face; }
std::shared_ptr<const otf::Face> font_ui_face();    // the first font the game opened from memory, or null

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
