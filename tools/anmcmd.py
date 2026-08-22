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

What the opcodes *mean* is open. `census` prints them with their sizes and the
directories they occur in, which is where naming them starts.

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
  python anmcmd.py find <dir> <glob>      locate a list at any depth
"""
from __future__ import annotations

import collections
import fnmatch
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

SUFFIX = '.anmcmd'


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
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
