// ps3kit runtime — cellSpursJq: SPURS job queues. A job is an SPU program
// (the descriptor's first word is its address) with its inputs and outputs
// described by DMA lists; the queue hands jobs to SPURS's SPUs as they free
// up, and a port is how a PPU thread pushes into it and waits for what it
// pushed.
//
// No SPU runs yet. A pushed job is accepted and is complete at once, having
// done nothing: a job that would have written its output leaves it as it
// was. Each distinct program is reported the first time it is pushed, with
// its descriptor, so that what the game asks of the SPUs is on record.
#include "rt.h"
#include <mutex>
#include <set>

namespace {
std::mutex g_mx;
std::set<uint64_t> g_seen;

void report(uint32_t job, uint32_t size) {
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
    rt_log("spursjq: first job for program %08llX (descriptor %08X, %X bytes):%s", (unsigned long long)bin,
           job, size, words.c_str());
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
    report(arg_u32(c, 1), arg_u32(c, 2));
    c.r[3] = CELL_OK;
}

PS3_HLE(_cellSpursJobQueuePort2PushJobBody) {
    report(arg_u32(c, 1), arg_u32(c, 2));
    c.r[3] = CELL_OK;
}

// (port, flag): until every job the port pushed has completed — always, so far.
PS3_HLE(cellSpursJobQueuePort2Sync) { c.r[3] = CELL_OK; }
