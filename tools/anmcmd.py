"""
anmcmd.py - reader for `.anmcmd`, the animation command lists.

2,053 files, **6,802 blocks, 10,175 commands, 0 unreadable.** This is what
turns an animation into an event: a `CNOM` moves the bones, and one of these
says what happens on which frame of it.

There is no magic word and no `POF0`; the file is three nested tables and
nothing else, and the arithmetic closes on all 2,053.

    0x00  u32   block count
    0x04  (u32 frame, u32 offset) per block
          then the blocks, in table order, the first at 4 + 8 * count

Offsets ascend on all 2,053 files. Frames ascend on 2,041 of them - twelve
files step backwards once, all of them monster lists, which is a thing a
hand-authored event track is allowed to do and a corrupt table is not.

## A block

    +0x00  u16   the frame again - it matches the table on all 6,802
    +0x02  u16   command count
    +0x04  the commands, end to end

## A command

    +0x00  u16   opcode
    +0x02  u16   size, this header included
    +0x04  the payload

**The commands fill their block exactly** - walk `count` of them from `+0x04`
and land on the next block's offset, or on the end of the file, on all 6,802
blocks. That is the identity that makes the format readable rather than
plausible, and it is worth having because nothing else here declares a size.

**51 of the 52 opcodes have one fixed size wherever they appear**, from 4 bytes
(the opcode and its size, and no payload at all) to 120. The exception is
opcode 0, the commonest at 2,508 uses, whose size is always `12 + 116 * n`:
twelve bytes of head, four of them the opcode and size, then a list of 116-byte
records running from one to sixteen. Two
opcode ranges exist: 0 to 62, then 1000, 1002, 1004 and 10000. Those four look
like locator ids at first glance - `1000` and `10000` are locator ids on 251
and 247 models - but 1002 and 1004 are not locator ids on any model on the
disc, so they are opcodes in a high range and not addresses.

## Opcode 0 and opcode 27 carry the same record, and it is the hit

**Opcode 27's payload is 116 bytes**, which is exactly one of opcode 0's
records. So the two are a list and a single of the same thing, and there are
6,193 of them: 4,989 inside opcode 0 and 1,204 standing alone.

Opcode 0's twelve-byte head says how many follow:

    +0x00  u16   opcode 0
    +0x02  u16   size == 12 + 116 * n
    +0x04  u32   a small number, or 1000
    +0x08  u16   n                       == (size - 12) / 116 on all 2,508
    +0x0A  u16   zero                    on all 2,508

Two independent fields agreeing on the count, on every command, is what closes
this: the size and the head are written by different parts of the exporter and
they never disagree.

**Opcode 0 declares the set and opcode 27 updates one of it.** Of the 185 files
carrying both, the first opcode 0 precedes the first opcode 27 on **all 185**,
and 1,176 of the 1,204 opcode-27 records name a slot an opcode 0 had already
declared. Four files use opcode 27 with no opcode 0 anywhere.

### The record

    +0x00  u8        slot           0 to 15
    +0x01  u8        flag           0 to 5
    +0x02  u16       the bone
    +0x04  u16       a second bone, or zero
    +0x06  u16
    +0x08  float[3]  \
    +0x14  float[3]   > three vectors; every one of the nine goes negative
    +0x20  float[3]  /
    +0x2C  float     a size    never negative, set on 6,145 of 6,193
    +0x30  float     a size    never negative, set on 5,926
    +0x34  u8[4]     the second byte scales with the strength of the hit
    +0x38  u8, 0xFF, 0, 0
    +0x3C  float
    +0x40  float     1.0       on 6,181, zero on the rest
    +0x44  float     usually 0.01
    +0x48  u16       an id in 1091..1106, then zero
    +0x4C  u16, u16  the second an id around 361..370
    +0x50  float
    +0x54  float     -1.0      on all 6,193
    +0x58  float
    +0x5C  float
    +0x60  u32
    +0x64  u32
    +0x68  zero      on all 6,193
    +0x6C  float
    +0x70  float

**The field at `+0x02` names a bone, and every one of them resolves.** It
addresses two spaces at once and the value says which: **locator ids on this
disc start at 1000 and no model has more than 149 nodes**, so a number below a
thousand is a node index and one above it is a locator id, with no case that
could be either.

Checked against the model that owns each animation - `bones` does this:

    player   433 locator ids, all present in the model's S4 table
               3 node indices, all in range
    monster  349 locator ids, all present
            3983 node indices, all in range

**4,768 of 4,768**, with 1,425 more records naming no bone at all. The locator
route is the `S4` table of [`cmdl.py`](cmdl.py), the same one the
`collision_*.CTXT` capsules bind through, so a hit and a hurt capsule reach the
skeleton by the same door.

Resolved to names, the node indices read as a hitbox set and nothing else
would: `node_head` 429 times, `node_r_weapon` 266, `node_r_hand` 236,
`node_l_hand` 202, `node_jaw` 201, `node_r_forearm` 162, `node_l_toe` 94,
`weapon` 81, `node_r_toe` 76, `b19_00_shield` 72.

A monster's hitboxes are on its jaw, its head, its hands, its weapon and its
toes. That is what an attack is, and it is what identifies the record. Read one
out and it says so plainly - `b01_00_507`, the sixth attack of the first
monster in the game, puts a hit on `node_l_hand` at frame 46 and another on
`node_r_hand` at frame 54. A one-two.

### The byte at `+0x35` scales with the strength of the hit

Two things say so, and neither needs the value's unit to be known.

**Within one attack it decays.** `sw383cge_l3` is the sword's fully charged
swing: opcode 0 declares two slots at frame 13, then three opcode 27s update
slot 1 at frames 14, 16 and 17, and across them the byte falls **95, 45, 15**
while the size at `+0x30` falls 2.70, 2.00, 1.50 and the second vector's `y`
falls 4.50, 3.50, 2.50. A shockwave travelling out and running down.

**Across charge levels it rises.** The sword is the only class with all three
on the disc:

    sw381cge_l1   1 record    +0x35  50    size 1.12
    sw382cge_l2   1 record    +0x35  70    size 1.33
    sw383cge_l3   5 records   +0x35  95    size 2.70

Both the byte and the capsule grow with the charge. The hammer has two levels
and goes 80 against 40 on the largest single value while rising 80 to 86 on the
sum, because its level 2 is four hits where level 1 is one - which is what a
charged multi-hit does to a per-hit number.

Monster records put 100 or 150 there far more often than players do, so the two
are on different scales; what the number *is* - damage, a percentage, a level -
is not established.

The nine floats at `+0x08` are three vectors rather than the `offset / size /
rol` of a `.CTXT` capsule: a size is never negative and all nine of these are,
between a fifth and a half of the time. The two at `+0x2C` and `+0x30` never
are, and those are the sizes. Which vector is an offset, which an end point and
which a direction is not settled here.

## What the other opcodes do, as far as position says

Naming an opcode needs a correlation, and where one exists it is given; where
none does, the entry says so.

- **opcode 13 opens a window and opcode 5 closes it.** Both carry no payload at
  all, both occur exactly once in a file, they appear together in 315 files,
  and 13 comes strictly before 5 on **356 of the 366** files with both. 13
  falls at 44% of the way through the list at the median; 5 is the last command
  in the file on 288 of 393.
- **Opcodes 24, 50, 41, 52 and 39 are exclusive terminators.** Each occurs at
  most once per file, at the last frame, as the last command - 63 of 63 for
  opcode 24, 39 of 39 for opcode 50, 6 of 6 for opcode 41 - and a file that
  carries one does not carry another. So a list ends with a statement of
  what kind of ending it is.
- **Opcode 17 is a boolean**, 242 payloads of `0` against 239 of `1`.
  Opcodes 8, 9, 11 and 14 are the same four bytes but almost always `1`.
- **Opcodes 1, 2 and 35 carry a small index** in their first byte, running from
  zero upwards.
- **Opcode 10 emits, and never appears in what it emits.** 288 files carry it
  and **not one of the 229 named `*bullet*` does**, while 197 of those carry a
  hit record instead. So the firing animation spawns and the projectile's own
  animation does the hitting. Among the player classes `ht` - the bow - carries
  it most at 65 files, and `ht383cge_l3`, the fully charged shot, issues it ten
  times in one list.
- **Opcode 22 places something and rotates it.** 448 uses, 82% at frame 0, and
  its 44 bytes hold a scale (1.0 on 322 of them, then 1.5, 2.0, 0.8), an offset
  and three angles that read as **degrees** - the only values ever seen there
  are 90, 180 and -15. Its second word is an id of 10300, 10301 or 10302.
- **Opcode 40 is frame-0 setup**, 87% of its 317 uses, and pairs a flag with a
  small id. **Opcode 53 is frame-0 setup on all 231 of its uses**, which is the
  only opcode that is.

Two id spaces appear and neither is named anywhere on the disc: **1091 to
1106** inside the hit record, and **10200 to 12130** in opcodes 10 and 22.
Neither occurs in any of the 4,941 `ECH` tables, so they belong to the sound
banks or the `.PTP` effects, and both of those are unopened.

## The name is the link to the motion

There is no id inside the file. The name carries it: a class prefix and a
three-digit motion id, `as213run` against `fas213run.CNOM` and `mas213run`, or
`b01_00_501` against `b01501*.CNOM`, with the model number dropped and a
`_quick` variant sharing the motion. **1,499 of the 2,053 resolve to a `CNOM`
that way, and on 1,473 of those every command frame lies inside the motion's
declared length** - which is the check that says the pairing is real and the
frame numbers are `CNOM` frames.

Usage:
  python anmcmd.py check <dir>            the whole arithmetic, every file
  python anmcmd.py survey <dir>           every list, most commands first
  python anmcmd.py census <dir>           every opcode, with its size
  python anmcmd.py list <dir> <name>      one list, frame by frame
  python anmcmd.py dump <dir> <name>      the same, with the payload bytes
  python anmcmd.py hits <dir> <name>      the hit records, with bone names
  python anmcmd.py bones <dir>            how many hit records name a bone
  python anmcmd.py find <dir> <glob>      locate a list at any depth
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

SUFFIX = '.anmcmd'
HIT = 116                 # the record opcode 0 lists and 27 carries
HEAD = 8                  # opcode 0's head, past the command header
LOCATOR = 1000            # ids start here; no node table reaches it
HIT_OPS = (0, 27)


class Hit:
    """One 116-byte hit record, from an opcode 0 list or an opcode 27.

    Only the fields the disc identifies are named. The rest are exposed as
    `words` so that `hits` can print them without pretending to read them."""

    __slots__ = ('slot', 'flag', 'bone', 'bone2', 'spare', 'vectors',
                 'sizes', 'power', 'raw')


    def __init__(self, raw: bytes):
        self.raw = raw
        self.slot, self.flag = raw[0], raw[1]
        self.bone, self.bone2, self.spare = struct.unpack_from('>3H', raw, 2)
        self.vectors = [struct.unpack_from('>3f', raw, 8 + 12 * k)
                        for k in range(3)]
        self.sizes = struct.unpack_from('>2f', raw, 0x2C)
        self.power = raw[0x35]

    @property
    def by_locator(self) -> bool:
        """Locator ids start at 1000 and no node table reaches 149, so the
        two address spaces never overlap and the value says which it is."""
        return self.bone >= LOCATOR

    def where(self, names: list[str], locators: dict) -> str:
        if not self.bone:
            return '-'
        if self.by_locator:
            node = locators.get(self.bone)
            at = names[node] if node is not None and node < len(names) else '?'
            return f'locator {self.bone} ({at})'
        return (names[self.bone] if self.bone < len(names)
                else f'node {self.bone}')


def hits_of(cmd: 'Command') -> list[Hit]:
    """The hit records a command carries, if it carries any."""
    if cmd.op == 27 and len(cmd.payload) == HIT:
        return [Hit(cmd.payload)]
    if cmd.op == 0 and len(cmd.payload) >= HEAD \
            and (len(cmd.payload) - HEAD) % HIT == 0:
        n = (len(cmd.payload) - HEAD) // HIT
        return [Hit(cmd.payload[HEAD + HIT * k:HEAD + HIT * (k + 1)])
                for k in range(n)]
    return []


class Command:
    __slots__ = ('op', 'size', 'payload')

    def __init__(self, op: int, size: int, payload: bytes):
        self.op, self.size, self.payload = op, size, payload


class Anmcmd:
    def __init__(self, buf: bytes, label: str = ''):
        self.label = label
        self.buf = buf
        if len(buf) < 4:
            raise ValueError(f'{label}: {len(buf)} bytes')
        self.count = struct.unpack_from('>I', buf, 0)[0]
        if not self.count or 4 + 8 * self.count > len(buf):
            raise ValueError(f'{label}: {self.count} blocks in {len(buf)} '
                             f'bytes')
        self.table = [struct.unpack_from('>II', buf, 4 + 8 * k)
                      for k in range(self.count)]

    def span(self, k: int) -> tuple[int, int]:
        """(start, end) of block k."""
        start = self.table[k][1]
        end = self.table[k + 1][1] if k + 1 < self.count else len(self.buf)
        return start, end

    def block(self, k: int) -> dict:
        start, end = self.span(k)
        frame, n = struct.unpack_from('>2H', self.buf, start)
        out, o = [], start + 4
        for _ in range(n):
            if o + 4 > end:
                break
            op, size = struct.unpack_from('>2H', self.buf, o)
            if size < 4 or o + size > end:
                break
            out.append(Command(op, size, self.buf[o + 4:o + size]))
            o += size
        return {'frame': frame, 'declared': n, 'commands': out, 'ends': o,
                'end': end}

    def blocks(self):
        for k in range(self.count):
            yield self.block(k)


# --------------------------------------------------------------------------

def collect(root, want: str = ''):
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*' + SUFFIX)):
            if p.is_file():
                yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, want):
        if path.endswith(SUFFIX):
            yield path, blob


def _one(root, name) -> tuple[str, Anmcmd]:
    for path, blob in collect(root):
        leaf = path.rsplit('/', 1)[-1]
        if name in (path, leaf, leaf[:-len(SUFFIX)]):
            return path, Anmcmd(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    files = bad = blocks = commands = 0
    tally: dict[str, int] = {}
    errs: list[str] = []

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /n'] = tally.get(k + ' /n', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    sizes: dict[int, set] = {}
    for path, blob in collect(root):
        try:
            a = Anmcmd(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {exc}')
            continue
        files += 1
        offs = [o for _, o in a.table]
        note('the first block follows the table',
             offs[0] == 4 + 8 * a.count,
             f'{path}: first block at {offs[0]:#x}')
        note('block offsets ascend and stay inside the file',
             all(x < y for x, y in zip(offs, offs[1:]))
             and offs[-1] < len(blob), f'{path}: offsets')
        note('frames ascend',
             all(x <= y for (x, _), (y, _) in zip(a.table, a.table[1:])),
             f'{path}: frames {[f for f, _ in a.table][:8]}')
        for k in range(a.count):
            b = a.block(k)
            blocks += 1
            commands += len(b['commands'])
            note('the block repeats the frame in the table',
                 b['frame'] == a.table[k][0],
                 f'{path}: block {k} says frame {b["frame"]}, '
                 f'the table says {a.table[k][0]}')
            note('the commands fill the block exactly',
                 len(b['commands']) == b['declared'] and b['ends'] == b['end'],
                 f'{path}: block {k} ends at {b["ends"]:#x}, '
                 f'not {b["end"]:#x}')
            for c in b['commands']:
                sizes.setdefault(c.op, set()).add(c.size)

    fixed = sum(1 for v in sizes.values() if len(v) == 1)
    print(f'{files} .anmcmd, {blocks:,} blocks, {commands:,} commands, '
          f'{bad} unreadable')
    for k in sorted(tally):
        if k.endswith(' /n'):
            continue
        print(f'  {tally[k]:>6,} / {tally[k + " /n"]:<6,}  {k}')
    print(f'  {fixed} of the {len(sizes)} opcodes have one fixed size')
    for op in sorted(sizes):
        if len(sizes[op]) > 1:
            got = sorted(sizes[op])
            step = {b - a for a, b in zip(got, got[1:])}
            print(f'    opcode {op}: {len(got)} sizes, {got[0]} to {got[-1]}'
                  + (f', all {step.pop()} apart' if len(step) == 1 else ''))
    for line in errs:
        print(line)
    return 1 if bad else 0


def cmd_survey(root) -> int:
    out = []
    for path, blob in collect(root):
        try:
            a = Anmcmd(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        n = sum(len(b['commands']) for b in a.blocks())
        last = a.table[-1][0]
        out.append((n, a.count, last, len(blob), path))
    out.sort(key=lambda r: -r[0])
    print(f'{len(out)} .anmcmd, most commands first')
    for n, blocks, last, size, path in out[:40]:
        print(f'  {n:>5} commands  {blocks:>4} blocks  last at frame '
              f'{last:>4}  {size:>7,} bytes  {path}')
    return 0


def cmd_census(root) -> int:
    count: collections.Counter = collections.Counter()
    sizes: dict[int, collections.Counter] = {}
    where: dict[int, set] = {}
    files = 0
    for path, blob in collect(root):
        try:
            a = Anmcmd(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        files += 1
        top = path.split('/')[0] if '/' in path else path
        for b in a.blocks():
            for c in b['commands']:
                count[c.op] += 1
                sizes.setdefault(c.op, collections.Counter())[c.size] += 1
                where.setdefault(c.op, set()).add(top)
    print(f'{files} .anmcmd, {sum(count.values()):,} commands, '
          f'{len(count)} opcodes')
    print('  opcode     uses   size                 seen under')
    for op in sorted(count):
        s = sizes[op]
        tag = str(next(iter(s))) if len(s) == 1 \
            else f'{min(s)}..{max(s)}, {len(s)} values'
        print(f'  {op:>6}  {count[op]:>7,}   {tag:<20} '
              + ', '.join(sorted(where[op])[:3]))
    return 0


def cmd_list(root, name, hexdump=False) -> int:
    path, a = _one(root, name)
    print(f'{path}  {a.count} blocks')
    for k in range(a.count):
        b = a.block(k)
        print(f'  frame {b["frame"]:>4}  {len(b["commands"])} commands')
        for c in b['commands']:
            print(f'    opcode {c.op:>5}  {c.size:>4} bytes')
            if hexdump:
                for r in range(0, len(c.payload), 16):
                    print('        ' + ' '.join('%02x' % x
                                                for x in c.payload[r:r + 16]))
    return 0


def cmd_find(root, pattern) -> int:
    n = 0
    for path, blob in collect(root):
        leaf = path.rsplit('/', 1)[-1]
        if fnmatch.fnmatch(leaf, pattern) or fnmatch.fnmatch(path, pattern):
            try:
                a = Anmcmd(blob, path)
            except Exception:                                 # noqa: BLE001
                continue
            n += 1
            print(f'  {a.count:>4} blocks, last at frame '
                  f'{a.table[-1][0]:>4}  {path}')
    print(f'{n} match')
    return 0


def _model_for(root, path: str):
    """The model whose skeleton a list's bone references address.

    A player class list names one of the six classes and any of its models
    will do, since they share a rig; a monster list names its own directory."""
    import cmdl                                               # noqa: PLC0415

    m = re.match(r'job\.cpk/([a-z]{2})/', path)
    want = (rf'[fm]{m.group(1)}\d' if m else None)
    if not want:
        m = re.match(r'monster\.cpk/([a-z0-9_]+)/', path)
        if not m:
            return None
        want = re.escape(m.group(1))
    for p, blob in cmdl.collect(root):
        if re.fullmatch(want, p.rsplit('/', 1)[-1][:-5]):
            return cmdl.Cmdl(blob, p)
    return None


def _skeleton(model):
    """(node names, {locator id: node}), or empty when the model has none."""
    if model is None:
        return [], {}
    names = model.names(5)
    table = model.section(4)
    loc = {}
    if table:
        o, _ = table
        n = struct.unpack_from('>I', model.buf, o)[0]
        for i in range(n):
            lid, node = struct.unpack_from('>2H', model.buf, o + 4 + 4 * i)
            loc[lid] = node
    return names, loc


def cmd_hits(root, name) -> int:
    path, a = _one(root, name)
    model = _model_for(root, path)
    names, loc = _skeleton(model)
    print(path)
    print(f'  skeleton: {model.name if model else "not found"}, '
          f'{len(names)} nodes, {len(loc)} locators')
    for b in a.blocks():
        for c in b['commands']:
            rec = hits_of(c)
            if not rec:
                continue
            for h in rec:
                v = '  '.join('(' + ' '.join(f'{x:6.2f}' for x in vec) + ')'
                              for vec in h.vectors)
                print(f'  f{b["frame"]:<4d} op{c.op:<3d} slot {h.slot:2d} '
                      f'flag {h.flag}  {h.where(names, loc):<28s} '
                      f'{v}  size {h.sizes[0]:6.2f} {h.sizes[1]:6.2f}  '
                      f'+0x35 {h.power}')
    return 0


def cmd_bones(root) -> int:
    """How many hit records name a bone their own model actually has."""
    import cmdl                                               # noqa: PLC0415

    models = {}
    for p, blob in cmdl.collect(root):
        try:
            m = cmdl.Cmdl(blob, p)
        except ValueError:
            continue
        names, loc = _skeleton(m)
        models[p.rsplit('/', 1)[-1][:-5]] = (m.nodes, names, set(loc))

    def owners(path):
        m = re.match(r'job\.cpk/([a-z]{2})/', path)
        if m:
            return [k for k in models
                    if re.fullmatch(rf'[fm]{m.group(1)}\d', k)]
        m = re.match(r'monster\.cpk/([a-z0-9_]+)/', path)
        return [m.group(1)] if m and m.group(1) in models else []

    tally: dict[str, int] = collections.Counter()
    where: dict[str, int] = collections.Counter()
    for path, blob in collect(root):
        own = owners(path)
        if not own:
            continue
        nodes = max(models[k][0] for k in own)
        names = max((models[k][1] for k in own), key=len)
        pool = set().union(*(models[k][2] for k in own))
        kind = 'player ' if path.startswith('job') else 'monster'
        for b in Anmcmd(blob, path).blocks():
            for c in b['commands']:
                for h in hits_of(c):
                    tally[f'{kind}: hit records'] += 1
                    if not h.bone:
                        tally[f'{kind}: no bone'] += 1
                    elif h.by_locator:
                        tally[f'{kind}: a locator id, and the model has it'] \
                            += h.bone in pool
                        tally[f'{kind}: a locator id'] += 1
                    else:
                        tally[f'{kind}: a node index, and it is in range'] \
                            += h.bone < nodes
                        tally[f'{kind}: a node index'] += 1
                    if h.bone and not h.by_locator and h.bone < len(names):
                        where[names[h.bone]] += 1
    for k in sorted(tally):
        print(f'{tally[k]:6d}  {k}')
    print('\nthe nodes a hit is bound to, by name')
    for k, v in where.most_common(20):
        print(f'  {v:5d}  {k}')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'survey':
        return cmd_survey(rest[0])
    if cmd == 'census':
        return cmd_census(rest[0])
    if cmd == 'list':
        return cmd_list(rest[0], rest[1])
    if cmd == 'dump':
        return cmd_list(rest[0], rest[1], True)
    if cmd == 'hits':
        return cmd_hits(rest[0], rest[1])
    if cmd == 'bones':
        return cmd_bones(rest[0])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
