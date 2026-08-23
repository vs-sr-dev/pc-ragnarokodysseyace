"""
squirrel.py - a Squirrel 2.2 virtual machine, and the protocol it suspends into.

[`format_psq.md`](../docs/format_psq.md) reads the bytecode and
[`format_api.md`](../docs/format_api.md) reads the vocabulary. This runs it.

The disc's scripts are `sq_writeclosure` output for **Squirrel 2.2** -
3,011 files, 11,232 functions - and [`../tools/psq.py`](../tools/psq.py)
already parses every one of them to the byte. What was missing was the
interpreter, so this file is the other half of that reader: it takes a
`psq.Function` and executes it.

    python engine/squirrel.py run   extract/tree <psq> [function [args]]
    python engine/squirrel.py sweep extract/tree [glob]

`run` loads one script and calls a function in it, printing every host call it
makes. `sweep` is the measurement: it loads **every** `.psq` on the disc, calls
**every** function each one puts on the table with the host stubbed, and
reports what the VM could not do and which opcodes it actually retired.

## What is implemented, and why that is the whole language here

Squirrel 2.2 has 61 opcodes. The disc emits **41**; this implements **48** -
those plus `LINE`, `BITW`, `LOADROOT`, `NEWTABLE`, `INC`, `EXISTS` and `NOT`,
which cost a line each and are the obvious neighbours of things the disc does
emit.

The **13** it raises on are the ones nothing here could reach: `LOADFREEVAR`
(no function on the disc captures a free variable), `YIELD` and `RESUME`
(`_bgenerator` is 0 on all 11,232), `PUSHTRAP`, `POPTRAP` and `THROW` (no
`try`), `DELETE`, `DELEGATE`, `GETPARENT`, `INSTANCEOF`, `BWNOT`, `CLONE` and
`TYPEOF`. Raising rather than ignoring is deliberate: a silent no-op would
make the sweep's zero meaningless.

The standard library is the same shape. The whole disc calls exactly four
methods on a receiver - `tointeger` 94 times, `setVolumeCategory` three,
`Print` once, and one `constructor` - so the default delegates are four lines
rather than a library. Squirrel's own globals in use are `print`, `suspend`,
`array`, `getroottable` and `getconsttable`, which is the list
[`format_api.md`](../docs/format_api.md) subtracts to get 285.

## The two decisions the disc does not make for us

**Unqualified names fall back to the root table.** Squirrel 2.2's `SQVM::Get`
takes the *register index* of the receiver and, when it is 0 - which is
`this` - retries the lookup against the root table before failing. That is
what makes `cfMapJump(...)` in a stage script find a host function it never
imported, and it is why one shared root table is enough: `main()` runs with
`this` = the root table, its `<-` slots land there, and every later call
finds them. It is reproduced here rather than invented.

**A suspend unwinds to the host and keeps its frames.** `suspend(n)` is
Squirrel's `sq_suspendvm`: the whole call stack stays where it is, the host
gets the number, and `resume(value)` puts the value in the register the call
was going to write and carries on. Every blocking thing in this game - a talk
line, a shop, a wait - is written that way, so the host is a scheduler over
threads that are somewhere inside a script. See `Thread`.

## Numbers

`SQInteger` is 32-bit on this build: `_OP_LOADINT` carries its value in the
instruction's own `s32` field, and integer division truncates toward zero the
way C does. Arithmetic promotes to float when either side is a float, `+`
concatenates when either side is a string, and nothing else coerces.
"""
from __future__ import annotations

import collections
import fnmatch
import math
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

from psq import Psq, collect, fields, sbyte, signed           # noqa: E402

MAXREG = 0xFF                      # MAX_FUNC_STACKSIZE: "no target register"
INT_MIN, INT_MAX = -0x80000000, 0x7FFFFFFF


class SquirrelError(Exception):
    """A script-level error: the VM is fine, the script asked for something
    the language does not allow. Squirrel would call `Raise_Error`."""


class VMError(Exception):
    """The VM could not do something. Every one of these is a bug here, and
    `sweep` counts them separately for that reason."""


# -- the object model ------------------------------------------------------
#
# null is None, integers and floats and strings and bools are Python's. The
# rest are these.


class Table:
    __slots__ = ('slots', 'delegate')

    def __init__(self, slots=None):
        self.slots = dict(slots or {})
        self.delegate = None

    def get(self, key):
        t = self
        while t is not None:
            if key in t.slots:
                return True, t.slots[key]
            t = t.delegate
        return False, None

    def set(self, key, value) -> bool:
        """`=` only writes a slot that exists; `<-` is what creates one."""
        t = self
        while t is not None:
            if key in t.slots:
                t.slots[key] = value
                return True
            t = t.delegate
        return False

    def __repr__(self):
        return '(table: %d slots)' % len(self.slots)


class Array:
    __slots__ = ('items',)

    def __init__(self, items=None):
        self.items = list(items or ())

    def __repr__(self):
        return '(array: %d)' % len(self.items)


class Closure:
    """A `SQFunctionProto` plus the default arguments bound when the
    enclosing `_OP_CLOSURE` ran - which is where Squirrel 2.2 takes them
    from, off the *creating* frame's registers."""

    __slots__ = ('proto', 'defaults')

    def __init__(self, proto, defaults=()):
        self.proto = proto
        self.defaults = list(defaults)

    @property
    def name(self):
        return self.proto.name

    def __repr__(self):
        return '(function %s)' % (self.proto.name or '#anonymous')


class Native:
    """A host function. `fn(*args)` - the receiver is not passed, because
    every one of the 285 is called on the root table."""

    __slots__ = ('name', 'fn')

    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    def __repr__(self):
        return '(native %s)' % self.name


class Class:
    __slots__ = ('members', 'base')

    def __init__(self, base=None):
        self.members = {}
        self.base = base

    def get(self, key):
        c = self
        while c is not None:
            if key in c.members:
                return True, c.members[key]
            c = c.base
        return False, None


class Instance:
    __slots__ = ('cls', 'fields')

    def __init__(self, cls):
        self.cls = cls
        self.fields = {}
        c, chain = cls, []
        while c is not None:
            chain.append(c)
            c = c.base
        for c in reversed(chain):               # a subclass overrides its base
            for k, v in c.members.items():
                if not isinstance(v, Closure):
                    self.fields[k] = v

    def get(self, key):
        if key in self.fields:
            return True, self.fields[key]
        return self.cls.get(key)

    def __repr__(self):
        return '(instance)'


class Suspend:
    """What a native returns to stop the thread. `suspend(n)` makes one."""

    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value


# -- values ----------------------------------------------------------------


def is_false(v) -> bool:
    """`IsFalse`: null, false, 0 and 0.0. A string is true however empty."""
    if v is None or v is False:
        return True
    if v is True:
        return False
    return isinstance(v, (int, float)) and v == 0


def type_name(v) -> str:
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'bool'
    if isinstance(v, int):
        return 'integer'
    if isinstance(v, float):
        return 'float'
    if isinstance(v, str):
        return 'string'
    if isinstance(v, Array):
        return 'array'
    if isinstance(v, Table):
        return 'table'
    if isinstance(v, (Closure, Native)):
        return 'function'
    if isinstance(v, Class):
        return 'class'
    if isinstance(v, Instance):
        return 'instance'
    return 'unknown'


def to_string(v) -> str:
    if v is None:
        return '(null)'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, float):
        return '%g' % v
    if isinstance(v, str):
        return v
    return repr(v)


def wrap_int(n: int) -> int:
    """32-bit `SQInteger`, which is what `_OP_LOADINT` says this build has."""
    n &= 0xFFFFFFFF
    return n - 0x100000000 if n > INT_MAX else n


def numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def arith(op: str, a, b):
    if op == '+' and (isinstance(a, str) or isinstance(b, str)):
        return to_string(a) + to_string(b)
    if not numeric(a) or not numeric(b):
        raise SquirrelError('arith %s on %s and %s'
                            % (op, type_name(a), type_name(b)))
    both_int = isinstance(a, int) and isinstance(b, int)
    if op == '+':
        r = a + b
    elif op == '-':
        r = a - b
    elif op == '*':
        r = a * b
    elif op == '/':
        if b == 0:
            if both_int:
                raise SquirrelError('integer divide by zero')
            return float('nan') if a == 0 else float('inf') * (1 if a > 0 else -1)
        r = a / b
        if both_int:                            # C truncation, not floor
            r = int(a / b)
    elif op == '%':
        if b == 0:
            raise SquirrelError('modulo by zero')
        r = (abs(a) % abs(b)) * (1 if a >= 0 else -1) if both_int else \
            math.fmod(float(a), float(b))
    else:
        raise VMError('unknown arithmetic operator %r' % op)
    return wrap_int(r) if both_int else float(r)


def bitwise(op: int, a, b):
    if not isinstance(a, int) or not isinstance(b, int) \
            or isinstance(a, bool) or isinstance(b, bool):
        raise SquirrelError('bitwise op on %s and %s'
                            % (type_name(a), type_name(b)))
    if op == 0:
        return wrap_int(a & b)
    if op == 1:
        return wrap_int(a | b)
    if op == 2:
        return wrap_int(a ^ b)
    if op == 3:
        return wrap_int(a << (b & 31))
    if op == 4:
        return wrap_int(a >> (b & 31))
    if op == 5:
        return wrap_int((a & 0xFFFFFFFF) >> (b & 31))
    raise VMError('unknown bitwise operator %d' % op)


def equal(a, b) -> bool:
    if numeric(a) and numeric(b):
        return a == b
    if type_name(a) != type_name(b):
        return False
    if isinstance(a, (str, bool)) or a is None:
        return a == b
    return a is b


def compare(a, b) -> int:
    if numeric(a) and numeric(b):
        return (a > b) - (a < b)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    if a is None and b is None:
        return 0
    raise SquirrelError('cannot compare %s with %s'
                        % (type_name(a), type_name(b)))


# -- the call stack --------------------------------------------------------


class Frame:
    __slots__ = ('closure', 'ip', 'base', 'target', 'root', 'vargs')

    def __init__(self, closure, base, target, root):
        self.closure = closure
        self.ip = 0
        self.base = base
        self.target = target                    # absolute register, or -1
        self.root = root                        # did the host start this one?
        self.vargs = []


class Thread:
    """One script in flight. It is either running, done, or stopped inside a
    `suspend` with every frame intact - which is the only way the game's
    blocking calls can work."""

    def __init__(self, vm, name=''):
        self.vm = vm
        self.name = name
        self.stack = []
        self.frames = []
        self.state = 'idle'                     # idle done suspended error
        self.value = None                       # return value, or suspend id
        self.error = None
        self.steps = 0
        self.calls = 0
        self._wake = -1

    # -- what the host does with one ---------------------------------------

    def start(self, closure, args=(), this=None):
        if self.frames:
            raise VMError('thread %s is already running' % self.name)
        self.stack = []
        base = 0
        self._need(base + 1 + len(args))
        self.stack[base] = self.vm.root if this is None else this
        for i, a in enumerate(args):
            self.stack[base + 1 + i] = a
        self._enter(closure, target=-1, nargs=1 + len(args), base=base,
                    root=True)
        return self.run()

    def resume(self, value=None):
        if self.state != 'suspended':
            raise VMError('thread %s is %s, not suspended'
                          % (self.name, self.state))
        if self._wake >= 0:
            self.stack[self._wake] = value
        self.state = 'running'
        return self.run()

    # -- the machine -------------------------------------------------------

    def _need(self, n):
        if len(self.stack) < n:
            self.stack.extend([None] * (n - len(self.stack)))

    def _top(self):
        if not self.frames:
            return 0
        f = self.frames[-1]
        return f.base + f.closure.proto.stack

    def _enter(self, closure, target, nargs, base, root=False, tail=False):
        p = closure.proto
        nparams = len(p.param)
        if p.varparams:
            # Every declared parameter keeps its register and only the
            # surplus goes to `vargv`. Squirrel's later versions add a
            # `vargv` parameter and step back over it; this build does not,
            # and the disc settles it - see `prt_select` in the boss AI,
            # whose weight column only sums to 10,000 under this reading.
            if nargs < nparams:
                raise SquirrelError('%s: wrong number of parameters' % p.name)
            frame_vargs = self.stack[base + nparams:base + nargs]
            for i in range(nargs - nparams):
                self.stack[base + nparams + i] = None
            nargs = nparams
        else:
            frame_vargs = []
            if nparams != nargs:
                ndef = len(closure.defaults)
                diff = nparams - nargs
                if ndef and 0 < diff <= ndef:
                    self._need(base + nparams)
                    for n in range(ndef - diff, ndef):
                        self.stack[base + nargs] = closure.defaults[n]
                        nargs += 1
                else:
                    raise SquirrelError(
                        '%s: wrong number of parameters (%d given, %d wanted)'
                        % (p.name or '?', nargs, nparams))
        self._need(base + p.stack)
        for i in range(base + nargs, base + p.stack):
            self.stack[i] = None
        if tail:
            f = self.frames[-1]
            f.closure, f.ip, f.vargs = closure, 0, frame_vargs
        else:
            f = Frame(closure, base, target, root)
            f.vargs = frame_vargs
            self.frames.append(f)
        self.calls += 1

    def _leave(self, retval):
        """Pop a frame. True when the host gets control back."""
        f = self.frames.pop()
        if f.root:
            self.state = 'done'
            self.value = retval
            return True
        if f.target >= 0:
            self.stack[f.target] = retval
        return False

    def _get(self, obj, key, selfidx):
        """`SQVM::Get`. `selfidx` is the register the receiver came out of,
        and 0 - which is `this` - is what makes the root table a fallback."""
        if isinstance(obj, Table):
            ok, v = obj.get(key)
            if ok:
                return v
        elif isinstance(obj, Array):
            if numeric(key):
                i = int(key)
                if -len(obj.items) <= i < len(obj.items):
                    return obj.items[i]
                raise SquirrelError('index %s out of range' % key)
        elif isinstance(obj, Instance):
            ok, v = obj.get(key)
            if ok:
                return v
        elif isinstance(obj, Class):
            ok, v = obj.get(key)
            if ok:
                return v
        ok, v = self.vm.delegate(obj, key)
        if ok:
            return v
        if selfidx == 0:
            ok, v = self.vm.root.get(key)
            if ok:
                return v
        raise SquirrelError("the index '%s' does not exist" % to_string(key))

    def _set(self, obj, key, value):
        if isinstance(obj, Table):
            if obj.set(key, value):
                return
            raise SquirrelError("the index '%s' does not exist"
                                % to_string(key))
        if isinstance(obj, Array):
            if not numeric(key):
                raise SquirrelError('array index is a %s' % type_name(key))
            i = int(key)
            if not -len(obj.items) <= i < len(obj.items):
                raise SquirrelError('index %s out of range' % key)
            obj.items[i] = value
            return
        if isinstance(obj, Instance):
            if key in obj.fields:
                obj.fields[key] = value
                return
            raise SquirrelError("the index '%s' does not exist"
                                % to_string(key))
        raise SquirrelError('cannot assign into a %s' % type_name(obj))

    def _newslot(self, obj, key, value):
        if isinstance(obj, Table):
            obj.slots[key] = value
        elif isinstance(obj, Class):
            obj.members[key] = value
        elif isinstance(obj, Instance):
            obj.fields[key] = value
        else:
            raise SquirrelError('cannot create a slot in a %s'
                                % type_name(obj))

    def _call(self, callee, target, nargs, base):
        """A call whose arguments are already at `base`. True when the VM
        should return to the host."""
        if isinstance(callee, Closure):
            self._enter(callee, target, nargs, base)
            return False
        if isinstance(callee, Native):
            args = self.stack[base + 1:base + nargs]
            self.vm.native_calls += 1
            r = callee.fn(*args)
            if isinstance(r, Suspend):
                self.state = 'suspended'
                self.value = r.value
                self._wake = target
                return True
            if target >= 0:
                self.stack[target] = r
            return False
        if isinstance(callee, Class):
            inst = Instance(callee)
            if target >= 0:         # the call yields the instance, not what
                self.stack[target] = inst      # the constructor returns, and
            ok, ctor = callee.get('constructor')   # the target register sits
            if ok and isinstance(ctor, Closure):   # below the call area, so
                self.stack[base] = inst            # writing it now is safe
                self._enter(ctor, -1, nargs, base)
            return False
        raise SquirrelError('attempt to call a %s' % type_name(callee))

    def run(self, budget=2_000_000):
        self.state = 'running'
        try:
            return self._loop(budget)
        except SquirrelError as e:
            self.state = 'error'
            self.error = e
            raise

    def _loop(self, budget):
        stack = self.stack
        count = self.vm.opcount
        while self.frames:
            f = self.frames[-1]
            code = f.closure.proto.code
            base = f.base
            lit = f.closure.proto.lit
            while True:
                if f.ip >= len(code):
                    raise VMError('%s: ran off the end of the function'
                                  % f.closure.proto.name)
                a1, w = code[f.ip]
                f.ip += 1
                self.steps += 1
                if count is not None:
                    count[w >> 24] += 1
                if self.steps > budget:
                    raise SquirrelError('instruction budget exhausted')
                op = w >> 24
                a0 = (w >> 16) & 0xFF
                a2 = (w >> 8) & 0xFF
                a3 = w & 0xFF
                trg = base + a0 if a0 != MAXREG else -1

                if op == 0x06 or op == 0x05:                  # CALL, TAILCALL
                    if op == 0x05:
                        callee = stack[base + a1]
                        if isinstance(callee, Closure):
                            for i in range(a3):
                                stack[base + i] = stack[base + a2 + i]
                            self._enter(callee, f.target, a3, base,
                                        root=f.root, tail=True)
                            break
                        nargs, cbase = a3, base + a2
                    else:
                        callee = stack[base + a1]
                        nargs, cbase = a3, base + a2
                    if self._call(callee, trg, nargs, cbase):
                        return self.state
                    if self.frames[-1] is not f:
                        break
                    continue
                if op == 0x08:                                # PREPCALLK
                    key = lit[a1]
                    obj = stack[base + a2]
                    stack[base + a3] = obj
                    if trg >= 0:
                        stack[trg] = self._get(obj, key, a2)
                    continue
                if op == 0x02:                                # LOADINT
                    if trg >= 0:
                        stack[trg] = signed(a1)
                    continue
                if op == 0x01:                                # LOAD
                    if trg >= 0:
                        stack[trg] = lit[a1]
                    continue
                if op == 0x00:                                # LINE
                    continue
                if op == 0x1A:                                # JZ
                    if is_false(stack[base + a0]):
                        f.ip += signed(a1)
                    continue
                if op == 0x18:                                # JMP
                    f.ip += signed(a1)
                    continue
                if op == 0x13:                                # RETURN
                    r = stack[base + a1] if a0 != MAXREG else None
                    if self._leave(r):
                        return self.state
                    break
                if op == 0x0F or op == 0x10:                  # EQ, NE
                    rhs = lit[a1] if a3 else stack[base + a1]
                    r = equal(stack[base + a2], rhs)
                    if trg >= 0:
                        stack[trg] = r if op == 0x0F else not r
                    continue
                if op == 0x28:                                # CMP
                    a = stack[base + a2]
                    b = stack[base + a1]
                    c = compare(a, b)
                    if a3 == 0:
                        r = c > 0
                    elif a3 == 2:
                        r = c >= 0
                    elif a3 == 3:
                        r = c < 0
                    elif a3 == 4:
                        r = c <= 0
                    elif a3 == 5:
                        r = c
                    else:
                        raise VMError('CMP with _arg3 = %d' % a3)
                    if trg >= 0:
                        stack[trg] = r
                    continue
                if op == 0x11:                                # ARITH
                    if trg >= 0:
                        stack[trg] = arith(chr(a3), stack[base + a2],
                                           stack[base + a1])
                    continue
                if op == 0x0A:                                # MOVE
                    if trg >= 0:
                        stack[trg] = stack[base + a1]
                    continue
                if op == 0x30:                                # CLOSURE
                    proto = f.closure.proto.child[a1]
                    defaults = [stack[base + i] for i in proto.default]
                    if trg >= 0:
                        stack[trg] = Closure(proto, defaults)
                    continue
                if op == 0x0B:                                # NEWSLOT
                    v = stack[base + a3]
                    self._newslot(stack[base + a1], stack[base + a2], v)
                    if trg >= 0:
                        stack[trg] = v
                    continue
                if op == 0x03:                                # LOADFLOAT
                    if trg >= 0:
                        stack[trg] = struct.unpack('>f',
                                                   a1.to_bytes(4, 'big'))[0]
                    continue
                if op == 0x04:                                # DLOAD
                    if trg >= 0:
                        stack[trg] = lit[a1]
                    stack[base + a2] = lit[a3]
                    continue
                if op == 0x09:                                # GETK
                    if trg >= 0:
                        stack[trg] = self._get(stack[base + a2], lit[a1], a2)
                    continue
                if op == 0x07:                                # PREPCALL
                    key = stack[base + a1]
                    obj = stack[base + a2]
                    stack[base + a3] = obj
                    if trg >= 0:
                        stack[trg] = self._get(obj, key, a2)
                    continue
                if op == 0x0E:                                # GET
                    if trg >= 0:
                        stack[trg] = self._get(stack[base + a1],
                                               stack[base + a2], a1)
                    continue
                if op == 0x0D:                                # SET
                    v = stack[base + a3]
                    self._set(stack[base + a1], stack[base + a2], v)
                    if trg >= 0:
                        stack[trg] = v
                    continue
                if op == 0x2B or op == 0x2C:                  # AND, OR
                    v = stack[base + a2]
                    if is_false(v) == (op == 0x2B):
                        if trg >= 0:
                            stack[trg] = v
                        f.ip += signed(a1)
                    continue
                if op == 0x26 or op == 0x24:                  # PINC, INC
                    obj, key = stack[base + a1], stack[base + a2]
                    old = self._get(obj, key, a1)
                    new = arith('+', old, sbyte(a3))
                    self._set(obj, key, new)
                    if trg >= 0:
                        stack[trg] = old if op == 0x26 else new
                    continue
                if op == 0x27 or op == 0x25:                  # PINCL, INCL
                    old = stack[base + a1]
                    new = arith('+', old, sbyte(a3))
                    stack[base + a1] = new
                    if trg >= 0:
                        stack[trg] = old if op == 0x27 else new
                    continue
                if op == 0x2D:                                # NEG
                    v = stack[base + a1]
                    if not numeric(v):
                        raise SquirrelError('cannot negate a %s'
                                            % type_name(v))
                    if trg >= 0:
                        stack[trg] = wrap_int(-v) if isinstance(v, int) else -v
                    continue
                if op == 0x2E:                                # NOT
                    if trg >= 0:
                        stack[trg] = is_false(stack[base + a1])
                    continue
                if op == 0x16:                                # LOADBOOL
                    if trg >= 0:
                        stack[trg] = bool(a1)
                    continue
                if op == 0x14:                                # LOADNULLS
                    for i in range(a1):
                        stack[base + a0 + i] = None
                    continue
                if op == 0x15:                                # LOADROOT
                    if trg >= 0:
                        stack[trg] = self.vm.root
                    continue
                if op == 0x17:                                # DMOVE
                    if trg >= 0:
                        stack[trg] = stack[base + a1]
                    stack[base + a2] = stack[base + a3]
                    continue
                if op == 0x19:                                # JNZ
                    if not is_false(stack[base + a0]):
                        f.ip += signed(a1)
                    continue
                if op == 0x1E:                                # NEWTABLE
                    if trg >= 0:
                        stack[trg] = Table()
                    continue
                if op == 0x1F:                                # NEWARRAY
                    if trg >= 0:
                        stack[trg] = Array()
                    continue
                if op == 0x20:                                # APPENDARRAY
                    arr = stack[base + a0]
                    if not isinstance(arr, Array):
                        raise SquirrelError('append to a %s' % type_name(arr))
                    arr.items.append(lit[a1] if a3 else stack[base + a1])
                    continue
                if op == 0x12:                                # BITW
                    if trg >= 0:
                        stack[trg] = bitwise(a3, stack[base + a2],
                                             stack[base + a1])
                    continue
                if op == 0x22:                                # COMPARITH
                    obj = stack[base + ((a1 >> 16) & 0xFFFF)]
                    key = stack[base + a2]
                    old = self._get(obj, key, (a1 >> 16) & 0xFFFF)
                    new = arith(chr(a3), old, stack[base + (a1 & 0xFFFF)])
                    self._set(obj, key, new)
                    if trg >= 0:
                        stack[trg] = new
                    continue
                if op == 0x23:                                # COMPARITHL
                    new = arith(chr(a3), stack[base + a1], stack[base + a2])
                    stack[base + a1] = new
                    if trg >= 0:
                        stack[trg] = new
                    continue
                if op == 0x1C:                                # VARGC
                    if trg >= 0:
                        stack[trg] = len(f.vargs)
                    continue
                if op == 0x1D:                                # GETVARGV
                    i = stack[base + a1]
                    if not numeric(i) or not 0 <= int(i) < len(f.vargs):
                        raise SquirrelError('vargv index %s' % to_string(i))
                    if trg >= 0:
                        stack[trg] = f.vargs[int(i)]
                    continue
                if op == 0x33:                                # FOREACH
                    jump = self._foreach(stack, base, a0, a2, signed(a1))
                    f.ip += jump
                    continue
                if op == 0x34:                                # POSTFOREACH
                    continue                    # generators only; none here
                if op == 0x29:                                # EXISTS
                    obj, key = stack[base + a1], stack[base + a2]
                    try:
                        self._get(obj, key, -1)
                        found = True
                    except SquirrelError:
                        found = False
                    if trg >= 0:
                        stack[trg] = found
                    continue
                if op == 0x3B:                                # CLASS
                    base_cls = stack[base + a1] if signed(a1) >= 0 else None
                    if base_cls is not None and not isinstance(base_cls, Class):
                        raise SquirrelError('cannot inherit from a %s'
                                            % type_name(base_cls))
                    if trg >= 0:
                        stack[trg] = Class(base_cls)
                    continue
                if op == 0x3C:                                # NEWSLOTA
                    self._newslot(stack[base + a1], stack[base + a2],
                                  stack[base + a3])
                    continue
                raise VMError('opcode %#04x is not implemented (%s at %d)'
                              % (op, f.closure.proto.name, f.ip - 1))
        self.state = 'done'
        return self.state

    def _foreach(self, stack, base, a0, a2, exitpos):
        """`FOREACH_OP` for the two containers the disc iterates. Returns the
        jump: 1 steps over the `POSTFOREACH` that follows, `exitpos` leaves."""
        obj = stack[base + a0]
        idx = stack[base + a2 + 2]
        i = 0 if idx is None else int(idx) + 1
        if isinstance(obj, Array):
            if i >= len(obj.items):
                return exitpos
            stack[base + a2] = i
            stack[base + a2 + 1] = obj.items[i]
        elif isinstance(obj, Table):
            keys = list(obj.slots.keys())
            if i >= len(keys):
                return exitpos
            stack[base + a2] = keys[i]
            stack[base + a2 + 1] = obj.slots[keys[i]]
        elif isinstance(obj, str):
            if i >= len(obj):
                return exitpos
            stack[base + a2] = i
            stack[base + a2 + 1] = ord(obj[i])
        else:
            raise SquirrelError('cannot iterate a %s' % type_name(obj))
        stack[base + a2 + 2] = i
        return 1


# -- the VM ----------------------------------------------------------------


class VM:
    """One root table, the host functions on it, and the threads that run
    against it."""

    def __init__(self, printer=None):
        self.root = Table()
        self.consts = Table()
        self.printer = printer or (lambda s: sys.stdout.write(s))
        self.native_calls = 0
        self.opcount = None                     # a Counter, when measuring
        self.threads = []
        self.owner = {}                         # name -> the file that defined it
        self.collisions = []                    # (name, first file, second)
        self._base_library()

    # -- Squirrel's own ----------------------------------------------------

    def _base_library(self):
        self.register('print', lambda s=None: self.printer(to_string(s)))
        self.register('suspend', lambda v=None: Suspend(v))
        self.register('array', lambda n, fill=None:
                      Array([fill] * int(n)))
        self.register('getroottable', lambda: self.root)
        self.register('getconsttable', lambda: self.consts)

    def delegate(self, obj, key):
        """The default delegates. The whole disc calls four methods on a
        receiver and one of them is this."""
        if key == 'tointeger' and numeric(obj):
            return True, Native('tointeger', lambda o=obj: int(o))
        if key == 'tofloat' and numeric(obj):
            return True, Native('tofloat', lambda o=obj: float(o))
        if key == 'tostring':
            return True, Native('tostring', lambda o=obj: to_string(o))
        if key == 'len':
            if isinstance(obj, Array):
                return True, Native('len', lambda o=obj: len(o.items))
            if isinstance(obj, str):
                return True, Native('len', lambda o=obj: len(o))
            if isinstance(obj, Table):
                return True, Native('len', lambda o=obj: len(o.slots))
        if key == 'append' and isinstance(obj, Array):
            return True, Native('append',
                                lambda v, o=obj: o.items.append(v))
        return False, None

    def register(self, name, fn):
        self.root.slots[name] = Native(name, fn)

    # -- loading -----------------------------------------------------------

    def load(self, proto, path='', this=None):
        """Run a script's `main()`, which is what puts its functions on the
        table. Every `.psq` on the disc is one `main` with its functions
        nested inside it.

        Two scripts that define the same name is the one thing a single
        shared root table cannot survive, so every definition is recorded
        against the file that made it and a second one is reported."""
        was = dict(self.root.slots)
        th = Thread(self, path or proto.name)
        th.start(Closure(proto), this=this)
        if th.state != 'done':
            raise VMError('%s: main() did not finish (%s)' % (path, th.state))
        for name, value in self.root.slots.items():
            if was.get(name) is value:
                continue                        # this load did not write it
            first = self.owner.get(name)
            if first is not None and first != path:
                self.collisions.append((name, first, path))
            self.owner[name] = path
        return th

    def load_file(self, blob, path=''):
        return self.load(Psq(blob, path).root, path)

    # -- calling -----------------------------------------------------------

    def find(self, name):
        ok, v = self.root.get(name)
        return v if ok else None

    def call(self, name, args=(), thread=None):
        """Call a script function by name and run it to completion or to its
        first `suspend`."""
        fn = name if isinstance(name, (Closure, Native)) else self.find(name)
        if fn is None:
            raise SquirrelError("no function named '%s'" % name)
        th = thread or Thread(self, str(name))
        th.start(fn, args)
        return th


# -- the harness -----------------------------------------------------------


class Recorder:
    """A stand-in host: every name the scripts call that nobody has bound is
    bound to this, which records the call and returns 0.

    Returning **0** rather than null is deliberate. Nearly every host function
    here answers a question with a number, and a null would turn the first
    comparison into a script error and hide everything downstream."""

    def __init__(self, vm, value=0):
        self.vm = vm
        self.value = value
        self.calls = collections.Counter()
        self.log = []

    def bind(self, names):
        for n in names:
            if n not in self.vm.root.slots:
                self.vm.register(n, self._make(n))

    def _make(self, name):
        def stub(*args):
            self.calls[name] += 1
            self.log.append((name, args))
            return self.value
        return stub


def globals_called(proto):
    """Every name this script calls on `this`, which - with the root fallback
    - is every host function it can reach.

    Two shapes, and `psq.py api` counts both: `_OP_PREPCALLK` with the
    receiver in register 0, which is an ordinary `name()`, and `_OP_PREPCALL`
    on the same register, which is `this['name']()` and is how nearly every
    quest script opens."""
    names = set()
    for f in proto.walk():
        loaded = {}                             # register -> string literal
        for a1, w in f.code:
            op, a0, a2, a3 = fields(w)
            if op == 0x01:
                v = f.lit[a1] if 0 <= a1 < len(f.lit) else None
                loaded[a0] = v if isinstance(v, str) else None
            elif op == 0x04:                    # DLOAD fills two registers,
                for reg, k in ((a0, a1), (a2, a3)):     # and `x <- this['f']()`
                    v = f.lit[k] if 0 <= k < len(f.lit) else None   # is one
                    loaded[reg] = v if isinstance(v, str) else None
            elif op == 0x08 and a2 == 0:
                if 0 <= a1 < len(f.lit) and isinstance(f.lit[a1], str):
                    names.add(f.lit[a1])
            elif op == 0x07 and a2 == 0:
                if loaded.get(a1):
                    names.add(loaded[a1])
            elif a0 != MAXREG and op not in (0x18, 0x19, 0x1A, 0x2B, 0x2C):
                loaded.pop(a0, None)
    return names


# -- commands --------------------------------------------------------------


def cmd_run(root, name, func='main', args=()) -> int:
    """Load one script and call one function in it, against a stub host."""
    path, q = _one(root, name)
    vm = VM()
    rec = Recorder(vm)
    rec.bind(globals_called(q.root))
    load = vm.load(q.root, path)
    defined = sorted(n for n, v in vm.root.slots.items()
                     if isinstance(v, Closure))
    print('%s' % path)
    print('  main(): %d instructions, %d functions defined - %s'
          % (load.steps, len(defined), ', '.join(defined)))
    if func != 'main':
        th = Thread(vm, func)
        shown = ', '.join(map(str, args))
        try:
            vm.call(func, [_arg(a) for a in args], thread=th)
            print('  %s(%s) -> %s after %d instructions [%s]'
                  % (func, shown, to_string(th.value), th.steps, th.state))
        except SquirrelError as e:
            print('  %s(%s) stopped after %d instructions: %s'
                  % (func, shown, th.steps, e))
    print('  %d host calls' % vm.native_calls)
    for n, c in rec.calls.most_common():
        shown = [to_string(a) for a in rec.log[
            [i for i, (m, _) in enumerate(rec.log) if m == n][0]][1]]
        print('    %4d  %s(%s)' % (c, n, ', '.join(shown)))
    return 0


def _arg(a: str):
    try:
        return int(a)
    except ValueError:
        pass
    try:
        return float(a)
    except ValueError:
        return a


def _one(root, name):
    """One script by path or by leaf name. The tree is 2 GB, so a path that
    is already a path is not searched for."""
    direct = pathlib.Path(root) / name
    if direct.is_file():
        return name, Psq(direct.read_bytes(), name)
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Psq(blob, path)
    raise SystemExit('not found: ' + name)


COMMON = 'misc.cpk/psq_common.pac/common.psq'


def scripts(root, want='*'):
    """Every `.psq` and `.cnut` under a tree. `psq.collect` reads every leaf
    of the 2 GB asset tree to find them, which is right for a survey and
    wrong for a loop that then runs them."""
    d = pathlib.Path(root)
    if any(p.is_file() for p in d.glob('*.cpk')):
        yield from collect(root, want)
        return
    found = sorted(list(d.rglob('*.psq')) + list(d.rglob('*.cnut')))
    for p in found:
        if fnmatch.fnmatch(p.name, want):
            yield p.relative_to(d).as_posix(), p.read_bytes()


def cmd_sweep(root, want='*') -> int:
    """Load every script and call every function it puts on the table.

    The point is not that the calls do anything - the arguments are zeros and
    the host is a stub - it is that the interpreter retires the instructions.
    A `VMError` is a hole in this file; a `SquirrelError` is the script
    objecting to what the stub handed it, which is expected and counted
    apart. `common.psq` is loaded into every VM first, because the game has
    it resident and the scripts call it as if it were the host.

    Nothing here suspends by accident: a thread that stops in a `suspend` is
    a script waiting on the host, and the count is the interface working."""
    common = None
    try:
        _, common = _one(root, COMMON)
    except SystemExit:
        pass
    files = funcs = called = 0
    steps = suspended = 0
    vm_faults = collections.Counter()
    script_errors = collections.Counter()
    ops = collections.Counter()
    static = collections.Counter()
    for path, blob in scripts(root, want):
        files += 1
        q = Psq(blob, path)
        for f in q.root.walk():
            for a1, w in f.code:
                static[w >> 24] += 1
        vm = VM(printer=lambda s: None)
        vm.opcount = ops
        rec = Recorder(vm)
        names = globals_called(q.root)
        if common is not None and path != COMMON:
            names |= globals_called(common.root)
        rec.bind(names)
        try:
            if common is not None and path != COMMON:
                vm.load(common.root, COMMON)
            vm.load(q.root, path)
        except (SquirrelError, VMError) as e:
            (vm_faults if isinstance(e, VMError) else script_errors)[
                str(e)[:60]] += 1
            continue
        entries = [(n, v) for n, v in vm.root.slots.items()
                   if isinstance(v, Closure) and vm.owner.get(n) == path]
        for name, clo in entries:
            funcs += 1
            nargs = max(0, len(clo.proto.param) - 1)
            th = Thread(vm, name)
            try:
                th.start(clo, [0] * nargs)
                called += 1
                if th.state == 'suspended':
                    suspended += 1
            except VMError as e:
                vm_faults[str(e)[:60]] += 1
            except SquirrelError as e:
                script_errors[str(e)[:60]] += 1
            except RecursionError:
                script_errors['python recursion'] += 1
            steps += th.steps
    print('%d files, %d functions on the table, %d ran to a stop, '
          '%d of them into a suspend' % (files, funcs, called, suspended))
    print('%d instructions retired, %d of the %d opcodes the disc contains'
          % (steps, len(set(ops) & set(static)), len(static)))
    missing = sorted(set(static) - set(ops))
    if missing:
        print('  never reached: %s' % ' '.join('%#04x' % o for o in missing))
    print('%d VM faults, %d script errors' % (sum(vm_faults.values()),
                                              sum(script_errors.values())))
    for e, c in vm_faults.most_common(20):
        print('  VM     %5d  %s' % (c, e))
    for e, c in script_errors.most_common(12):
        print('  script %5d  %s' % (c, e))
    return 1 if vm_faults else 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    cmd, rest = a[0], a[1:]
    if cmd == 'run' and len(rest) >= 2:
        return cmd_run(rest[0], rest[1], *(rest[2:3] or ['main']),
                       args=rest[3:])
    if cmd == 'sweep' and rest:
        return cmd_sweep(rest[0], *rest[1:2])
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
