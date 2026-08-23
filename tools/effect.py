"""
effect.py - reader for `effect.bin`, the table that says what an effect *is*.

69 files, two schemas, 3,918 rows; **69 read, 0 failures**. A
[`.PTP`](ptp.py) block is a particle system with no placement in it: it does
not know how big it is, where on the body it hangs, or how often it fires.
This is the file that knows.

    54 motion tables   character.cpk/motion.cpk/<class>.pac/effect.bin
                       monster.cpk/pac/<mon>.pac/effect.bin
                       one per motion set, addressed by `.mkc` opcode `0801`

    15 stage tables    stage.cpk/<nnn>/effect.pac/effect.bin
                       the ambient effects of a stage, one row per marker

Both are [`ECH`](ech.py) tables of 60-byte rows and they are otherwise
unrelated structs. The stage one carries a string pool and the motion one
does not, which is the quickest way to tell them apart.

## The motion row

    +0x00  u8   kind       1, and 0 on 102 rows of 2,434
    +0x01  u8   id         the number `.mkc` 0801 asks for
    +0x02  u8   category   0 = misc.cpk/misc.PTP, 1 = the actor's own
    +0x03  u8   slot       the block in that bank
    +0x04  u32  locator    a `CMDL` S4 id - where on the body it hangs
    +0x08  u8   unread     0, 1 or 2
    +0x09  u8   unread     a bit field, 0x00 0x40 0x60 0x80 0xc0 0xe0
    +0x0a  u8   unread     a bit field, 0x00 .. 0x0a
    +0x0b  u8   0xff       on all 2,434 rows
    +0x0c  f32  scale      1.0 on 1,081 rows, 0.2 .. 30 elsewhere
    +0x10  f32  x          an offset from the locator, in metres
    +0x14  f32  y
    +0x18  f32  z
    +0x1c  u32  axis       1, 2 or 3, with the angle beside it
    +0x20  f32  degrees
    +0x24  u32  axis       a second rotation, never about the first axis
    +0x28  f32  degrees
    +0x2c  ...  zero on all 2,434 rows

**`.mkc` addresses the id, not the row.** `0801`'s argument is the byte at
`+0x01`, which is unique within every one of the 54 tables but skips wherever
an effect was cut: `b15` has 48 rows and ids up to 67. Read as an id **4,187
of 4,190 references resolve**, against 4,125 read as a row position, and
thirteen of the fourteen pacs that were said to *index past the end of their
own table* stop doing so. The exception is `z07`, which asks for 4, 5 and 6
and carries ids 1, 2, 3, 7, 8.

**The `(category, slot)` pair is the `.PTP` address**, the same one
`eff_vari_tbl` and the stage scripts use: 2,410 of the 2,434 rows land on a
filled block of the named bank. 18 of the 24 that do not are row 0, which
every table opens with - `id 1, (1, 1)` - and which `.mkc` asks for on three
tables only.

**The `u32` at `+0x04` is a `CMDL` locator id**, the same namespace as
`.mkc`'s `7ff9` emitter: 455 of the 457 non-zero values resolve against the
actor's own model, and the vocabulary reads itself - `node_r_weapon` on 66
rows, `node_hip`, the hands, the head, the toes, `big_gun`, and the rig's
own `eff_*` sockets. The other 1,977 rows leave it at 0 and hang the effect
off the actor's origin.

## Category 2 is this file

The six classes' `eff_hitlevel_tbl` addresses effects as `(2, id)` and no
`PTCP` on the disc has the 252 slots it reaches. It does not need one:
**category 2 is the class's own `effect.bin`, addressed by row id - 96 of 96
pairs resolve.** `fht`'s ids are 110, 111, 112, 120, 121, 122 ... 250, 251,
252, eleven weapon kinds by three hit levels, and each triple is *one* `.PTP`
slot at scale 0.5, 0.8 and 1.0. The hit level is the scale.

## The stage row

    +0x00  u32  str  the room, or 0 to carry the previous row's
    +0x04  u32  str  the `HTA` marker the effect stands on
    +0x08  u8   unread    0 or 1
    +0x09  u8   unread    1 or 10
    +0x0a  u8   slot      in the stage's own effect.PTP
    +0x0b  u8   unread    0x80 or 0xc0
    +0x0c  f32  near      a distance, 15 .. 50
    +0x10  f32  far       the other one, >= near on 1,469 rows of 1,484
    +0x14  f32  x         zero on every row
    +0x18  f32  y         the offset the script calls `_y_offset`
    +0x1c  f32  z         non-zero on three rows
    +0x20  f32  rotation about x, in degrees
    +0x24  f32  about y   which is where all the variety is
    +0x28  f32  about z   zero on every row
    +0x2c  f32  scale
    +0x30  f32  seconds, fixed     `_sec_fix`
    +0x34  f32  seconds, random    `_sec_rnd`
    +0x38  i32  cue id, -1 for none

There is no category lane because there is no choice: **all 1,484 rows land
on a filled block of the stage's own `effect.PTP`**, and 24 of them are on a
slot `misc.PTP` leaves empty or does not have, which is what rules the common
bank out.

The names come from a script. `stage.cpk/050_02_03/param.pac` declares
`class EffData { _hta_name; _eff_cate; _eff_id; _rnd_radius; _y_offset;
_sec_fix; _sec_rnd; _cue_id; _work }` and lists the same six markers this
table lists for the same room - and the two agree field for field:

    ef_fire01  slot 8   y -8.5   5 s + 5 s        the script: (1, 8, 0, -8.5, 5, 5, ...)
    ef_fire03  slot 9   y -8.5   5 s + 5 s        the script: (1, 9, 2, -8.5, 5, 5, ...)

**A row names a cue exactly when it carries a period**: 44 rows do both, 1,440
do neither, and not one does one without the other. A fire that restarts every
five seconds makes a noise when it does; embers and smoke run continuously and
are silent.

Usage:
  python effect.py check <dir>            every table, every identity
  python effect.py survey <dir>           every table, one line each
  python effect.py list <dir> <name>      one table, decoded
  python effect.py refs <dir>             `.mkc` indices, as a row and as an id
  python effect.py hitlevel <dir>         category 2 against the class's table
  python effect.py locators <dir>         `+0x04` against the models' S4
"""

import collections
import fnmatch
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                       # noqa: E402
from cmdl import Cmdl                                           # noqa: E402
from ptp import Ptp                                             # noqa: E402

NAME = 'effect.bin'
MAGIC = b'ECH\0'
MISC = 'misc.cpk/misc.PTP'

CLASSES = {'as': 'as', 'cl': 'cl', 'hs': 'hs', 'ht': 'ht', 'mg': 'mg',
           'sw': 'sw'}


# --------------------------------------------------------------------------
# the rows

class Motion:
    """One row of a motion set's table."""

    __slots__ = ('index', 'kind', 'id', 'cate', 'slot', 'locator', 'scale',
                 'offset', 'rot', 'raw')

    def __init__(self, index: int, r: bytes):
        self.index, self.raw = index, r
        self.kind, self.id, self.cate, self.slot = r[0], r[1], r[2], r[3]
        self.locator = struct.unpack_from('>I', r, 4)[0]
        self.scale = struct.unpack_from('>f', r, 12)[0]
        self.offset = struct.unpack_from('>3f', r, 16)
        a1, d1, a2, d2 = struct.unpack_from('>IfIf', r, 28)
        self.rot = [(a, d) for a, d in ((a1, d1), (a2, d2)) if a]

    @property
    def rot_text(self) -> str:
        return ' '.join('%s%+g' % ('xyz'[a - 1] if 1 <= a <= 3 else '?%d' % a,
                                   d) for a, d in self.rot)


class Ambient:
    """One row of a stage's table."""

    __slots__ = ('index', 'room', 'marker', 'slot', 'near', 'far', 'offset',
                 'rot', 'scale', 'sec_fix', 'sec_rnd', 'cue', 'raw')

    def __init__(self, index: int, r: bytes, room: str, marker: str):
        self.index, self.raw, self.room, self.marker = index, r, room, marker
        self.slot = r[10]
        self.near, self.far = struct.unpack_from('>2f', r, 12)
        self.offset = struct.unpack_from('>3f', r, 20)
        self.rot = struct.unpack_from('>3f', r, 32)
        self.scale = struct.unpack_from('>f', r, 44)[0]
        self.sec_fix, self.sec_rnd = struct.unpack_from('>2f', r, 48)
        cue = struct.unpack_from('>i', r, 56)[0]
        self.cue = None if cue == -1 else cue


class Table:
    """One `effect.bin`, either schema. `stage` says which."""

    def __init__(self, blob: bytes, path: str = ''):
        self.path, self.buf = path, blob
        if blob[:4] != MAGIC:
            raise ValueError(f'{path}: not an ECH ({blob[:4]!r})')
        head, spare, version, n, width = struct.unpack_from('>5I', blob, 4)
        if head != 0x18 + width:
            raise ValueError(f'{path}: header {head:#x} against width {width}')
        if width != 60:
            raise ValueError(f'{path}: row width {width}, expected 60')
        self.count, self.width, self.head = n, width, head
        self.default = blob[0x18:head]
        self.pool = blob[head + n * width:]
        self.stage = bool(self.pool)
        self.rows: list = []
        room = ''
        for i in range(n):
            r = blob[head + i * width:head + (i + 1) * width]
            if self.stage:
                a, b = struct.unpack_from('>2I', r)
                room = self.string(a) or room
                self.rows.append(Ambient(i, r, room, self.string(b)))
            else:
                self.rows.append(Motion(i, r))

    def string(self, off: int) -> str:
        if off >= len(self.pool):
            return ''
        end = self.pool.find(b'\0', off)
        return self.pool[off:end].decode('ascii', 'replace')

    def by_id(self) -> dict:
        return {r.id: r for r in self.rows}


# --------------------------------------------------------------------------
# the disc around it

WANTED = (NAME, '.ptp', '.cmdl', '.mkc')


def collect(root, want: str = ''):
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.name.lower().endswith(WANTED):
                yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, want):
        if path.lower().endswith(WANTED):
            yield path, blob


def family(stem: str) -> str:
    """`b09_00`, `b09_01` and `b09_02` are one actor."""
    if len(stem) == 6 and stem[0] in 'bz' and stem[1:3].isdigit() \
            and stem[3] == '_' and stem[4:].isdigit():
        return stem[:3]
    return stem


class Disc:
    """The tables, the banks they address, and the models they hang off."""

    def __init__(self, root, locators: bool = False):
        self.tables: dict[str, Table] = {}
        self.ptp: dict[str, bytes] = {}
        self.mkc: list[tuple[str, bytes]] = []
        self.locators: dict[str, dict[int, list]] = {}
        for path, blob in collect(root):
            low = path.lower()
            if low.endswith(NAME) and blob[:4] == MAGIC:
                self.tables[path] = Table(blob, path)
            elif low.endswith('.ptp'):
                self.ptp[path] = blob
            elif low.endswith('.mkc'):
                self.mkc.append((path, blob))
            elif low.endswith('.cmdl') and locators:
                self._locators(path, blob)
        self._banks: dict[str, Ptp | None] = {}
        self._rigs: dict[str, dict[int, list]] = {}

    def _locators(self, path: str, blob: bytes) -> None:
        stem = path.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        try:
            body = Cmdl(blob, stem)
            names = body.names(5)
        except (ValueError, struct.error):
            return
        t = self.locators.setdefault(family(stem), {})
        for i, node in body.locators():
            name = names[node] if node < len(names) else ''
            got = t.setdefault(i, [])
            if name and name not in got:
                got.append(name)

    # -- which bank a table's category names ---------------------------------

    def owner(self, table: str) -> str:
        """The actor a table belongs to: `b09.pac` -> `b09`, and the two
        shield tables -> `shield`."""
        name = table.rsplit('/', 2)[-2]
        for suffix in ('.mot.pac', '.pac'):
            if name.endswith(suffix):
                return name[:-len(suffix)]
        return name

    def own_ptp(self, table: str) -> str:
        """The `.PTP` that is category 1 for this table."""
        d = table.rsplit('/', 1)[0]
        name = d.rsplit('/', 1)[-1]
        if 'monster.cpk' in d:
            return f'monster.cpk/{name[:-4]}/effect.PTP'
        if 'character.cpk' in d:
            return f'job.cpk/{name[1:-4]}/effect.PTP'
        return f'{d}/effect.PTP'

    def bank(self, path: str) -> Ptp | None:
        if path not in self._banks:
            blob = self.ptp.get(path)
            try:
                self._banks[path] = Ptp(blob, path) if blob else None
            except ValueError:
                self._banks[path] = None
        return self._banks[path]

    def resolve(self, table: str, cate: int, slot: int):
        """`(bank, entry)`, with `entry` None when the slot is not filled."""
        want = MISC if cate == 0 else self.own_ptp(table)
        b = self.bank(want)
        if b is None or slot >= len(b.blocks) or not b.blocks[slot].used:
            return b, None
        return b, b.blocks[slot]

    def assets(self, table: str, cate: int, slot: int, n: int = 2) -> str:
        b, e = self.resolve(table, cate, slot)
        if e is None:
            return '-'
        try:
            return ', '.join(b.names(e)[:n])
        except (ValueError, struct.error):
            return '?'

    def rig(self, table: str) -> dict[int, list]:
        """Every locator any model of this actor declares. A monster ships in
        two or three sets of armour and they share a rig, so an id may be
        named by only one of them."""
        key = self.owner(table)
        if key not in self._rigs:
            merged: dict[int, list] = {}
            for name, t in self.locators.items():
                if name == key or name.startswith(key):
                    for i, names in t.items():
                        got = merged.setdefault(i, [])
                        got.extend(n for n in names if n not in got)
            self._rigs[key] = merged
        return self._rigs[key]

    def node(self, table: str, loc: int) -> str:
        """What the locator id binds to on this actor's own rig."""
        if not loc:
            return ''
        got = self.rig(table).get(loc)
        return got[0] if got else '?'


def _one(disc: Disc, name: str) -> tuple[str, Table]:
    for path, t in disc.tables.items():
        if name in path or fnmatch.fnmatch(path, name):
            return path, t
    raise SystemExit(f'not found: {name}')


# --------------------------------------------------------------------------

def cmd_check(root) -> int:
    disc = Disc(root)
    motion = {p: t for p, t in disc.tables.items() if not t.stage}
    stage = {p: t for p, t in disc.tables.items() if t.stage}
    print(f'{len(disc.tables)} tables: {len(motion)} motion, {len(stage)} '
          f'stage, {sum(t.count for t in disc.tables.values()):,} rows')

    bad = []
    dup = 0
    for p, t in motion.items():
        seen = collections.Counter(r.id for r in t.rows)
        dup += sum(v - 1 for v in seen.values() if v > 1)
        if t.rows and (t.rows[0].id != 1):
            bad.append(f'{p}: row 0 has id {t.rows[0].id}')
    print(f'  the id byte is unique in every motion table: '
          f'{dup} duplicates over {sum(t.count for t in motion.values()):,} '
          f'rows')
    print(f'  every motion table opens on id 1: '
          f'{len(motion) - len(bad)} of {len(motion)}')

    used = empty = past = 0
    for p, t in motion.items():
        for r in t.rows:
            b, e = disc.resolve(p, r.cate, r.slot)
            if e is not None:
                used += 1
            elif b is None or r.slot >= len(b.blocks):
                past += 1
            else:
                empty += 1
    print(f'  (category, slot) lands on a filled block: {used:,} of '
          f'{used + empty + past:,}   ({empty} empty, {past} past the end)')

    used = other = 0
    for p, t in stage.items():
        b = disc.bank(disc.own_ptp(p))
        m = disc.bank(MISC)
        for r in t.rows:
            if b is not None and r.slot < len(b.blocks) \
                    and b.blocks[r.slot].used:
                used += 1
            if m is None or r.slot >= len(m.blocks) \
                    or not m.blocks[r.slot].used:
                other += 1
    total = sum(t.count for t in stage.values())
    print(f'  a stage row lands on its own bank: {used:,} of {total:,}, '
          f'and {other} of those are a slot misc.PTP has not got')

    pair = collections.Counter()
    for p, t in stage.items():
        for r in t.rows:
            pair[(bool(r.sec_fix or r.sec_rnd), r.cue is not None)] += 1
    print(f'  a stage row names a cue exactly when it has a period: '
          f'{pair[(True, True)]} do both, {pair[(False, False)]} neither, '
          f'{pair[(True, False)] + pair[(False, True)]} disagree')

    zeros = sum(1 for t in disc.tables.values() for r in t.rows
                if not t.stage and r.raw[44:] == bytes(16))
    print(f'  the last sixteen bytes of a motion row are zero: {zeros:,} of '
          f'{sum(t.count for t in motion.values()):,}')

    found, lost, unknown = _markers(root, stage)
    print(f'  a stage row stands on a marker its room declares: {found:,} of '
          f'{found + lost:,}'
          + (f', {unknown} rooms not on the disc' if unknown else ''))
    for b in bad:
        print('   ', b)
    return 0


def _markers(root, stage: dict) -> tuple:
    """Every `(room, marker)` a stage table names, against `hta.bin`."""
    from stage import stages                                    # noqa: PLC0415

    rooms: dict[str, set] = {}
    for st in stages(root):
        rooms[st.name] = {m.name for m in st.markers}
    found = lost = unknown = 0
    for t in stage.values():
        for r in t.rows:
            names = rooms.get(r.room)
            if names is None:
                unknown += 1
            elif r.marker in names:
                found += 1
            else:
                lost += 1
    return found, lost, unknown


def cmd_survey(root) -> int:
    disc = Disc(root)
    print(f'{"table":<58} {"rows":>5}  {"kind":<7} what it addresses')
    for p in sorted(disc.tables):
        t = disc.tables[p]
        if t.stage:
            rooms = len({r.room for r in t.rows})
            cues = sum(1 for r in t.rows if r.cue is not None)
            what = f'{rooms} rooms, {cues} with a cue'
        else:
            own = sum(1 for r in t.rows if r.cate == 1)
            loc = sum(1 for r in t.rows if r.locator)
            what = (f'ids 1..{max(r.id for r in t.rows)}, {own} own bank, '
                    f'{loc} on a locator')
        print(f'{p:<58} {t.count:>5}  {"stage" if t.stage else "motion":<7} '
              f'{what}')
    return 0


def cmd_list(root, name) -> int:
    disc = Disc(root, locators=True)
    path, t = _one(disc, name)
    print(f'{path}   {t.count} rows, '
          f'{"stage" if t.stage else "motion"} schema')
    if t.stage:
        print(f'{"room":<11} {"marker":<12} {"slot":>4} {"scale":>6} '
              f'{"y":>7} {"yaw":>6} {"period":>12} {"cue":>4}  asset')
        last = ''
        for r in t.rows:
            room = '' if r.room == last else r.room
            last = r.room
            period = ('%g+%g s' % (r.sec_fix, r.sec_rnd)
                      if r.sec_fix or r.sec_rnd else '')
            print(f'{room:<11} {r.marker:<12} {r.slot:>4} {r.scale:>6g} '
                  f'{r.offset[1]:>7g} {r.rot[1]:>6g} {period:>12} '
                  f'{"" if r.cue is None else r.cue:>4}  '
                  f'{disc.assets(path, 1, r.slot)}')
        return 0
    print(f'{"id":>4} {"cat":>3} {"slot":>4} {"locator":>7} {"node":<16} '
          f'{"scale":>6} {"offset":>20} {"rotation":<14} asset')
    for r in t.rows:
        off = ('%g %g %g' % r.offset) if any(r.offset) else ''
        print(f'{r.id:>4} {r.cate:>3} {r.slot:>4} '
              f'{r.locator if r.locator else "":>7} '
              f'{disc.node(path, r.locator):<16} {r.scale:>6g} {off:>20} '
              f'{r.rot_text:<14} {disc.assets(path, r.cate, r.slot)}')
    return 0


def cmd_refs(root) -> int:
    """`.mkc` `0801` read as a row position and read as the id byte."""
    from mkc import Mkc, EFFECT_OPS                             # noqa: PLC0415

    disc = Disc(root)
    per: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for path, blob in disc.mkc:
        pac = '/'.join(path.split('/')[:-2])
        for r in Mkc(blob, path).records:
            if r.op in EFFECT_OPS and r.args:
                per[pac][r.args[0]] += 1

    pos_ok = pos_no = id_ok = id_no = 0
    print(f'{"pac":<16} {"rows":>5} {"refs":>6} {"as a position":>16} '
          f'{"as an id":>12}')
    for path in sorted(disc.tables):
        t = disc.tables[path]
        if t.stage:
            continue
        owner = path.rsplit('/', 1)[0]
        refs = per.get(owner)
        if not refs:
            continue
        ids = {r.id for r in t.rows}
        a = sum(c for v, c in refs.items() if 1 <= v <= t.count)
        b = sum(c for v, c in refs.items() if v in ids)
        n = sum(refs.values())
        pos_ok += a
        pos_no += n - a
        id_ok += b
        id_no += n - b
        miss = sorted(v for v in refs if v not in ids)
        print(f'{owner.rsplit("/", 1)[-1]:<16} {t.count:>5} {n:>6} '
              f'{a:>9} of {n:<4} {b:>7} of {n:<4}'
              + ('   <- ' + str(miss) if miss else ''))
    print(f'\nas a row position: {pos_ok:,} resolve, {pos_no} do not')
    print(f'as the id byte   : {id_ok:,} resolve, {id_no} do not')
    return 0


def cmd_hitlevel(root) -> int:
    """`eff_hitlevel_tbl`'s category 2, against the class's own table."""
    from elbn import Elbn                                       # noqa: PLC0415

    root = pathlib.Path(root)
    disc = Disc(root)
    total = ok = 0
    for c in sorted(CLASSES):
        objbin = root / 'job.cpk' / c / 'objbin.bin'
        if not objbin.is_file():
            print(f'{c}: no objbin.bin')
            continue
        e = Elbn(objbin.read_bytes(), objbin.name)
        ent = e.by_name().get('eff_hitlevel_tbl')
        if ent is None:
            continue
        n = e.word(ent.offset)
        ptr = e.word(ent.offset + 4)
        want = sorted({e.word(ptr + 8 * k + 4) for k in range(n * 5)
                       if e.word(ptr + 8 * k) == 2})
        for sex in 'fm':
            path = (f'character.cpk/motion.cpk/{sex}{c}.pac/{NAME}')
            t = disc.tables.get(path)
            if t is None:
                print(f'{sex}{c}: no table')
                continue
            have = t.by_id()
            miss = [v for v in want if v not in have]
            total += len(want)
            ok += len(want) - len(miss)
            scales = [have[v].scale for v in want if v in have]
            print(f'{sex}{c}  {n:>2} rows  {len(want):>2} distinct (2, id), '
                  f'{len(want) - len(miss):>2} resolve   scales '
                  f'{sorted(set(scales))}'
                  + (f'   missing {miss}' if miss else ''))
    print(f'\n{ok} of {total} category-2 ids are a row of the class own '
          f'effect.bin')
    return 0


def cmd_locators(root) -> int:
    disc = Disc(root, locators=True)
    hit = collections.Counter()
    by_id: dict[int, collections.Counter] = {}
    stray = []
    for path, t in disc.tables.items():
        if t.stage:
            continue
        for r in t.rows:
            if not r.locator:
                hit['no locator'] += 1
                continue
            name = disc.node(path, r.locator)
            if name and name != '?':
                hit['resolves'] += 1
                by_id.setdefault(r.locator, collections.Counter())[name] += 1
            else:
                hit['stray'] += 1
                stray.append((path.split('/')[-2], r.id, r.locator))
    print(f'{hit["resolves"]} of {hit["resolves"] + hit["stray"]} non-zero '
          f'locators resolve on the actor own model; '
          f'{hit["no locator"]:,} rows leave the field at 0')
    print(f'\n  {"locator":<9} {"n":>5}   the node it binds to')
    for k in sorted(by_id):
        c = by_id[k]
        print(f'  {k:<9} {sum(c.values()):>5}   '
              + ', '.join(f'{a} x{b}' for a, b in c.most_common(3)))
    for s in stray:
        print(f'  stray: {s[0]} id {s[1]} locator {s[2]}')
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
    if cmd == 'refs':
        return cmd_refs(rest[0])
    if cmd == 'hitlevel':
        return cmd_hitlevel(rest[0])
    if cmd == 'locators':
        return cmd_locators(rest[0])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
