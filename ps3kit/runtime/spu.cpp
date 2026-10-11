// ps3kit runtime — an SPU's channels: the MFC (DMA between local store and
// main memory, its tag groups, the atomic unit), the mailboxes and the
// decrementer. What a recompiled SPU program reaches with rdch, wrch and
// rchcnt (spu.h).
//
// The MFC here completes every command as it is issued: a GET or PUT has
// moved its bytes by the time wrch returns, so every tag group is always
// complete and a tag-status read never waits. A list command walks its list
// at once; stall-and-notify is not honoured. GETLLAR copies a 128-byte line
// and keeps what it saw; PUTLLC writes the line back only if main memory
// still holds what was seen, under one lock shared by every SPU — the PPU's
// own reservations do not take it.
#include "rt.h"
#include "spu.h"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <mutex>

namespace {
enum : uint32_t {
    SPU_RdEventStat = 0, SPU_WrEventMask = 1, SPU_WrEventAck = 2, SPU_RdSigNotify1 = 3, SPU_RdSigNotify2 = 4,
    SPU_WrDec = 7, SPU_RdDec = 8, SPU_RdEventMask = 11, SPU_RdMachStat = 13, SPU_WrSRR0 = 14, SPU_RdSRR0 = 15,
    MFC_LSA = 16, MFC_EAH = 17, MFC_EAL = 18, MFC_Size = 19, MFC_TagID = 20, MFC_Cmd = 21,
    MFC_WrTagMask = 22, MFC_WrTagUpdate = 23, MFC_RdTagStat = 24, MFC_RdListStallStat = 25,
    MFC_WrListStallAck = 26, MFC_RdAtomicStat = 27, SPU_WrOutMbox = 28, SPU_RdInMbox = 29,
    SPU_WrOutIntrMbox = 30,
};
enum : uint32_t {
    MFC_PUT = 0x20, MFC_PUTL = 0x24, MFC_GET = 0x40, MFC_GETL = 0x44,
    MFC_PUTLLUC = 0xB0, MFC_PUTLLC = 0xB4, MFC_PUTQLLUC = 0xB8, MFC_GETLLAR = 0xD0,
    MFC_SNDSIG = 0xA0, MFC_BARRIER = 0xC0, MFC_EIEIO = 0xC8, MFC_SYNC = 0xCC,
};
constexpr uint32_t MFC_PUTLLC_SUCCESS = 0, MFC_PUTLLC_FAILURE = 1, MFC_PUTLLUC_SUCCESS = 2, MFC_GETLLAR_SUCCESS = 4;

std::mutex g_atomic;
const bool g_dma_trace = std::getenv("PS3KIT_SPU_DMA") != nullptr;    // every transfer, reported
const bool g_dma_dump = g_dma_trace && std::atoi(std::getenv("PS3KIT_SPU_DMA")) >= 2;   // and its words

// One transfer between local store and main memory; main memory is guest
// memory at its effective address (the high word is ignored: 32-bit space).
void transfer(SPUContext& s, bool get, uint32_t lsa, uint32_t ea, uint32_t size) {
    if (!size) return;
    lsa &= SPU_LS_MASK;
    if (lsa + size > SPU_LS_SIZE) {
        rt_log("spu %u: DMA of %X bytes at LS %05X runs past local store", s.id, size, lsa);
        size = SPU_LS_SIZE - lsa;
    }
    if (get) std::memcpy(s.ls + lsa, g_mem + ea, size);
    else std::memcpy(g_mem + ea, s.ls + lsa, size);
    if (g_dma_trace) {
        uint32_t nz = 0;
        float peak = 0;
        for (uint32_t i = 0; i < size; ++i) nz += s.ls[lsa + i] != 0;
        for (uint32_t i = 0; i + 4 <= size; i += 4) {
            uint32_t u;
            std::memcpy(&u, s.ls + lsa + i, 4);
            float f = as_f32(PPU_BSWAP32(u));
            if (std::isfinite(f) && std::fabs(f) > peak) peak = std::fabs(f);
        }
        rt_log("spu %u: %s LS %05X %s %08X, %X bytes (%u not zero, peak %g as floats)", s.id, get ? "get" : "put",
               lsa, get ? "<-" : "->", ea, size, nz, peak);
        if (g_dma_dump && size <= 0x800) {
            for (uint32_t i = 0; i + 4 <= size; i += 32) {
                std::string line;
                for (uint32_t k = i; k < i + 32 && k + 4 <= size; k += 4) {
                    uint32_t u;
                    std::memcpy(&u, s.ls + lsa + k, 4);
                    u = PPU_BSWAP32(u);
                    char b[40];
                    std::snprintf(b, sizeof b, " %08X(%.4g)", u, as_f32(u));
                    line += b;
                }
                rt_log("   +%03X%s", i, line.c_str());
            }
        }
    }
}

void command(SPUContext& s, uint32_t cmd) {
    uint32_t lsa = s.mfc_lsa, eal = s.mfc_eal, size = s.mfc_size;
    uint32_t base = cmd & 0xFF;
    switch (base & ~3u) {                                     // the barrier and fence forms
    case MFC_PUT: case MFC_GET:
        transfer(s, (base & ~3u) == MFC_GET, lsa, eal, size);
        return;
    case MFC_PUTL: case MFC_GETL: {
        // a list of {size, ea} in local store at eal; each element lands at the
        // next 16-byte step plus its own ea's offset in a quadword
        bool get = (base & ~3u) == MFC_GETL;
        uint32_t at = lsa & 0x3FFF0;
        for (uint32_t i = 0; i < size; i += 8) {
            uint32_t le = (eal + i) & SPU_LS_MASK, ts, ea;
            std::memcpy(&ts, s.ls + le, 4);
            std::memcpy(&ea, s.ls + le + 4, 4);
            ts = PPU_BSWAP32(ts) & 0x7FFF;
            ea = PPU_BSWAP32(ea);
            transfer(s, get, at + (ea & 0xF), ea, ts);
            at += (ts + 15) & ~15u;
        }
        return;
    }
    default: break;
    }
    switch (base) {
    case MFC_GETLLAR: {
        std::lock_guard<std::mutex> lk(g_atomic);
        uint32_t line = eal & ~127u;
        std::memcpy(s.rdata, g_mem + line, 128);
        std::memcpy(s.ls + (lsa & 0x3FF80), s.rdata, 128);
        s.raddr = line;
        s.atomic_stat = MFC_GETLLAR_SUCCESS;
        s.atomic_pending = true;
        return;
    }
    case MFC_PUTLLC: {
        std::lock_guard<std::mutex> lk(g_atomic);
        uint32_t line = eal & ~127u;
        bool ok = s.raddr == line && std::memcmp(g_mem + line, s.rdata, 128) == 0;
        if (ok) std::memcpy(g_mem + line, s.ls + (lsa & 0x3FF80), 128);
        s.raddr = ~0u;
        s.atomic_stat = ok ? MFC_PUTLLC_SUCCESS : MFC_PUTLLC_FAILURE;
        s.atomic_pending = true;
        return;
    }
    case MFC_PUTLLUC: case MFC_PUTQLLUC: {
        std::lock_guard<std::mutex> lk(g_atomic);
        uint32_t line = eal & ~127u;
        std::memcpy(g_mem + line, s.ls + (lsa & 0x3FF80), 128);
        if (s.raddr == line) s.raddr = ~0u;
        if (base == MFC_PUTLLUC) {
            s.atomic_stat = MFC_PUTLLUC_SUCCESS;
            s.atomic_pending = true;
        }
        return;
    }
    case MFC_BARRIER: case MFC_EIEIO: case MFC_SYNC:
        return;
    default:
        rt_log("spu %u: MFC command %02X (lsa %05X, ea %08X, size %X) not handled", s.id, cmd, lsa, eal, size);
        return;
    }
}

uint64_t now_ticks() {                                        // the decrementer's 79.8 MHz
    using namespace std::chrono;
    return (uint64_t)duration_cast<nanoseconds>(steady_clock::now().time_since_epoch()).count() * 798 / 10000;
}
}  // namespace

uint32_t spu_rdch(SPUContext& s, uint32_t ch) {
    switch (ch) {
    case MFC_RdTagStat:
        s.tag_stat = s.tag_mask;                              // every group is complete
        return s.tag_stat;
    case MFC_RdAtomicStat:
        s.atomic_pending = false;
        return s.atomic_stat;
    case SPU_RdDec:
        return s.dec_value - (uint32_t)(now_ticks() - s.dec_base);
    case MFC_RdListStallStat:
        return 0;
    case SPU_RdEventMask: case SPU_RdEventStat: case SPU_RdMachStat: case SPU_RdSRR0:
        return 0;
    case SPU_RdInMbox:
        rt_log("spu %u: reads its inbound mailbox; nothing is sent", s.id);
        return 0;
    default:
        rt_log("spu %u: rdch %u not handled", s.id, ch);
        return 0;
    }
}

uint32_t spu_rchcnt(SPUContext& s, uint32_t ch) {
    switch (ch) {
    case MFC_RdTagStat: return 1;
    case MFC_RdAtomicStat: return s.atomic_pending ? 1 : 0;
    case MFC_Cmd: return 16;                                  // the queue is always empty
    case SPU_WrOutMbox: case SPU_WrOutIntrMbox: return 1;
    case SPU_RdInMbox: return 0;
    case SPU_RdDec: return 1;
    default: return 1;
    }
}

void spu_wrch(SPUContext& s, uint32_t ch, uint32_t v) {
    switch (ch) {
    case MFC_LSA: s.mfc_lsa = v; return;
    case MFC_EAH: s.mfc_eah = v; return;
    case MFC_EAL: s.mfc_eal = v; return;
    case MFC_Size: s.mfc_size = v & 0xFFFF; return;
    case MFC_TagID: s.mfc_tag = v & 0x1F; return;
    case MFC_Cmd: command(s, v); return;
    case MFC_WrTagMask: s.tag_mask = v; return;
    case MFC_WrTagUpdate: s.tag_update = v; return;
    case MFC_WrListStallAck: return;
    case SPU_WrDec: s.dec_value = v; s.dec_base = now_ticks(); return;
    case SPU_WrEventMask: case SPU_WrEventAck: case SPU_WrSRR0: return;
    case SPU_WrOutMbox: case SPU_WrOutIntrMbox:
        rt_log("spu %u: mailbox%s %08X", s.id, ch == SPU_WrOutIntrMbox ? " (interrupt)" : "", v);
        return;
    default:
        rt_log("spu %u: wrch %u, %08X not handled", s.id, ch, v);
        return;
    }
}

bool g_spu_trace = std::getenv("PS3KIT_SPU_TRACE") != nullptr;
int g_spu_step = std::getenv("PS3KIT_SPU_TRACE") && std::atoi(std::getenv("PS3KIT_SPU_TRACE")) >= 2;

void spu_trace_step(SPUContext& s, uint32_t pc) {
    rt_log("spu %u: %05X  $0 %05X $1 %05X $3 %08X", s.id, pc, s.r[0].u32[3], s.r[1].u32[3], s.r[3].u32[3]);
}

void spu_trace_dispatch(SPUContext& s, uint32_t pc) {
    rt_log("spu %u: -> %05X  ($0 %05X, $1 %05X, $3 %08X)", s.id, pc, s.r[0].u32[3], s.r[1].u32[3], s.r[3].u32[3]);
}

namespace {
// the preferred slots of the registers that are not zero
void dump(SPUContext& s) {
    std::string line;
    for (int i = 0; i < 128; ++i) {
        const SPUReg& r = s.r[i];
        if (!r.u32[0] && !r.u32[1] && !r.u32[2] && !r.u32[3]) continue;
        char b[48];
        std::snprintf(b, sizeof b, " $%d=%08X", i, r.u32[3]);
        line += b;
        if (line.size() > 100) { rt_log("   %s", line.c_str()); line.clear(); }
    }
    if (!line.empty()) rt_log("   %s", line.c_str());
}

}  // namespace

void spu_stop(SPUContext& s, uint32_t pc, uint32_t code) {
    rt_log("spu %u: stop %X at %05X", s.id, code, pc);
    dump(s);
    std::fflush(stderr);
    std::exit(1);
}

void spu_halt(SPUContext& s, uint32_t pc) {
    rt_log("spu %u: halt at %05X", s.id, pc);
    dump(s);
    std::fflush(stderr);
    std::exit(1);
}

void spu_illegal(SPUContext& s, uint32_t pc, uint32_t word) {
    rt_log("spu %u: illegal instruction %08X at %05X", s.id, word, pc);
    dump(s);
    std::fflush(stderr);
    std::exit(1);
}
