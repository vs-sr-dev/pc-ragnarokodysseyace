"""Trace recompiled guest functions under gdb: arguments in, r3 out, the guest call chain.

    PS3KIT_TRACE_FUNCS=81BEE8,81C890 [PS3KIT_TRACE_CHAIN=1] \
        gdb -q -batch -x ps3kit/gdb_trace.py --args build/recomp-build/ps3boot GAME.elf ...

Each listed guest address is the recompiled function f_XXXXXXXX. On entry it
prints r3-r6 and the guest LR, with PS3KIT_TRACE_CHAIN the saved LRs up the
guest stack's back chain; on return, r3. No debug information is needed: the
PPUContext is the first argument (rcx on Windows x64, rdi elsewhere), and
the offsets below are runtime/ppu.h's.

This is how a guest allocation that returned NULL was followed to a size the
runtime had invented, two levels below the crash it caused.
"""
import os

import gdb

R_OFF, LR_OFF, TID_OFF = 0, 0x420, 0x450      # PPUContext: r[32], ..., lr, ..., thread_id
ARG = "$rcx" if os.name == "nt" else "$rdi"
_base = [0]


def ctx_u64(ctx, off):
    return int(gdb.parse_and_eval("*(unsigned long long*)(%d)" % (ctx + off)))


def ctx_u32(ctx, off):
    return int(gdb.parse_and_eval("*(unsigned int*)(%d)" % (ctx + off)))


def guest_u32(a):
    if not _base[0]:
        _base[0] = int(gdb.parse_and_eval("*(unsigned long long*)&g_mem"))
    v = int(gdb.parse_and_eval("*(unsigned int*)%d" % (_base[0] + a)))
    return int.from_bytes(v.to_bytes(4, "little"), "big")


def chain(ctx, depth=8):
    sp, out = ctx_u64(ctx, R_OFF + 8), []
    for _ in range(depth):
        nxt = guest_u32(sp + 4)                    # the back chain's low word
        if not nxt:
            break
        out.append("%x" % guest_u32(nxt + 20))     # the LR the caller's frame saved
        sp = nxt
    return out


class Return(gdb.FinishBreakpoint):
    def __init__(self, ctx, name):
        super().__init__(gdb.newest_frame(), internal=True)
        self.ctx, self.name = ctx, name

    def stop(self):
        print("<- %s = %x" % (self.name, ctx_u64(self.ctx, R_OFF + 24)))
        return False

    def out_of_scope(self):
        pass


class Entry(gdb.Breakpoint):
    def __init__(self, addr):
        super().__init__("_Z10f_%08XR10PPUContext" % addr, internal=True)
        self.name = "f_%08X" % addr

    def stop(self):
        ctx = int(gdb.parse_and_eval(ARG))
        args = ", ".join("%x" % ctx_u64(ctx, R_OFF + 8 * n) for n in range(3, 7))
        line = "-> %s(%s) lr %x thread %x" % (self.name, args, ctx_u64(ctx, LR_OFF), ctx_u32(ctx, TID_OFF))
        if os.environ.get("PS3KIT_TRACE_CHAIN"):
            line += "  chain " + " ".join(chain(ctx))
        print(line)
        Return(ctx, self.name)
        return False


for a in os.environ.get("PS3KIT_TRACE_FUNCS", "").split(","):
    if a.strip():
        Entry(int(a, 16))
gdb.execute("set pagination off")
gdb.execute("set print thread-events off")
gdb.execute("run")
