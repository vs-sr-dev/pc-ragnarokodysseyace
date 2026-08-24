"""
hitbox.py - a hit volume, on a skeleton that is moving.

Two records on this disc describe a volume attached to a bone, and until now
both have only ever been read as numbers:

- **the `.anmcmd` hit record**, which is the attack - a shape, a bone, and up
  to three vectors, fired on one frame of one animation. See
  [`format_anmcmd.md`](../docs/format_anmcmd.md);
- **`col_hit` in an `ELBN` `objbin.bin`**, which is the body - a bone, two
  endpoints and a radius, standing all the time. See
  [`format_elbn.md`](../docs/format_elbn.md).

[`pose.py`](pose.py) already runs a `CNOM` over a `CMDL` and puts a node in
world space. What it did not have was the node's **orientation**, and that is
the whole of the question this file was written to answer.

## The question the rest pose could not answer

`format_anmcmd.md` left one thing open about the hit record and said what
would settle it:

> **Whether an offset is turned by the bone or only carried with it.** ...
> These rigs' bind rotations sit too close to identity for a rest pose to tell
> the readings apart. An animated frame with a bent elbow would.

So this file computes both readings on every frame that fires a hit, and
measures them against something neither of them was fitted to: **the limb the
capsule is wrapped around**. A capsule whose two ends hang off two bones of
one arm should lie along that arm. Under the wrong reading, the moment the arm
leaves its bind pose, it does not.

    turned    p = M_bone * v          the offset is in the bone's own frame
    carried   p = origin(M_bone) + v  the offset is in the actor's frame

The measurement is the angle between the capsule's axis and the limb's, taken
over every capsule record on the disc whose two bones are different, at the
frame it fires, on the animation it belongs to. Nothing about the record is
consulted except the two vectors and the two bones.

## The other record answers it too, and in the rest pose

`col_hit` does not need an animation, because its numbers are large enough to
read straight off. A player's body is two capsules on `node_hip`, running to
`(0, 0, -0.6)` and `(0, 0, +0.6)` with a radius of 0.3. `node_hip`'s own `z`
axis points **down** in the rest pose of every player model, so turned by the
bone those two capsules stand the body up from `y = 0.37` to `y = 1.57` - an
adult of 1.6 m in a 0.3 m sleeve. Carried, they would lie flat on the floor
front-to-back through the hips. One of those is a person and the other is not.

## Reading order

    body      one actor's `col_hit`, in the rest pose and in world space
    show      one `.anmcmd`, every hit record placed, both readings
    turned    the measurement, over every capsule on the disc
    obj       a frame as Wavefront OBJ: skeleton, body capsules, hit volumes
"""
from __future__ import annotations

import math
import pathlib
import re
import statistics
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

import anmcmd                                                 # noqa: E402
from cmdl import Cmdl                                         # noqa: E402
from cnom import Cnom                                         # noqa: E402
from elbn import Elbn, capsules                               # noqa: E402
from pose import Body, Play, skeleton_for                     # noqa: E402

LOCATOR = 1000            # ids at or above this are `S4`, below are nodes
SEGMENTS = 12             # how round a capsule is drawn


# --------------------------------------------------------------------------
# vectors, kept local so this file owes nothing but `pose`

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-9 else None


def angle(a, b) -> float | None:
    """Degrees between two directions, or None when either has no direction."""
    ua, ub = unit(a), unit(b)
    if ua is None or ub is None:
        return None
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(ua, ub)))))


def origin(m):
    return (m[0][3], m[1][3], m[2][3])


def apply(m, v):
    """A point in the matrix's own frame, brought out into the world."""
    return tuple(m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] + m[r][3]
                 for r in range(3))


def carry(m, v):
    """The same point, if the offset were never turned - only moved."""
    o = origin(m)
    return (o[0] + v[0], o[1] + v[1], o[2] + v[2])


PLACE = {'turned': apply, 'carried': carry}


# --------------------------------------------------------------------------
# an actor, its skeleton, its parameters and one of its animations

def cnom_index(root, _seen={}) -> dict[str, pathlib.Path]:
    """Every `CNOM` on the disc by stem, walked once instead of per lookup.

    Once per *tree*, not once per caller: the walk is 32,600 leaves and a
    quest that fields six kinds of monster asked for it six times. It is a
    pure function of `root` and the tree does not change under a run.
    """
    key = str(root)
    if key not in _seen:
        out: dict[str, pathlib.Path] = {}
        for q in sorted(pathlib.Path(root).rglob('*.CNOM')):
            out.setdefault(q.stem, q)
        _seen[key] = out
    return _seen[key]


def motion_for(name: str, root, index=None) -> pathlib.Path | None:
    """The `CNOM` an `.anmcmd` plays over, by the naming rule in `anmcmd.py`.

    A player list is `<class><id><verb>` and its motion is the same with a
    body letter in front - `as213run` against `fas213run.CNOM`. A monster
    list is `<monster>_<model>_<id>` and its motion drops the model number
    and the underscores - `b01_00_501` against `b01501at1.CNOM`. A `_quick`
    or `_en` suffix is a variant of the list, not of the motion.
    """
    if index is None:
        index = cnom_index(root)
    stem = pathlib.Path(name).stem
    m = re.match(r'([a-z0-9]+(?:_[a-z]+)*)_(\d\d)_(\d+)', stem)
    if m:
        want = f'{m.group(1)}{m.group(3)}'
        got = [v for k, v in index.items() if k.startswith(want)]
        return got[0] if got else None
    m = re.match(r'([a-z]{2,3})(\d{3})(\w*)', stem)
    if not m:
        return None
    cls, mid, tail = m.groups()
    tail = re.sub(r'_(quick|en|ex)\d*$', '', tail)
    for body in ('f', 'm'):
        hit = index.get(f'{body}{cls}{mid}{tail}')
        if hit is not None:
            return hit
        want = f'{body}{cls}{mid}'
        got = [v for k, v in index.items() if k.startswith(want)]
        if got:
            return got[0]
    return None


class Actor:
    """A skeleton, the locator table that also addresses it, and its body."""

    def __init__(self, model: pathlib.Path, objbin: pathlib.Path | None):
        self.body = Body(model)
        self.names = self.body.names
        self.cmdl = self.body.cmdl
        self.locators = dict(self.cmdl.locators())
        self.col_hit = []
        if objbin is not None and objbin.is_file():
            f = Elbn(objbin.read_bytes(), objbin.name)
            self.col_hit = capsules(f, 'col_hit')

    def node(self, bone: int):
        """A bone word is a node index below 1000 and a locator id above it."""
        if not bone:
            return None
        i = self.locators.get(bone) if bone >= LOCATOR else bone
        return i if i is not None and i < len(self.names) else None

    def name_of(self, bone: int) -> str:
        i = self.node(bone)
        return self.names[i] if i is not None else f'?{bone}'

    def child_of(self, i: int):
        """One child node index, for measuring which way a bone points."""
        for k, p in enumerate(self.body.parent):
            if p == i:
                return k
        return None


def actor_for(path: str, root) -> Actor | None:
    """The actor a path belongs to, model and `objbin.bin` both.

    A monster keeps the two together. A player class keeps its parameters in
    `job.cpk/<class>/objbin.bin` and its skeleton in `character.cpk`, and the
    class's models share one rig, so any of them will do.
    """
    root = pathlib.Path(root)
    m = re.search(r'monster\.cpk/([a-z0-9_]+)', path)
    if m:
        d = root / 'monster.cpk' / m.group(1)
        got = sorted(d.rglob('*.CMDL'))
        return Actor(got[0], d / 'objbin.bin') if got else None
    m = re.search(r'job\.cpk/([a-z]{2})', path)
    if not m:
        return None
    cls = m.group(1)
    got = sorted((root / 'character.cpk' / 'model.cpk').rglob(f'f{cls}1.CMDL'))
    return Actor(got[0], root / 'job.cpk' / cls / 'objbin.bin') if got \
        else None


# --------------------------------------------------------------------------
# placing a record

class Placed:
    """One hit record, in world space, under one reading."""

    __slots__ = ('hit', 'reading', 'p0', 'p1', 'p2', 'axis', 'radius')

    def __init__(self, hit, actor: Actor, play: Play, frame: float,
                 reading: str):
        put = PLACE[reading]
        self.hit, self.reading = hit, reading
        m0 = _frame_of(actor, play, hit.bone, frame)
        m1 = _frame_of(actor, play, hit.bone2 or hit.bone, frame)
        self.p0 = put(m0, hit.vectors[0]) if m0 else None
        self.p1 = put(m1, hit.vectors[1]) if m1 and hit.flag in (1, 2, 4) \
            else None
        self.p2 = put(m0, hit.vectors[2]) if m0 and hit.flag == 4 else None
        # On a cylinder the second vector is an axis and the third a radius,
        # so neither is a point and only the direction is turned.
        self.axis = None
        self.radius = hit.vectors[2][0] if hit.flag in (3, 5) else None
        if hit.flag in (3, 5) and m0:
            v = hit.vectors[1]
            self.axis = unit(sub(put(m0, v), self.p0)) if reading == 'turned' \
                else unit(v)


def _frame_of(actor: Actor, play: Play, bone: int, frame: float):
    """A bone's world matrix, or the actor's own origin when it names none."""
    i = actor.node(bone)
    if i is None:
        return [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.]]
    return play.matrix(actor.names[i], frame)


def records_of(a: anmcmd.Anmcmd):
    """Every `(frame, opcode, hit)` in one list."""
    for b in a.blocks():
        for c in b['commands']:
            for h in anmcmd.hits_of(c):
                yield b['frame'], c.op, h


# --------------------------------------------------------------------------
# commands

def _load(root, name):
    path, a = anmcmd._one(root, name)                          # noqa: SLF001
    actor = actor_for(path, root)
    if actor is None:
        raise SystemExit(f'{path}: no model for it')
    cnom = motion_for(path, root)
    if cnom is None:
        raise SystemExit(f'{path}: no CNOM pairs with it')
    want = sorted({actor.names[i] for i in range(len(actor.names))})
    play = Play(actor.body, Cnom(cnom.read_bytes(), cnom.name), want)
    return path, a, actor, cnom, play


def cmd_show(root, name) -> int:
    path, a, actor, cnom, play = _load(root, name)
    print(f'{path}\n  on {actor.body.path.name}, posed by {cnom.name}, '
          f'{play.declared} frames')
    for frame, op, h in records_of(a):
        if frame > play.declared:
            continue
        line = (f'  f{frame:<4d} op{op:<3d} slot {h.slot:2d} '
                f'{h.shape:<13s} {actor.name_of(h.bone):<16s}'
                f'{actor.name_of(h.bone2) if h.bone2 else "":<16s}')
        print(line)
        for reading in ('turned', 'carried'):
            q = Placed(h, actor, play, float(frame), reading)
            pts = '  '.join('(' + ' '.join(f'{x:6.2f}' for x in p) + ')'
                            for p in (q.p0, q.p1, q.p2) if p is not None)
            extra = ''
            if q.p0 is not None and q.p1 is not None:
                extra = f'   span {norm(sub(q.p1, q.p0)):5.2f} m'
            print(f'      {reading:<8s} {pts}{extra}')
    return 0


def cmd_body(root, spec) -> int:
    """One actor's `col_hit`, in the rest pose, under both readings.

    The rest pose is enough here because the numbers are body-sized: a
    capsule that stands a body up under one reading lies it flat on the floor
    under the other, and no measurement is needed to tell those apart.
    """
    actor = actor_for(spec, root)
    if actor is None:
        raise SystemExit(f'no actor for {spec!r}')
    rest = actor.cmdl.world()
    print(f'{spec}   {actor.body.path.name}, '
          f'{len(actor.col_hit)} col_hit capsules')
    lo = [1e9, 1e9]
    hi = [-1e9, -1e9]
    for i, (bone, va, vb, r0, r1) in enumerate(actor.col_hit):
        n = actor.node(bone)
        if n is None:
            continue
        m = rest[n]
        out = [f'  [{i:3d}] {actor.names[n]:<16s} r {r0:4.2f}']
        for k, reading in enumerate(('turned', 'carried')):
            put = PLACE[reading]
            a, b = put(m, va), put(m, vb)
            lo[k] = min(lo[k], a[1] - r0, b[1] - r1)
            hi[k] = max(hi[k], a[1] + r0, b[1] + r1)
            out.append(f'{reading} ({a[0]:6.2f} {a[1]:6.2f} {a[2]:6.2f})'
                       f' -> ({b[0]:6.2f} {b[1]:6.2f} {b[2]:6.2f})')
        print('  '.join(out))
    ground = min(m[1][3] for m in rest)
    top = max(m[1][3] for m in rest)
    print(f'\n  the rest pose runs from y = {ground:.2f} to y = {top:.2f}')
    for k, reading in enumerate(('turned', 'carried')):
        print(f'  {reading:<8s} the capsules run y = {lo[k]:6.2f} .. '
              f'{hi[k]:6.2f}   {hi[k] - lo[k]:5.2f} m of body')
    return 0


def _chance(k: float) -> float:
    """What fraction of *random* directions fall within k degrees of a fixed
    one. The solid angle of a cap, and the only baseline these angles have:
    a reading that scores this is a reading that has found nothing."""
    return 100.0 * (1.0 - math.cos(math.radians(k))) / 2.0


def _z(v, k: float) -> float:
    """How many standard deviations the count sits above that baseline."""
    q = _chance(k) / 100.0
    n = len(v)
    got = sum(1 for x in v if x <= k)
    sd = math.sqrt(n * q * (1 - q))
    return (got - n * q) / sd if sd else 0.0


def _stats(v):
    w = lambda k: 100.0 * sum(1 for x in v if x <= k) / len(v)   # noqa: E731
    return (f'{len(v):>6,} {statistics.median(v):>8.1f} '
            f'{statistics.mean(v):>8.1f} '
            f'{w(26):>8.1f}% z{_z(v, 26):>+6.1f} '
            f'{w(60):>8.1f}% z{_z(v, 60):>+6.1f}')


def cmd_turned(root) -> int:
    """Which reading points a hit offset the way the bone is pointing.

    Two measurements, on every hit record on the disc, at the frame it fires,
    on the animation it belongs to. Both compare an offset against a
    direction the record never mentions, and both are only *able* to answer
    once the bone has turned away from its bind pose - which is the whole
    reason they are run on an animated frame and not on the rest one.

    **Down the limb.** A hitbox on a forearm is written from the elbow
    towards the wrist, so the offset should point roughly the way the bone
    points. `d` is the direction from the bone to its child in world space.
    Turned, the offset is `R * v`; carried, it is `v` unchanged.

    **Along the limb.** Where the two ends of a capsule hang off two
    different bones, the capsule's axis should lie along the segment between
    them.

    Frames where the two readings differ by less than a degree cannot answer
    either question, and are counted separately rather than averaged in.
    """
    root = pathlib.Path(root)
    down = {'turned': [], 'carried': []}
    down_bent = {'turned': [], 'carried': []}
    along = {'turned': [], 'carried': []}
    along_bent = {'turned': [], 'carried': []}
    files = used = placed = spans = skipped = 0
    actors: dict[str, Actor] = {}
    motions = cnom_index(root)
    under = {'turned': 0, 'carried': 0}
    deep = {'turned': 0.0, 'carried': 0.0}
    ground = 0

    def keep(table, bent, a, b, cut=1.0):
        if a is None or b is None:
            return
        table['turned'].append(a)
        table['carried'].append(b)
        if abs(a - b) > cut:
            bent['turned'].append(a)
            bent['carried'].append(b)

    for path, blob in anmcmd.collect(root):
        try:
            a = anmcmd.Anmcmd(blob, path)
        except Exception:                                     # noqa: BLE001
            continue
        files += 1
        recs = [(f, h) for f, _, h in records_of(a) if h.bone]
        if not recs:
            continue
        key = path.rsplit('/', 3)[0]
        if key not in actors:
            try:
                actors[key] = actor_for(path, root)
            except (ValueError, struct.error):
                actors[key] = None
        actor = actors[key]
        cnom = motion_for(path, root, motions) if actor else None
        if actor is None or cnom is None:
            skipped += 1
            continue
        want = set()
        for _, h in recs:
            for i in (actor.node(h.bone), actor.node(h.bone2)):
                if i is None:
                    continue
                want.add(actor.names[i])
                kid = actor.child_of(i)
                if kid is not None:
                    want.add(actor.names[kid])
        if not want:
            continue
        try:
            play = Play(actor.body, Cnom(cnom.read_bytes(), cnom.name),
                        sorted(want))
        except (ValueError, struct.error):
            continue
        used += 1
        for frame, h in recs:
            if frame > play.declared:
                continue
            i0 = actor.node(h.bone)
            if i0 is None:
                continue
            m0 = play.matrix(actor.names[i0], float(frame))
            kid = actor.child_of(i0)
            v = h.vectors[0]
            if norm(v) > 1e-4:
                # An attack's volume can graze the floor; it cannot be buried
                # in it. The reading that puts more of them underground is
                # the wrong one, and neither reading was fitted to the floor.
                ground += 1
                for reading in ('turned', 'carried'):
                    y = PLACE[reading](m0, v)[1]
                    if y < 0.0:
                        under[reading] += 1
                        deep[reading] = min(deep[reading], y)
            if kid is not None and norm(v) > 1e-4:
                d = sub(origin(play.matrix(actor.names[kid], float(frame))),
                        origin(m0))
                if norm(d) > 0.05:
                    placed += 1
                    keep(down, down_bent,
                         angle(sub(apply(m0, v), origin(m0)), d),
                         angle(v, d))
            i1 = actor.node(h.bone2)
            if (h.flag not in (1, 2) or i1 is None or i1 == i0
                    or norm(h.vectors[1]) < 1e-4):
                continue
            m1 = play.matrix(actor.names[i1], float(frame))
            limb = sub(origin(m1), origin(m0))
            if norm(limb) < 0.05:
                continue
            spans += 1
            keep(along, along_bent,
                 angle(sub(apply(m1, h.vectors[1]), apply(m0, v)), limb),
                 angle(sub(carry(m1, h.vectors[1]), carry(m0, v)), limb))

    print(f'{files} .anmcmd, {used} posed, {skipped} without a model or a '
          f'motion\n{placed} offsets against the bone they hang off, '
          f'{spans} capsules against the limb they wrap\n')
    if ground:
        print('how many of those offsets land under the floor the actor '
              'stands on')
        for reading in ('turned', 'carried'):
            print(f'  {reading:<8s} {under[reading]:>5,} of {ground:,}  '
                  f'{100.0 * under[reading] / ground:5.1f}%   deepest '
                  f'{deep[reading]:6.2f} m')
        print()
    head = (f'{"":<12s} {"n":>6s} {"median":>8s} {"mean":>8s} '
            f'{"<=26deg":>9s} {"":>6s} {"<=60deg":>9s}')
    for title, table, bent in (
            ('the offset against the direction to the bone\'s child', down,
             down_bent),
            ('the capsule axis against the limb between its two bones',
             along, along_bent)):
        print(title)
        print(head)
        for label, src in (('all frames', table),
                           ('  and where the readings differ', bent)):
            print(f'  {label}')
            for reading in ('turned', 'carried'):
                if src[reading]:
                    print(f'    {reading:<8s} {_stats(src[reading])}')
        print(f'    {"chance":<8s} {"":>6s} {90.0:>8.1f} {90.0:>8.1f} '
              f'{_chance(26):>8.1f}% {"":>6s} {_chance(60):>8.1f}%')
        print()
    return 0


# --------------------------------------------------------------------------
# drawing it

def _ring(centre, axis, r, n=SEGMENTS):
    u = unit(axis) or (0., 1., 0.)
    t = (1., 0., 0.) if abs(u[0]) < 0.9 else (0., 1., 0.)
    a = unit((u[1] * t[2] - u[2] * t[1], u[2] * t[0] - u[0] * t[2],
              u[0] * t[1] - u[1] * t[0])) or (1., 0., 0.)
    b = (u[1] * a[2] - u[2] * a[1], u[2] * a[0] - u[0] * a[2],
         u[0] * a[1] - u[1] * a[0])
    out = []
    for k in range(n):
        s, c = math.sin(2 * math.pi * k / n), math.cos(2 * math.pi * k / n)
        out.append(tuple(centre[j] + r * (c * a[j] + s * b[j])
                         for j in range(3)))
    return out


def _capsule(fh, base: int, p0, p1, r0, r1, name: str) -> int:
    """Two rings and a wall between them - enough to see, cheap to write."""
    axis = sub(p1, p0)
    if norm(axis) < 1e-6:
        axis = (0., 1., 0.)
    a, b = _ring(p0, axis, r0), _ring(p1, axis, r1)
    fh.write(f'o {name}\n')
    for p in a + b:
        fh.write(f'v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\n')
    n = SEGMENTS
    for k in range(n):
        i0, i1 = base + k, base + (k + 1) % n
        j0, j1 = base + n + k, base + n + (k + 1) % n
        fh.write(f'f {i0} {i1} {j1} {j0}\n')
    return base + 2 * n


def cmd_obj(root, name, frame, out) -> int:
    """One frame as OBJ: the bones, the body capsules, the hit volumes."""
    path, a, actor, cnom, play = _load(root, name)
    frame = float(frame)
    base = 1
    with open(out, 'w', encoding='ascii') as fh:
        fh.write(f'# {path} frame {frame:g} on {cnom.name}\n')
        fh.write('o skeleton\n')
        pos = [origin(play.matrix(n, frame)) for n in actor.names]
        for p in pos:
            fh.write(f'v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\n')
        for i, par in enumerate(actor.body.parent):
            if par >= 0:
                fh.write(f'l {base + par} {base + i}\n')
        base += len(pos)
        for i, (bone, va, vb, r0, r1) in enumerate(actor.col_hit):
            n = actor.node(bone)
            if n is None:
                continue
            m = play.matrix(actor.names[n], frame)
            base = _capsule(fh, base, apply(m, va), apply(m, vb), r0, r1,
                            f'col_hit_{i}_{actor.names[n]}')
        for f, op, h in records_of(a):
            if f != int(frame):
                continue
            q = Placed(h, actor, play, frame, 'turned')
            if q.p0 is None:
                continue
            r = max(h.sizes[0], 0.05)
            base = _capsule(fh, base, q.p0, q.p1 or q.p0, r, r,
                            f'hit_{h.slot}_{h.shape.replace(" ", "_")}')
    print(f'{out}: frame {frame:g} of {path}')
    print(f'  {len(pos)} bones, {len(actor.col_hit)} body capsules, '
          f'{sum(1 for f, _, _ in records_of(a) if f == int(frame))} '
          f'hit records')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'show':
        return cmd_show(rest[0], rest[1])
    if cmd == 'body':
        return cmd_body(rest[0], rest[1])
    if cmd == 'turned':
        return cmd_turned(rest[0])
    if cmd == 'obj':
        return cmd_obj(rest[0], rest[1], rest[2], rest[3])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
