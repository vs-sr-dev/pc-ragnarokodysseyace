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

`api` separates the two halves of the vocabulary: 453 names are called on the
root table, 164 of them are defined by a `.psq` and **289 are not, so those
289 are the engine's own script interface** - the host functions a
reimplementation has to provide. 119 of them begin `cf`.

Usage:
  python psq.py check <dir>               parse every file, exact consumption
  python psq.py list <dir>                every file, most instructions first
  python psq.py dump <dir> <name>         one file, annotated disassembly
  python psq.py src <dir> <name>          one file, reconstructed statements
  python psq.py api <dir>                 every global called, with arities
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
    if op in (0x0A, 0x1D, 0x23, 0x25, 0x27, 0x2D, 0x2E, 0x2F, 0x36, 0x37):
        return {a1}
    if op in (0x0B, 0x0D, 0x3C):
        return {a1, a2, a3}
    if op in (0x0C, 0x0E, 0x11, 0x12, 0x24, 0x26, 0x28, 0x35):
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


def live(f, pc: int, reg: int) -> bool:
    """Is `reg` read after `pc` before anything overwrites it?"""
    for j in range(pc + 1, len(f.code)):
        a1, w = f.code[j]
        if reg in reads(a1, w):
            return True
        op, a0, a2, _ = fields(w)
        if op in JUMPS:
            return True                        # control flow: assume it is
        if op in (0x04, 0x17) and reg in (a0, a2):
            return False
        if op == 0x14 and a0 <= reg < a0 + a1:
            return False
        if op not in (0x0B, 0x0D, 0x13, 0x3A) and a0 == reg:
            return False
    return False


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
        self.reg = {}
        for i, name in enumerate(f.param):
            self.reg[i] = name
        self.note = {}                          # pc -> statement
        self.targets = set()
        # A local becomes live one instruction after the one that fills it,
        # so `start_op` names the register write that declares it.
        self.declare = {}                       # (pc, register) -> name
        self.scope = {}                         # register -> (name, last pc)
        for name, pos, start, end in f.local:
            if pos >= len(f.param):
                self.declare[(start - 1, pos)] = (name, end)

    def r(self, i: int) -> str:
        return self.reg.get(i, 'r%d' % i)

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
                out = '%s(%s)' % (self.r(a1), ', '.join(args))
                if op == 0x05:
                    text = 'return ' + out
                elif not live(f, pc, a0):
                    text = out
            elif op == 0x07:
                self.reg[a3] = self.r(a2)
                out = '%s[%s]' % (self.r(a2), self.r(a1))
            elif op in (0x08, 0x09):
                if op == 0x08:
                    self.reg[a3] = self.r(a2)
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
                text = 'if (%s%s) goto %s' % ('!' if op == 0x2B else '',
                                              self.r(a0), self.label(pc, a1))
                out = self.r(a0)
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


# --------------------------------------------------------------------------

def collect(root, want: str = ''):
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.read_bytes()[:6] == MAGIC:
                yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, want):
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
    if f.local and not src:
        print('%s  locals %s' % (indent, ', '.join(
            'r%d=%s' % (p, n) for n, p, _, _ in reversed(f.local))))
    for pc, (a1, w) in enumerate(f.code):
        op, a0, a2, a3 = fields(w)
        if pc in t.targets:
            print('%sL%d:' % (indent, pc))
        head = ('%s  /* %d */' % (indent, ln[pc]) if pc in ln
                else indent).ljust(len(indent) + 13)
        if src:
            if pc in t.note:
                print(head + t.note[pc])
            continue
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


def cmd_api(root) -> int:
    """Every name fetched off the root table and called, with its arity."""
    use = collections.defaultdict(collections.Counter)
    defined = collections.Counter()
    for path, blob in collect(root):
        q = Psq(blob, path)
        for f in q.functions():
            defined[f.name] += 1
            pend = {}
            for a1, w in f.code:
                op, a0, a2, a3 = fields(w)
                if op == 0x08 and a2 == 0:
                    pend[a0] = key(f, a1)
                elif op == 0x06 and a1 in pend:
                    use[pend.pop(a1)][a3 - 1] += 1
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


def string_calls(root):
    """Every call on the root table whose arguments are literal constants."""
    out = collections.defaultdict(list)
    for path, blob in collect(root):
        for f in Psq(blob, path).functions():
            pend, regs = {}, {}
            for a1, w in f.code:
                op, a0, a2, a3 = fields(w)
                if op == 0x01:
                    regs[a0] = f.lit[a1] if a1 < len(f.lit) else None
                elif op == 0x04:
                    regs[a0] = f.lit[a1] if a1 < len(f.lit) else None
                    regs[a2] = f.lit[a3] if a3 < len(f.lit) else None
                elif op == 0x08 and a2 == 0:
                    pend[a0] = key(f, a1)
                elif op == 0x06:
                    if a1 in pend:
                        out[pend.pop(a1)].append(
                            (path, f.name,
                             [regs.get(i) for i in range(a2 + 1, a2 + a3)]))
                    regs.pop(a0, None)
                else:
                    regs.pop(a0, None)
    return out


def cmd_xref(root) -> int:
    """Do the names the scripts pass around name anything on the disc?"""
    import stage as stagemod                                  # noqa: PLC0415
    marker, line = {}, {}
    for st in stagemod.stages(root):
        marker[st.name] = set(m.name for m in st.markers)
        line[st.name] = set(pl.name.lower() for pl in st.lines)
    calls = string_calls(root)
    here = re.compile(r'/(\d{3}_\d{2}_\d{2})')

    def run(name, resolve):
        hit = miss = skip = 0
        for path, _, args in calls.get(name, ()):
            if not args or not isinstance(args[0], str):
                skip += 1
                continue
            m = here.search(path)
            if not m or m.group(1) not in marker:
                skip += 1
                continue
            ok = resolve(args[0], m.group(1))
            hit += ok
            miss += not ok
        print('  %-24s %5d resolve, %4d do not, %4d not testable'
              % (name, hit, miss, skip))

    run('cfSetEnableHitArea', lambda a, s: a in marker[s])
    run('cfSetEnableEmGen',
        lambda a, s: a in marker[s] or a.replace('emgen', 'emgen_pos', 1)
        in marker[s])
    run('cfSetEnableBorderline', lambda a, s: a.lower() in line[s])

    hit = miss = skip = 0
    for path, _, args in calls.get('cfMapJump', ()):
        a = [x for x in args if isinstance(x, str)]
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
    if cmd == 'xref':
        return cmd_xref(rest[0])
    if cmd == 'api':
        return cmd_api(rest[0])
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
