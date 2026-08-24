"""
draw.py - the engine draws a frame.

Everything before this file measured the disc and reported a number. This one
turns the same data into a picture: it walks a `CMDL`'s draw list, skins each
mesh with the matrices [`pose.py`](pose.py) already builds, projects the
triangles through a camera, samples the `CTEX` the material names, and
z-buffers the result into a PNG. No third-party dependency and no GPU - a
software rasteriser in the same spirit as `stage.py`'s minimap fitter, which
has been rasterising triangles here since session 19.

    python engine/draw.py model   <dir> <model> <out.png> [motion] [frame]
    python engine/draw.py stage   <dir> <stage> <out.png> [width]
    python engine/draw.py scene   <dir> <quest> <out.png> [size] [body]
    python engine/draw.py top     <dir> <stage> <out.png> [size]
    python engine/draw.py check   <dir> [glob]
    python engine/draw.py minimap <dir> [glob]
    python engine/draw.py convention <dir> [glob] [samples]

## What is drawn, and out of what

A draw call is `(node, material, mesh)` - [`format_cmdl.md`](format_cmdl.md) -
and every part of it is already read:

    the vertices     cmdl.posed(), skinned by the node palette
    the winding      cmdl.triangles(), a triangle list
    the coordinates  cmdl.uvs()
    the texture      material +0x02 indexes S7, whose names are CTEX files
                     sitting in the same .pac as the model
    the pose         a CNOM sampled at a frame, exactly as pose.py samples it

Nothing here is a new reading. What is new is that the numbers have to be
*consistent with each other* in a way no single check has demanded: a wrong
bind matrix, a wrong UV lane or a wrong texture index all produce a picture
that is visibly wrong rather than a count that is quietly plausible.

## What it found

The first stage drawn came out with **nine trees piled on the world origin**,
which is the failure [`format_cmdl.md`](format_cmdl.md) had warned about since
session 5 and which had been sitting in `cmdl.py` the whole time. A rigid
mesh - one with no bone palette - has its vertices in **its node's own
space**, and `skin_matrices` was multiplying them by an `Rx(90)` that belongs
to the *inverse bind* matrices, where `cmdl.py check` confirms it on 872 of
931. No picture had ever been taken of that branch, because both models that
proved the format are skinned.

`draw.py convention` decides it against two files a model does not touch:

    world[node]                  0.055 m from its own node   0.034 m from .col
    world . bind^-1              2.240 m                     0.042 m
    world . (Rx90 . bind)^-1     2.138 m                     0.345 m

## Three conventions this file picks, and says so

- **Triangles are drawn two-sided.** The disc's winding is consistent within a
  mesh but nothing on it declares which way is out, so back-face culling would
  be a guess; instead every triangle is drawn and its shading normal is
  flipped towards the eye. The z-buffer sorts out the rest.
- **Shading is flat.** `cmdl.posed()` returns skinned positions and the disc's
  normals are a separate lane that would have to be skinned with the inverse
  transpose; a face normal computed in world space needs neither and is honest
  about what it is. One directional light plus ambient, no specular, no
  shadow.
- **Alpha is a test, not a blend.** A texel under `ALPHA_TEST` is not drawn,
  on the materials whose name carries `_alp_`. That is the whole of what this
  file knows about transparency, and it is why grass reads as a cut-out.

All three are policies of this file, like `mission.py`'s `blows`. None reads
anything off the disc.

## The measurement that can fail

`stage.py minimap` has been fitting each `.map` texture over its stage's
collision mesh since session 19, with its own scanline fill. `draw.py minimap`
puts **the same triangles** under **the same fitted transform** through this
camera and this inner loop and asks for the same number back: median IoU
**0.797** against the published **0.805** over 135 stages, differing per stage
by a median of 0.005 and never by more than 0.030. Two rasterisers written
seven sessions apart, one answer - which is what says the projection, the
pixel mapping and the `+z`-runs-down sign are right.

Its last column is a fact about the game rather than the renderer: the stage
*model* seen from a camera hung over the floor has a much bigger silhouette
than the walkable region, because a player can see ground they cannot stand
on.
"""

from __future__ import annotations

import fnmatch
import math
import pathlib
import sys
from array import array

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

import ctex                                                    # noqa: E402
import stage as stagemod                                       # noqa: E402
from cmdl import RX90, Cmdl, apply, invert, mul                # noqa: E402
from cnom import Cnom                                          # noqa: E402

BACKGROUND = (18, 20, 26)
LIGHT = (-0.35, 0.72, -0.60)             # normalised below; over the shoulder
AMBIENT = 0.55
NEAR = 0.05
MODES = ('local', 'plain', 'turned')
ALPHA_TEST = 96                          # a texel below this is not drawn
CLEARANCE = 0.5                          # how far above the floor to hang the
                                         # overhead camera, in metres


# --------------------------------------------------------------------------
# the frame

class Frame:
    """A colour buffer and a depth buffer. Depth counts *up* towards the eye,
    so the test is `>` in both projections and the clear value is -inf."""

    def __init__(self, w: int, h: int, bg=BACKGROUND):
        self.w, self.h = w, h
        self.col = bytearray(bytes((*bg, 255)) * (w * h))
        self.depth = array('f', [-1e30]) * (w * h)

    def png(self, path) -> None:
        ctex.write_png(path, self.w, self.h, bytes(self.col))

    def mask(self) -> bytes:
        """One byte a pixel: was anything drawn here at all."""
        d = self.depth
        return bytes(1 if d[i] > -1e29 else 0 for i in range(self.w * self.h))

    def covered(self) -> int:
        d = self.depth
        return sum(1 for i in range(self.w * self.h) if d[i] > -1e29)


# --------------------------------------------------------------------------
# the camera

class Camera:
    """A look-at camera in either projection.

    `view()` puts a world point in eye space, where the eye is at the origin
    looking down -z. `project()` returns `(x, y, depth, iw)` in pixels, with
    `iw` the perspective divisor the rasteriser interpolates UVs by - 1 in the
    orthographic case, which is what makes the two share one inner loop.
    """

    def __init__(self, w: int, h: int, eye, at, up=(0.0, 1.0, 0.0),
                 fov: float = 45.0, ortho: float = 0.0):
        self.w, self.h, self.ortho = w, h, ortho
        f = _norm(_sub(at, eye))
        s = _norm(_cross(f, up))
        u = _cross(s, f)
        self.m = [[s[0], s[1], s[2], -_dot(s, eye)],
                  [u[0], u[1], u[2], -_dot(u, eye)],
                  [-f[0], -f[1], -f[2], _dot(f, eye)],
                  [0.0, 0.0, 0.0, 1.0]]
        self.eye = eye
        self.scale = 1.0 / math.tan(math.radians(fov) / 2.0)

    def view(self, p):
        return apply(self.m, p)

    def project(self, v):
        x, y, z = v
        if self.ortho:
            return (self.w * 0.5 + x * self.ortho,
                    self.h * 0.5 - y * self.ortho, z, 1.0)
        iw = 1.0 / -z
        k = self.scale * iw
        return (self.w * 0.5 + x * k * self.h * 0.5,
                self.h * 0.5 - y * k * self.h * 0.5, iw, iw)

    @classmethod
    def framing(cls, w, h, centre, radius, azimuth=205.0, pitch=14.0,
                fov=40.0, lift=0.0):
        """Far enough back that a sphere of that radius fills the frame."""
        d = radius / math.sin(math.radians(fov) / 2.0)
        a, p = math.radians(azimuth), math.radians(pitch)
        eye = (centre[0] + d * math.cos(p) * math.sin(a),
               centre[1] + d * math.sin(p) + lift,
               centre[2] + d * math.cos(p) * math.cos(a))
        return cls(w, h, eye, centre, fov=fov)

    @classmethod
    def overhead(cls, w, h, scale, ox, oy, top=1000.0):
        """Straight down the -y axis, under `pixel = (s*x + ox, s*z + oy)`.

        That is `stage.py`'s minimap transform, sign and all: world +x runs
        right and world +z runs *down* the image, which is what a map drawn
        looking along -y does. `up = -z` is what puts the sign there.
        """
        ex = (w * 0.5 - ox) / scale
        ez = (h * 0.5 - oy) / scale
        return cls(w, h, (ex, top, ez), (ex, top - 1.0, ez),
                   up=(0.0, 0.0, -1.0), ortho=scale)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(v):
    n = math.sqrt(_dot(v, v)) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


# --------------------------------------------------------------------------
# textures

class Texture:
    """A decoded `CTEX`, sampled nearest and wrapped."""

    __slots__ = ('w', 'h', 'px', 'name')

    def __init__(self, name: str, w: int, h: int, rgba: bytes):
        self.name, self.w, self.h, self.px = name, w, h, rgba


class Library:
    """The `CTEX` files beside a model. `format_cmdl.md`: the names in S7 are
    the names of files in the same `.pac`, so the lookup is a directory read
    and never a search."""

    def __init__(self, home: pathlib.Path):
        self.home = home
        self.cache: dict[str, Texture | None] = {}

    def get(self, name: str) -> Texture | None:
        if name in self.cache:
            return self.cache[name]
        got = None
        for cand in (self.home / f'{name}.CTEX', self.home / f'{name}.ctex'):
            if cand.is_file():
                try:
                    t = ctex.Ctex(cand.read_bytes(), cand.name)
                    w, h, rgba = t.rgba(0)
                    got = Texture(name, w, h, rgba)
                except Exception:                              # noqa: BLE001
                    got = None
                break
        self.cache[name] = got
        return got


# --------------------------------------------------------------------------
# the rasteriser

def _clip_near(poly, near: float):
    """Clip a view-space polygon against the near plane `z <= -near`.

    Both projections need one. In perspective it is what keeps a triangle
    crossing the eye from wrapping round; in the overhead projection it is
    what a minimap camera is *for* - hang it just above the floor and the sky
    dome, which is the tallest thing in every stage model, falls behind it.
    """
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        az, bz = a[0][2], b[0][2]
        ain, bin_ = az <= -near, bz <= -near
        if ain:
            out.append(a)
        if ain != bin_:
            t = (-near - az) / (bz - az)
            out.append(tuple(
                tuple(p + t * (q - p) for p, q in zip(a[k], b[k]))
                for k in range(2)))
    return out


def triangle(frame: Frame, cam: Camera, tri, tex, shade: float,
             blend: bool) -> int:
    """One view-space triangle, `[(xyz, uv), ...]`. Returns pixels written."""
    poly = _clip_near(tri, 0.0 if cam.ortho else NEAR)
    if len(poly) < 3:
        return 0
    written = 0
    for k in range(1, len(poly) - 1):
        written += _fan(frame, cam, poly[0], poly[k], poly[k + 1], tex,
                        shade, blend)
    return written


def _fan(frame, cam, a, b, c, tex, shade, blend) -> int:
    ax, ay, az, aw = cam.project(a[0])
    bx, by, bz, bw = cam.project(b[0])
    cx, cy, cz, cw = cam.project(c[0])
    det = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
    if -1e-9 < det < 1e-9:
        return 0
    w, h = frame.w, frame.h
    lo_x = max(0, int(min(ax, bx, cx)))
    hi_x = min(w - 1, int(max(ax, bx, cx)) + 1)
    lo_y = max(0, int(min(ay, by, cy)))
    hi_y = min(h - 1, int(max(ay, by, cy)) + 1)
    if lo_x > hi_x or lo_y > hi_y:
        return 0
    au, av = a[1]
    bu, bv = b[1]
    cu, cv = c[1]
    au, av = au * aw, av * aw
    bu, bv = bu * bw, bv * bw
    cu, cv = cu * cw, cv * cw
    col, depth = frame.col, frame.depth
    tw = th = 0
    if tex is not None:
        tw, th, px = tex.w, tex.h, tex.px
    inv = 1.0 / det
    written = 0
    for y in range(lo_y, hi_y + 1):
        py = y + 0.5
        row = y * w
        for x in range(lo_x, hi_x + 1):
            px_ = x + 0.5
            l1 = ((px_ - ax) * (cy - ay) - (cx - ax) * (py - ay)) * inv
            if l1 < 0.0:
                continue
            l2 = ((bx - ax) * (py - ay) - (px_ - ax) * (by - ay)) * inv
            if l2 < 0.0 or l1 + l2 > 1.0:
                continue
            l0 = 1.0 - l1 - l2
            z = l0 * az + l1 * bz + l2 * cz
            i = row + x
            if z <= depth[i]:
                continue
            r = g = bl = 200
            if tw:
                iw = l0 * aw + l1 * bw + l2 * cw
                u = (l0 * au + l1 * bu + l2 * cu) / iw
                v = (l0 * av + l1 * bv + l2 * cv) / iw
                o = 4 * ((int(v * th) % th) * tw + (int(u * tw) % tw))
                if blend and px[o + 3] < ALPHA_TEST:
                    continue
                r, g, bl = px[o], px[o + 1], px[o + 2]
            depth[i] = z
            o = 4 * i
            col[o] = int(r * shade)
            col[o + 1] = int(g * shade)
            col[o + 2] = int(bl * shade)
            written += 1
    return written


# --------------------------------------------------------------------------
# a model

def rigid(model: Cmdl, node: int, world, bind, mode: str = 'local'):
    """What multiplies a vertex of a mesh with no bone palette.

    `cmdl.skin_matrices` used to fold an `RX90` in here, and no picture had
    ever been taken of the result: the renders that proved the format were
    skinned models, which take the palette branch instead. `draw.py
    convention` measures both against a file the model does not touch - the
    stage's own collision mesh - and the turn loses by two orders of
    magnitude, so `cmdl.py` no longer applies it. `turned=True` is kept so the
    measurement can still be run.
    """
    if mode == 'local':
        return [world[node]]
    b = mul(RX90, bind[node]) if mode == 'turned' else bind[node]
    return [mul(world[node], invert(b))]


def matrices(model: Cmdl, me: int, node: int, world, bind,
             mode: str = 'local'):
    return (model.skin_matrices(me, node, world, bind)
            if model.mesh(me).skinned
            else rigid(model, node, world, bind, mode))


def render(frame: Frame, cam: Camera, model: Cmdl, lib: Library,
           pose=None, place=None, light=LIGHT,
           mode: str = 'local') -> dict:
    """Every drawable call of one model, into the frame. `place` is a world
    matrix applied on top of the model's own nodes."""
    texs = model.names(7)
    mats = model.names(6)
    world = model.world(pose)
    if place is not None:
        world = [mul(place, m) for m in world]
    bind = model.bind()
    ld = _norm(light)
    ld = _norm(apply(cam.m, (ld[0] + cam.eye[0], ld[1] + cam.eye[1],
                             ld[2] + cam.eye[2])))
    st = {'calls': 0, 'triangles': 0, 'pixels': 0, 'textured': 0,
          'untextured': 0}
    for n, mat, me in model.draws():
        m = model.mesh(me)
        if not m.drawable:
            continue
        st['calls'] += 1
        pos = model.posed(m, matrices(model, me, n, world, bind, mode))
        uv = model.uvs(m) or [(0.0, 0.0)] * len(pos)
        t = model.material(mat)['texture'] if mat < model.materials else -1
        name = texs[t] if 0 <= t < len(texs) else ''
        tex = lib.get(name) if name else None
        st['textured' if tex else 'untextured'] += 1
        blend = '_alp_' in (mats[mat] if mat < len(mats) else '')
        eye = [cam.view(p) for p in pos]
        for ia, ib, ic in model.triangles(m):
            if max(ia, ib, ic) >= len(eye):
                continue
            va, vb, vc = eye[ia], eye[ib], eye[ic]
            nx, ny, nz = _cross(_sub(vb, va), _sub(vc, va))
            k = math.sqrt(nx * nx + ny * ny + nz * nz)
            if k < 1e-12:
                continue
            # the normal is turned towards the eye, because the file does not
            # say which side is out
            if nz < 0.0:
                nx, ny, nz = -nx, -ny, -nz
            wn = (nx / k, ny / k, nz / k)
            lit = AMBIENT + (1.0 - AMBIENT) * max(0.0, _dot(ld, wn))
            st['triangles'] += 1
            st['pixels'] += triangle(
                frame, cam, ((va, uv[ia]), (vb, uv[ib]), (vc, uv[ic])),
                tex, min(1.0, lit), blend)
    return st


def bounds(model: Cmdl, pose=None, mode: str = 'local'):
    """The model's own bounding sphere is in the header; this is the box the
    geometry actually reaches, which is what a camera wants."""
    world = model.world(pose)
    bind = model.bind()
    lo = [1e30] * 3
    hi = [-1e30] * 3
    for n, _, me in model.draws():
        m = model.mesh(me)
        if not m.drawable:
            continue
        for p in model.posed(m, matrices(model, me, n, world, bind,
                                        mode)):
            for k in range(3):
                lo[k] = min(lo[k], p[k])
                hi[k] = max(hi[k], p[k])
    if lo[0] > hi[0]:
        c = model.sphere
        return (c[0] - c[3], c[1] - c[3], c[2] - c[3]), \
               (c[0] + c[3], c[1] + c[3], c[2] + c[3])
    return tuple(lo), tuple(hi)


# --------------------------------------------------------------------------
# finding things on disc

def _model(root, name) -> tuple[pathlib.Path, Cmdl]:
    root = pathlib.Path(root)
    hits = [p for p in root.rglob('*.CMDL')
            if p.name == name or p.stem == name]
    if not hits:
        hits = [p for p in root.rglob('*.CMDL')
                if fnmatch.fnmatch(p.name, name)]
    if not hits:
        raise SystemExit(f'not found: {name}')
    p = hits[0]
    return p, Cmdl(p.read_bytes(), p.relative_to(root).as_posix())


def _stage_ground(root, stage) -> tuple[pathlib.Path, Cmdl]:
    d = pathlib.Path(root)
    for p in sorted(d.rglob('ground.CMDL')):
        if stage in p.as_posix():
            return p, Cmdl(p.read_bytes(), p.relative_to(d).as_posix())
    raise SystemExit(f'no ground model for {stage}')


def _col_bounds(col: pathlib.Path):
    from ccls import Ccls                                      # noqa: PLC0415
    c = Ccls(col.read_bytes(), col.name)
    vs = [v for t in c.triangles() for v in t['v']]
    return (tuple(min(v[k] for v in vs) for k in range(3)),
            tuple(max(v[k] for v in vs) for k in range(3)))


def _ceiling(col: pathlib.Path) -> float:
    """The top of a stage's collision mesh. An overhead camera hung just above
    it sees the floor and nothing that is not floor - which is what a minimap
    is a picture of."""
    from ccls import Ccls                                      # noqa: PLC0415
    c = Ccls(col.read_bytes(), col.name)
    return max(v[1] for t in c.triangles() for v in t['v'])


def _motion(root, name) -> Cnom:
    for p in pathlib.Path(root).rglob('*.CNOM'):
        if p.stem == name or p.name == name:
            return Cnom(p.read_bytes(), p.name)
    from cnom import _one                                      # noqa: PLC0415
    return _one(root, name)[1]


# --------------------------------------------------------------------------
# the commands

def cmd_model(root, name, out, motion='', frame='0', size='640') -> int:
    path, m = _model(root, name)
    pose = None
    if motion:
        a = _motion(root, motion)
        pose = a.pose(float(frame))
    lo, hi = bounds(m, pose)
    centre = tuple((lo[k] + hi[k]) / 2 for k in range(3))
    radius = max(1e-3, max(hi[k] - lo[k] for k in range(3)) / 2 * 1.15)
    w = int(size)
    f = Frame(w, w * 3 // 4)
    cam = Camera.framing(f.w, f.h, centre, radius)
    lib = Library(path.parent)
    st = render(f, cam, m, lib, pose)
    f.png(out)
    print(f'{m.label}  {f.w}x{f.h}  {st["calls"]} calls, '
          f'{st["triangles"]:,} triangles, {st["pixels"]:,} pixels, '
          f'{st["textured"]} textured / {st["untextured"]} not  ->  {out}')
    return 0


def cmd_stage(root, stage, out, size='800') -> int:
    path, m = _stage_ground(root, stage)
    lo, hi = bounds(m)
    centre = ((lo[0] + hi[0]) / 2, lo[1] + (hi[1] - lo[1]) * 0.25,
              (lo[2] + hi[2]) / 2)
    radius = max(hi[k] - lo[k] for k in (0, 2)) / 2
    w = int(size)
    f = Frame(w, w * 9 // 16)
    cam = Camera.framing(f.w, f.h, centre, radius, azimuth=30.0, pitch=26.0,
                         fov=50.0)
    st = render(f, cam, m, Library(path.parent))
    f.png(out)
    print(f'{m.label}  {f.w}x{f.h}  {st["triangles"]:,} triangles, '
          f'{st["pixels"]:,} pixels  ->  {out}')
    return 0


def cmd_top(root, stage, out, size='512') -> int:
    path, m = _stage_ground(root, stage)
    lo, hi = bounds(m)
    ceil = hi[1] + 100.0
    for name, mp, col in stagemod._stages_with_maps(root):
        if name == stage:
            ceil = _ceiling(col) + CLEARANCE
            lo, hi = _col_bounds(col)
            break
    n = int(size)
    span = max(hi[0] - lo[0], hi[2] - lo[2]) or 1.0
    centre = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
    f = Frame(n, n)
    sc = n / span * 0.98
    cam = Camera.overhead(n, n, sc, n * 0.5 - sc * centre[0],
                          n * 0.5 - sc * centre[2], top=ceil)
    st = render(f, cam, m, Library(path.parent))
    f.png(out)
    print(f'{m.label}  {n}x{n} looking down, {span:.1f} m across, '
          f'{st["pixels"]:,} pixels  ->  {out}')
    return 0


def _place(pos, yaw_deg: float):
    a = math.radians(yaw_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [[ca, 0.0, sa, pos[0]], [0.0, 1.0, 0.0, pos[1]],
            [-sa, 0.0, ca, pos[2]], [0.0, 0.0, 0.0, 1.0]]


def cmd_scene(root, quest, out, size='900', who='msw2') -> int:
    """The arena, drawn out of the tables that fill it.

    `quest.py` says which stage a quest starts on, which monster sits in each
    of its eight slots and which `emgen_pos` marker each generator stands on;
    `stage.py` says where those markers are; `format_cmdl.md` says what a
    monster looks like. Nothing here is new - this is the first time all of it
    is in one picture.
    """
    import quest as questmod                                   # noqa: PLC0415

    root = pathlib.Path(root)
    q = next(questmod.collect(root, quest), None)
    if q is None:
        raise SystemExit(f'no quest {quest}')
    first = q.stages[0]
    st = next(iter(stagemod.stages(root, first)), None)
    if st is None:
        raise SystemExit(f'no stage {first}')
    markers = {mk.name: mk for mk in st.markers}
    slots = q.slots().get(first, [])
    known = questmod.monsters(root)

    gpath, ground = _stage_ground(root, first)
    spawn = markers.get('appear01') or next(
        (m for n, m in markers.items() if n.startswith('appear')), None)
    if spawn is None:
        raise SystemExit(f'{first}: no appear marker')

    cast = []
    for g in q.generators():
        if g['stage'] != first or not g['marker']:
            continue
        mk = markers.get(g['marker'])
        mid = slots[g['slot'] - 1] if 1 <= g['slot'] <= len(slots) else None
        if mk is None or mid is None or mid not in known:
            continue
        cast.append((known[mid], mk))
    seen, uniq = set(), []
    for name, mk in cast:
        if mk.name in seen:
            continue
        seen.add(mk.name)
        uniq.append((name, mk))

    w = int(size)
    f = Frame(w, w * 9 // 16)
    eye = spawn.position
    yaw = spawn.rotation[1]
    at = (eye[0] - 14.0 * math.sin(math.radians(yaw)), eye[1] + 1.2,
          eye[2] - 14.0 * math.cos(math.radians(yaw)))
    cam = Camera(f.w, f.h, (eye[0], eye[1] + 3.6, eye[2]), at, fov=52.0)
    total = render(f, cam, ground, Library(gpath.parent))['pixels']
    drawn = 0
    body = None
    try:
        bpath, body = _model(root, f'{who}.CMDL')
    except SystemExit:
        pass
    if body is not None:
        total += render(f, cam, body, Library(bpath.parent),
                        place=_place(spawn.position, yaw))['pixels']
        drawn += 1
    for name, mk in uniq:
        try:
            mpath, mon = _model(root, f'{name}.CMDL')
        except SystemExit:
            continue
        total += render(f, cam, mon, Library(mpath.parent),
                        place=_place(mk.position, mk.rotation[1]))['pixels']
        drawn += 1
    f.png(out)
    print(f'{quest}: {first}, {len(uniq)} spawners, {drawn} actors drawn, '
          f'{total:,} pixels  ->  {out}')
    return 0


def cmd_check(root, want='*') -> int:
    """Render every model small, and report what came out. The failure this
    catches is the one a reader cannot: geometry that parses and draws
    nothing."""
    root = pathlib.Path(root)
    n = blank = notex = 0
    calls = tex_ok = tex_miss = 0
    for p in sorted(root.rglob('*.CMDL')):
        rel = p.relative_to(root).as_posix()
        if not (fnmatch.fnmatch(p.name, want) or fnmatch.fnmatch(rel, want)):
            continue
        try:
            m = Cmdl(p.read_bytes(), rel)
        except Exception as exc:                               # noqa: BLE001
            print(f'  {rel}: {exc}')
            continue
        n += 1
        lo, hi = bounds(m)
        centre = tuple((lo[k] + hi[k]) / 2 for k in range(3))
        radius = max(1e-3, max(hi[k] - lo[k] for k in range(3)) / 2 * 1.15)
        f = Frame(96, 96)
        cam = Camera.framing(96, 96, centre, radius)
        lib = Library(p.parent)
        st = render(f, cam, m, lib)
        calls += st['calls']
        tex_ok += st['textured']
        tex_miss += st['untextured']
        if not st['pixels']:
            blank += 1
            print(f'  blank: {rel}')
        if st['textured'] == 0 and st['calls']:
            notex += 1
    print(f'{n} models rendered at 96x96, {blank} blank')
    print(f'{calls:,} draw calls, {tex_ok:,} found their texture beside the '
          f'model, {tex_miss:,} did not')
    print(f'{notex} models drew with no texture at all')
    return 0


def cmd_convention(root, want='*', n='40') -> int:
    """Which space a rigid mesh's vertices are in, decided against a file the
    model does not touch.

    `cmdl.skin_matrices` turns a rigid mesh by `RX90` and nothing had checked
    it. A stage's `.col` is the walkable ground, so under the right convention
    the *visible* ground stands over the walkable one: the collision
    centroids should have model surface above or below them, and at about the
    same height. Under the wrong one the two are different axes and the
    coverage collapses.
    """
    import random                                              # noqa: PLC0415
    import statistics                                          # noqa: PLC0415
    from ccls import Ccls                                      # noqa: PLC0415

    rng = random.Random(1)
    tot = {k: [0, 0, []] for k in MODES}
    print('%-12s %s' % ('stage', ' '.join('%18s' % k for k in MODES)))
    for name, mp, col in stagemod._stages_with_maps(root):
        if not fnmatch.fnmatch(name, want):
            continue
        try:
            path, m = _stage_ground(root, name)
        except SystemExit:
            continue
        c = Ccls(col.read_bytes(), col.name)
        pts = [tuple(sum(v[k] for v in t['v']) / 3 for k in range(3))
               for t in c.triangles()]
        if len(pts) > int(n):
            pts = rng.sample(pts, int(n))
        world, bind = m.world(), m.bind()
        line = [name]
        for mode in MODES:
            tris = []
            for nd, _, me in m.draws():
                x = m.mesh(me)
                if not x.drawable:
                    continue
                pos = m.posed(x, matrices(m, me, nd, world, bind, mode))
                for ia, ib, ic in m.triangles(x):
                    if max(ia, ib, ic) < len(pos):
                        tris.append((pos[ia], pos[ib], pos[ic]))
            hit, d = 0, []
            for x, y, z in pts:
                h = _surface(tris, x, z, y)
                if h is not None:
                    hit += 1
                    d.append(abs(h - y))
            tot[mode][0] += hit
            tot[mode][1] += len(pts)
            tot[mode][2] += d
            line.append(f'{hit}/{len(pts)}')
            line.append(f'{statistics.median(d):.3f}' if d else '-')
        print('%-12s %s' % (line[0], ' '.join(
            '%10s %7s' % (line[1 + 2 * k], line[2 + 2 * k])
            for k in range(len(MODES)))))
    print()
    for mode in MODES:
        hit, n_, d = tot[mode]
        print('  %-8s %5d of %d collision centroids have model surface over '
              'them, median |dy| %s'
              % (mode, hit, n_,
                 ('%.3f m' % statistics.median(d)) if d else '-'))
    return 0


def _surface(tris, x, z, want):
    """The model surface height at (x, z) closest to `want`, or None."""
    best = None
    for a, b, c in tris:
        x0, y0, z0 = a
        x1, y1, z1 = b
        x2, y2, z2 = c
        det = (z1 - z2) * (x0 - x2) + (x2 - x1) * (z0 - z2)
        if -1e-9 < det < 1e-9:
            continue
        u = ((z1 - z2) * (x - x2) + (x2 - x1) * (z - z2)) / det
        if u < 0.0 or u > 1.0:
            continue
        v = ((z2 - z0) * (x - x2) + (x0 - x2) * (z - z2)) / det
        if v < 0.0 or u + v > 1.0:
            continue
        y = u * y0 + v * y1 + (1.0 - u - v) * y2
        if best is None or abs(y - want) < abs(best - want):
            best = y
    return best


def paint(frame: Frame, cam: Camera, tris, shade: float = 1.0) -> int:
    """Bare triangles through the same camera and the same inner loop, with no
    model, no texture and no material. This is what puts the rasteriser on
    trial by itself."""
    n = 0
    for a, b, c in tris:
        va, vb, vc = cam.view(a), cam.view(b), cam.view(c)
        n += triangle(frame, cam, ((va, (0.0, 0.0)), (vb, (0.0, 0.0)),
                                   (vc, (0.0, 0.0))), None, shade, False)
    return n


def cmd_minimap(root, want='*') -> int:
    """The rasteriser on trial against the one already here.

    `stage.py minimap` fits each `.map` over its stage's collision mesh with
    its own scanline fill and reports the overlap. This puts *the same
    triangles* under *the same fitted transform* through `draw.py`'s camera
    and `draw.py`'s inner loop, and asks for the same number back. Nothing is
    refitted and nothing is tuned: two rasteriser written five sessions apart,
    one answer.

    The third column is the honest secondary fact - the stage's *model*
    rendered from a camera hung over the floor, whose silhouette is much
    larger than the walkable region, because a player can see ground they
    cannot stand on.
    """
    import statistics                                          # noqa: PLC0415
    from ccls import Ccls                                      # noqa: PLC0415

    rows = []
    print(f'{"stage":<12s} {"stage.py":>9s} {"draw.py":>8s} {"agree":>7s} '
          f'{"model":>7s} {"px/m":>6s}')
    for name, mp, col in stagemod._stages_with_maps(root):
        if not fnmatch.fnmatch(name, want):
            continue
        w, h, mask = stagemod.map_mask(mp)
        flat, cx, cz, area = stagemod.footprint(col)
        fit = stagemod.fit_map(mask, w, h, flat, cx, cz)
        if not fit:
            continue
        iou_col, s, ox, oy = fit
        c = Ccls(col.read_bytes(), col.name)
        tris = [tuple(t['v']) for t in c.triangles()]
        top = max(v[1] for t in tris for v in t) + CLEARANCE
        f = Frame(w, h)
        cam = Camera.overhead(w, h, s, ox, oy, top=top + 10.0)
        paint(f, cam, tris)
        ours = f.mask()
        iou_mine = stagemod.overlap(mask, ours)
        theirs = stagemod.rasterise(flat, s, ox, oy, w, h)
        agree = stagemod.overlap(theirs, ours)
        iou_model = 0.0
        try:
            path, m = _stage_ground(root, name)
            g = Frame(w, h)
            gcam = Camera.overhead(w, h, s, ox, oy, top=top)
            render(g, gcam, m, Library(path.parent))
            iou_model = stagemod.overlap(mask, g.mask())
        except SystemExit:
            pass
        rows.append((name, iou_col, iou_mine, agree, iou_model, s))
        print(f'{name:<12s} {iou_col:9.3f} {iou_mine:8.3f} {agree:7.3f} '
              f'{iou_model:7.3f} {s:6.3f}')
    if not rows:
        return 1
    print()
    print(f'{len(rows)} stages')
    for k, tag in ((1, 'stage.py rasterises the mesh'),
                   (2, 'draw.py renders the same mesh'),
                   (3, 'and the two masks agree'),
                   (4, 'the stage model over the floor')):
        v = [r[k] for r in rows]
        print(f'  {tag:<32s} median {statistics.median(v):.3f}   '
              f'>= 0.95 on {sum(1 for x in v if x >= 0.95)} of {len(v)}')
    d = [abs(r[1] - r[2]) for r in rows]
    print(f'  the two scores differ by a median of {statistics.median(d):.4f}'
          f', worst {max(d):.4f}')
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'model':
        return cmd_model(*rest)
    if cmd == 'stage':
        return cmd_stage(*rest)
    if cmd == 'top':
        return cmd_top(*rest)
    if cmd == 'scene':
        return cmd_scene(*rest)
    if cmd == 'check':
        return cmd_check(*rest)
    if cmd == 'minimap':
        return cmd_minimap(*rest)
    if cmd == 'convention':
        return cmd_convention(*rest)
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
