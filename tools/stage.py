"""
stage.py - reader for the stage layout: `ATIH` markers, `borderline` fences and
`trigger.trg` scripts.

This is where things *are*. [`cmdl.py`](cmdl.py) draws a stage and
[`ccls.py`](ccls.py) says which of it is solid; these three files, all of them
sitting in the same `param.pac`, say where the player enters, where the
monsters come from, where the fence is, and what happens when you walk into it. **163 stages,
5,934 markers, 1,455 polylines, 508 triggers, 0 unreadable.**

**It is not `.map`.** The obvious file to open was the 137 `.map` files, on the
reasoning that 137 against 155 stages is close enough to be per-stage. All 137
begin `CTEX`: they are 256x256 8-bit paletted images, and decoding one draws
the stage's silhouette. `.map` is the **minimap**, and belongs to
[`ctex.py`](ctex.py). The layout was three doors along in the same directory.

## `hta.bin` - `ATIH`, the marker table

163 files, one per stage, 5,934 markers. A named point or box in stage space.

    0x00  'ATIH'
    0x04  u16   0x0106                  constant
    0x06  u16   marker count
    0x08  u32   name pool offset        == align16(0x10 + 40 * count)
    0x0C  u32   zero
    0x10  the markers, 40 bytes each
          the name pool, NUL-terminated, ending at the last byte of the file

The name pool arithmetic closes on all 163 files, and the alignment is what
makes it: `0x10 + 40 * count` is 16-aligned when the count is even and eight
short when it is odd, and 75 files take the first branch and 88 the second.

### The marker

    +0x00  u32       zero                on all 5,934
    +0x04  u32       name pointer        a file offset, into the name pool
    +0x08  u16       rotation x
    +0x0A  u16       rotation y          the one that varies
    +0x0C  u16       rotation z
    +0x0E  u16       zero                on all 5,934
    +0x10  float[3]  position            x y z, stage space, Y up
    +0x1C  float[3]  half-extents        x y z

**The rotations are 16-bit binary angles, 65536 to the turn.** Of the 3,394
non-zero ones, 3,192 are a whole number of degrees on that scale against 2,271
on a scale of 65536 to the half-turn - and the discriminating cases are the odd
degrees, which only the first scale can produce. The values are the ones a
level editor's snap produces: `0x1fff` is 45 degrees, `0x1555` is 30, `0x71c`
is 10. `rotation x` is zero on 5,923 markers and `rotation z` on 5,925, which
is what markers standing on the ground look like.

**The half-extents say which markers are volumes.** A point marker carries a
uniform 0.25 or 0.5 - an editor gizmo, not an extent - and 5,400 of the 5,934
do. A volume marker carries three different numbers: a `jump_next` is
`(10, 25, 1.5)`, a doorway 20 units wide, 50 tall and 3 thick; a `lock_start`
is `(7.5, 15, 7.5)`; an `SE_area` is `(3.75, 25, 3.75)`. So the same record
serves both, and the extents tell them apart - and the split it produces is
its own confirmation, because **every one of the 534 volumes is a kind that
has to be a region**: 270 `jump_*` doorways, 131 `pl_q` quest areas, 44
`lock_start`, 34 `SE_area` and 55 assorted `itembox`, `savearea`, `enemypop`
and `camera_*` - and not one `emgen_pos` or `ef_*` among them.

### What the names say

The engine names its own markers, and the prefix is the kind:

    emgen_pos*   2,123   enemy generator positions - where monsters come from
    obj*           772   objects
    ef*          ~1,200  effects: ef_light, ef_fog, ef_leaf, ef_fire, ef_sm
    appear*        289   where the player and the party enter, a b c per point
    pl_q*          131   quest volumes, named after a quest id
    jump_*         272   map transitions, named after the stage they lead to
    lock_start      44   camera lock
    SE_area         34   sound areas

**The proof that these are stage-space positions is the collision.** Drop each
`appear*` marker straight down onto the stage's own `.col` and 660 of the 661
land on a triangle, with a **median height difference of 0.000** and the tenth
to ninetieth percentile inside a fifth of a unit. Spawn points do not merely
lie in the neighbourhood of the walkable ground; they lie on it. `emgen_pos`
markers sit on it too, 2,113 of 2,123, with a longer tail upwards - p90 is
+3.7 - which is what a flying monster's spawn height looks like.

## `borderline.bin` - the fences

146 `borderline.bin`, 137 `borderline.cmr.bin`, 25 `borderline.se.bin`; 1,455
polylines between them. No magic, no version.

    0x00  u32   polyline count
    then, per polyline:
    +0x00  u32   point count
    +0x04  u32   name pointer
    +0x08  u32   a small number, 0 to 5
    +0x0C  the points, 8 bytes each
    then the name pool

The walk ends exactly at the first polyline's name pointer on all 308 files,
which is the only thing in the format that confirms it: nothing declares a
length and nothing declares where the names begin.

### The point, and the scale

    +0x00  s16   x
    +0x02  s16   y
    +0x04  s16   z
    +0x06  s16   zero

**Hundredths of a world unit.** These are integers where everything else on the
disc is a float, and nothing says what they are worth. Divide by a hundred and
the median `chara_line` vertex sits **0.75 units** from the nearest boundary
edge of the same stage's collision mesh; divide by 128 and it is 4.2, by 64 and
it is 10.2, by 32 and it is 57. The scale is 100, and the identity that finds
it is the one [`format_ccls.md`](../docs/format_ccls.md) already established -
that the single-use edges of the collision mesh are the outline of the stage.
`borderline.bin` is that outline written down again, explicitly, as a fence.

The names say what each fence is for: `chara_line` (700) is where the player
stops, `lock_line` (304) and `lockarea` (101) are camera, `cam_line`/`cmr_line`
(289, in the `.cmr` file) is where the camera stops, `seLine`/`SE_line` (23, in
the `.se` file) is sound. The `.cmr` points carry `y = 1000` where the others
carry zero, so the camera fence stands ten units up.

## `trigger.trg` - the scripts, in the clear

163 files, 508 triggers. No magic either.

    0x00  u32   trigger count
    0x04  count * 12 bytes:
          +0x00  u32   name pointer
          +0x04  u8    event kind, then three zero bytes
          +0x08  u32   script pointer
    then the string pool

**The name is an `ATIH` marker, and that is the binding.** 507 of the 508
trigger names are markers in the same stage's `hta.bin` - the one exception is
`jump_010_01_01` in `900_03_02`, a jump to the first field from a menu stage
that has no such marker. So `hta.bin` places a named volume and `trigger.trg`
hangs a script on it; neither file makes sense without the other.

**The script is source text, not bytecode.** `cfMapJump("010_01_02",
"appear03");` - the name of the destination stage and the name of the `appear`
marker to arrive at, both spelled out. The vocabulary is small: `cfMapJump`
(160), `callQuestScript` (147), `MapJump` (46), `sfMapJumpA`..`F` (49),
`sfAreaVolumeCtrl` (52), `sfUpdateCamera`, `ClosetCamera`, `questStart`,
`room_select`. `callQuestScript` takes the name of another script as a string,
which is where the quest layer starts.

The **event kind** is 0 (440), 1 (25), 2 (21) or 4 (22), and
`sfAreaVolumeCtrl` settles two of them: every one of the 21 kind-2 triggers
passes 0 and every one of the 21 kind-0 and kind-1 triggers passes 1, and the
markers that carry both carry kind 1 with `( 1 )` and kind 2 with `( 0 )`. So
**kind 2 fires on leaving the volume and kinds 0 and 1 on entering it**. Kind 4
is the town: `ClosetCamera`, `RecycleboxCamera`, `room_select`, `questStart` -
things you walk up to and press a button on.

## Reading order

    check    every arithmetic identity above, on every stage
    survey   the census, by marker kind and by script function
    info     one stage: its markers, its fences and its triggers
    obj      the layout as Wavefront OBJ, in the same space as `ccls.py obj`
"""

from __future__ import annotations

import collections
import math
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

ATIH = b'ATIH'
MARKER = 40
GIZMO = (0.25, 0.5)          # the uniform half-extents an editor point writes
BORDER_SCALE = 100.0         # borderline points are hundredths of a unit
KIND = {0: 'enter', 1: 'enter', 2: 'leave', 4: 'interact'}

LAYOUT = ('borderline.bin', 'borderline.cmr.bin', 'borderline.se.bin')


def turn(a: int) -> float:
    """A 16-bit binary angle in degrees, 65536 to the turn."""
    return a * 360.0 / 65536.0


def cstr(buf: bytes, o: int) -> str:
    return buf[o:buf.index(b'\0', o)].decode('ascii', 'replace')


class Marker:
    __slots__ = ('name', 'rotation', 'position', 'extents')

    def __init__(self, buf: bytes, o: int):
        self.name = cstr(buf, struct.unpack_from('>I', buf, o + 4)[0])
        self.rotation = tuple(turn(a) for a
                              in struct.unpack_from('>3H', buf, o + 8))
        self.position = struct.unpack_from('>3f', buf, o + 0x10)
        self.extents = struct.unpack_from('>3f', buf, o + 0x1C)

    @property
    def kind(self) -> str:
        """The prefix of the name, which is what the engine sorts markers by."""
        n = self.name.rstrip('0123456789').rstrip('_')
        return n or self.name

    @property
    def volume(self) -> bool:
        """A point marker carries a uniform editor gizmo; a volume does not.

        The three extents of a gizmo agree only to about a part in ten
        million - a marker the editor rotated writes 0.4999999 twice and 0.5
        once - so the comparison has to be a loose one."""
        e = self.extents
        return max(e) > max(GIZMO) * 1.001 or max(e) > min(e) * 1.01

    def __repr__(self) -> str:
        p = '  '.join(f'{v:9.3f}' for v in self.position)
        e = '  '.join(f'{v:7.3f}' for v in self.extents)
        r = ' '.join(f'{v:7.2f}' for v in self.rotation)
        return (f'{self.name:<20s} {p}   rot {r}   '
                f'{"box" if self.volume else "pt "} {e}')


class Atih:
    """The marker table of one stage."""

    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != ATIH:
            raise ValueError(f'{label}: not an ATIH ({buf[:4]!r})')
        self.label = label
        self.buf = buf
        self.version, self.count = struct.unpack_from('>HH', buf, 4)
        self.pool, spare = struct.unpack_from('>II', buf, 8)
        if spare:
            raise ValueError(f'{label}: word at 0x0C is {spare:#x}, not zero')
        self.markers = [Marker(buf, 0x10 + MARKER * i)
                        for i in range(self.count)]

    @property
    def expected_pool(self) -> int:
        return (0x10 + MARKER * self.count + 15) & ~15

    def by_name(self) -> dict[str, Marker]:
        return {m.name: m for m in self.markers}


class Polyline:
    __slots__ = ('name', 'flag', 'points')

    def __init__(self, name: str, flag: int, points: list):
        self.name, self.flag, self.points = name, flag, points

    @property
    def kind(self) -> str:
        return self.name.rstrip('0123456789').rstrip('_')

    def world(self):
        """The points in world units."""
        return [tuple(v / BORDER_SCALE for v in p) for p in self.points]


class Borderline:
    """One of the three fence files. No magic; the walk is the only check."""

    def __init__(self, buf: bytes, label: str = ''):
        self.label = label
        self.buf = buf
        self.count = struct.unpack_from('>I', buf, 0)[0]
        self.lines: list[Polyline] = []
        o = 4
        self.first_name = 0
        for i in range(self.count):
            n, name, flag = struct.unpack_from('>3I', buf, o)
            if not self.first_name:
                self.first_name = name
            pts = [struct.unpack_from('>3h', buf, o + 12 + 8 * k)
                   for k in range(n)]
            for k in range(n):
                if struct.unpack_from('>h', buf, o + 12 + 8 * k + 6)[0]:
                    raise ValueError(f'{label}: point {k} of line {i} '
                                     f'has a non-zero fourth word')
            self.lines.append(Polyline(cstr(buf, name), flag, pts))
            o += 12 + 8 * n
        self.end = o


class Trigger:
    __slots__ = ('name', 'kind', 'script')

    def __init__(self, name: str, kind: int, script: str):
        self.name, self.kind, self.script = name, kind, script

    @property
    def event(self) -> str:
        return KIND.get(self.kind, f'kind {self.kind}')

    @property
    def call(self) -> str:
        return self.script.split('(', 1)[0]


class Trg:
    """The trigger list of one stage. No magic."""

    def __init__(self, buf: bytes, label: str = ''):
        self.label = label
        self.count = struct.unpack_from('>I', buf, 0)[0]
        self.pool = 4 + 12 * self.count
        self.triggers: list[Trigger] = []
        for i in range(self.count):
            name, kind, script = struct.unpack_from('>3I', buf, 4 + 12 * i)
            if kind & 0x00FFFFFF:
                raise ValueError(f'{label}: trigger {i} kind word is '
                                 f'{kind:#x}, not a byte')
            self.triggers.append(
                Trigger(cstr(buf, name), kind >> 24, cstr(buf, script)))


class Stage:
    """Everything `param.pac` says about where things are."""

    def __init__(self, name: str, files: dict[str, bytes]):
        self.name = name
        self.files = files
        self.atih = (Atih(files['hta.bin'], f'{name}/hta.bin')
                     if 'hta.bin' in files else None)
        self.trg = (Trg(files['trigger.trg'], f'{name}/trigger.trg')
                    if 'trigger.trg' in files else None)
        self.borders: dict[str, Borderline] = {}
        for fn in LAYOUT:
            if fn in files:
                self.borders[fn] = Borderline(files[fn], f'{name}/{fn}')

    @property
    def markers(self) -> list[Marker]:
        return self.atih.markers if self.atih else []

    @property
    def lines(self) -> list[Polyline]:
        return [ln for b in self.borders.values() for ln in b.lines]

    @property
    def triggers(self) -> list[Trigger]:
        return self.trg.triggers if self.trg else []

    @property
    def collision(self):
        """The stage's own `.col`, if it is here."""
        return self.files.get(f'{self.name}.col')


# --------------------------------------------------------------------------

WANTED = {'hta.bin', 'trigger.trg', *LAYOUT}


def collect(root, want: str = ''):
    """Yield `(stage name, {basename: bytes})` for every stage directory."""
    root = pathlib.Path(root)
    found: dict[str, dict[str, bytes]] = collections.defaultdict(dict)

    def note(path: str, blob: bytes) -> None:
        parts = path.split('/')
        if len(parts) < 3 or parts[-2] != 'param.pac':
            return
        base = parts[-1]
        stage = parts[-3]
        if base in WANTED or base == f'{stage}.col':
            found[stage][base] = blob

    if any(p.is_file() for p in root.glob('*.cpk')):
        for path, blob in leaves(root, want):
            note(path, blob)
    else:
        for p in sorted(root.rglob('*')):
            if p.is_file():
                note(p.relative_to(root).as_posix(), p.read_bytes())

    for name in sorted(found):
        if 'hta.bin' in found[name] or 'trigger.trg' in found[name]:
            yield name, found[name]


def stages(root, want: str = ''):
    for name, files in collect(root, want):
        yield Stage(name, files)


def _one(root, name: str) -> Stage:
    for st in stages(root):
        if st.name == name:
            return st
    raise SystemExit(f'not found: {name}')


# --------------------------------------------------------------------------

def ground_height(col: bytes, x: float, z: float) -> float | None:
    """Drop a plumb line onto the collision mesh and return what it hits."""
    from ccls import Ccls                                      # noqa: PLC0415

    best = None
    for t in Ccls(col).triangles():
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = t['v']
        d = (z1 - z2) * (x0 - x2) + (x2 - x1) * (z0 - z2)
        if abs(d) < 1e-9:
            continue
        a = ((z1 - z2) * (x - x2) + (x2 - x1) * (z - z2)) / d
        b = ((z2 - z0) * (x - x2) + (x0 - x2) * (z - z2)) / d
        c = 1.0 - a - b
        if a < -1e-4 or b < -1e-4 or c < -1e-4:
            continue
        y = a * y0 + b * y1 + c * y2
        if best is None or y > best:
            best = y
    return best


def cmd_check(root) -> int:
    tally: dict[str, int] = {}
    errs: list[str] = []
    drop: list[float] = []
    n = markers = lines = triggers = 0

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /n'] = tally.get(k + ' /n', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    for st in stages(root):
        n += 1
        if st.atih:
            a = st.atih
            markers += a.count
            note('ATIH  pool == align16(0x10 + 40n)',
                 a.pool == a.expected_pool,
                 f'{st.name}: pool {a.pool:#x}, expected {a.expected_pool:#x}')
            names = [m.name for m in a.markers]
            note('ATIH  names ascending and unique',
                 names == sorted(names) and len(set(names)) == len(names),
                 f'{st.name}: names out of order or repeated')
            note('ATIH  leading word zero',
                 all(struct.unpack_from('>I', a.buf, 0x10 + MARKER * i)[0] == 0
                     for i in range(a.count)), f'{st.name}: +0x00 not zero')
            note('ATIH  fourth angle zero',
                 all(struct.unpack_from('>H', a.buf, 0x10 + MARKER * i + 14)[0]
                     == 0 for i in range(a.count)),
                 f'{st.name}: +0x0E not zero')
            last = max((struct.unpack_from('>I', a.buf,
                                            0x10 + MARKER * i + 4)[0]
                        for i in range(a.count)), default=a.pool)
            note('ATIH  name pool ends at EOF',
                 a.buf.index(b'\0', last) + 1 == len(a.buf),
                 f'{st.name}: pool does not reach the end')

        for fn, b in st.borders.items():
            lines += len(b.lines)
            note('border  walk ends at the name pool', b.end == b.first_name,
                 f'{st.name}/{fn}: walked to {b.end:#x}, '
                 f'names at {b.first_name:#x}')

        if st.trg:
            triggers += st.trg.count
            known = st.atih.by_name() if st.atih else {}
            for t in st.trg.triggers:
                note('trg  name is an ATIH marker', t.name in known,
                     f'{st.name}: trigger {t.name!r} names no marker')
                note('trg  event kind is 0, 1, 2 or 4', t.kind in KIND,
                     f'{st.name}: {t.name} kind {t.kind}')

        col = st.collision
        if col:
            for m in st.markers:
                if not m.name.startswith('appear'):
                    continue
                y = ground_height(col, m.position[0], m.position[2])
                note('appear  stands over the collision ground', y is not None,
                     f'{st.name}: {m.name} is over no triangle')
                if y is not None:
                    drop.append(m.position[1] - y)
                    note('appear  within 2 units of it',
                         abs(y - m.position[1]) < 2.0,
                         f'{st.name}: {m.name} at y {m.position[1]:.2f}, '
                         f'ground {y:.2f}')

    print(f'{n} stages, {markers} markers, {lines} polylines, '
          f'{triggers} triggers')
    for k in sorted(tally):
        if k.endswith(' /n'):
            continue
        print(f'  {tally[k]:6d} / {tally[k + " /n"]:<6d} {k}')
    if drop:
        drop.sort()
        print(f'\n  appear height above the ground it stands on: '
              f'median {drop[len(drop) // 2]:+.3f}, '
              f'p10 {drop[len(drop) // 10]:+.3f}, '
              f'p90 {drop[len(drop) * 9 // 10]:+.3f}')
    if errs:
        print('\nfirst failures:')
        print('\n'.join(errs))
    return 0


def cmd_survey(root) -> int:
    kinds: collections.Counter = collections.Counter()
    volumes: collections.Counter = collections.Counter()
    lines: collections.Counter = collections.Counter()
    calls: collections.Counter = collections.Counter()
    events: collections.Counter = collections.Counter()
    n = 0
    for st in stages(root):
        n += 1
        for m in st.markers:
            kinds[m.kind] += 1
            if m.volume:
                volumes[m.kind] += 1
        for ln in st.lines:
            lines[ln.kind] += 1
        for t in st.triggers:
            calls[t.call] += 1
            events[t.event] += 1

    print(f'{n} stages\n')
    print(f'{"marker":<16s} {"n":>6s} {"volumes":>8s}')
    for k, v in kinds.most_common(24):
        print(f'  {k:<14s} {v:6d} {volumes.get(k, 0):8d}')
    print(f'\n{"polyline":<16s} {"n":>6s}')
    for k, v in lines.most_common(12):
        print(f'  {k:<14s} {v:6d}')
    print(f'\n{"script":<20s} {"n":>6s}')
    for k, v in calls.most_common(20):
        print(f'  {k:<18s} {v:6d}')
    print('\nevents  ' + '  '.join(f'{k} {v}' for k, v in events.most_common()))
    return 0


def cmd_info(root, name: str) -> int:
    st = _one(root, name)
    print(st.name)
    if st.atih:
        a = st.atih
        print(f'  hta.bin        {a.count} markers, pool at {a.pool:#x}')
    for fn, b in st.borders.items():
        pts = sum(len(ln.points) for ln in b.lines)
        print(f'  {fn:<14s} {b.count} polylines, {pts} points')
    if st.trg:
        print(f'  trigger.trg    {st.trg.count} triggers')
    if st.collision:
        from ccls import Ccls                                  # noqa: PLC0415
        c = Ccls(st.collision)
        lo, hi = c.bounds()
        print(f'  {st.name}.col  {c.count} triangles, '
              f'x {lo[0]:.1f}..{hi[0]:.1f}  y {lo[1]:.1f}..{hi[1]:.1f}  '
              f'z {lo[2]:.1f}..{hi[2]:.1f}')

    print('\nmarkers')
    for m in st.markers:
        print(f'  {m!r}')
    print('\npolylines')
    for fn, b in st.borders.items():
        for ln in b.lines:
            p = ln.world()
            xs = [v[0] for v in p]
            zs = [v[2] for v in p]
            print(f'  {ln.name:<16s} {fn:<20s} {len(p):4d} points  '
                  f'flag {ln.flag}  x {min(xs):8.2f}..{max(xs):8.2f}  '
                  f'z {min(zs):8.2f}..{max(zs):8.2f}')
    print('\ntriggers')
    known = st.atih.by_name() if st.atih else {}
    for t in st.triggers:
        m = known.get(t.name)
        where = ('  '.join(f'{v:8.2f}' for v in m.position) if m else '?')
        print(f'  {t.name:<18s} on {t.event:<9s} {where}   {t.script}')
    return 0


def cmd_markers(root, name: str) -> int:
    for m in _one(root, name).markers:
        print(repr(m))
    return 0


def cmd_triggers(root, name: str) -> int:
    for t in _one(root, name).triggers:
        print(f'{t.name:<20s} {t.event:<9s} {t.script}')
    return 0


def cmd_grep(root, text: str) -> int:
    lo = text.lower()
    for st in stages(root):
        for m in st.markers:
            if lo in m.name.lower():
                print(f'{st.name:<12s} marker   {m!r}')
        for t in st.triggers:
            if lo in t.name.lower() or lo in t.script.lower():
                print(f'{st.name:<12s} trigger  {t.name:<18s} '
                      f'{t.event:<9s} {t.script}')
        for ln in st.lines:
            if lo in ln.name.lower():
                print(f'{st.name:<12s} line     {ln.name:<18s} '
                      f'{len(ln.points)} points')
    return 0


BOX = ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1),
       (-1, 1, -1), (1, 1, -1), (1, 1, 1), (-1, 1, 1))
EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
         (0, 4), (1, 5), (2, 6), (3, 7))


def cmd_obj(root, name: str, out: str) -> int:
    """The layout as line geometry, in the same space as `ccls.py obj`."""
    st = _one(root, name)
    lines = [f'# {st.name} layout: {len(st.markers)} markers, '
             f'{len(st.lines)} polylines']
    v = 0
    for m in st.markers:
        cy = math.cos(math.radians(m.rotation[1]))
        sy = math.sin(math.radians(m.rotation[1]))
        lines.append(f'o {m.name}')
        for bx, by, bz in BOX:
            x, y, z = bx * m.extents[0], by * m.extents[1], bz * m.extents[2]
            lines.append(f'v {m.position[0] + x * cy + z * sy:.4f} '
                         f'{m.position[1] + y:.4f} '
                         f'{m.position[2] - x * sy + z * cy:.4f}')
        for a, b in EDGES:
            lines.append(f'l {v + a + 1} {v + b + 1}')
        v += 8
    for fn, b in st.borders.items():
        for ln in b.lines:
            pts = ln.world()
            if not pts:
                continue
            lines.append(f'o {ln.name}')
            for p in pts:
                lines.append(f'v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}')
            lines.append('l ' + ' '.join(str(v + k + 1)
                                         for k in range(len(pts))))
            v += len(pts)
    pathlib.Path(out).write_text('\n'.join(lines) + '\n')
    print(f'{st.name}  ->  {out}   {v} vertices')
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
    if cmd == 'info':
        return cmd_info(rest[0], rest[1])
    if cmd == 'markers':
        return cmd_markers(rest[0], rest[1])
    if cmd == 'triggers':
        return cmd_triggers(rest[0], rest[1])
    if cmd == 'grep':
        return cmd_grep(rest[0], rest[1])
    if cmd == 'obj':
        return cmd_obj(rest[0], rest[1], rest[2])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
