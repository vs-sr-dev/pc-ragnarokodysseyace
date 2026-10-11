// ps3kit runtime — cellSpursJq: SPURS job queues. A job is an SPU program
// (the descriptor's first word is its address) with its inputs and outputs
// described by DMA lists; the queue hands jobs to SPURS's SPUs as they free
// up, and a port is how a PPU thread pushes into it and waits for what it
// pushed.
//
// The job manager here is the runtime's own. A pushed job runs at once, on
// the pushing thread, in a local store of that thread's: the binary is
// copied to where its recompiled program was compiled to sit, the job's
// context (CellSpursJobContext2) and a copy of its descriptor are written
// below it, its buffers and stack above, and its entry (+0x10) is called
// with the context in $3 and the descriptor in $4 until it returns to the
// manager. Every job has completed by the time the push returns, so a sync
// never waits. A job whose program was not recompiled is reported and
// completes having done nothing.
//
// The descriptor is CellSpursJobHeader followed by its DMA list and the
// job's own parameters:
//   +0x00 eaBinary (u64)   +0x08 sizeBinary (u16, 16-byte units)
//   +0x0A sizeDmaList (u16) +0x0C eaHighInput  +0x10 useInOutBuffer
//   +0x14 sizeInOrInOut    +0x18 sizeOut      +0x1C sizeStack (u16, units of 16)
//   +0x1E sizeScratch (u16, units of 16)      +0x20 eaHighCache
//   +0x24 sizeCacheDmaList
// and the context the job reads:
//   +0x00 ioBuffer  +0x04 cacheBuffer[4]  +0x14 a local-store pointer (low 18 bits)
//   +0x1C oBuffer   +0x20 sBuffer         +0x24 dmaTag       +0x28 eaJobDescriptor (u64)
// The word at +0x14 is read by the job runtime the binaries link (JOBCRT):
// it fails the job with CELL_SPURS_JOB_ERROR_NULL_POINTER when it is zero,
// reads a word at the pointer plus 4 for its trace packets, and clears the
// pointer. What the system's kernel points it at is not known; it points at
// the descriptor's copy here, and its top four bits (flags) are clear.
#include "rt.h"
#include "spu.h"
#include <chrono>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <set>

extern const SPUProgram g_spu_programs[];
extern const size_t g_spu_nprograms;

namespace {
std::mutex g_mx;
std::set<uint64_t> g_seen;
const bool g_trace = std::getenv("PS3KIT_SPU") != nullptr;

// the stack pointer starts below a caller's frame of its own: a callee saves
// its link register at 16($1), in its caller's frame
constexpr uint32_t kCtx = 0x100, kDesc = 0x200, kReturn = 0x0F00, kStackTop = 0x3FFC0;
// The job's DMA tag group. AtomDecoder uses the next one up as well and
// asserts it is below 32; which tag the system's kernel hands out is not
// known, so this is the middle of the range.
constexpr uint32_t kDmaTag = 16;

void report(uint32_t job, uint32_t size, const char* what) {
    uint64_t bin = ld64(job);
    {
        std::lock_guard<std::mutex> lk(g_mx);
        if (!g_seen.insert(bin).second) return;
    }
    std::string words;
    for (uint32_t i = 0; i < 0x30 && i < size; i += 4) {
        char w[12];
        std::snprintf(w, sizeof w, " %08X", ld32(job + i));
        words += w;
    }
    rt_log("spursjq: first job for program %08llX, %s (descriptor %08X, %X bytes):%s", (unsigned long long)bin,
           what, job, size, words.c_str());
}

const SPUProgram* program_at(uint32_t ea) {
    for (size_t i = 0; i < g_spu_nprograms; ++i)
        if (g_spu_programs[i].ea == ea) return &g_spu_programs[i];
    return nullptr;
}

struct Worker {
    SPUContext s{};
    std::unique_ptr<uint8_t[]> ls{new uint8_t[SPU_LS_SIZE]};
    Worker() {
        static uint32_t next = 0;
        s.ls = ls.get();
        s.id = __atomic_fetch_add(&next, 1, __ATOMIC_RELAXED);
        s.raddr = ~0u;
    }
};

void ls_w32(SPUContext& s, uint32_t a, uint32_t v) { v = PPU_BSWAP32(v); std::memcpy(s.ls + a, &v, 4); }
void ls_w64(SPUContext& s, uint32_t a, uint64_t v) { v = PPU_BSWAP64(v); std::memcpy(s.ls + a, &v, 8); }
uint32_t align(uint32_t v, uint32_t a) { return (v + a - 1) & ~(a - 1); }

// Runs one job to completion. Returns false if it could not be run.
bool run(uint32_t job, uint32_t size) {
    uint32_t ea_bin = (uint32_t)ld64(job);
    const SPUProgram* p = program_at(ea_bin);
    if (!p) { report(job, size, "not recompiled: completes without running"); return false; }
    report(job, size, p->name);
    uint32_t size_bin = ld16(job + 0x08) * 16u, size_list = ld16(job + 0x0A);
    uint32_t use_inout = ld32(job + 0x10), size_in = ld32(job + 0x14), size_out = ld32(job + 0x18);
    uint32_t size_stack = ld16(job + 0x1C) * 16u, size_scratch = ld16(job + 0x1E) * 16u;
    uint32_t ea_high_in = ld32(job + 0x0C), size_cache = ld32(job + 0x24);
    if (size_cache || use_inout) {
        report(job, size, "asks for a cache list or an in-out buffer, which the manager does not provide");
        return false;
    }

    thread_local Worker w;
    SPUContext& s = w.s;
    std::memset(s.ls, 0, SPU_LS_SIZE);
    std::memset(s.r, 0, sizeof s.r);
    s.raddr = ~0u;
    s.atomic_pending = false;
    s.tag_mask = 0;

    // the layout: context and descriptor, the binary at its base, then the
    // input buffer, the output buffer, scratch, and the stack at the top
    uint32_t at = align(p->base + size_bin, 128);
    uint32_t io = at;          at = align(at + size_in, 128);
    uint32_t out = at;         at = align(at + size_out, 128);
    uint32_t scratch = at;     at = align(at + size_scratch, 128);
    if (at + size_stack > kStackTop || kDesc + size > p->base) {
        rt_log("spursjq: job %08X does not fit in local store (%X bytes below the stack)", job, at);
        return false;
    }
    std::memcpy(s.ls + p->base, g_mem + ea_bin, size_bin);
    std::memcpy(s.ls + kDesc, g_mem + job, size);

    // the input list: {size, eal} pairs after the header, into the input buffer
    for (uint32_t i = 0, dst = io; i < size_list; i += 8) {
        uint32_t ts = ld32(job + 0x30 + i) & 0x7FFF, eal = ld32(job + 0x30 + i + 4);
        (void)ea_high_in;
        if (dst + ts > io + size_in) { rt_log("spursjq: job %08X's input list overflows its buffer", job); return false; }
        std::memcpy(s.ls + dst + (eal & 0xF), g_mem + eal, ts);
        dst += align(ts, 16);
    }

    ls_w32(s, kCtx + 0x00, size_in ? io : 0);
    ls_w32(s, kCtx + 0x14, kDesc);
    ls_w32(s, kCtx + 0x1C, size_out ? out : 0);
    ls_w32(s, kCtx + 0x20, size_scratch ? scratch : 0);
    ls_w32(s, kCtx + 0x24, kDmaTag);
    ls_w64(s, kCtx + 0x28, job);

    s.r[0] = spu_slot(kReturn);
    s.r[1].w = (spu_u32x4){0, 0, kStackTop - at, kStackTop};    // the stack pointer and the room below it
    s.r[3] = spu_slot(kCtx);
    s.r[4] = spu_slot(kDesc);

    auto t0 = std::chrono::steady_clock::now();
    uint32_t pc = p->fn(s, p->base + 0x10);
    if (g_trace) {
        static thread_local double total[8];
        static thread_local uint32_t count[8];
        size_t k = (size_t)(p - g_spu_programs) & 7;
        total[k] += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        if (++count[k] % 500 == 0) rt_log("spu %u: %s, %u runs, %.3f ms each", s.id, p->name, count[k], total[k] / count[k]);
    }
    if (pc != kReturn) {
        rt_log("spursjq: job %08X (%s) left its program for %05X", job, p->name, pc);
        return false;
    }
    return true;
}
}  // namespace

PS3_HLE(cellSpursJobQueueAttributeInitialize) { c.r[3] = CELL_OK; }
PS3_HLE(_cellSpursCreateJobQueueWithJobDescriptorPool) { c.r[3] = CELL_OK; }
PS3_HLE(cellSpursJobQueuePort2Create) { c.r[3] = CELL_OK; }
PS3_HLE(cellSpursJobQueuePort2Destroy) { c.r[3] = CELL_OK; }
PS3_HLE(cellSpursShutdownJobQueue) { c.r[3] = CELL_OK; }
PS3_HLE(cellSpursJoinJobQueue) { c.r[3] = CELL_OK; }

// (port, job descriptor, descriptor size, ..., tag, is sync): the descriptor
// is copied, so the caller may reuse it as soon as this returns.
PS3_HLE(_cellSpursJobQueuePort2CopyPushJobBody) {
    run(arg_u32(c, 1), arg_u32(c, 2));
    c.r[3] = CELL_OK;
}

PS3_HLE(_cellSpursJobQueuePort2PushJobBody) {
    run(arg_u32(c, 1), arg_u32(c, 2));
    c.r[3] = CELL_OK;
}

// (port, flag): until every job the port pushed has completed — always, here.
PS3_HLE(cellSpursJobQueuePort2Sync) { c.r[3] = CELL_OK; }
