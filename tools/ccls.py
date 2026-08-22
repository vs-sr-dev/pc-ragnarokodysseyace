"""
ccls.py - reader for `CCLS`, the stage collision format.

155 files, one per stage, named `<stage>.col` and living in `param.pac` beside
the stage's models. **107,343 triangles, 0 unreadable.** This is the ground the
game stands on: with [`cmdl.py`](cmdl.py) drawing a stage and this saying which
of it is solid, a stage stops being scenery.

`CCLS` is the plain one of the family. Same 16-byte shell as `CMDL`, `CNOM` and
`CTEX` - magic, payload size, `0x00010005`, zero - but **no `POF0`**, so no
pointers, so no directory to follow: it is a header and then one flat array,
and the arithmetic closes on all 155 files.

    file length == 16 + payload + 16

    0x00  'CCLS'
    0x04  u32   payload size
    0x08  u32   0x00010005
    0x0C  u32   zero
    0x10  u32   1
    0x14  u32   zero
    0x18  u32   triangle count
    0x1C  u32   zero
    0x20  u32   0x7fffffff
    0x24  the triangles, 112 bytes each
          then twelve zero bytes, then sixteen more

    0x24 + 112 * count + 12 == 0x10 + payload size     on all 155 files

## The triangle

    +0x00  float[3]  v0
    +0x0C  float[3]  v1
    +0x18  float[3]  v2
    +0x24  float[3]  the face normal
    +0x30  u32       surface code, 1 to 13
    +0x34  s32[15]   all 1, or all -1

**The normal is the normalised cross product of `v1 - v0` and `v2 - v0`, on
107,338 of the 107,343**, with the same winding every time; the five that are
not are degenerate triangles with no normal to compute. That is what identifies
the record, and it is worth saying how easily it is missed: read the array as
starting where a header of `0x20` bytes would end, at `0x30`, and every field
lands twelve bytes late. The count still divides, the vertices still look like
vertices, and the normal is still perpendicular to `v1 - v0` on every record -
because a plane normal is perpendicular to *any* edge in its plane. Only the
cross product notices, and it says the array starts at `0x24`, twelve bytes
into what looks like the header.

**It is a ground mesh, not a collision hull.** 98.4% of the triangles have a
normal pointing up within 45 degrees, and only 814 of 107,343 stand vertical.
The engine is not tracing a closed volume here; it is deciding what is walkable
and where the walkable region ends.

**And it is welded.** Match triangles by exact vertex equality and 150,236 of
the disc's edges are shared by exactly two triangles, 21,448 by one, and 31 by
more - so this is a proper surface with a boundary, not a soup, and the
vertices meet to the last bit with no T-junctions anywhere. 144 of the 155
stages are clean on their own. That boundary is the answer to where the walls
are: there are not enough vertical triangles to fence a level, because the edge
of the walkable region *is* the fence.

**The coordinates are the stage's own model space**, with nothing between them:
on 124 of the 155 stages every collision vertex lies inside the bounding box of
the stage's `ground.CMDL` - which draws a good deal further out than the
collision does, since the backdrop terrain is geometry nobody walks on. Note
that this is Y-up - the thinnest axis of a stage ground is `y` on 119 of 155 -
whereas a character's vertex buffer is Z-up. Stage geometry needs no `Rx(90)`;
skinned geometry has one baked into its inverse bind matrices.

The **surface code** runs 1 to 13, with 8 the commonest at half the disc, and a
stage uses two or three of them - `100_03_01` uses 8 and 13, `110_01_02` uses 3
and 7. Drawn as a plan they are broad contiguous patches, not scattered, which
is what a terrain type looks like: footstep sound and footprint effect are what
a per-triangle ground code usually selects, though the disc does not say so.

The **fifteen words** move as one - all 1, or all -1, never mixed - and so does
a whole file. **146 stages are entirely 1 and 9 are entirely -1**, with no stage
mixing the two, so this is not a per-triangle attribute at all: it is one bit
about the stage, written into every triangle fifteen times over. The nine are
`010_01_01`, `010_01_02`, `010_02_02`, `010_02_03`, `020_01_02`, `020_02_02`,
`020_02_03`, `020_02_04` and `020_03_01` - the first two areas of the game, and
nothing later. What the bit means is open.

Usage:
  python ccls.py check <dir>              the whole arithmetic, every file
  python ccls.py survey <dir>             every stage, largest first
  python ccls.py info <dir> <name>        header, bounds, codes
  python ccls.py dump <dir> <name> [n]    the first n triangles
  python ccls.py obj <dir> <name> <out>   export the ground as Wavefront OBJ
  python ccls.py find <dir> <glob>        locate a stage at any depth
"""
from __future__ import annotations

import collections
import fnmatch
import math
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

MAGIC = b'CCLS'
HEADER = 0x10
FIRST = 0x24
TRIANGLE = 112
FLAGS = 15


class Ccls:
    def __init__(self, buf: bytes, label: str = ''):
        if buf[:4] != MAGIC:
            raise ValueError(f'{label}: not a CCLS ({buf[:4]!r})')
        self.label = label
        self.buf = buf
        self.size, self.version, spare = struct.unpack_from('>III', buf, 4)
        self.end = HEADER + self.size
        if len(buf) != self.end + 16:
            raise ValueError(f'{label}: {len(buf)} bytes, but 32 + '
                             f'{self.size} is {self.size + 32}')
        if spare:
            raise ValueError(f'{label}: word at 0x0C is {spare:#x}, not zero')
        self.count = struct.unpack_from('>I', buf, 0x18)[0]
        self.sentinel = struct.unpack_from('>I', buf, 0x20)[0]

    def triangle(self, i: int) -> dict:
        o = FIRST + i * TRIANGLE
        b = self.buf
        return {
            'v': [struct.unpack_from('>3f', b, o + 12 * k) for k in range(3)],
            'normal': struct.unpack_from('>3f', b, o + 0x24),
            'code': struct.unpack_from('>I', b, o + 0x30)[0],
            'flags': struct.unpack_from(f'>{FLAGS}i', b, o + 0x34),
        }

    def triangles(self):
        for i in range(self.count):
            yield self.triangle(i)

    def bounds(self) -> tuple[list[float], list[float]]:
        lo = [float('inf')] * 3
        hi = [float('-inf')] * 3
        for t in self.triangles():
            for p in t['v']:
                for k in range(3):
                    lo[k] = min(lo[k], p[k])
                    hi[k] = max(hi[k], p[k])
        return lo, hi


def cross(t: dict) -> tuple[list[float], float]:
    """The face normal the three vertices imply, and its length."""
    a, b, c = t['v']
    e1 = [b[k] - a[k] for k in range(3)]
    e2 = [c[k] - a[k] for k in range(3)]
    n = [e1[1] * e2[2] - e1[2] * e2[1],
         e1[2] * e2[0] - e1[0] * e2[2],
         e1[0] * e2[1] - e1[1] * e2[0]]
    ln = math.sqrt(sum(v * v for v in n))
    return ([v / ln for v in n] if ln else n), ln


# --------------------------------------------------------------------------

def collect(root, want: str = ''):
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if not p.is_file():
                continue
            with p.open('rb') as fh:
                if fh.read(4) != MAGIC:
                    continue
            yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, want):
        if blob[:4] == MAGIC:
            yield path, blob


def _one(root, name) -> tuple[str, Ccls]:
    for path, blob in collect(root):
        if path == name or path.rsplit('/', 1)[-1] == name:
            return path, Ccls(blob, path)
    raise SystemExit(f'not found: {name}')


def cmd_check(root) -> int:
    files = bad = tris = 0
    tally: dict[str, int] = {}
    errs: list[str] = []

    def note(k: str, ok: bool, detail: str = '') -> None:
        tally[k] = tally.get(k, 0) + (1 if ok else 0)
        tally[k + ' /n'] = tally.get(k + ' /n', 0) + 1
        if not ok and len(errs) < 12:
            errs.append(f'  {detail}')

    for path, blob in collect(root):
        try:
            c = Ccls(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            if len(errs) < 12:
                errs.append(f'  {exc}')
            continue
        files += 1
        note('the array fills the payload, with twelve bytes over',
             FIRST + c.count * TRIANGLE + 12 == c.end,
             f'{path}: {c.count} triangles do not fill {c.size} bytes')
        note('those twelve bytes are zero',
             blob[c.end - 12:c.end] == bytes(12), f'{path}: tail not zero')
        note('the sixteen-byte tail is zero', blob[-16:] == bytes(16),
             f'{path}: tail not zero')
        note('the sentinel at 0x20 is 0x7fffffff', c.sentinel == 0x7FFFFFFF,
             f'{path}: sentinel {c.sentinel:#x}')
        normal = degenerate = unit = flags = True
        edges: dict[frozenset, int] = {}
        for t in c.triangles():
            tris += 1
            want, ln = cross(t)
            v = [tuple(p) for p in t['v']]
            for k in range(3):
                e = frozenset((v[k], v[(k + 1) % 3]))
                edges[e] = edges.get(e, 0) + 1
            if ln < 1e-9:
                degenerate = False
                continue
            got = t['normal']
            if abs(sum(want[k] * got[k] for k in range(3)) - 1) > 2e-3:
                normal = False
            if abs(math.sqrt(sum(v * v for v in got)) - 1) > 1e-3:
                unit = False
            if len(set(t['flags'])) != 1 or t['flags'][0] not in (1, -1):
                flags = False
        note('no edge is shared by more than two triangles',
             max(edges.values(), default=0) <= 2,
             f'{path}: an edge is used by more than two triangles')
        note('the whole file agrees on the flag',
             len({t['flags'][0] for t in c.triangles()}) <= 1,
             f'{path}: the flag is not uniform')
        note('the normal is the cross product of the two edges', normal,
             f'{path}: a normal does not match its vertices')
        note('no degenerate triangles', degenerate,
             f'{path}: a triangle has no area')
        note('the normal is a unit vector', unit,
             f'{path}: a normal is not unit')
        note('the fifteen flag words agree, and are 1 or -1', flags,
             f'{path}: mixed flags')

    print(f'{files} CCLS, {tris:,} triangles, {bad} unreadable')
    for k in sorted(tally):
        if k.endswith(' /n'):
            continue
        print(f'  {tally[k]:>5,} / {tally[k + " /n"]:<5,}  {k}')
    for line in errs:
        print(line)
    return 1 if bad else 0


def cmd_survey(root) -> int:
    out = []
    for path, blob in collect(root):
        try:
            c = Ccls(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        lo, hi = c.bounds()
        codes = sorted({t['code'] for t in c.triangles()})
        out.append((c.count, hi[0] - lo[0], hi[2] - lo[2], codes, path))
    out.sort(key=lambda r: -r[0])
    print(f'{len(out)} CCLS, largest first')
    for n, w, d, codes, path in out[:40]:
        print(f'  {n:>7,} triangles  {w:>8.1f} x {d:<8.1f}  '
              f'codes {",".join(str(k) for k in codes):<12}  {path}')
    return 0


def cmd_info(root, name) -> int:
    path, c = _one(root, name)
    lo, hi = c.bounds()
    codes: collections.Counter = collections.Counter()
    up = flat = marked = 0
    for t in c.triangles():
        codes[t['code']] += 1
        up += t['normal'][1] > 0.707
        flat += abs(t['normal'][1]) < 0.3
        marked += t['flags'][0] == -1
    print(path)
    print(f'  payload     {c.size:,} bytes')
    print(f'  triangles   {c.count:,}')
    print('  bounds      ' + '  '.join(f'{lo[k]:.2f} .. {hi[k]:.2f}'
                                       for k in range(3)))
    print(f'  walkable    {up:,} face up, {flat:,} stand vertical')
    print(f'  flagged     {marked:,} carry -1')
    print('  codes       ' + ', '.join(f'{k}: {v:,}'
                                       for k, v in sorted(codes.items())))
    return 0


def cmd_dump(root, name, n='8') -> int:
    path, c = _one(root, name)
    print(f'{path}  {c.count:,} triangles')
    for i in range(min(int(n), c.count)):
        t = c.triangle(i)
        print(f'  {i:>6}  code {t["code"]:>2}  flag {t["flags"][0]:>2}  '
              + '  '.join('(%8.3f %8.3f %8.3f)' % p for p in t['v']))
        print('          normal %7.4f %7.4f %7.4f' % t['normal'])
    return 0


def cmd_obj(root, name, out) -> int:
    path, c = _one(root, name)
    lines = [f'# {path}', f'# {c.count} collision triangles']
    groups: dict[int, list[int]] = {}
    for i, t in enumerate(c.triangles()):
        for p in t['v']:
            lines.append('v %.6f %.6f %.6f' % p)
        groups.setdefault(t['code'], []).append(i)
    for code in sorted(groups):
        lines.append(f'g code_{code}')
        for i in groups[code]:
            b = 3 * i + 1
            lines.append(f'f {b} {b + 1} {b + 2}')
    pathlib.Path(out).write_text('\n'.join(lines) + '\n', encoding='ascii')
    print(f'{path}  ->  {out}  ({c.count:,} triangles, '
          f'{len(groups)} surface codes)')
    return 0


def cmd_find(root, pattern) -> int:
    n = 0
    for path, blob in collect(root):
        if fnmatch.fnmatch(path.rsplit('/', 1)[-1], pattern) \
                or fnmatch.fnmatch(path, pattern):
            try:
                c = Ccls(blob, path)
            except Exception:                                 # noqa: BLE001
                continue
            n += 1
            print(f'  {c.count:>7,} triangles  {path}')
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
    if cmd == 'info':
        return cmd_info(rest[0], rest[1])
    if cmd == 'dump':
        return cmd_dump(rest[0], rest[1], *rest[2:3])
    if cmd == 'obj':
        return cmd_obj(rest[0], rest[1], rest[2])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
