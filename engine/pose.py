"""
pose.py - the skeleton, and where things are on it.

`actor.py` moves a capsule at the numbers the parameter table declares and
`world.py` says where the floor is. Neither of them has a body. This file is
the join: it plays a [`CNOM`](../tools/cnom.py) on a
[`CMDL`](../tools/cmdl.py) skeleton and answers the questions a pose can be
checked against - **is the foot where the animation says it is**, and **is
the limb where the sound says it is**.

    python engine/pose.py body <tree> <model>
    python engine/pose.py track <tree> <motion>
    python engine/pose.py footfall <tree>
    python engine/pose.py locomotion <tree> <class json>
    python engine/pose.py emitter <tree>

`body` prints a skeleton's contact nodes and the height they stand at. `track`
plays one animation and prints, per frame, where those nodes are. The other
three are the checks, and none of them could be run by a reader:

- `footfall` measures the skeleton against [`.mkc`](../docs/format_mkc.md)
  opcode `7ffa`, which fires on the frame a foot lands. A hand-authored byte
  and forward kinematics over a quaternion channel have no reason to agree
  unless the pose is right.
- `locomotion` measures every named walk, run and dash against the `walk_sp`,
  `run_sp` and `fast_sp` the parameter table declares - `cmdl.py gait`'s one
  measurement, done on all 48 cycles the disc ships.
- `emitter` names the last unread field of `7ff9`. It is a `CMDL` locator id,
  and the limb the locator binds to is the one arriving on that frame.

`run.py stride` is the fourth: it puts the animation on the moving capsule and
prints the planted foot's height above the collision mesh, frame by frame.

## The contact node, and the height it stands at

A skeleton's ground contact is **the toe when it has one and the ankle when it
does not**. The players are plantigrade and stop at `node_l_foot`; every
monster with legs carries a `node_l_toe` under it, and on `b01_00` the ankle
sits at 1.02 m while the toe sits at 0.42 - the toe is what is on the floor.

The height that counts as *down* is read off the **rest pose**, and the disc
says the rest pose is a standing one: on every player model the lowest node in
it is at exactly `y = 0` and the ankle is at 0.142 m, which is an ankle height.
The same skeleton played through `fas213run` puts that ankle at 0.138 at its
lowest, so the rest height is the standing height to four millimetres. Nothing
here is fitted: `standing` is a number read out of the model.

## What is assumed, and where

- **The animation is in place.** A locomotion cycle keeps the root still and
  slides the feet backwards; `cmdl.py gait` measures that slide and gets
  `run_sp` back. So the model is placed at the actor's own position each
  frame, and any root translation the animation carries is added on top of it.
  For a walk or a run that translation is zero. For an animation that moves
  its own root - a dodge, a lunge - it is not, and this file does not try to
  separate the two.
- **Model space is the stage's space.** Y up, one unit a metre,
  [`units.md`](../docs/units.md); and `+Z` forward, which is the convention
  `world.py` adopted for a heading of zero. Those two agreeing is not proved
  anywhere - it is what makes a run cycle carry a body forwards rather than
  sideways, and `pose.py track` prints the slide so it can be argued with.
- **Contact has a tolerance**, because a foot planted on a floor still moves a
  few millimetres. It is `TOUCH`, three centimetres, the same constant
  `cmdl.py` already uses to find a planted ankle. `footfall` prints what the
  answer does at one centimetre and at five, so the tolerance can be seen not
  to be carrying the result.
- **A cycle whose last frame repeats its first is a loop one frame shorter.**
  `fas213run` declares 21 frames and its frame 20 is its frame 0 to the last
  digit, so the loop is 20 long. That is tested per animation rather than
  assumed.
"""
from __future__ import annotations

import collections
import pathlib
import statistics
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

from actor import load as load_params                         # noqa: E402
from cmdl import (Cmdl, IDENTITY, compose, from_euler,        # noqa: E402
                  from_quaternion, mul)
from cnom import KIND, Cnom                                   # noqa: E402
from mkc import Disc, Mkc                                     # noqa: E402

TOUCH = 0.03                # metres; `cmdl.py` calls the same number PLANTED
TOLS = (0.01, TOUCH, 0.05)  # and what the answer does either side of it
LIFT = 0.10                 # a foot that never rises this far never lands
BACK = 3                    # frames of descent that count as an arrival
FOOT = '_foot'
TOE = '_toe'

# `.mkc` 7ffa's argument, which picks a cue from the model's own four-cue set.
KINDS = {0: 'WALK', 1: 'RUN', 2: 'LANDING', 3: 'DRESS'}
DRESS = 3                   # and the skeleton says this one is not the ground


# --------------------------------------------------------------------------
# the skeleton

class Body:
    """A `CMDL` skeleton, with the nodes that touch the ground picked out."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.cmdl = Cmdl(self.path.read_bytes(), self.path.name)
        self.name = self.path.stem
        self.names = self.cmdl.names(5)
        self.index = {n: i for i, n in enumerate(self.names)}
        self.parent = self.cmdl.parents()
        self.local = [self._rest_local(i) for i in range(self.cmdl.nodes)]

        toes = [n for n in self.names if n.endswith(TOE)]
        feet = [n for n in self.names if n.endswith(FOOT)]
        self.contact = sorted(toes or feet)
        self.rest = self.cmdl.world()
        self.standing = {n: self.rest[self.index[n]][1][3]
                         for n in self.contact}
        self.chain = {n: self._chain(self.index[n]) for n in self.contact}

    def chain_of(self, node: str) -> list[int]:
        """The node's ancestry, root first, for a node outside `contact`."""
        got = self.chain.get(node)
        if got is None:
            got = self.chain[node] = self._chain(self.index[node])
        return got

    def _rest_local(self, i: int) -> list:
        n = self.cmdl.node(i)
        return compose(n['translation'], from_euler(n['rotation']),
                       n['scale'])

    def _chain(self, i: int) -> list[int]:
        out = []
        while i >= 0:
            out.append(i)
            i = self.parent[i]
        return list(reversed(out))

    def floor(self, node: str) -> float:
        """The height this node sits at when the body is standing.

        Read off the rest pose, which on a player model is a standing one.
        On a monster whose rest pose is not - `b19`'s horse hangs two metres
        over it - this is a reference and not a floor, which is why the
        emitter check measures a descent rather than a height."""
        got = self.standing.get(node)
        if got is None:
            got = self.standing[node] = self.rest[self.index[node]][1][3]
        return got


# --------------------------------------------------------------------------
# one animation on one skeleton

class Play:
    """A `CNOM` on a `Body`, sampled only along the chains that reach the
    ground - the rest of the skeleton costs time and answers nothing here."""

    def __init__(self, body: Body, cnom: Cnom, nodes=None):
        self.body, self.cnom = body, cnom
        self.name = cnom.name or ''
        self.nodes = list(nodes) if nodes else list(body.contact)
        need: set[int] = set()
        for n in self.nodes:
            need.update(body.chain_of(n))
        self.animated = {}
        for t, name in enumerate(cnom.names()):
            i = body.index.get(name)
            if i is not None and i in need:
                self.animated[i] = cnom.channels(t)
        self._cache: dict[tuple[int, float], list] = {}
        self._track = None
        self.declared = cnom.frames
        self.length = self._loop()

    def _loop(self) -> int:
        """The declared length, less one when the last frame repeats the
        first - which is how a cycle is authored to join up."""
        n = self.declared
        if n < 2:
            return max(n, 1)
        a, b = self.at(0.0), self.at(float(n - 1))
        same = all(abs(a[k][j] - b[k][j]) < 1e-6
                   for k in a for j in range(3))
        return n - 1 if same else n

    def local(self, i: int, frame: float) -> list:
        key = (i, frame)
        got = self._cache.get(key)
        if got is None:
            ch = self.animated.get(i)
            if ch is None:
                got = self.body.local[i]
            else:
                v = {KIND.get(c.kind, ''): self.cnom.sample(c, frame)
                     for c in ch}
                got = compose(v.get('translation', (0., 0., 0.)),
                              from_quaternion(v.get('rotation',
                                                    (0., 0., 0., 1.))),
                              v.get('scale', (1., 1., 1.)))
            self._cache[key] = got
        return got

    def at(self, frame: float) -> dict[str, tuple[float, float, float]]:
        """Every contact node's position in model space, at one frame."""
        out = {}
        for n in self.nodes:
            m = IDENTITY
            for i in self.body.chain_of(n):
                m = mul(m, self.local(i, frame))
            out[n] = (m[0][3], m[1][3], m[2][3])
        return out

    def height(self, frame: float) -> dict[str, float]:
        """Each contact node's height above where it stands, at one frame."""
        p = self.at(frame)
        return {n: p[n][1] - self.body.floor(n) for n in p}

    def track(self) -> list[dict[str, tuple[float, float, float]]]:
        if self._track is None:
            self._track = [self.at(float(f))
                           for f in range(self.declared + 1)]
        return self._track

    def lift(self) -> float:
        """How far the highest contact node ever gets off the ground.

        An animation whose feet never leave the floor cannot be asked when a
        foot lands, so `footfall` asks it only of the ones that do."""
        t = self.track()
        return max(max(r[n][1] - self.body.floor(n)
                       for n in self.nodes) for r in t)

    def down(self, tol: float = TOUCH) -> dict[str, list[bool]]:
        """Per node, whether it is on the ground on each frame."""
        t = self.track()
        return {n: [r[n][1] - self.body.floor(n) <= tol for r in t]
                for n in self.nodes}

    def landings(self, tol: float = TOUCH) -> list[tuple[int, str]]:
        """The frames a node comes down, as `(frame, node)`.

        Frame 0 is never one: an animation that opens with a foot already on
        the floor did not land it there, it inherited it from whatever ran
        before."""
        out = []
        for n, on in self.down(tol).items():
            out += [(f, n) for f in range(1, len(on))
                    if on[f] and not on[f - 1]]
        return sorted(out)

    def slide(self, tol: float = TOUCH) -> float | None:
        """How far a planted node travels backwards in one frame, median.

        This is `cmdl.py gait` measured over the contact node rather than the
        ankle, and it is the animation's own idea of how fast the body moves.
        """
        t = self.track()
        v = []
        for n, on in self.down(tol).items():
            v += [t[f - 1][n][2] - t[f][n][2]
                  for f in range(1, min(len(on), self.length + 1))
                  if on[f] and on[f - 1]]
        return statistics.median(v) if v else None


# --------------------------------------------------------------------------
# finding the skeleton a motion belongs to

def _first(pattern: str, root: pathlib.Path) -> pathlib.Path | None:
    hit = sorted(root.glob(pattern))
    return hit[0] if hit else None


def skeleton_for(cnom_path, root) -> pathlib.Path | None:
    """The `CMDL` a `CNOM` keys onto, by where the disc puts the two.

    Three arrangements cover everything with feet on it:

        npc.cpk/npc_03.pac/         the model sits beside the motion
        monster.cpk/pac/b01.pac/    the model is in monster.cpk/b01_00/
        character.cpk/motion.cpk/fas.pac/   the model is model.cpk/fas1

    The players' three body models share one skeleton, so the first is taken.
    `com` is the shared emote set and `cm` has no model at all - both borrow
    the skeleton of the class whose name they sort next to, which is sound
    because a `CNOM` binds by node name and the eight player skeletons carry
    the same names and the same ankle height to a tenth of a millimetre.
    """
    p = pathlib.Path(cnom_path)
    root = pathlib.Path(root)
    here = _first('*.CMDL', p.parent)
    if here is not None:
        return here
    d = p.parent.name
    if d.endswith('.pac'):
        stem = d[:-4]
        mon = root / 'monster.cpk' / f'{stem}_00' / 'model.pac' \
            / f'{stem}_00.CMDL'
        if mon.is_file():
            return mon
        if len(stem) == 3:
            sex, cls = stem[0], stem[1:]
            if stem == 'com':
                sex, cls = 'f', 'as'
            elif cls == 'cm':
                cls = 'as'
            m = root / 'character.cpk' / 'model.cpk' / f'{sex}{cls}1.pac' \
                / f'{sex}{cls}1.pac' / f'{sex}{cls}1.CMDL'
            if m.is_file():
                return m
    return None


def pairs(root):
    """Every `(mkc, cnom, cmdl)` the disc puts together.

    A `.mkc` sits in `<set>.mkc.pac` and its `CNOM` is one directory up under
    the same stem. Where either half is missing the animation is skipped, and
    `footfall` counts what it skipped.
    """
    root = pathlib.Path(root)
    for mkc in sorted(root.rglob('*.mkc')):
        cnom = mkc.parent.parent / (mkc.stem + '.CNOM')
        skel = skeleton_for(cnom, root)
        yield mkc, (cnom if cnom.is_file() else None), skel


def find(root, name: str) -> pathlib.Path:
    """A `CNOM` by name, or by path when one is given."""
    p = pathlib.Path(name)
    if p.is_file():
        return p
    root = pathlib.Path(root)
    stem = name[:-5] if name.endswith('.CNOM') else name
    hit = sorted(root.rglob(f'{stem}.CNOM'))
    if not hit:
        raise SystemExit(f'not found: {name}')
    return hit[0]


def load(root, name: str) -> tuple[Body, Play, pathlib.Path]:
    path = find(root, name)
    skel = skeleton_for(path, root)
    if skel is None:
        raise SystemExit(f'{path}: no skeleton found for it')
    body = Body(skel)
    if not body.contact:
        raise SystemExit(f'{skel}: no *_foot or *_toe node')
    return body, Play(body, Cnom(path.read_bytes(), path.name)), path


# --------------------------------------------------------------------------
# commands

def cmd_body(root, name) -> int:
    p = find(root, name) if not pathlib.Path(name).is_file() \
        else pathlib.Path(name)
    if p.suffix != '.CMDL':
        p = skeleton_for(p, root)
    body = Body(p)
    print(p)
    print(f'  {body.cmdl.nodes} nodes, {len(body.contact)} of them touch '
          f'the ground')
    for n in body.contact:
        print(f'    {n:<20} stands at y = {body.standing[n]:.4f}')
    rest = body.cmdl.world()
    print(f'  the lowest node in the rest pose is at '
          f'y = {min(m[1][3] for m in rest):.4f}')
    return 0


def cmd_track(root, name) -> int:
    body, play, path = load(root, name)
    print(f'{path}')
    print(f'  on {body.path.name}, {play.declared} frames declared, '
          f'{play.length} in the loop')
    t = play.track()
    on = play.down()
    print()
    head = '  frame'
    for n in body.contact:
        head += f'   {n[-12:]:>14}  down'
    print(head + '     slide')
    for f in range(len(t)):
        line = f'  {f:5d}'
        for n in body.contact:
            h = t[f][n][1] - body.standing[n]
            line += f'   y{h:+7.3f} z{t[f][n][2]:+6.3f}  ' \
                    f'{"on" if on[n][f] else "  "}  '
        low = min(body.contact, key=lambda n: t[f][n][1])
        if f and on[low][f] and on[low][f - 1]:
            line += f'  {t[f - 1][low][2] - t[f][low][2]:+7.4f}'
        print(line)
    s = play.slide()
    if s is not None:
        print()
        print(f'  the planted node slides back {s:.4f} m a frame '
              f'= {s * 30:.2f} m/s at 30 fps')
    return 0


def _events(mkc: Mkc) -> list[tuple[int, int]]:
    """Every `7ffa` in a `.mkc`, as `(frame, kind)`."""
    return [(r.frame, r.args[0] if r.args else -1)
            for r in mkc.records if r.op == 0x7FFA]


def _pct(v, k) -> float:
    return 100.0 * sum(1 for x in v if abs(x) <= k) / len(v) if v else 0.0


def _spread(label, v) -> None:
    s = sorted(v)
    print(f'{label} n {len(s):>6,}   median {statistics.median(s):>7.3f}   '
          f'p10 {s[len(s) // 10]:>7.3f}   p90 {s[len(s) * 9 // 10]:>7.3f}')


def cmd_footfall(root) -> int:
    """Every `7ffa` on the disc, against the frame the skeleton lands a foot.

    The two have nothing to do with each other until here. One is a byte in a
    presentation track, put there by hand; the other is forward kinematics
    over a quaternion channel, run on a skeleton the track never mentions. If
    the pose is wrong they have no reason to agree, and the control says how
    much agreement is worth having: the same question asked of an arbitrary
    frame of the same animation.
    """
    bodies: dict[str, Body] = {}
    seen = paired = skinned = firing = 0
    lifting = still = 0
    events: list[float] = []
    control: list[float] = []
    by_kind: dict[int, list[float]] = {}
    off: dict[float, list[tuple[int, int]]] = {t: [] for t in TOLS}
    ctl: dict[float, list[tuple[int, int]]] = {t: [] for t in TOLS}
    no_skel: set[str] = set()

    for mkc_path, cnom_path, skel in pairs(root):
        seen += 1
        if cnom_path is None:
            continue
        paired += 1
        if skel is None:
            no_skel.add(mkc_path.parent.name)
            continue
        body = bodies.get(str(skel))
        if body is None:
            body = bodies[str(skel)] = Body(skel)
        if not body.contact:
            continue
        skinned += 1
        fire = _events(Mkc(mkc_path.read_bytes(), str(mkc_path)))
        if not fire:
            continue
        play = Play(body, Cnom(cnom_path.read_bytes(), cnom_path.name))
        fire = [(f, k) for f, k in fire if 0 <= f <= play.declared]
        if play.declared < 4 or not fire:
            continue
        firing += 1
        if play.lift() <= LIFT:
            still += 1
            continue
        lifting += 1

        t = play.track()

        def arrival(f, track=t, b=body):
            """How far the lower foot fell over the three frames into `f`,
            and where it ends up - the two halves of *the foot arrives*."""
            n = min(b.contact, key=lambda k: track[f][k][1])
            g = max(0, f - BACK)
            return (track[g][n][1] - track[f][n][1],
                    track[f][n][1] - b.standing[n])

        for f, kind in fire:
            fell, low = arrival(f)
            events.append((fell, low))
            by_kind.setdefault(kind, []).append((fell, low))
        for f in range(play.declared + 1):
            control.append(arrival(f))
        for tol in TOLS:
            land = [g for g, _ in play.landings(tol)]
            if not land:
                continue
            for f, kind in fire:
                off[tol].append((min((g - f for g in land), key=abs), kind))
            for f in range(play.declared + 1):
                ctl[tol].append((min((g - f for g in land), key=abs), -1))

    print(f'{seen:,} .mkc files; {paired:,} have a CNOM one directory up; '
          f'{skinned:,} of those land on a skeleton with feet')
    if no_skel:
        print(f'  and {len(no_skel)} pacs resolve to no skeleton at all: '
              + ', '.join(sorted(no_skel)))
    print(f'  {firing:,} animations fire 7ffa; on {still:,} of them no foot '
          f'ever rises {LIFT * 100:.0f} cm, so the question is only asked of '
          f'the other {lifting:,}')
    if not events:
        return 1

    print()
    print(f'  the foot arrives: how far the lower foot fell over the '
          f'{BACK} frames into the event,')
    print('  and how high it is when it gets there, both in metres')
    print('                       n      fell   fell >2cm      height   '
          'on the floor')
    for label, v in (('    at 7ffa     ', events),
                     ('    at any frame', control)):
        fell = [x[0] for x in v]
        low = [x[1] for x in v]
        print(f'{label} {len(v):>7,}   {statistics.median(fell):>+7.4f}   '
              f'{100.0 * sum(1 for x in fell if x > 0.02) / len(v):>8.1f}%   '
              f'{statistics.median(low):>+7.4f}   '
              f'{_pct(low, 0.01):>10.1f}%')
    print('  (a foot on the floor says little on its own - in most animations '
          'one of the two')
    print('  always is. It is the falling and the frame that carry the '
          'result.)')

    print()
    print('  the frame 7ffa fires, against the frame the foot comes down')
    print('    a foot is down when it is within        7ffa fires there'
          '        an arbitrary frame does')
    print('    of where it stands        n      exact  within 1  within 2 '
          '     exact  within 1  within 2')
    for tol in TOLS:
        a = [x for x, _ in off[tol]]
        c = [x for x, _ in ctl[tol]]
        print(f'      {tol * 100:>2.0f} cm  {len(a):>17,}   '
              f'{_pct(a, 0):>6.1f}%   {_pct(a, 1):>6.1f}%   '
              f'{_pct(a, 2):>6.1f}%    {_pct(c, 0):>6.1f}%   '
              f'{_pct(c, 1):>6.1f}%   {_pct(c, 2):>6.1f}%')
    a = [x for x, _ in off[TOUCH]]
    print(f'    median offset at {TOUCH * 100:.0f} cm: '
          f'{statistics.median(a):+.1f} frames, mean '
          f'{statistics.fmean(a):+.2f}')
    keep = [x for x, k in off[TOLS[0]] if k != DRESS]
    print(f'    at {TOLS[0] * 100:.0f} cm with kind {DRESS} left out - see '
          f'below, it is not a footstep - {len(keep):,} events')
    print(f'    come to {_pct(keep, 0):.1f}% exact and '
          f'{_pct(keep, 1):.1f}% within one')

    print()
    print('  by which of its four cues 7ffa names')
    print('    kind             n      fell      height   on the floor')
    for k in sorted(by_kind):
        v = by_kind[k]
        fell = [x[0] for x in v]
        low = [x[1] for x in v]
        print(f'    {k} {KINDS.get(k, "?"):<9} {len(v):>7}   '
              f'{statistics.median(fell):>+7.4f}   '
              f'{statistics.median(low):>+7.4f}   {_pct(low, 0.01):>10.1f}%')
    return 0


# The named locomotion cycles, and the parameter each one is authored against.
CYCLES = (('walk', 'walk_sp'), ('run', 'run_sp'), ('run_dash', 'fast_sp'))

# The classes with a directory in `job.cpk`, which is the same thing as the
# classes with a parameter table. `cm`, `gn` and `nn` have motion sets and no
# table, so they are what the check gets to be checked against.
PLAYER = ('as', 'cl', 'hs', 'ht', 'mg', 'sw')


def cmd_locomotion(root, json_path) -> int:
    """Every named walk, run and dash, against the speed the table declares.

    `cmdl.py gait` made this measurement once, on `fas213run`, and
    [`units.md`](../docs/units.md) built the frame rate on it. Doing it on
    every cycle the disc ships is what turns one coincidence into a rule -
    and it is the players' cycles that have a parameter table to be checked
    against, so the two motion sets that have no class behind them are the
    control that comes free.
    """
    root = pathlib.Path(root)
    p = load_params(json_path)
    rows: dict[str, list] = {k: [] for k, _ in CYCLES}
    for d in sorted((root / 'character.cpk' / 'motion.cpk').iterdir()):
        if not d.is_dir():
            continue
        for path in sorted(d.glob('*.CNOM')):
            key = next((k for k, _ in reversed(CYCLES)
                        if path.stem.endswith(k)), None)
            if key is None:
                continue
            skel = skeleton_for(path, root)
            if skel is None:
                continue
            body = Body(skel)
            play = Play(body, Cnom(path.read_bytes(), path.name))
            rows[key].append((path.stem, body.name, play.declared,
                              play.slide(), d.name[1:3] in PLAYER))

    print(f'{pathlib.Path(json_path).stem} record 0, against every named '
          f'locomotion cycle on the disc')
    print('  a * marks a set with no directory in job.cpk - no class, and so '
          'no table to obey')
    for key, field in CYCLES:
        v = rows[key]
        print()
        print(f'  *{key}   {len(v)} cycles, {field} = {p[field]}')
        for label, sel in (('the six classes    ', True),
                           ('the other sets     ', False)):
            good = sorted(x[3] for x in v if x[3] is not None and x[4] is sel)
            if not good:
                continue
            near = sum(1 for x in good if abs(x - p[field]) <= 0.005)
            print(f'    {label} n {len(good):>2}   median '
                  f'{statistics.median(good):.4f} m a frame, '
                  f'{min(good):.4f} to {max(good):.4f}   '
                  f'{near} within 5 mm of {field}')
        for stem, model, frames, s, player in v:
            note = 'no frame with a foot down' if s is None \
                else f'{s:.4f}   {s - p[field]:+.4f} against {field}'
            mark = ('' if player else '*') + stem
            print(f'      {mark:<18} {model:<8} '
                  f'{frames:>3} frames   {note}')
    return 0


# --------------------------------------------------------------------------
# the emitter, which is a place on the body

SOUND = (0x7FF9, 0x7FFD)


def family(stem: str) -> str:
    """The models that are one actor: `b09_00`, `b09_01`, `b09_02`.

    A monster ships in two or three sets of armour and they share a rig, so
    an emitter may name a node only one of them declares."""
    if len(stem) == 6 and stem[0] in 'bz' and stem[1:3].isdigit() \
            and stem[3] == '_' and stem[4:].isdigit():
        return stem[:3]
    return stem


def _end(text: str, front: tuple, rear: tuple) -> str:
    """Which end of an animal a cue name or a node name is talking about."""
    if any(k in text for k in front):
        return 'front'
    if any(k in text for k in rear):
        return 'rear'
    return ''


def twin(name: str) -> str:
    """The node's mirror image, or an empty string when it has none."""
    for a, b in (('_l_', '_r_'), ('_r_', '_l_')):
        if a in name:
            return name.replace(a, b, 1)
    return ''


def cmd_emitter(root) -> int:
    """`7ff9`'s third argument, against the model's own locator table.

    The `.mkc` says a sound comes from emitter 1700 and stops there. `CMDL`
    section `S4` is a list of `(id, node)` pairs - numeric attachment points,
    the same ids the `.CTXT` collision and spring files are named after. The
    two are the same namespace, and once they are joined the vocabulary reads
    itself: 1300 is the head and carries the voice, 1100 and 1200 are the
    hands and carry the cues that end `_L` and `_R`, 1700 and 1800 are the
    feet and carry `STEP`.

    Then the skeleton says the same thing a second time. If the id really is
    the limb the sound comes from, that limb should be the one arriving on
    that frame - and it is, while its mirror twin is not moving at all.
    """
    root = pathlib.Path(root)
    # An id may bind to more than one node: `b09_00` declares 6100 twice,
    # once for its head mesh and once for the damaged one, and an actor's
    # armour variants share the rig. All of them are kept.
    tables: dict[str, dict[int, list]] = {}
    for p in sorted(root.rglob('*.CMDL')):
        try:
            body = Cmdl(p.read_bytes(), p.name)
            names = body.names(5)
        except (ValueError, struct.error):
            continue
        t = tables.setdefault(family(p.stem), {})
        for i, n in body.locators():
            name = names[n] if n < len(names) else ''
            got = t.setdefault(i, [])
            if name and name not in got:
                got.append(name)

    disc = Disc(root)
    bodies: dict[str, Body] = {}
    refs = 0
    fore = collections.Counter()
    by_id: dict[int, collections.Counter] = {}
    stray: list[str] = []
    fell: dict[str, list[tuple[float, float]]] = {}

    for mkc_path, cnom_path, skel in pairs(root):
        recs = [r for r in Mkc(mkc_path.read_bytes(), str(mkc_path)).records
                if r.op in SOUND and len(r.args) >= 3]
        refs += len(recs)
        recs = [r for r in recs if r.args[2]]
        table = tables.get(family(skel.stem), {}) if skel else {}
        mirrored = []
        for r in recs:
            node = table.get(r.args[2], [])
            if node:
                # A cue that says which end of the animal it comes from is a
                # second, independent reading of the same id - and the rig
                # calls a quadruped's forelimb a hand.
                cue = disc.cue(r.args[0], r.args[1]) or ''
                if 'STEP' in cue:
                    said = _end(cue, ('_F', 'FRONT'), ('_B', 'REAR'))
                    got = _end(node[0], ('hand', 'finger'),
                               ('toe', 'foot', 'claw'))
                    if said and got:
                        fore[(said, got)] += 1
                by_id.setdefault(r.args[2],
                                 collections.Counter())[tuple(node)] += 1
                if twin(node[0]):
                    mirrored.append((r, node[0], twin(node[0])))
            else:
                stray.append(f'{mkc_path.stem} frame {r.frame}, '
                             f'emitter {r.args[2]}')
        if not mirrored or cnom_path is None:
            continue
        body = bodies.get(str(skel)) or bodies.setdefault(str(skel),
                                                          Body(skel))
        want = sorted({n for _, a, b in mirrored for n in (a, b)
                       if n in body.index})
        mirrored = [m for m in mirrored
                    if m[1] in body.index and m[2] in body.index]
        if not mirrored:
            continue
        play = Play(body, Cnom(cnom_path.read_bytes(), cnom_path.name), want)
        t = play.track()
        for r, node, other in mirrored:
            if r.frame > play.declared:
                continue
            g = max(0, r.frame - BACK)
            key = 'hand' if 'hand' in node or 'finger' in node else \
                'foot' if any(k in node for k in ('toe', 'foot', 'claw')) \
                else 'elsewhere'
            fell.setdefault(key, []).append(
                (t[g][node][1] - t[r.frame][node][1],
                 t[g][other][1] - t[r.frame][other][1]))

    told = sum(sum(c.values()) for c in by_id.values())
    print(f'{refs:,} sound references; {refs - told - len(stray):,} leave the '
          f'emitter at 0 and {told + len(stray):,} name one')
    print(f'  {told:,} of those are a locator id on the actor own model - '
          f'CMDL section S4,')
    print('  the same table the .CTXT collision and spring files are named '
          'after')
    print()
    print('  emitter      n   the node its locator binds to')
    for e in sorted(by_id):
        c = by_id[e]
        print(f'  {e:>8} {sum(c.values()):>6}   '
              + ' | '.join(', '.join(n) + (f' x{k}' if len(c) > 1 else '')
                           for n, k in c.most_common(3)))
    if stray:
        print()
        print(f'  and {len(stray)} that resolve to nothing: '
              + '; '.join(stray[:4]))

    if fore:
        n = sum(fore.values())
        same = sum(v for k, v in fore.items() if k[0] == k[1])
        print()
        print(f'  {n} of them carry a cue whose name says which end of the '
              f'animal it is,')
        print(f'  and the locator is the matching pair on {same} '
              f'({100.0 * same / n:.1f}%):')
        for k in sorted(fore):
            print(f'    the cue says {k[0]:<6} and the locator is the '
                  f'{k[1]:<6} pair {fore[k]:>5}')

    if not fell:
        return 0
    print()
    print(f'  and the limb it names is the one that has just come down. '
          f'Over the {sum(len(v) for v in fell.values()):,}')
    print('  references whose emitter names a node with a mirror twin, how '
          'far each')
    print(f'  of the two fell over the {BACK} frames into the event:')
    print('    family          n   the named node   its twin   named fell '
          'further')
    for k in ('hand', 'foot', 'elsewhere'):
        v = fell.get(k)
        if not v:
            continue
        a = statistics.median(x[0] for x in v)
        b = statistics.median(x[1] for x in v)
        more = 100.0 * sum(1 for x in v if x[0] > x[1]) / len(v)
        print(f'    {k:<10} {len(v):>6}   {a:>+12.4f}   {b:>+9.4f}   '
              f'{more:>11.1f}%')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'body':
        return cmd_body(rest[0], rest[1])
    if cmd == 'track':
        return cmd_track(rest[0], rest[1])
    if cmd == 'footfall':
        return cmd_footfall(rest[0])
    if cmd == 'locomotion':
        return cmd_locomotion(rest[0], rest[1])
    if cmd == 'emitter':
        return cmd_emitter(rest[0])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
