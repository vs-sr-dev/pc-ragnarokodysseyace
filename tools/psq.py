"""
psq.py - reader for `.psq`, the sequence language.

**`.psq` is Squirrel 2.2 bytecode**, written by `sq_writeclosure` on a
big-endian host. Nothing about the format had to be guessed once the first
four words were read: `0xFAFA` is `SQ_BYTECODE_STREAM_TAG`, `SQIR`, `PART`
and `TAIL` are `SQ_CLOSURESTREAM_HEAD`, `_PART` and `_TAIL`, and the word
`0x08000010` that introduces every string is `OT_STRING`, which is
`_RT_STRING | SQOBJECT_REF_COUNTED`. The `00 00 00 01` after `SQIR` is
`sizeof(SQChar)`, so the strings are 8-bit.

**3,011 files, 11,232 functions, 314,930 instructions, 0 unreadable**, every
file consumed to the byte. 2,992 of them are `.psq`; the other 19 are `.cnut`
under `monster.cpk/*/ai.pac` and `mercenary.cpk/*/`, which is the same format
under Squirrel's own extension - **six bosses and thirteen mercenaries carry
their AI as script**.

## The container

    fa fa            SQ_BYTECODE_STREAM_TAG
    'SQIR'  u32      SQ_CLOSURESTREAM_HEAD, then sizeof(SQChar) = 1
    'PART'  function the root closure, children nested inside it
    'TAIL'

and a function is `SQFunctionProto::Save` verbatim - source name, function
name, then eight counts and eight `PART`-separated tables:

    nliterals nparameters noutervalues nlocalvarinfos
    nlineinfos ndefaultparams ninstructions nfunctions

    literals        OT_STRING objects - 3,790 distinct, and every one of the
                    55,368 is a string, because Squirrel puts numbers in the
                    instruction. 1,578 are Japanese, all valid UTF-8
    parameters      names; parameter 0 is `this` on all 11,232
    outervalues     0 on all 11,232 - nothing on the disc captures a free
                    variable, and `_OP_LOADFREEVAR` never appears
    localvarinfos   (name, register, first pc, last pc)
    lineinfos       (source line, pc) - the source line of every instruction
    defaultparams   160 functions have one, 2 have two
    instructions    `SQInstruction`: `s32 _arg1` then `op _arg0 _arg2 _arg3`
    functions       nested, each preceded by its own `PART`

    u32 u8 u8       _stacksize, _bgenerator, _varparams

`_stacksize` is the register count, and it covers every register the code
touches on all 11,232. `_bgenerator` is 0 on all of them - there are no
generators - and `_varparams` is 1 on exactly the 19 functions that use
`_OP_VARGC`, which is what says the last two bytes are one byte each rather
than one `u16`.

## What settles the opcode table

The header carries no version, so the version is settled by the code itself,
three ways:

- **the highest opcode on the disc is `0x3C`**, which is `_OP_NEWSLOTA`, the
  last entry of Squirrel 2.2's enum. Squirrel 3.x renumbers everything from
  `_OP_ARITH` onwards and adds `_OP_JCMP`, so a 3.x reading puts `_OP_MUL`
  where every function ends and the returns stop making sense;
- **`_OP_ARITH`'s `_arg3` is the operator as ASCII** - 4,423 `+`, 674 `*`,
  295 `-`, 42 `/`, and nothing else;
- **`CLAMP` decodes to its own source.** `common.psq` carries a three-line
  `CLAMP(v, l, h)`; its twelve instructions read `CMP r4 = v < l` with
  `_arg3 = 3 = CMP_L`, then `CMP r5 = v > h` with `_arg3 = 0 = CMP_G`. Get
  the operand order backwards and it reads `l > v`, and the function would
  clamp the wrong way round.

## What the scripts are

The cutscenes, the quest logic and the stage scripts are Squirrel source
compiled at build time, and the source survives the compile: every function
records the `.ppcut` it came from and the source line of every instruction,
so a `.psq` disassembles with the author's own names against the author's own
line numbers.

`[ERROR] in nut : ` is a literal in the pool, and `nut` is Squirrel's own
extension. `sfEnmGenStart`, `cfMapJump`, `cfSetGlobalFlag` and the rest of the
vocabulary [`format_stage.md`](../docs/format_stage.md) found inside
`trigger.trg` are the names these scripts define and call, so
`callQuestScript("sfEnmGenStart()")` names a Squirrel function that is on the
disc in compiled form - and `xref` shows **144 of the 147 triggers that call
one resolve against a function their own stage's `.psq` defines**.

`api` separates the two halves of the vocabulary: 587 names are called on the
root table, 296 of them are defined by a `.psq` and **291 are not**. Five of
those 291 are Squirrel's own standard library and one is a script that was
never exported, so **285 are the engine's own script interface** - the host
functions a reimplementation has to provide. See
[`format_api.md`](../docs/format_api.md); 119 of them begin `cf`.

`calls` is what says more than an arity: for every name it prints the constants
each argument position is handed, and what the callers name the result -
`localvarinfos` keeps the author's own variable names, so `getHpRate` comes
back with `own_hp_rate` beside it.

## The jumps go back into statements, all of them

`src` used to print control flow as labels and `goto`. It does not any more:
`Structure` turns the jump graph back into `if`/`else`/`switch`/`while`, and
the measurement that says the reading is right is that **there is nothing left
over**.

**Squirrel has no `goto`.** Every jump in a `.psq` came out of a construct, so
"most of them placed" would not be a result - the target is all of them, and
`psq.py struct` reports the shortfall over the whole disc:

    2,753 of 2,753 functions that carry a jump, structured with nothing left
    0 jumps not placed, 0 statements stepped over

    if 5,068   if/else 3,483   break 1,761   switch 248 (203 fall-throughs)
    while 34   foreach 11      do..while 4

plus the 2,635 `_OP_AND` and `_OP_OR`, which are folded a level down in
`Trace` because they are expression and not control flow. That fold is not
cosmetic: unfolded, `a && b` printed as a branch on `b` alone and silently
lost `a`.

**What separates a `switch` from an `else if` is a jump no `if` ever makes.**
Both compile to a chain of tests on one register, but a `switch` case falls
through by jumping into the *next case's body*, past that case's own test -
and Squirrel emits that jump even when the case ended in `break`, which is why
a `switch` shows two consecutive `_OP_JMP` where an `else if` shows one. The
first discriminator written here was "three links or more"; it read a
two-case `switch` in `sfQuestDemoInit` as a branch and left its `break`
behind.

Usage:
  python psq.py check <dir>               parse every file, exact consumption
  python psq.py list <dir>                every file, most instructions first
  python psq.py dump <dir> <name>         one file, annotated disassembly
  python psq.py src <dir> <name>          one file, reconstructed source
  python psq.py struct <dir> [-v]         does every jump go back into one?
  python psq.py api <dir>                 every global called, with arities
  python psq.py calls <dir> [glob]        ... and its arguments and result
  python psq.py sites <dir> <glob> [n]    the call sites themselves
  python psq.py xref <dir>                do the names name anything?
  python psq.py names <dir>               every literal, most used first
  python psq.py ops <dir>                 opcode histogram
  python psq.py find <dir> <glob>         locate one at any depth
"""
from __future__ import annotations

import collections
import fnmatch
import pathlib
import re
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

MAGIC = b'\xfa\xfaSQIR'
TAIL = b'TAIL'
PART = b'PART'
OT_STRING = b'\x08\x00\x00\x10'

OPS = {
    0x00: 'LINE',        0x01: 'LOAD',        0x02: 'LOADINT',
    0x03: 'LOADFLOAT',   0x04: 'DLOAD',       0x05: 'TAILCALL',
    0x06: 'CALL',        0x07: 'PREPCALL',    0x08: 'PREPCALLK',
    0x09: 'GETK',        0x0A: 'MOVE',        0x0B: 'NEWSLOT',
    0x0C: 'DELETE',      0x0D: 'SET',         0x0E: 'GET',
    0x0F: 'EQ',          0x10: 'NE',          0x11: 'ARITH',
    0x12: 'BITW',        0x13: 'RETURN',      0x14: 'LOADNULLS',
    0x15: 'LOADROOT',    0x16: 'LOADBOOL',    0x17: 'DMOVE',
    0x18: 'JMP',         0x19: 'JNZ',         0x1A: 'JZ',
    0x1B: 'LOADFREEVAR', 0x1C: 'VARGC',       0x1D: 'GETVARGV',
    0x1E: 'NEWTABLE',    0x1F: 'NEWARRAY',    0x20: 'APPENDARRAY',
    0x21: 'GETPARENT',   0x22: 'COMPARITH',   0x23: 'COMPARITHL',
    0x24: 'INC',         0x25: 'INCL',        0x26: 'PINC',
    0x27: 'PINCL',       0x28: 'CMP',         0x29: 'EXISTS',
    0x2A: 'INSTANCEOF',  0x2B: 'AND',         0x2C: 'OR',
    0x2D: 'NEG',         0x2E: 'NOT',         0x2F: 'BWNOT',
    0x30: 'CLOSURE',     0x31: 'YIELD',       0x32: 'RESUME',
    0x33: 'FOREACH',     0x34: 'POSTFOREACH', 0x35: 'DELEGATE',
    0x36: 'CLONE',       0x37: 'TYPEOF',      0x38: 'PUSHTRAP',
    0x39: 'POPTRAP',     0x3A: 'THROW',       0x3B: 'CLASS',
    0x3C: 'NEWSLOTA',
}

CMP = {0: '>', 2: '>=', 3: '<', 4: '<=', 5: '<=>'}
JUMPS = (0x18, 0x19, 0x1A, 0x2B, 0x2C, 0x33, 0x34)


class PsqError(Exception):
    pass


# -- the container ---------------------------------------------------------

class Reader:
    """A byte cursor. The stream is tokens, not an offset table."""

    def __init__(self, buf: bytes):
        self.buf = buf
        self.o = 0

    def u8(self) -> int:
        v = self.buf[self.o]
        self.o += 1
        return v

    def u32(self) -> int:
        v = int.from_bytes(self.buf[self.o:self.o + 4], 'big')
        self.o += 4
        return v

    def part(self) -> None:
        if self.buf[self.o:self.o + 4] != PART:
            raise PsqError(f'PART expected at {self.o:#x}')
        self.o += 4

    def text(self) -> str:
        if self.buf[self.o:self.o + 4] != OT_STRING:
            raise PsqError(f'OT_STRING expected at {self.o:#x}')
        self.o += 4
        n = self.u32()
        s = self.buf[self.o:self.o + n]
        self.o += n
        try:                       # 1,578 literals are Japanese, all UTF-8
            return s.decode('utf-8')
        except UnicodeDecodeError:
            return s.decode('latin1')

    def is_text(self) -> bool:
        return self.buf[self.o:self.o + 4] == OT_STRING


class Function:
    """`SQFunctionProto`, as `Save` wrote it."""

    def __init__(self, r: Reader):
        self.src = r.text()
        self.name = r.text()
        r.part()
        self.head = [r.u32() for _ in range(8)]
        r.part()
        n = self.head
        self.lit = [r.text() if r.is_text() else r.u32() for _ in range(n[0])]
        r.part()
        self.param = [r.text() for _ in range(n[1])]
        r.part()
        self.outer = [(r.text(), r.text(), r.text()) for _ in range(n[2])]
        r.part()
        self.local = [(r.text(), r.u32(), r.u32(), r.u32())
                      for _ in range(n[3])]
        r.part()
        self.line = [(r.u32(), r.u32()) for _ in range(n[4])]
        r.part()
        self.default = [r.u32() for _ in range(n[5])]
        r.part()
        self.code = [(r.u32(), r.u32()) for _ in range(n[6])]
        r.part()
        self.child = []
        for _ in range(n[7]):
            r.part()
            self.child.append(Function(r))
        self.stack = r.u32()
        self.generator = r.u8()
        self.varparams = r.u8()

    def walk(self):
        yield self
        for c in self.child:
            yield from c.walk()

    def lines(self) -> dict:
        """pc -> source line, for the instructions that begin one."""
        return {pc: ln for ln, pc in self.line}


class Psq:
    """One compiled sequence."""

    def __init__(self, blob: bytes, path: str = ''):
        self.path = path
        if blob[:6] != MAGIC or blob[-4:] != TAIL:
            raise PsqError('not a psq')
        r = Reader(blob[:-4])
        r.o = 6
        self.charsize = r.u32()
        r.part()
        self.root = Function(r)
        if r.o != len(blob) - 4:
            raise PsqError(f'{len(blob) - 4 - r.o} bytes left at {r.o:#x}')

    def functions(self) -> list:
        return list(self.root.walk())


# -- the disassembler ------------------------------------------------------

def fields(word: int):
    """op, _arg0, _arg2, _arg3."""
    return word >> 24, (word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF


def signed(v: int) -> int:
    return v - 0x100000000 if v & 0x80000000 else v


def sbyte(v: int) -> int:
    return v - 0x100 if v & 0x80 else v


def step(where: str, delta: int) -> str:
    if delta in (1, -1):
        return where + ('++' if delta == 1 else '--')
    return '%s %s= %d' % (where, '+' if delta > 0 else '-', abs(delta))


def reads(a1: int, word: int) -> set:
    """Which registers an instruction reads, so dead results can be dropped."""
    op, a0, a2, a3 = fields(word)
    if op in (0x05, 0x06):
        return {a1} | set(range(a2, a2 + a3))
    if op == 0x07:
        return {a1, a2}
    if op in (0x08, 0x09):
        return {a2}
    if op in (0x0A, 0x1D, 0x25, 0x27, 0x2D, 0x2E, 0x2F, 0x36, 0x37):
        return {a1}
    if op in (0x0B, 0x0D, 0x3C):
        return {a1, a2, a3}
    # `a += b` reads the accumulator *and* the value. Reading only the first
    # made the right-hand side look dead, so a call there printed twice: once
    # as a statement of its own and once inside the compound assignment.
    if op in (0x0C, 0x0E, 0x11, 0x12, 0x23, 0x24, 0x26, 0x28, 0x35):
        return {a1, a2}
    if op == 0x3B:                             # base and attributes optional
        return ({a1} if signed(a1) >= 0 else set()) | \
               ({a2} if a2 != 0xFF else set())
    if op in (0x0F, 0x10):
        return {a2} if a3 else {a1, a2}
    if op == 0x13:
        return set() if a0 == 0xFF else {a1}
    if op == 0x17:
        return {a1, a3}
    if op in (0x19, 0x1A, 0x2B, 0x2C, 0x34, 0x3A):
        return {a0}
    if op == 0x20:
        return {a0} if a3 else {a0, a1}
    if op == 0x22:
        return {(a1 >> 16) & 0xFFFF, a1 & 0xFFFF, a2}
    if op == 0x33:
        return {a0, a2, a2 + 1, a2 + 2}
    return set()


def writes(a1: int, word: int) -> set:
    """Which registers an instruction fills. The mirror of `reads`, and the
    other half of what liveness needs."""
    op, a0, a2, a3 = fields(word)
    if op in (0x0B, 0x0D, 0x13, 0x3A) or a0 == 0xFF:
        return set()
    if op == 0x14:                             # LOADNULLS fills a run
        return set(range(a0, a0 + a1))
    if op in (0x04, 0x17):                     # DLOAD and DMOVE fill two
        return {a0, a2}
    if op == 0x33:                             # FOREACH fills key, value, it
        return {a2, a2 + 1, a2 + 2}
    return {a0}


def successors(f) -> list:
    """The control-flow graph, as the jump fields give it."""
    n = len(f.code)
    out = []
    for pc, (a1, w) in enumerate(f.code):
        op = w >> 24
        t = pc + 1 + signed(a1)
        nxt = [pc + 1] if pc + 1 < n else []
        if op == 0x18:
            out.append([t])
        elif op == 0x13:
            out.append([])
        elif op in (0x19, 0x1A, 0x2B, 0x2C, 0x33, 0x34):
            out.append([t] + nxt)
        else:
            out.append(nxt)
    return out


def liveness(f) -> list:
    """Which registers are read before they are written, at every pc.

    Backward dataflow to a fixed point, over the real graph. The rule this
    replaced walked forward and gave up at the first jump it met - *control
    flow: assume it is* - which made a call at the end of a block look live
    and dropped it from the listing. That hid **3,004 statement calls**, most
    of them the last action of an `if` arm in a cutscene, and it stayed hidden
    for as long as the arm's own end was printed as a `goto`.
    """
    n = len(f.code)
    succ = successors(f)
    lin = [frozenset()] * n
    changed = True
    while changed:
        changed = False
        for pc in range(n - 1, -1, -1):
            a1, w = f.code[pc]
            out = set()
            for t in succ[pc]:
                if 0 <= t < n:
                    out |= lin[t]
            new = frozenset((out - writes(a1, w)) | reads(a1, w))
            if new != lin[pc]:
                lin[pc] = new
                changed = True
    return lin


def lit(f, i: int) -> str:
    if 0 <= i < len(f.lit):
        v = f.lit[i]
        return repr(v) if isinstance(v, str) else str(v)
    return 'K%d' % i


def key(f, i: int) -> str:
    if 0 <= i < len(f.lit) and isinstance(f.lit[i], str):
        return f.lit[i]
    return 'K%d' % i


class Trace:
    """Symbolic execution of one function: a register holds an expression."""

    def __init__(self, f):
        self.f = f
        self.livein = liveness(f)
        self.reg = {}
        for i, name in enumerate(f.param):
            self.reg[i] = name
        self.note = {}                          # pc -> statement
        self.cond = {}                          # pc -> the test a jump reads
        self.eq = {}                            # pc -> (left, right) of a test
        self.fold = []                          # (merge pc, register, lhs, op)
        self.targets = set()
        self.calls = []                         # (pc, callee, [argument])
        self.root = {}                          # register -> root-table name
        # A local becomes live one instruction after the one that fills it,
        # so `start_op` names the register write that declares it.
        self.declare = {}                       # (pc, register) -> name
        self.scope = {}                         # register -> (name, last pc)
        for name, pos, start, end in f.local:
            if pos >= len(f.param):
                self.declare[(start - 1, pos)] = (name, end)

    def r(self, i: int) -> str:
        return self.reg.get(i, 'r%d' % i)

    def live(self, pc: int, reg: int) -> bool:
        """Is the value this instruction just produced read anywhere? If it
        is not, the instruction was a statement and not an expression."""
        return (pc + 1 < len(self.livein)
                and reg in self.livein[pc + 1])

    def bind(self, pc: int, reg: int, value: str):
        """Put an expression in a register, naming it if a local starts here."""
        self.reg[reg] = value
        if (pc, reg) in self.declare:
            name, end = self.declare[(pc, reg)]
            self.scope[reg] = (name, end)
            self.reg[reg] = name
            return 'local %s = %s' % (name, value)
        if reg in self.scope and pc <= self.scope[reg][1]:
            name = self.scope[reg][0]
            if value != name:
                self.reg[reg] = name
                return '%s = %s' % (name, value)
        return None

    def slot(self, obj: int, k: int) -> str:
        """`obj[key]`, written the way the source would have written it."""
        o, key = self.r(obj), self.r(k)
        if key[:1] == "'" and key[-1:] == "'" and key[1:-1].isidentifier():
            return key[1:-1] if o == 'this' else '%s.%s' % (o, key[1:-1])
        return '%s[%s]' % (o, key)

    def label(self, pc: int, a1: int) -> str:
        t = pc + 1 + signed(a1)
        self.targets.add(t)
        return 'L%d' % t

    def run(self):
        f = self.f
        for pc, (a1, w) in enumerate(f.code):
            op, a0, a2, a3 = fields(w)
            s1 = signed(a1)
            out = text = None
            # `a && b` leaves `a` in a register and jumps here over `b`, so
            # arriving at the merge is what completes the expression. Innermost
            # first, which is why the list is drained from the end.
            for k in range(len(self.fold) - 1, -1, -1):
                at, reg, lhs, sym = self.fold[k]
                if at == pc:
                    self.reg[reg] = '(%s %s %s)' % (lhs, sym, self.r(reg))
                    del self.fold[k]
            if op == 0x01:
                out = lit(f, a1)
            elif op == 0x02:
                out = str(s1)
            elif op == 0x03:
                out = '%g' % struct.unpack('>f', a1.to_bytes(4, 'big'))[0]
            elif op == 0x04:
                text = self.bind(pc, a2, lit(f, a3))
                out = lit(f, a1)
            elif op in (0x05, 0x06):
                args = [self.r(i) for i in range(a2 + 1, a2 + a3)]
                if a1 in self.root:             # fetched off the root table,
                    self.calls.append((pc, self.root.pop(a1), args))
                out = '%s(%s)' % (self.r(a1), ', '.join(args))
                if op == 0x05:
                    text = 'return ' + out
                elif not self.live(pc, a0):
                    text = out
            elif op == 0x07:
                self.reg[a3] = self.r(a2)
                k = self.r(a1)
                if a2 == 0 and k[:1] == "'" and k[-1:] == "'":
                    self.root[a0] = k[1:-1]     # this['name']() is a root call
                out = '%s[%s]' % (self.r(a2), k)
            elif op in (0x08, 0x09):
                if op == 0x08:
                    self.reg[a3] = self.r(a2)
                    if a2 == 0:                 # ... and not through a local
                        self.root[a0] = key(f, a1)
                obj = self.r(a2)
                out = key(f, a1) if obj == 'this' \
                    else '%s.%s' % (obj, key(f, a1))
            elif op == 0x0A:
                out = self.r(a1)
            elif op == 0x0B:
                out = self.r(a3)
                text = '%s <- %s' % (self.slot(a1, a2), out)
            elif op == 0x0C:
                out = text = 'delete %s[%s]' % (self.r(a1), self.r(a2))
            elif op == 0x0D:
                out = self.r(a3)
                text = '%s = %s' % (self.slot(a1, a2), out)
            elif op == 0x0E:
                out = self.slot(a1, a2)
            elif op in (0x0F, 0x10):
                rhs = lit(f, a1) if a3 else self.r(a1)
                if op == 0x0F:
                    self.eq[pc] = (self.r(a2), rhs)
                out = '(%s %s %s)' % (self.r(a2),
                                      '==' if op == 0x0F else '!=', rhs)
            elif op in (0x11, 0x12):
                out = '(%s %s %s)' % (self.r(a2), chr(a3), self.r(a1))
            elif op == 0x13:
                text = 'return' if a0 == 0xFF else 'return ' + self.r(a1)
            elif op == 0x14:
                said = [self.bind(pc, i, 'null') for i in range(a0, a0 + a1)]
                text = '; '.join(s for s in said if s) or None
            elif op == 0x15:
                out = '::'
            elif op == 0x16:
                out = 'true' if a1 else 'false'
            elif op == 0x17:
                text = self.bind(pc, a2, self.r(a3))
                out = self.r(a1)
            elif op == 0x18:
                text = 'goto ' + self.label(pc, a1)
            elif op in (0x19, 0x1A):
                # JZ jumps when the test is false, so the test itself is what
                # an `if` was written with; JNZ is the negation of it.
                self.cond[pc] = (self.r(a0) if op == 0x1A
                                 else '!' + self.r(a0))
                text = 'if (%s%s) goto %s' % ('' if op == 0x19 else '!',
                                              self.r(a0), self.label(pc, a1))
            elif op == 0x1C:
                out = 'vargc'
            elif op == 0x1D:
                out = 'vargv[%s]' % self.r(a1)
            elif op == 0x1E:
                out = '{}'
            elif op == 0x1F:
                out = '[]'
            elif op == 0x20:
                text = '%s.append(%s)' % (self.r(a0),
                                          lit(f, a1) if a3 else self.r(a1))
            elif op == 0x22:
                text = '%s[%s] %s= %s' % (self.r((a1 >> 16) & 0xFFFF),
                                          self.r(a2), chr(a3),
                                          self.r(a1 & 0xFFFF))
            elif op == 0x23:
                out = self.r(a1)
                text = '%s %s= %s' % (out, chr(a3), self.r(a2))
            elif op in (0x24, 0x26):
                out = self.slot(a1, a2)
                text = step(out, sbyte(a3))
            elif op in (0x25, 0x27):
                out = self.r(a1)
                text = step(out, sbyte(a3))
            elif op == 0x28:
                out = '(%s %s %s)' % (self.r(a2), CMP.get(a3, a3),
                                      self.r(a1))
            elif op == 0x29:
                out = '(%s in %s)' % (self.r(a2), self.r(a1))
            elif op == 0x2A:
                out = '(%s instanceof %s)' % (self.r(a1), self.r(a2))
            elif op in (0x2B, 0x2C):
                # Short-circuit, not control flow: the operand register is
                # `a0` and `a2` alike - they are equal on all 2,635 of these
                # on the disc - and the jump only skips the right-hand side.
                self.fold.append((pc + 1 + s1, a0, self.r(a0),
                                  '&&' if op == 0x2B else '||'))
                self.targets.add(pc + 1 + s1)
            elif op == 0x2D:
                out = '-' + self.r(a1)
            elif op == 0x2E:
                out = '!' + self.r(a1)
            elif op == 0x2F:
                out = '~' + self.r(a1)
            elif op == 0x30:
                sub = f.child[a1] if a1 < len(f.child) else None
                out = 'function %s' % (sub.name if sub else '#%d' % a1)
            elif op == 0x31:
                text = 'yield ' + self.r(a1)
            elif op == 0x33:
                # The key and the value are written here, and `localvarinfos`
                # has the author's names for both.
                for k in (a2, a2 + 1):
                    for name, pos, start, stop in f.local:
                        if pos == k and start <= pc + 1 <= stop:
                            self.reg[k] = name
                            break
                text = 'foreach ' + self.label(pc, a1)
            elif op == 0x34:
                text = 'endforeach ' + self.label(pc, a1)
            elif op == 0x36:
                out = 'clone ' + self.r(a1)
            elif op == 0x37:
                out = 'typeof ' + self.r(a1)
            elif op == 0x3A:
                text = 'throw ' + self.r(a0)
            elif op == 0x3B:
                out = 'class'
            elif op == 0x3C:
                text = '%s[%s] <- %s' % (self.r(a1), self.r(a2), self.r(a3))
            if out is not None and a0 != 0xFF and op not in (0x14, 0x18,
                                                             0x19, 0x1A):
                text = self.bind(pc, a0, out) or text
            if text:
                self.note[pc] = text
        return self


# -- the structurer --------------------------------------------------------

STRUCT_JUMPS = (0x18, 0x19, 0x1A, 0x33)


def bare(test: str) -> str:
    """Drop the outer parentheses an expression already carries, so that a
    test reads `if (a == b)` and not `if ((a == b))`."""
    if not (test.startswith('(') and test.endswith(')')):
        return test
    depth = 0
    for i, c in enumerate(test):
        depth += (c == '(') - (c == ')')
        if depth == 0 and i < len(test) - 1:
            return test                        # the pair does not span it all
    return test[1:-1]


class Structure:
    """The jump graph, put back into the statements it was compiled from.

    **Squirrel has no `goto`.** Every jump in a `.psq` came out of an `if`, a
    loop, a `break`, a `continue` or a short-circuit operator, so a correct
    reconstruction places all of them and leaves nothing behind. `residual`
    counts the jumps this pass could not place, which is what turns a wrong
    reading into a number instead of a plausible-looking listing: `psq.py
    struct` prints it over the whole disc.

    `_OP_AND` and `_OP_OR` are handled a level down, in `Trace`, because they
    are expression and not control flow - the jump only skips the right-hand
    operand. Folding them is not cosmetic: unfolded, `a && b` prints as a
    branch on `b` alone and silently loses `a`.
    """

    def __init__(self, f, tr):
        self.f, self.tr = f, tr
        self.jmp = {}
        for pc, (a1, w) in enumerate(f.code):
            op = w >> 24
            if op in STRUCT_JUMPS:
                self.jmp[pc] = (op, pc + 1 + signed(a1))
        # A jump that lands at or before itself closes a loop. The *last* one
        # that lands on a given instruction is the loop's own back edge.
        self.back = {}
        for pc, (op, t) in self.jmp.items():
            if t <= pc and pc > self.back.get(t, -1):
                self.back[t] = pc
        self.residual = 0
        self.used = set()               # every pc the tree accounts for
        self.tree = self.body(0, len(f.code))
        # Conservation: a statement that the walk stepped over is a statement
        # lost, and dropping one is exactly how a wrong loop or branch would
        # look right. `struct` sums this over the disc.
        self.lost = sorted(set(tr.note) - self.used)

    # -- the walk ----------------------------------------------------------

    def body(self, lo, hi, loop=None, sw=None):
        """The statements of `[lo, hi)`, as a tree. `loop` is `(header,
        exit)` of the innermost enclosing loop and `sw` is `(end, body
        starts)` of the innermost enclosing `switch`; between them they are
        what names a jump `break`, `continue` or a fall-through."""
        out, pc = [], lo
        while pc < hi:
            end = self.back.get(pc)
            if end is not None and pc <= end < hi:
                node, pc = self.loop(pc, end)
                out.append(node)
                continue
            j = self.jmp.get(pc)
            if j is None:
                if pc in self.tr.note:
                    out.append(('stmt', pc))
                    self.used.add(pc)
                pc += 1
                continue
            op, t = j
            if op == 0x1A and pc < t <= hi:
                links, sel = self.chain(pc, hi)
                if self.is_switch(links, hi):
                    node, pc = self.switch(links, sel, hi)
                    out.append(node)
                    continue
            if op in (0x19, 0x1A) and pc < t <= hi:
                node, pc = self.branch(pc, t, hi, loop, sw)
                out.append(node)
                continue
            if op == 0x18:
                if sw and t == sw[0]:
                    out.append(('word', 'break'))
                    self.used.add(pc)
                    pc += 1
                    continue
                if sw and t in sw[1]:
                    out.append(('word', '// falls through'))
                    self.used.add(pc)
                    pc += 1
                    continue
                if loop and t == loop[0]:
                    out.append(('word', 'continue'))
                    self.used.add(pc)
                    pc += 1
                    continue
                if loop and t == loop[1]:
                    out.append(('word', 'break'))
                    self.used.add(pc)
                    pc += 1
                    continue
                if t == hi:              # a jump to the end of this block is
                    self.used.add(pc)    # the fall-through an `if` arm ends on
                    pc += 1
                    continue
            out.append(('stmt', pc))     # not placed, so the goto stays
            self.used.add(pc)
            self.residual += 1
            pc += 1
        return out

    def branch(self, pc, t, hi, loop, sw=None):
        """A conditional jump forward is an `if`, and the instruction before
        its target is an `else` jump when it goes forward past it - unless it
        is the `break` of an enclosing loop or `switch`, which lands past the
        target too and means something else entirely."""
        cond = self.tr.cond.get(pc, '?')
        tail = self.jmp.get(t - 1)
        self.used.add(pc)
        if (tail and tail[0] == 0x18 and t - 1 > pc
                and t < tail[1] <= hi
                and not (loop and tail[1] in loop)
                and not (sw and (tail[1] == sw[0] or tail[1] in sw[1]))):
            self.used.add(t - 1)
            return ('if', cond, self.body(pc + 1, t - 1, loop, sw),
                    self.body(t, tail[1], loop, sw)), tail[1]
        return ('if', cond, self.body(pc + 1, t, loop, sw), None), t

    def loop(self, h, end):
        """`[h, end]` is a loop and `end` is the jump back to `h`."""
        op0, a0, a2, _ = fields(self.f.code[h][1])
        self.used.add(end)
        if op0 == 0x33:                                  # foreach
            leave = self.jmp[h][1]
            self.used.update((h, h + 1))
            return ('foreach', self.local(a2, h + 2), self.local(a2 + 1, h + 2),
                    self.tr.r(a0),
                    self.body(h + 2, end, (h, leave))), leave
        leave = end + 1
        for pc in range(h, end):                         # the test at the top
            j = self.jmp.get(pc)
            if j and j[0] in (0x19, 0x1A) and j[1] == leave:
                self.used.add(pc)
                return ('while', self.tr.cond.get(pc, '?'),
                        self.body(pc + 1, end, (h, leave))), leave
        if self.jmp[end][0] in (0x19, 0x1A):             # the test at the foot
            return ('dowhile', self.tr.cond.get(end, '?'),
                    self.body(h, end, (h, leave))), leave
        return ('forever', self.body(h, end, (h, leave))), leave

    # -- switch ------------------------------------------------------------

    def chain(self, pc, hi):
        """A run of tests of one register against constants, each jumping to
        the next. This is what a `switch` compiles to - and two links of it
        are also what an `else if` compiles to, so the caller asks for three
        before calling it one."""
        links, sel, p = [], None, pc
        while p is not None and p < hi:
            j = self.jmp.get(p)
            if not (j and j[0] == 0x1A and p < j[1] <= hi):
                break
            got = self.tr.eq.get(p - 1) if p else None
            if got is None or (sel is not None and got[0] != sel):
                break
            sel = got[0]
            links.append((p, j[1], got[1]))
            p = None
            for k in range(j[1], hi):        # what follows the target is the
                if k in self.jmp:            # next test, or a case body. a
                    p = k                    # jump carries a statement too,
                    break                    # so it has to be asked first
                if k in self.tr.note:
                    break
        return links, sel

    def is_switch(self, links, hi) -> bool:
        """A chain of tests is a `switch` and not an `else if` when one of its
        arms jumps **into another arm's body**, past that arm's own test.

        Squirrel compiles a case's fall-through as a jump to the next case's
        body, and emits it even when the case ended in `break` - which is why
        a `switch` shows two consecutive `_OP_JMP` where an `else if` shows
        one. Nothing else on the disc produces that, because the language has
        no `goto`, so this is a discriminator and not a threshold: the first
        one written here was "three links or more", and it read a two-case
        `switch` in `sfQuestDemoInit` as a branch and left its `break` behind.
        """
        if len(links) < 2:
            return False
        bodies = {p + 1 for p, _, _ in links[1:]}
        for k in range(links[0][0], links[-1][1]):
            j = self.jmp.get(k)
            if j and j[0] == 0x18 and j[1] in bodies:
                return True
        return False

    def switch(self, links, sel, hi):
        """`links` is `[(test pc, next test, case value)]`.

        A case body runs from its own test to the next one. The jump that
        ends it is a `break` when it leaves the whole statement and a
        **fall-through** when it lands in the next case's body - which is the
        thing no `if`/`else` ever does, and the reason this has to be read as
        a `switch` rather than a chain of branches."""
        last = links[-1][1]
        end = last
        for k in range(links[0][0], last):
            j = self.jmp.get(k)
            if j and j[0] == 0x18 and end < j[1] <= hi:
                end = j[1]
        sw = (end, {p + 1 for p, _, _ in links} | {last})
        cases = []
        for p, nxt, value in links:
            self.used.add(p)
            cases.append((value, self.trim(self.body(p + 1, nxt, None, sw))))
        default = (self.trim(self.body(last, end, None, sw))
                   if last < end else None)
        return ('switch', sel, cases, default), end

    @staticmethod
    def trim(nodes):
        """Squirrel emits a case's fall-through jump even when the case ended
        in `break`, so the second of the two is unreachable."""
        while (len(nodes) >= 2 and nodes[-1] == ('word', '// falls through')
               and nodes[-2] == ('word', 'break')):
            nodes.pop()
        return nodes

    def local(self, reg: int, pc: int) -> str:
        """The author's name for a register, at one instruction."""
        for name, pos, start, stop in self.f.local:
            if pos == reg and start <= pc <= stop:
                return name
        return 'r%d' % reg

    # -- rendering ---------------------------------------------------------

    def render(self, nodes=None, depth: int = 0, out=None) -> list:
        out = [] if out is None else out
        pad = '    ' * depth
        for n in (self.tree if nodes is None else nodes):
            if n[0] == 'stmt':
                out.append(pad + self.tr.note.get(n[1], ''))
            elif n[0] == 'word':
                out.append(pad + n[1])
            elif n[0] == 'if':
                out.append('%sif (%s) {' % (pad, bare(n[1])))
                self.render(n[2], depth + 1, out)
                els = n[3]
                while els is not None:
                    # An `else` holding nothing but an `if` is an `else if`,
                    # which is also how a `switch` comes back.
                    if len(els) == 1 and els[0][0] == 'if':
                        out.append('%s} else if (%s) {'
                                   % (pad, bare(els[0][1])))
                        self.render(els[0][2], depth + 1, out)
                        els = els[0][3]
                        continue
                    out.append(pad + '} else {')
                    self.render(els, depth + 1, out)
                    break
                out.append(pad + '}')
            elif n[0] == 'switch':
                out.append('%sswitch (%s) {' % (pad, bare(n[1])))
                for value, arm in n[2]:
                    out.append('%s  case %s:' % (pad, value))
                    self.render(arm, depth + 1, out)
                if n[3] is not None:
                    out.append(pad + '  default:')
                    self.render(n[3], depth + 1, out)
                out.append(pad + '}')
            elif n[0] == 'while':
                out.append('%swhile (%s) {' % (pad, bare(n[1])))
                self.render(n[2], depth + 1, out)
                out.append(pad + '}')
            elif n[0] == 'dowhile':
                out.append(pad + 'do {')
                self.render(n[2], depth + 1, out)
                out.append('%s} while (%s)' % (pad, bare(n[1])))
            elif n[0] == 'forever':
                out.append(pad + 'while (true) {')
                self.render(n[1], depth + 1, out)
                out.append(pad + '}')
            elif n[0] == 'foreach':
                out.append('%sforeach (%s, %s in %s) {'
                           % (pad, n[1], n[2], n[3]))
                self.render(n[4], depth + 1, out)
                out.append(pad + '}')
        return out


# --------------------------------------------------------------------------

def walk(root, want: str = ''):
    """Every leaf of the asset tree, expanded or still in its containers."""
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if p.is_file():
                yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    yield from leaves(root, want)


def collect(root, want: str = ''):
    for path, blob in walk(root, want):
        if blob[:6] == MAGIC:
            yield path, blob


def _one(root, name):
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Psq(blob, path)
    raise SystemExit('not found: ' + name)


def cmd_check(root) -> int:
    files = bad = funcs = ins = lits = 0
    stack_ok = stack_n = nonstring = noself = 0
    gen = varp = 0
    for path, blob in collect(root):
        files += 1
        try:
            q = Psq(blob, path)
        except Exception as e:                                # noqa: BLE001
            bad += 1
            print('  %s: %s' % (path, e))
            continue
        for f in q.functions():
            funcs += 1
            ins += len(f.code)
            lits += len(f.lit)
            nonstring += sum(not isinstance(v, str) for v in f.lit)
            noself += bool(f.param) and f.param[0] != 'this'
            gen += f.generator
            varp += f.varparams
            hi = -1
            for a1, w in f.code:
                op, a0, a2, a3 = fields(w)
                if a0 != 0xFF and op not in JUMPS:
                    hi = max(hi, a0)
                hi = max(hi, max(reads(a1, w), default=-1))
            stack_n += 1
            stack_ok += f.stack >= hi + 1
    print('%d files, %d functions, %d instructions, %d literals, '
          '%d unreadable' % (files, funcs, ins, lits, bad))
    print('%d literals are not strings; %d functions do not take `this`'
          % (nonstring, noself))
    print('_stacksize covers every register used on %d of %d functions'
          % (stack_ok, stack_n))
    print('%d generators, %d vararg functions' % (gen, varp))
    return 1 if bad else 0


def cmd_list(root) -> int:
    rows = []
    for path, blob in collect(root):
        fs = Psq(blob, path).functions()
        rows.append((sum(len(f.code) for f in fs), len(fs), path))
    rows.sort(reverse=True)
    for ins, nf, path in rows:
        print('  %6d ins %4d fn  %s' % (ins, nf, path))
    print('%d files' % len(rows))
    return 0


def _dump(f, indent: str, src: bool) -> None:
    t = Trace(f).run()
    ln = f.lines()
    first = f.line[0][0] if f.line else 0
    print('%sfunction %s(%s)   // %s:%d, %d registers'
          % (indent, f.name, ', '.join(f.param[1:]), f.src, first, f.stack))
    if src:
        s = Structure(f, t)
        for row in s.render():
            print(indent + '    ' + row)
        if s.residual:
            print('%s    // %d jump%s not placed' % (indent, s.residual,
                                                     '' if s.residual == 1
                                                     else 's'))
        for c in f.child:
            print()
            _dump(c, indent + '  ', src)
        return
    if f.local:
        print('%s  locals %s' % (indent, ', '.join(
            'r%d=%s' % (p, n) for n, p, _, _ in reversed(f.local))))
    for pc, (a1, w) in enumerate(f.code):
        op, a0, a2, a3 = fields(w)
        if pc in t.targets:
            print('%sL%d:' % (indent, pc))
        head = ('%s  /* %d */' % (indent, ln[pc]) if pc in ln
                else indent).ljust(len(indent) + 13)
        raw = '%02x %02x %02x %02x %8d' % (op, a0, a2, a3, signed(a1))
        print('%s%4d %s  %-12s %s'
              % (head, pc, raw, OPS.get(op, '%#04x' % op), t.note.get(pc, '')))
    for c in f.child:
        print()
        _dump(c, indent + '  ', src)


def cmd_dump(root, name, src=False) -> int:
    path, q = _one(root, name)
    print('%s   sizeof(SQChar) = %d' % (path, q.charsize))
    print()
    _dump(q.root, '', src)
    return 0


def cmd_struct(root, verbose=False) -> int:
    """Does the jump graph go back into statements, on every function?

    Squirrel has no `goto`, so the honest target is not "most" but **all**:
    a jump this pass cannot place is a hole in the reading, and a statement
    it steps over is worse, because the listing still looks like source."""
    files = funcs = withj = clean = 0
    residual = lost = 0
    shapes = collections.Counter()
    bad = []
    for path, blob in collect(root):
        try:
            q = Psq(blob, path)
        except PsqError:
            continue
        files += 1
        for f in q.functions():
            funcs += 1
            s = Structure(f, Trace(f).run())
            if not s.jmp:
                continue
            withj += 1
            for node in _shapes(s.tree):
                shapes[node] += 1
            residual += s.residual
            lost += len(s.lost)
            if s.residual or s.lost:
                bad.append((path, f.name, s.residual, len(s.lost)))
            else:
                clean += 1
    print(f'{files} files, {funcs} functions, {withj} of them carrying a jump')
    print(f'  structured with nothing left over   {clean} of {withj}')
    print(f'  jumps not placed                    {residual}')
    print(f'  statements stepped over             {lost}')
    print()
    print('  what the jumps turned into')
    for k, v in shapes.most_common():
        print(f'    {k:<12} {v}')
    if bad:
        print()
        print(f'  {len(bad)} function{"" if len(bad) == 1 else "s"} left '
              f'something behind')
        for path, name, r, l in bad[:40 if verbose else 12]:
            print(f'    {path}  {name}   {r} jump(s), {l} statement(s)')
    return 0


def _shapes(nodes):
    """Every construct in a tree, so the census says what was rebuilt."""
    for n in nodes:
        if n[0] == 'switch':
            yield 'switch'
            for _, arm in n[2]:
                yield from _shapes(arm)
            if n[3] is not None:
                yield from _shapes(n[3])
        elif n[0] == 'if':
            yield 'if/else' if n[3] else 'if'
            yield from _shapes(n[2])
            if n[3]:
                yield from _shapes(n[3])
        elif n[0] in ('while', 'dowhile'):
            yield n[0]
            yield from _shapes(n[2])
        elif n[0] == 'forever':
            yield 'while(true)'
            yield from _shapes(n[1])
        elif n[0] == 'foreach':
            yield 'foreach'
            yield from _shapes(n[4])
        elif n[0] == 'word':
            yield n[1]
        elif n[0] == 'stmt':
            pass


def cmd_api(root) -> int:
    """Every name fetched off the root table and called, with its arity."""
    defined, sites = call_sites(root)
    use = {n: collections.Counter(len(a) for _, _, a, _ in rows)
           for n, rows in sites.items()}
    rows = sorted(use.items(), key=lambda kv: -sum(kv[1].values()))
    for name, ar in rows:
        shape = ' '.join('%d(%d)' % (n, c) for n, c in sorted(ar.items()))
        mark = ' *' if defined[name] else ''
        print('  %6d  %-36s args %s%s'
              % (sum(ar.values()), name, shape, mark))
    native = sum(1 for n, _ in rows if not defined[n])
    print('%d names called on the root table, %d of them defined by no `.psq` '
          '(* marks the ones that are)' % (len(rows), native))
    return 0


def text_arg(a: str):
    """The string a rendered argument is, or None if it is not one."""
    return a[1:-1] if a[:1] == "'" and a[-1:] == "'" else None


def cmd_xref(root) -> int:
    """Do the names the scripts pass around name anything on the disc?"""
    import stage as stagemod                                  # noqa: PLC0415
    marker, line = {}, {}
    for st in stagemod.stages(root):
        marker[st.name] = set(m.name for m in st.markers)
        line[st.name] = set(pl.name.lower() for pl in st.lines)
    calls = call_sites(root)[1]
    here = re.compile(r'/(\d{3}_\d{2}_\d{2})')

    def run(name, resolve):
        hit = miss = skip = 0
        for path, _, args, _ in calls.get(name, ()):
            a = text_arg(args[0]) if args else None
            m = here.search(path)
            if a is None or not m or m.group(1) not in marker:
                skip += 1
                continue
            ok = resolve(a, m.group(1))
            hit += ok
            miss += not ok
        print('  %-24s %5d resolve, %4d do not, %4d not testable'
              % (name, hit, miss, skip))

    run('cfSetEnableHitArea', lambda a, s: a in marker[s])
    run('cfGetPosInHta', lambda a, s: a in marker[s])
    run('getCharacter', lambda a, s: 'pos_' + a in marker[s])
    run('cfSetEnableEmGen',
        lambda a, s: a in marker[s] or a.replace('emgen', 'emgen_pos', 1)
        in marker[s])
    run('cfSetEnableBorderline', lambda a, s: a.lower() in line[s])

    hit = miss = skip = 0
    for path, _, args, _ in calls.get('cfMapJump', ()):
        a = [t for t in (text_arg(x) for x in args) if t]
        if len(a) < 2:
            skip += 1
            continue
        ok = a[0] in marker and a[1] in marker[a[0]]
        hit += ok
        miss += not ok
    print('  %-24s %5d resolve, %4d do not, %4d not testable'
          % ('cfMapJump', hit, miss, skip))

    defined = collections.defaultdict(set)
    for path, blob in collect(root):
        m = here.search(path)
        if m:
            for f in Psq(blob, path).functions():
                defined[m.group(1)].add(f.name)
    hit = miss = 0
    for st in stagemod.stages(root):
        for t in st.triggers:
            m = re.match(r'callQuestScript\("([A-Za-z_0-9]+)', t.script or '')
            if not m:
                continue
            ok = m.group(1) in defined.get(st.name, ())
            hit += ok
            miss += not ok
    print('  %-24s %5d resolve, %4d do not'
          % ('trg callQuestScript', hit, miss))
    cmd_sound(root, calls)
    return cmd_text(root, calls)


TALK = ('talk', 'talk_open', 'talk_auto')


def cmd_text(root, calls=None) -> int:
    """Do the two arguments of a `talk` name a message and a speaker?"""
    import rmsg                                                # noqa: PLC0415
    msg = {}
    for path, blob in rmsg.collect(pathlib.Path(root)):
        for want in ('msg_npc_talk.bin', 'msg_npc.bin'):
            if path.endswith(want):
                msg[want] = rmsg.Rmsg(blob, path).texts
    calls = calls if calls is not None else call_sites(root)[1]

    for pos, want, what in ((1, 'msg_npc_talk.bin', 'name a message'),
                            (0, 'msg_npc.bin', 'name a speaker')):
        hit = miss = skip = 0
        for name in TALK:
            for _, _, args, _ in calls.get(name, ()):
                if len(args) <= pos or not args[pos].lstrip('-').isdigit():
                    skip += 1
                    continue
                ok = 0 <= int(args[pos]) < len(msg[want])
                hit += ok
                miss += not ok
        print('  %-24s %5d %s, %4d do not, %4d not testable   %s'
              % ('talk arg%d' % pos, hit, what, miss, skip, want))

    # The stage scripts are named after who speaks in them - `No11000.psq` is
    # Norn's - so the speaker id can be checked against the file name.
    who = re.compile(r'/([A-Z][a-z])\d{4,5}\.psq$')
    seen = collections.defaultdict(collections.Counter)
    for name in TALK:
        for path, _, args, _ in calls.get(name, ()):
            m = who.search(path)
            if m and args and args[0].isdigit():
                seen[m.group(1)][int(args[0])] += 1
    hit = tot = 0
    for tag, c in sorted(seen.items()):
        top, n = c.most_common(1)[0]
        hit += n
        tot += sum(c.values())
        print('     %-3s %-14s %4d of %-4d' % (tag, msg['msg_npc.bin'][top],
                                               n, sum(c.values())))
    print('  %-24s %5d of %d lines, over %d file prefixes'
          % ('talk speaker vs file', hit, tot, len(seen)))
    return cmd_motion(root)


CHR_DECL = re.compile(r"^(?:local )?(\w+) = getCharacter\('([^']+)'\)")
CHR_LIT = re.compile(r"^getCharacter\('([^']+)'\)$")


def cmd_motion(root) -> int:
    """Does a motion id name a `.CNOM` of the character it is played on?

    `npc.bin` gives every character a model pac, and every animation in that
    pac is named `n<model><id><what it is>` - `n16015talk.CNOM` is NPC 16's
    motion 15, and it is a talk.
    """
    from ech import Ech                                        # noqa: PLC0415
    pac, mot = {}, collections.defaultdict(set)
    for path, blob in walk(root):
        if path.endswith('param.pac/npc.bin'):
            e = Ech(blob, path)

            def text(o, pool=e.pool):
                return pool[o:pool.index(b'\0', o)].decode('ascii', 'replace')

            for i in range(e.rows):
                r = e.row(i)
                pac[text(int.from_bytes(r[4:8], 'big'))] = \
                    text(int.from_bytes(r[8:12], 'big'))
        m = re.search(r'/(npc_\d+\.pac)/n\d\d(\d\d\d)\w*\.CNOM$', path)
        if m:
            mot[m.group(1)].add(int(m.group(2)))

    hit = miss = skip = 0
    bad = collections.Counter()
    for path, blob in collect(root):
        for f in Psq(blob, path).functions():
            t = Trace(f).run()
            who = {}
            for pc, txt in t.note.items():
                m = CHR_DECL.match(txt)
                if m:
                    who[m.group(1)] = m.group(2)
            for pc, callee, args in t.calls:
                if callee not in ('chrSetMotion', 'chrSetMotionNPC') \
                        or len(args) < 2:
                    continue
                m = CHR_LIT.match(args[0])
                ids = mot.get(pac.get(m.group(1) if m else who.get(args[0])))
                if not ids or not args[1].isdigit():
                    skip += 1
                    continue
                ok = int(args[1]) in ids
                hit += ok
                miss += not ok
                if not ok:
                    bad[int(args[1])] += 1
    print('  %-24s %5d name a motion of that character, %4d do not, '
          '%4d not testable' % ('chrSetMotion[NPC]', hit, miss, skip))
    print('     the ids that do not: %s'
          % ' '.join('%d(%d)' % kv for kv in bad.most_common()))
    return 0


BANKS = {'bgm': 'sound.cpk/bgm.acb', 'common': 'sound.cpk/common.acb',
         'vnpc': 'sound.cpk/en/vnpc.acb'}
SPELT = {'SILON': 'SHILLON', 'OTTAL': 'OTTAR', 'TERING': 'TELLING',
         'KAFRA': 'UNDEADKAFLA'}


def cmd_sound(root, calls=None) -> int:
    """Do the cue ids the scripts pass name a cue in the bank they must?"""
    import awb                                                 # noqa: PLC0415
    want = set(BANKS.values())
    blobs = {p: b for p, b in leaves(pathlib.Path(root)) if p in want} \
        if any(p.is_file() for p in pathlib.Path(root).glob('*.cpk')) \
        else {r: (pathlib.Path(root) / r).read_bytes() for r in want}
    cue = {}
    for tag, rel in BANKS.items():
        bank = awb.Bank(blobs[rel], rel)
        cue[tag] = {r['CueId']: bank.names.get(i, '?')
                    for i, r in enumerate(bank.cues)}
    calls = calls if calls is not None else call_sites(root)[1]

    def run(name, pos, tag):
        hit = miss = skip = 0
        for _, _, args, _ in calls.get(name, ()):
            if len(args) <= pos or not args[pos].lstrip('-').isdigit():
                skip += 1
                continue
            ok = int(args[pos]) in cue[tag]
            hit += ok
            miss += not ok
        print('  %-24s %5d resolve, %4d do not, %4d not testable   %s'
              % (name, hit, miss, skip, BANKS[tag]))

    run('cfSndPlayBGM', 1, 'bgm')
    run('cfSndPlayStgBGMOW', 1, 'bgm')
    run('cfSndPlayCmnSE', 1, 'common')
    run('cfSndPlayVoiceNPC', 0, 'vnpc')

    # `chrPlayVoice` says more than that: the cue should carry the name of
    # the character the script hands it.
    decl = re.compile(r"^(?:local )?(\w+) = getCharacter\('([^']+)'\)")
    lit = re.compile(r"^getCharacter\('([^']+)'\)$")
    hit = miss = skip = 0
    for path, blob in collect(root):
        for f in Psq(blob, path).functions():
            t = Trace(f).run()
            who = {}
            for pc, txt in t.note.items():
                m = decl.match(txt)
                if m:
                    who[m.group(1)] = m.group(2)
            for pc, callee, args in t.calls:
                if callee != 'chrPlayVoice' or len(args) != 2:
                    continue
                m = lit.match(args[0])
                actor = m.group(1) if m else who.get(args[0])
                if actor is None or not args[1].isdigit():
                    skip += 1
                    continue
                key = re.sub(r'^(NPC|DEMO|HIRO)_', '', actor).upper()
                name = cue['vnpc'].get(int(args[1]), '')
                ok = name.startswith('VC_' + SPELT.get(key, key))
                hit += ok
                miss += not ok
    print('  %-24s %5d name the speaker, %4d do not, %4d not testable'
          % ('chrPlayVoice', hit, miss, skip))
    return 0


CONST = re.compile(r"^(?:-?\d+|-?\d*\.\d+(?:e[-+]?\d+)?|'.*'|true|false|null)$",
                   re.S)
BOUND = re.compile(r'^(?:local )?([A-Za-z_]\w*) = ')


def call_sites(root):
    """Every call the disc makes, with its arguments as the source wrote them.

    `Trace` already turns registers back into expressions, so an argument
    comes out either as a constant - `3`, `0.5`, `'emgen01'` - or as the
    expression that produced it. What the result is bound to is read off the
    same trace: `localvarinfos` gives the author's own name for it.
    """
    defined, sites = collections.Counter(), collections.defaultdict(list)
    for path, blob in collect(root):
        for f in Psq(blob, path).functions():
            defined[f.name] += 1
            t = Trace(f).run()
            for pc, callee, args in t.calls:
                m = BOUND.match(t.note.get(pc, ''))
                sites[callee].append((path, f.name, args,
                                      m.group(1) if m else None))
    return defined, sites


def cmd_calls(root, pattern='*') -> int:
    """What each name is handed, and what the callers call the answer."""
    defined, sites = call_sites(root)
    names = [n for n in sites if fnmatch.fnmatch(n, pattern)]
    for name in sorted(names, key=lambda n: -len(sites[n])):
        rows = sites[name]
        ar = collections.Counter(len(a) for _, _, a, _ in rows)
        print('%s  %d calls  arity %s%s'
              % (name, len(rows),
                 ' '.join('%d(%d)' % kv for kv in sorted(ar.items())),
                 '   [script]' if defined[name] else ''))
        for i in range(max(ar, default=0)):
            vals = [a[i] for _, _, a, _ in rows if len(a) > i]
            const = collections.Counter(v for v in vals if CONST.match(v))
            var = len(vals) - sum(const.values())
            show = ' '.join('%s(%d)' % (v, n) for v, n in const.most_common(8))
            print('    arg%-2d %4d  %s%s'
                  % (i, len(vals), show,
                     ('  ..%d expr' % var) if var else ''))
        got = collections.Counter(b for _, _, _, b in rows if b)
        if got:
            print('    -> %s' % ' '.join('%s(%d)' % (v, n)
                                         for v, n in got.most_common(8)))
        where = collections.Counter(p.split('/')[0] for p, _, _, _ in rows)
        print('    in %s' % ' '.join('%s(%d)' % (v, n)
                                     for v, n in where.most_common(6)))
    print('%d names' % len(names))
    return 0


def cmd_sites(root, pattern, limit=40) -> int:
    """The call sites themselves, one line each."""
    _, sites = call_sites(root)
    for name in sorted(n for n in sites if fnmatch.fnmatch(n, pattern)):
        rows = sites[name]
        print('%s  %d calls' % (name, len(rows)))
        seen = set()
        for path, fn, args, bound in rows:
            line = '%s%s(%s)' % ('%s = ' % bound if bound else '',
                                 name, ', '.join(args))
            if line in seen:
                continue
            seen.add(line)
            print('  %-70s  %s  %s' % (line[:70], fn, path))
            if len(seen) >= limit:
                print('  ... first %d distinct of %d calls'
                      % (limit, len(rows)))
                break
    return 0


def cmd_names(root) -> int:
    c = collections.Counter()
    for path, blob in collect(root):
        for f in Psq(blob, path).functions():
            for v in f.lit:
                c[v] += 1
    for v, n in c.most_common():
        print('  %6d  %r' % (n, v))
    print('%d distinct literals' % len(c))
    return 0


def cmd_ops(root) -> int:
    c = collections.Counter()
    for path, blob in collect(root):
        for f in Psq(blob, path).functions():
            for _, w in f.code:
                c[w >> 24] += 1
    for op in sorted(c):
        print('  %#04x  %-12s %8d' % (op, OPS.get(op, '?'), c[op]))
    print('%d of %d opcodes used, %d instructions'
          % (len(c), len(OPS), sum(c.values())))
    return 0


def cmd_find(root, pattern) -> int:
    n = 0
    for path, blob in collect(root):
        if fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern) \
                or fnmatch.fnmatch(path, pattern):
            fs = Psq(blob, path).functions()
            n += 1
            print('  %6d ins %3d fn  %s'
                  % (sum(len(f.code) for f in fs), len(fs), path))
    print('%d match' % n)
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'list':
        return cmd_list(rest[0])
    if cmd == 'dump':
        return cmd_dump(rest[0], rest[1])
    if cmd == 'src':
        return cmd_dump(rest[0], rest[1], True)
    if cmd == 'struct':
        return cmd_struct(rest[0], len(rest) > 1)
    if cmd == 'xref':
        return cmd_xref(rest[0])
    if cmd == 'api':
        return cmd_api(rest[0])
    if cmd == 'calls':
        return cmd_calls(rest[0], rest[1] if len(rest) > 1 else '*')
    if cmd == 'sites':
        return cmd_sites(rest[0], rest[1],
                         int(rest[2]) if len(rest) > 2 else 40)
    if cmd == 'names':
        return cmd_names(rest[0])
    if cmd == 'ops':
        return cmd_ops(rest[0])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
