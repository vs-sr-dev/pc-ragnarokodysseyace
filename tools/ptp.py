"""
ptp.py - reader for `PTCP`, the particle-effect containers.

70 files, three of them zero bytes; **67 read, 1,108 `PTB` blocks, 2,002
resources, 4,451 resource references, 0 unreadable**, and sixteen arithmetic
identities closing on all 67.

This is the bank an animation fires from. A `.anmcmd` opcode 10 spawns an
effect, the [`ELBN`](elbn.py) parameter blocks name effects, and the stage
scripts start them by hand - and all three address the same thing: **a pair,
a category and an index into that category's bank**. The disc says so in its
own words, because one stage script declares the fields:

    class EffData { _hta_name; _eff_cate; _eff_id; ... }
    handle = effStart(data._eff_cate, data._eff_id)

`_eff_id` is the slot number of a `PTB` block in the `PTCP` the category
selects. See [`../docs/format_ptp.md`](../docs/format_ptp.md).

## The container

Five tables and then the payload. The header gives four of the five offsets
and the two counts; the fifth offset is the first table, always `0x40`.

    0x00  u32   A, the block directory        always 0x40
    0x04  u32   B, the resource directory
    0x08  u32   E, the reference list
    0x0C  u16   nA          entries in A
    0x0E  u16   nB          entries in B
    0x10  'PTCP'
    0x14  u32   1           version
    0x18  u32   C, one u32 per A entry
    0x1C  u32   D, one u32 per B entry
    0x20  32 zero bytes

Each table ends exactly where the next begins, which is what says the five are
five and not four or six:

    A + 8 * nA == B      B + 8 * nB == C
    C + 4 * nA == D      D + 4 * nB == E

An A or B entry is `(u32 offset, u16 first, u16 zero)` and the matching C or D
word is that block's **size in bytes, little-endian** - the one field on this
big-endian disc that is not. An empty slot is all zero in both tables at once.

`A` is **sparse**: `misc.PTP` declares 161 slots and fills 137 of them. The
holes are the point, because the slot number is the effect's name.

`E` is a `u16` array. `first` in an A entry is where that block's run begins;
the run ends where the next used block's begins, and the values index `B`.
**Every non-final `PTB` names exactly as many files, in the clear, as it has
distinct references in `E` - 1,041 of 1,041.** That is the identity that binds
the two directories together, and it is why the format can be said to be read
rather than guessed: the block's own strings and the container's index agree
on the count, every time.

## What a resource is

790 `CTEX` textures and 736 `ARC` archives, plus 476 blocks with no magic at
all - raw curve data, whose first word reads as a float. A `PTB` names them
`ef_I_circle002.ctex`, `anm_ef_I_smoke001_roop.txx`, `ef_h_z21_19_cirl000.rnx`,
so the container needs no name table: the consumer carries its own.

Usage:
  python ptp.py check <dir>              every file, every identity
  python ptp.py survey <dir>             every file, blocks and resources
  python ptp.py list <dir> <name>        one file, its slots and their assets
  python ptp.py slot <dir> <name> <n>    one block, hex and strings
  python ptp.py refs <dir>               where the (category, id) pairs resolve
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

SUFFIX = '.ptp'
MAGIC = b'PTCP'
BLOCK = b'PTB\0'
HEAD = 0x40               # the first table, and the size of the header
ASSET = re.compile(rb'[A-Za-z0-9_.\-]+\.(?:ctex|pac|txx|rnx|dds|CTEX)\b')

# `misc.PTP` is the common bank; a category of 1 means the actor's or the
# stage's own file. Proven on 104 of 104 pairs, see `refs`.
COMMON = 'misc.cpk/misc.PTP'


class Entry:
    """One slot of the block directory or the resource directory."""

    __slots__ = ('index', 'offset', 'first', 'size')

    def __init__(self, index: int, offset: int, first: int, size: int):
        self.index, self.offset, self.first, self.size = \
            index, offset, first, size

    @property
    def used(self) -> bool:
        return self.offset != 0


class Ptp:
    def __init__(self, buf: bytes, label: str = ''):
        self.label, self.buf = label, buf
        if len(buf) < HEAD:
            raise ValueError(f'{label}: {len(buf)} bytes')
        if buf[0x10:0x14] != MAGIC:
            raise ValueError(f'{label}: not a PTCP ({buf[0x10:0x14]!r})')
        self.a_off, self.b_off, self.e_off = struct.unpack_from('>3I', buf, 0)
        self.na, self.nb = struct.unpack_from('>2H', buf, 0x0C)
        self.version = struct.unpack_from('>I', buf, 0x14)[0]
        self.c_off, self.d_off = struct.unpack_from('>2I', buf, 0x18)
        self.blocks = self._table(self.a_off, self.c_off, self.na)
        self.resources = self._table(self.b_off, self.d_off, self.nb)

    def _table(self, index: int, sizes: int, n: int) -> list[Entry]:
        out = []
        for k in range(n):
            off, first, spare = struct.unpack_from('>IHH', self.buf,
                                                   index + 8 * k)
            # the size is the one little-endian field in the file
            size = struct.unpack_from('<I', self.buf, sizes + 4 * k)[0]
            if spare:
                raise ValueError(f'{self.label}: slot {k} spare {spare}')
            out.append(Entry(k, off, first, size))
        return out

    @property
    def used(self) -> list[Entry]:
        return [e for e in self.blocks if e.used]

    @property
    def first_payload(self) -> int:
        """Where the tables stop and the blocks begin."""
        off = [e.offset for e in self.blocks + self.resources if e.used]
        return min(off) if off else len(self.buf)

    def refs(self, e: Entry) -> tuple[int, ...]:
        """The resource indices block `e` uses.

        The run ends where the next used block's begins. The last block has no
        successor, so its run is what its own strings say it is - which is the
        identity `check` tests everywhere else."""
        used = self.used
        k = used.index(e)
        if k + 1 < len(used):
            n = used[k + 1].first - e.first
        else:
            n = len(self.names(e))
        return struct.unpack_from(f'>{n}H', self.buf, self.e_off + 2 * e.first)

    def names(self, e: Entry) -> list[str]:
        """The files a block names, in the clear, first use first."""
        seg = self.buf[e.offset:e.offset + e.size]
        return list(dict.fromkeys(m.group().decode()
                                  for m in ASSET.finditer(seg)))

    def magic(self, e: Entry) -> str:
        head = self.buf[e.offset:e.offset + 4]
        return head.decode('ascii') if head[:1].isalpha() else '-'


# --------------------------------------------------------------------------

def collect(root, want: str = ''):
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix.lower() == SUFFIX:
                yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, want):
        if path.lower().endswith(SUFFIX):
            yield path, blob


def _one(root, name) -> tuple[str, Ptp]:
    for path, blob in collect(root):
        leaf = path.rsplit('/', 1)[-1]
        if name in (path, leaf) or fnmatch.fnmatch(path, name):
            return path, Ptp(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    files = empty = bad = 0
    tally: dict[str, int] = {}
    errs: list[str] = []
    b_total = r_total = e_total = 0
    pad: collections.Counter = collections.Counter()

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /n'] = tally.get(k + ' /n', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    for path, blob in collect(root):
        if not blob:
            empty += 1
            continue
        try:
            p = Ptp(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {exc}')
            continue
        files += 1
        note('the first table is at 0x40', p.a_off == HEAD,
             f'{path}: {p.a_off:#x}')
        note('the magic is PTCP and the version 1', p.version == 1,
             f'{path}: version {p.version}')
        note('bytes 0x20..0x40 are zero', blob[0x20:HEAD] == b'\0' * 32, path)
        note('the block directory ends on the resource directory',
             p.a_off + 8 * p.na == p.b_off,
             f'{path}: {p.a_off + 8 * p.na:#x} != {p.b_off:#x}')
        note('the resource directory ends on the block sizes',
             p.b_off + 8 * p.nb == p.c_off,
             f'{path}: {p.b_off + 8 * p.nb:#x} != {p.c_off:#x}')
        note('one block size per block slot',
             p.c_off + 4 * p.na == p.d_off,
             f'{path}: {p.c_off + 4 * p.na:#x} != {p.d_off:#x}')
        note('one resource size per resource slot',
             p.d_off + 4 * p.nb == p.e_off,
             f'{path}: {p.d_off + 4 * p.nb:#x} != {p.e_off:#x}')
        note('an empty slot has a zero size',
             all(e.used == bool(e.size)
                 for e in p.blocks + p.resources), path)
        note('every block slot points at a PTB',
             all(blob[e.offset:e.offset + 4] == BLOCK for e in p.used), path)

        spans = sorted((e.offset, e.size)
                       for e in p.blocks + p.resources if e.used)
        note('the blocks ascend and none overlaps the next',
             all(o + s <= n for (o, s), (n, _) in zip(spans, spans[1:])),
             path)
        note('the last block ends on the end of the file',
             0 <= len(blob) - (spans[-1][0] + spans[-1][1]) < 16,
             f'{path}: ends {spans[-1][0] + spans[-1][1]:#x} '
             f'of {len(blob):#x}')
        note('the first block follows the reference list',
             spans[0][0] >= p.e_off,
             f'{path}: {spans[0][0]:#x} < {p.e_off:#x}')
        note("the blocks' reference runs ascend",
             all(x.first <= y.first for x, y in zip(p.used, p.used[1:])),
             path)

        used, total = p.used, 0
        for k, e in enumerate(used):
            names = p.names(e)
            refs = p.refs(e)
            note('every reference indexes a resource slot',
                 all(v < p.nb for v in refs), f'{path}: slot {e.index}')
            if k + 1 < len(used):
                note('a block names one file per distinct reference',
                     len(set(refs)) == len(names),
                     f'{path}: slot {e.index} has {len(set(refs))} '
                     f'references and names {len(names)} files')
            total = e.first + len(refs)
        e_total += total
        b_total += len(used)
        r_total += sum(1 for e in p.resources if e.used)
        gap = p.first_payload - (p.e_off + 2 * total)
        pad[gap] += 1
        note('the reference list ends within sixteen bytes of the first block',
             0 <= gap < 16, f'{path}: {gap} bytes over')

    print(f'{files + empty + bad} .PTP, {empty} of them zero bytes, '
          f'{files} read, {b_total:,} PTB blocks, {r_total:,} resources, '
          f'{e_total:,} resource references, {bad} unreadable')
    for k in sorted(tally):
        if k.endswith(' /n'):
            continue
        print(f'  {tally[k]:>6,} / {tally[k + " /n"]:<6,}  {k}')
    for line in errs:
        print(line)
    return 1 if bad else 0


def cmd_survey(root) -> int:
    out = []
    for path, blob in collect(root):
        if not blob:
            out.append((0, 0, 0, 0, path + '   (zero bytes)'))
            continue
        try:
            p = Ptp(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        out.append((len(p.used), p.na, sum(1 for e in p.resources if e.used),
                    len(blob), path))
    out.sort(key=lambda r: -r[0])
    print(f'{len(out)} .PTP, most blocks first')
    print('  blocks  slots  resources        bytes  file')
    for n, na, nr, size, path in out:
        print(f'  {n:>6}  {na:>5}  {nr:>9}  {size:>11,}  {path}')
    return 0


def cmd_list(root, name) -> int:
    path, p = _one(root, name)
    print(f'{path}  {len(p.used)} of {p.na} block slots, '
          f'{sum(1 for e in p.resources if e.used)} of {p.nb} resources')
    for e in p.used:
        refs = p.refs(e)
        names = p.names(e)
        print(f'  slot {e.index:>3}  {e.offset:#09x}  {e.size:>7,} bytes  '
              f'{len(refs)} refs {list(refs)}')
        for nm in names:
            print(f'      {nm}')
    print('  resources:')
    for e in p.resources:
        if e.used:
            print(f'    {e.index:>3}  {p.magic(e):<5} {e.size:>8,} bytes  '
                  f'{e.offset:#09x}')
    return 0


def cmd_slot(root, name, which) -> int:
    path, p = _one(root, name)
    k = int(which)
    if k >= p.na or not p.blocks[k].used:
        raise SystemExit(f'{path}: slot {k} is empty')
    e = p.blocks[k]
    seg = p.buf[e.offset:e.offset + e.size]
    print(f'{path}  slot {k}  {e.offset:#x}  {e.size:,} bytes')
    n, head = struct.unpack_from('>II', seg, 8)
    print(f'  head: {n} emitters, header {head:#x}')
    for i in range(5):
        c, o = struct.unpack_from('>II', seg, 0x10 + 8 * i)
        print(f'    sub {i}: {c:>5} entries at {o:#x}')
    for r in range(0, min(len(seg), 0x80), 16):
        row = seg[r:r + 16]
        print(f'  {r:04x}  ' + ' '.join('%02x' % x for x in row) + '  '
              + ''.join(chr(x) if 32 <= x < 127 else '.' for x in row))
    print('  names: ' + ', '.join(p.names(e)))
    return 0


def cmd_refs(root) -> int:
    """Where the `(category, id)` pairs in `ELBN` resolve.

    `eff_vari_tbl` is a monster's list of effect variations and it is written
    as pairs. Category 0 is the common bank, category 1 the monster's own -
    and every id lands on a slot that exists."""
    from elbn import Elbn                                     # noqa: PLC0415

    root = pathlib.Path(root)
    banks: dict[str, set] = {}
    for path, blob in collect(root):
        if blob:
            try:
                banks[path] = {e.index for e in Ptp(blob, path).used}
            except Exception:                                 # noqa: BLE001
                pass
    common = next((v for k, v in banks.items() if k.endswith(COMMON)), set())

    files = ok = pairs = hit = 0
    for path, blob in leaves(root, 'monster') \
            if any(p.is_file() for p in root.glob('*.cpk')) \
            else ((p.relative_to(root).as_posix(), p.read_bytes())
                  for p in sorted(root.glob('monster.cpk/*/objbin.bin'))):
        if not path.endswith('objbin.bin'):
            continue
        try:
            e = Elbn(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        entry = e.by_name().get('eff_vari_tbl')
        if not entry:
            continue
        rows = e.word(entry.offset)
        ptr = e.word(entry.offset + 4)
        words = [e.word(ptr + 4 * i) for i in range(rows * 4)]
        pair = [(words[i], words[i + 1]) for i in range(0, len(words), 2)]
        family = path.split('/')[1].split('_')[0]
        own = next((v for k, v in banks.items()
                    if k.endswith(f'monster.cpk/{family}/effect.PTP')), set())
        good = 0
        for cate, eid in pair:
            pairs += 1
            if eid in (common if cate == 0 else own):
                good += 1
        hit += good
        files += 1
        ok += good == len(pair)
        print(f'  {path.split("/")[1]:<10} {rows} rows  '
              f'{good}/{len(pair)} pairs resolve   {pair}')
    print(f'eff_vari_tbl: {ok} of {files} files, {hit} of {pairs} pairs '
          f'land on a slot that exists '
          f'(category 0 -> {COMMON}, category 1 -> the monster\'s own)')
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
    if cmd == 'list':
        return cmd_list(rest[0], rest[1])
    if cmd == 'slot':
        return cmd_slot(rest[0], rest[1], rest[2])
    if cmd == 'refs':
        return cmd_refs(rest[0])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
