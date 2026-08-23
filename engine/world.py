"""
world.py - one stage, loaded from the disc, as something a body can stand on.

This is the first file in the repository that is not a reader. Everything
under `tools/` answers *what does the disc say*; this answers *where is the
floor*, which is a different question and the first one an engine has to have
an opinion about.

A stage's `param.pac` holds five files this needs and
[`../tools`](../tools) already opens all five:

    <stage>.col        CCLS, the ground - one welded triangle mesh
    hta.bin            ATIH, the markers - where things are
    borderline.bin     the fences - where the player may not go
    trigger.trg        what happens on entering a marker
    stageparam.bin     ELBN, not used here

Nothing is decoded here that `tools/` does not already decode. What is added
is the two queries a simulation makes every frame:

    floor(x, z)        the highest ground under a point, or None
    blocked(a, b)      does the step from a to b cross a fence

## Where the numbers come from, and where they do not

The mesh, the markers and the fence are the disc's, to the byte. **The axis
convention is an inference and it is stated here rather than buried**: stage
space is Y-up, as [`format_stage.md`](../docs/format_stage.md) established from
the marker table, and a heading of zero faces `+Z`.

That second half is not declared anywhere. It is adopted because it makes the
stage make sense: `010_01_01` spawns the player at `appear01`, whose marker
carries a Y rotation of 180 degrees, and the only exit is 71 metres away in
`-Z`. Under the convention here the spawn faces its exit; under the opposite
one it faces the wall behind it. `run.py` prints the check rather than assuming
it.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

from ccls import Ccls                                         # noqa: E402
from stage import Stage                                       # noqa: E402

# The floor query ignores triangles steeper than this. A stage ground is a
# welded mesh with walls in it, and standing on a wall is not standing.
WALKABLE_COS = 0.34                    # about 70 degrees from horizontal


class World:
    """A stage: its ground, its markers and its fences."""

    def __init__(self, directory):
        d = pathlib.Path(directory)
        files = {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()}
        self.name = d.parent.name if d.name == 'param.pac' else d.name
        self.stage = Stage(self.name, files)
        blob = self.stage.collision
        if blob is None:
            raise SystemExit(f'{self.name}: no .col in {d}')
        self.ccls = Ccls(blob, f'{self.name}.col')
        self.tris = [t for t in self.ccls.triangles()]
        self.lo, self.hi = self.ccls.bounds()
        self._walkable = [t for t in self.tris
                          if abs(_unit_normal(t['v'])[1]) >= WALKABLE_COS]

    # -- markers ----------------------------------------------------------

    def marker(self, name: str):
        m = self.stage.atih.by_name().get(name)
        if m is None:
            raise SystemExit(f'{self.name}: no marker named {name}')
        return m

    def markers(self, kind: str = ''):
        return [m for m in self.stage.markers
                if not kind or m.kind == kind]

    # -- the ground -------------------------------------------------------

    def floor(self, x: float, z: float, ceiling: float = None):
        """The highest walkable ground under `(x, z)`, at or below `ceiling`.

        346 triangles on this stage, so the search is linear and stays
        linear: a broad phase is an optimisation and this is not the session
        for optimisations."""
        best = None
        for t in self._walkable:
            y = _height_at(t['v'], x, z)
            if y is None:
                continue
            if ceiling is not None and y > ceiling:
                continue
            if best is None or y > best:
                best = y
        return best

    def surface(self, x: float, z: float):
        """The surface code of the ground under a point, or None.

        `CCLS` gives every triangle a code from 1 to 13 and nothing on the
        disc says what they name - see [`format_ccls.md`]. Reporting it here
        costs nothing and is how it will eventually get named: walk the stage
        and see where the code changes."""
        best, code = None, None
        for t in self._walkable:
            y = _height_at(t['v'], x, z)
            if y is not None and (best is None or y > best):
                best, code = y, t['code']
        return code

    # -- the fence --------------------------------------------------------

    def fences(self, kind: str = 'chara_line'):
        """The polylines that stop a body. `chara_line` is the player's."""
        return [ln for ln in self.stage.lines if ln.kind == kind]

    def push_out(self, p, radius: float, kind: str = 'chara_line'):
        """Move `p` out of any fence it is within `radius` of.

        This is what makes `col_r` load-bearing: the fence is a line, the body
        is a capsule of radius 0.5 m, so the centre may not come closer than
        0.5 m to the line. Two passes, because a corner is two segments and
        resolving one can violate the other."""
        x, z = p
        touched = []
        for _ in range(4):
            moved = False
            for ln in self.fences(kind):
                pts = [(q[0], q[2]) for q in ln.world()]
                for u, v in zip(pts, pts[1:]):
                    cx, cz = _closest(u, v, (x, z))
                    dx, dz = x - cx, z - cz
                    d = math.hypot(dx, dz)
                    if d >= radius:
                        continue
                    if d < 1e-9:
                        dx, dz, d = v[1] - u[1], u[0] - v[0], 1.0
                        d = math.hypot(dx, dz) or 1.0
                    x = cx + dx / d * radius
                    z = cz + dz / d * radius
                    touched.append(ln.name)
                    moved = True
            if not moved:
                break
        return (x, z), touched

    def blocked(self, a, b, kind: str = 'chara_line'):
        """Does the step from `a` to `b` cross a fence?

        Returns the crossed segment, or None. Treating the fence as a set of
        segments rather than as a closed region is deliberate: whether a
        `borderline` closes is on the open list in
        [`format_stage.md`](../docs/format_stage.md), and a segment test does
        not need to know."""
        for ln in self.fences(kind):
            pts = [(p[0], p[2]) for p in ln.world()]
            for p, q in zip(pts, pts[1:]):
                if _crosses(a, b, p, q):
                    return ln.name, p, q
        return None


# --------------------------------------------------------------------------

def _unit_normal(v):
    a, b, c = v
    e1 = [b[k] - a[k] for k in range(3)]
    e2 = [c[k] - a[k] for k in range(3)]
    n = [e1[1] * e2[2] - e1[2] * e2[1],
         e1[2] * e2[0] - e1[0] * e2[2],
         e1[0] * e2[1] - e1[1] * e2[0]]
    ln = math.sqrt(sum(t * t for t in n))
    return [t / ln for t in n] if ln else [0.0, 0.0, 0.0]


def _height_at(v, x, z):
    """The plane height of a triangle at `(x, z)`, if the point is inside it.

    Barycentric in the XZ projection, which is the right projection because
    the query is "what is under my feet" and feet fall in Y."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = v
    d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
    if abs(d) < 1e-12:
        return None
    u = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d
    w = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d
    t = 1.0 - u - w
    if u < -1e-6 or w < -1e-6 or t < -1e-6:
        return None
    return u * ay + w * by + t * cy


def _closest(a, b, p):
    """The point of segment `a`-`b` nearest `p`, in the XZ plane."""
    ax, az = a
    bx, bz = b
    vx, vz = bx - ax, bz - az
    d2 = vx * vx + vz * vz
    if d2 < 1e-12:
        return a
    t = ((p[0] - ax) * vx + (p[1] - az) * vz) / d2
    t = max(0.0, min(1.0, t))
    return ax + vx * t, az + vz * t


def _side(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _crosses(a, b, p, q):
    """Proper segment intersection, in the XZ plane."""
    d1, d2 = _side(p, q, a), _side(p, q, b)
    d3, d4 = _side(a, b, p), _side(a, b, q)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))
