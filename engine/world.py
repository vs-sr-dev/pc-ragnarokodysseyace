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
is the queries a simulation makes and a reader does not:

    floor(x, z)        the highest ground under a point, or None
    blocked(a, b)      does the step from a to b cross a fence
    path(a, b)         waypoints from a to b over the ground

`path` is session 24's, and it is the same mesh read as a navigation mesh -
see `graph` below for why that costs no new data at all, and
[`milestone_quest.md`](../docs/milestone_quest.md) for what it is for.

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
        # A stage's `lockarea` and `lock_line` polylines are down until a
        # quest raises them - `cfStartPieceLock` is what does it, and
        # `mission.py` puts the names it raises in here. A fence in this set
        # stops a body exactly as `chara_line` does.
        self.raised: set = set()

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

    # -- the ground as a graph --------------------------------------------

    def graph(self) -> dict:
        """Which walkable triangles share an edge with which.

        [`format_ccls.md`](../docs/format_ccls.md) established that the mesh
        is **welded** - 150,236 of the disc's edges are shared by exactly two
        triangles, matched by exact vertex equality, with no T-junctions - and
        that *the edge of the walkable region is the fence*, because there are
        not enough vertical triangles to wall a level. Both of those facts
        together say the ground mesh is already a navigation mesh, and this is
        what reads it as one. Nothing is decoded here that
        [`../tools/ccls.py`](../tools/ccls.py) does not decode.
        """
        if getattr(self, '_adj', None) is None:
            edges = {}
            for i, t in enumerate(self._walkable):
                for k in range(3):
                    e = tuple(sorted((t['v'][k], t['v'][(k + 1) % 3])))
                    edges.setdefault(e, []).append(i)
            adj = [[] for _ in self._walkable]
            for e, who in edges.items():
                if len(who) != 2:
                    continue
                mid = ((e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2,
                       (e[0][2] + e[1][2]) / 2)
                adj[who[0]].append((who[1], mid))
                adj[who[1]].append((who[0], mid))
            self._adj = adj
            self._centre = [((t['v'][0][0] + t['v'][1][0] + t['v'][2][0]) / 3,
                             (t['v'][0][1] + t['v'][1][1] + t['v'][2][1]) / 3,
                             (t['v'][0][2] + t['v'][1][2] + t['v'][2][2]) / 3)
                            for t in self._walkable]
        return self._adj

    def triangle_at(self, x: float, z: float, y: float = None):
        """The index of the walkable triangle under a point."""
        best, at = None, None
        for i, t in enumerate(self._walkable):
            h = _height_at(t['v'], x, z)
            if h is None or (y is not None and h > y + 1.0):
                continue
            if best is None or h > best:
                best, at = h, i
        return at

    def nearest_triangle(self, p):
        """The walkable triangle whose centre is nearest a point.

        A `jump_` marker sits in a doorway and a `lockarea` centre is the
        middle of a room, and neither is guaranteed to be over ground the
        mesh calls walkable. This is what a destination falls back to.
        """
        self.graph()
        best, at = None, None
        for i, c in enumerate(self._centre):
            d = math.dist((c[0], c[2]), p)
            if best is None or d < best:
                best, at = d, i
        return at

    def path(self, a, b, radius: float = 0.5, kind: str = 'chara_line'):
        """Waypoints from `a` to `b` over the ground, or None.

        A* across the triangle graph, with a step refused when the segment
        between the two centres crosses a fence or when the shared edge is
        narrower than the body. The waypoints are the shared edges' midpoints,
        which is the crossing the mesh itself offers.

        This is the engine's own, like the sliding rule in
        [`actor.py`](actor.py): the disc says where the ground is and where
        the fence is, and says nothing at all about how a body gets across a
        room.
        """
        adj = self.graph()
        start = self.triangle_at(a[0], a[1])
        goal = self.triangle_at(b[0], b[1])
        if goal is None:
            goal = self.nearest_triangle(b)     # a marker off the mesh
        if start is None:
            start = self.nearest_triangle(a)
        if start is None or goal is None:
            return None
        if start == goal:
            return [b]
        segs = []
        for ln in self.fences(kind):
            pts = [(q[0], q[2]) for q in ln.world()]
            segs += list(zip(pts, pts[1:]))
        c = self._centre
        end = (c[goal][0], c[goal][2])

        def h(i):
            return math.dist((c[i][0], c[i][2]), end)

        import heapq                                       # noqa: PLC0415
        seen = {start: (0.0, None, None)}
        heap = [(h(start), start)]
        while heap:
            _, i = heapq.heappop(heap)
            if i == goal:
                break
            g0 = seen[i][0]
            for j, mid in adj[i]:
                p = (c[i][0], c[i][2])
                q = (c[j][0], c[j][2])
                if any(_crosses(p, q, u, v) for u, v in segs):
                    continue
                if any(math.dist(_closest(u, v, (mid[0], mid[2])),
                                 (mid[0], mid[2])) < radius * 0.6
                       for u, v in segs):
                    continue
                g = g0 + math.dist(p, q)
                if j in seen and seen[j][0] <= g:
                    continue
                seen[j] = (g, i, mid)
                heapq.heappush(heap, (g + h(j), j))
        if goal not in seen:
            return None
        last = (b if self.triangle_at(b[0], b[1]) is not None
                else (c[goal][0], c[goal][2]))
        out, i = [last], goal
        while seen[i][1] is not None:
            mid = seen[i][2]
            out.append((mid[0], mid[2]))
            i = seen[i][1]
        out.reverse()
        return out

    # -- the fence --------------------------------------------------------

    def fences(self, kind: str = 'chara_line'):
        """The polylines that stop a body. `chara_line` is the player's."""
        return [ln for ln in self.stage.lines
                if ln.kind == kind or ln.name in self.raised]

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

    def touching(self, name: str, p, radius: float) -> bool:
        """Is a point within `radius` of a named polyline?

        What it is for: a fence that goes up around a body already standing
        on it would wall that body out of the room it just walked into. See
        [`mission.py`](mission.py).
        """
        for ln in self.stage.lines:
            if ln.name != name:
                continue
            pts = [(q[0], q[2]) for q in ln.world()]
            for u, v in zip(pts, pts[1:]):
                if math.dist(_closest(u, v, p), p) < radius:
                    return True
        return False

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
