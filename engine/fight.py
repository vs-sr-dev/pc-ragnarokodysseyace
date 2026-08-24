"""
fight.py - a monster on a stage: it decides, it turns, it swings, and the
swing reaches.

[`brain.py`](brain.py) runs the decision - the rule ladder, the weighted
table and the action it picks. This is the other half: an action becomes a
motion, a motion becomes an animation with an event list on it, and the hit
volumes on that list are placed against a body standing on the collision
mesh.

    python engine/fight.py fight  extract/tree 010_01_01 AI_Z01_Orc [frames]
    python engine/fight.py fights extract/tree [stage] [class json] [frames]
    python engine/fight.py reach extract/tree [glob]
    python engine/fight.py chain extract/tree

`fight` runs the loop. `reach` and `chain` are the measurements, and `reach`
is the one that says the chain is real.

## The chain, and where each link was read

    a rule                 SelectScript.dat        format_ai.md
      -> a group           ProbList.dat            format_ai.md
      -> an action         a weighted roll         format_ai.md
      -> a motion id       action + 200/401/301    format_ai.md
      -> an animation      <prefix><id><name>.CNOM format_cnom.md
      -> an event list     <kind>_<id>.anmcmd      format_anmcmd.md
      -> a hit volume      flag, three vectors     format_anmcmd.md
      -> a place in the world, on the bone the record names

Every arrow in that list was measured by a different session against a
different file. `chain` walks all of them at once and reports where each
one breaks.

## What `reach` measures, and why it is a join and not a plot

`_act.par` gives every action **one range** - "act 100 range 3.00, angle
67.50" - and [`format_ai.md`](../docs/format_ai.md) reads it as the gate the
engine puts in front of that action. Nothing on the disc says what the
distance *is* a distance to.

The `.anmcmd` for the same action's motion says how far its hit volumes get
from the body, which is a different file, read by a different tool, in the
same metres. `reach` puts the two side by side over every action of every
monster. They are independent measurements of the same quantity if the
reading is right, and unrelated numbers if it is not.

Two things are excluded and both are the disc's own convention:
`_act.par` writes **100.0 on an unused slot and 999.0 for "any"**, and an
action whose motion carries no hit record at all has no reach to compare.

## What the fight does not do

There is no damage. [`combat_loop.md`](../docs/combat_loop.md) ends in a
ledger of nine, and the damage expression is one of the five that needs the
EBOOT - so a hit here is reported as a **connection**, not as a number, and
the monster's hit points are an input to the run rather than something the
run takes down. Everything else in the loop is the disc's: the decision, the
gate, the motion, the frame the hit fires on and the volume it fires with.
"""
from __future__ import annotations

import collections
import fnmatch
import json
import math
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

import anmcmd                                                  # noqa: E402
import hitbox                                                  # noqa: E402
from actor import FPS, Actor, bearing, load as load_params     # noqa: E402
from brain import (ANGLE_AT, ANGLE_TO, Brain, Monster, State,  # noqa: E402
                   index)
from cnom import Cnom                                          # noqa: E402
from pose import Play                                          # noqa: E402
from world import World                                        # noqa: E402

APPROACH = 4                # the one action id that resolves to no motion
# `_act.par` writes 100.0 on an unused slot and 999.0 for "any"; 999999.0
# turns up on one monster and reads the same way. Anything from 100 m up is a
# sentinel and not a distance - the largest real gate on the disc is 45 m.
UNUSED = (100.0, 999.0)
SENTINEL = 100.0
MIN_RADIUS = 0.05           # what `hitbox.py obj` already uses for a hit


def load_json(path, record='0') -> dict:
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)[record]


# -- the animation an action names -----------------------------------------


class Move:
    """One action, resolved all the way to the volumes it swings."""

    def __init__(self, monster: Monster, action: int, root, index_=None):
        self.action = action
        self.motion, self.name = monster.motion_of(action)
        self.range = monster.ranges.get(action)
        self.angle = monster.angles.get(action)
        self.play = None
        self.anm = None
        self.frames = 0
        self.hits = []                  # (frame, Hit)
        self.reach = None
        # The animation and the event list are separate files and either can
        # be missing: 432 of the 1,109 motions a table can name have no
        # `.anmcmd` at all. A motion without one still takes time to play, so
        # the `CNOM` is looked up by the motion id and not through the list.
        if index_ is None:
            index_ = hitbox.cnom_index(root)
        stem = '%s%03d%s' % (monster.prefix, self.motion, self.name)
        cn = index_.get(stem)
        if cn is not None:
            self.cnom = Cnom(cn.read_bytes(), cn.name)
            self.frames = self.cnom.frames
        p = (pathlib.Path(root) / 'monster.cpk' / monster.kind /
             'animcmd.pac' / ('%s_%d.anmcmd' % (monster.kind, self.motion)))
        self.path = p if p.is_file() else None
        if self.path is None:
            return
        self.anm = anmcmd.Anmcmd(p.read_bytes(), p.name)
        self.hits = [(f, h) for f, op, h in hitbox.records_of(self.anm)]

    def place(self, actor, frame):
        """The hit volumes that fire on this frame, in the body's own space."""
        if self.play is None:
            if not self.hits or not hasattr(self, 'cnom'):
                return []
            self.play = Play(actor.body, self.cnom,
                             sorted(set(actor.names)))
        out = []
        for f, h in self.hits:
            if f != frame:
                continue
            q = hitbox.Placed(h, actor, self.play, frame, 'turned')
            if q.p0 is not None:
                out.append((h, q))
        return out

    def measure(self, actor):
        """How far from the body's own origin the volumes get, over every
        frame the list fires on. The radius is `+0x2C`, which is what
        [`hitbox.py`](hitbox.py) already draws a hit with."""
        best = 0.0
        seen = 0
        for f, h in self.hits:
            for hh, q in self.place(actor, f):
                seen += 1
                r = max(hh.sizes[0], MIN_RADIUS)
                for pt in (q.p0, q.p1):
                    if pt is None:
                        continue
                    best = max(best, math.hypot(pt[0], pt[2]) + r)
        self.reach = best if seen else None
        return self.reach


# -- the fight -------------------------------------------------------------


def closing_distance(m: Monster, pr: float, radius: float) -> float:
    """How close the player gets.

    Not a guess: the monster's own `_act.par` says the range at which each of
    its actions is worth starting, so the shortest of those is where its
    melee lives. A body that stops further out than that is standing where
    nothing the monster does can reach it - which is a fact about the player
    and not about the monster."""
    gates = [g for g in m.ranges.values() if 0 < g < SENTINEL]
    return min(gates) if gates else radius + pr + 1.0


class Enemy:
    """A monster standing somewhere, playing something."""

    def __init__(self, tree, name, x=0.0, y=0.0, z=0.0, heading=0.0):
        self.tree = pathlib.Path(tree)
        self.m = Monster(tree, name)
        self.brain = Brain(self.m)
        self.state = State()
        self.x, self.y, self.z, self.heading = x, y, z, heading
        p = self.tree / 'monster.cpk' / self.m.kind / (self.m.kind + '.json')
        self.p = load_json(p) if p.is_file() else {}
        self.radius = self.p.get('col_r', 1.0)
        self.turn_speed = self.p.get('rot_y_spd', 8.0)
        self.speed = self.p.get('run_sp', 0.1)
        self.actor = hitbox.actor_for('monster.cpk/%s/x' % self.m.kind,
                                      self.tree)
        self.index = hitbox.cnom_index(self.tree)
        self.moves = {}
        self.move = None                # what it is playing
        self.frame = 0
        self.since = 0                  # frames since the last action began
        self.last_act = 0
        self.log = collections.Counter()

    def resolve(self, action):
        if action not in self.moves:
            self.moves[action] = Move(self.m, action, self.tree, self.index)
        return self.moves[action]

    def walk(self, tx, tz, world=None, frames=1):
        """Close on the target at the monster's own `run_sp`, turning at its
        own `rot_y_spd`. Both are its JSON's."""
        for _ in range(frames):
            self.face(tx, tz)
            a = math.radians(self.heading)
            nx = self.x + math.sin(a) * self.speed
            nz = self.z + math.cos(a) * self.speed
            if math.dist((nx, nz), (tx, tz)) < self.radius:
                break
            self.x, self.z = nx, nz
            if world is not None:
                # `stand` rather than `floor`: the ground a walking monster
                # follows is the level it is already on, not the highest one
                # the mesh has over that point.
                y = world.stand(self.x, self.z, self.y)
                if y is not None:
                    self.y = y

    def face(self, tx, tz):
        want = bearing(self.x, self.z, tx, tz)
        d = ((want - self.heading + 180.0) % 360.0) - 180.0
        step = min(abs(d), self.turn_speed)
        self.heading = (self.heading + math.copysign(step, d)) % 360.0
        return abs(d)

    def world_point(self, p):
        """A point in the body's own space, put where the body is standing."""
        a = math.radians(self.heading)
        ca, sa = math.cos(a), math.sin(a)
        return (self.x + p[0] * ca + p[2] * sa,
                self.y + p[1],
                self.z - p[0] * sa + p[2] * ca)


def segment_distance(p, a, b) -> float:
    """Point to segment, which is all a capsule test needs."""
    ax, ay, az = a
    bx, by, bz = b
    vx, vy, vz = bx - ax, by - ay, bz - az
    wx, wy, wz = p[0] - ax, p[1] - ay, p[2] - az
    den = vx * vx + vy * vy + vz * vz
    t = 0.0 if den == 0 else max(0.0, min(1.0, (wx * vx + wy * vy + wz * vz)
                                          / den))
    cx, cy, cz = ax + vx * t, ay + vy * t, az + vz * t
    return math.dist(p, (cx, cy, cz))


def gap(points, radius, px, py, pz, pr, ph) -> float:
    """How far a hit volume passed from the player's capsule. Negative is a
    connection, and the number is what makes a miss legible: a volume that
    goes by at 0.1 m is a different thing from one that never comes near."""
    lo = (px, py, pz)
    hi = (px, py + ph, pz)
    best = None
    for p in points:
        if p is None:
            continue
        d = segment_distance(p, lo, hi) - radius - pr
        best = d if best is None else min(best, d)
    return 1e9 if best is None else best


def connects(points, radius, px, py, pz, pr, ph) -> bool:
    """Does a hit volume reach the player's capsule?

    The player is a vertical segment from the feet to `ph` with radius `pr`,
    which is [`actor.py`](actor.py)'s own body: `col_r` from the class JSON."""
    lo = (px, py, pz)
    hi = (px, py + ph, pz)
    for p in points:
        if p is None:
            continue
        if segment_distance(p, lo, hi) <= radius + pr:
            return True
    return False


def fill(state: State, e: Enemy, px, py, pz, hp_rate, elapsed):
    """Answer the predicates that a running fight can answer.

    The two bands are this file's reading and are marked as such in
    [`brain.py`](brain.py): `getAngleTypeToTarget` is where the target sits in
    my frame, two bands; `getAngleTypeAtTarget` is where I sit in the
    target's, four."""
    dx, dz = px - e.x, pz - e.z
    state.target_range = math.hypot(dx, dz)
    state.target_pos_y = py - e.y
    want = bearing(e.x, e.z, px, pz)
    off = abs(((want - e.heading + 180.0) % 360.0) - 180.0)
    state.angle_to = ANGLE_TO[0] if off <= 90.0 else ANGLE_TO[1]
    state.angle_at = ANGLE_AT[int((off / 90.0) % 4)]
    state.hp_rate = hp_rate
    state.total_time = elapsed / FPS
    state.boss_time = elapsed / FPS
    state.timers = {t: e.since / FPS for t in range(10, 18)}
    state.timers[119] = e.since / FPS
    state.last_act = e.last_act
    state.lock_range = state.target_range
    # `checkRangeParam` is 0, 1 or 2 and `_act.par` gives every action one
    # range. Inside it, beyond it, and beyond twice it: the disc says only
    # that the three are distinct.
    rng = e.m.ranges.get(e.last_act)
    if rng and rng not in UNUSED:
        state.range_band = (0 if state.target_range <= rng else
                            1 if state.target_range <= 2 * rng else 2)
    return state


def cmd_fight(tree, stage='010_01_01', monster='AI_Z01_Orc',
              json_path='job.cpk/sw/sw.json', frames='900',
              hp_rate='100') -> int:
    """One monster, one player capsule, one stage, and the loop between."""
    root = pathlib.Path(tree)
    world = World(root / 'stage.cpk' / stage / 'param.pac')
    spawn = world.marker('appear01')
    params = load_params(root / json_path)
    player = Actor(params, spawn.position[0], spawn.position[1],
                   spawn.position[2], spawn.rotation[1])
    # The monster stands on the first spawner the stage declares, which is
    # what `enemy_gen.bin` addresses - see format_quest.md.
    gen = [m for m in world.stage.markers if m.kind.startswith('emgen')]
    at = gen[0] if gen else world.stage.markers[0]
    ground = world.floor(at.position[0], at.position[2])
    e = Enemy(tree, monster, at.position[0],
              at.position[1] if ground is None else ground,
              at.position[2], (at.rotation[1] + 180.0) % 360.0)
    rng = random.Random(20260823)
    print('%s on %s: the monster stands on %s, %.1f m from appear01'
          % (e.m.name, stage, at.name,
             math.dist((e.x, e.z), (player.x, player.z))))
    print('  %s: col_r %.2f, run_sp %.3f, rot_y_spd %.1f, %d groups, '
          '%d actions gated' % (e.m.kind, e.radius, e.speed, e.turn_speed,
                                len(e.m.groups), len(e.m.ranges)))
    height = params.get('col_h', 1.6)
    close = closing_distance(e.m, params.get('col_r', 0.5), e.radius)
    print('  the player closes to %.2f m, the shortest range its `_act.par` '
          'gates an action at' % close)
    fired = touched = played = decided = approached = 0
    blocked = inside = 0
    nearest = 1e9
    chosen = collections.Counter()
    events = []
    for f in range(int(frames)):
        # the player walks up to the monster and holds at arm's length
        d = math.dist((player.x, player.z), (e.x, e.z))
        if d > close:
            player.step(world, gait='run',
                        facing=bearing(player.x, player.z, e.x, e.z))
        fill(e.state, e, player.x, player.y, player.z, int(hp_rate), f)
        e.state.rand = rng.randrange(10001)
        if e.move is None:
            g, action, mid, name = e.brain.act(e.state, rng)
            decided += 1
            if action is None:
                continue
            gate = e.m.ranges.get(action)
            far = (gate is not None and 0 < gate < SENTINEL
                   and e.state.target_range > gate)
            if action == APPROACH or far:
                # `_act.par` gives the action one range, and the reading here
                # is that it is a gate: too far, and the monster closes
                # instead. `reach` is the measurement that supports it.
                approached += 1
                blocked += far
                e.walk(player.x, player.z, world, 20)
                e.last_act = action
                e.since = 0
                continue
            chosen[(action, mid, name)] += 1
            inside += 1
            e.last_act = action
            e.since = 0
            mv = e.resolve(action)
            if mv.frames:
                e.move, e.frame, played = mv, 0, played + 1
            continue
        e.since += 1
        for h, q in e.move.place(e.actor, e.frame):
            fired += 1
            pts = [e.world_point(p) for p in (q.p0, q.p1) if p is not None]
            r = max(h.sizes[0], MIN_RADIUS)
            miss = gap(pts, r, player.x, player.y, player.z,
                       params.get('col_r', 0.5), height)
            if miss <= 0:
                touched += 1
                events.append((f, e.move.name, e.move.motion, h.slot,
                               round(d, 2), round(r, 2)))
            else:
                nearest = min(nearest, miss)
        e.frame += 1
        if e.frame > e.move.frames:
            e.move = None
        else:
            e.face(player.x, player.z)
    print()
    print('  %d frames = %.1f s, %d decisions, %d motions played, '
          '%d approaches' % (int(frames), int(frames) / FPS, decided, played,
                             approached))
    print('  %d actions started inside their own `_act.par` gate, '
          '%d put off because the target was beyond it' % (inside, blocked))
    print('  %d hit records fired, %d of them reaching the player%s'
          % (fired, touched,
             '' if nearest > 1e8 else
             '; the nearest miss passed %.2f m off the capsule' % nearest))
    for f, name, mid, slot, dist, r in events[:8]:
        print('    frame %4d  %-10s motion %3d slot %d at %.2f m, '
              'radius %.2f' % (f, name, mid, slot, dist, r))
    print('  the actions it chose:')
    for (action, mid, name), n in chosen.most_common(10):
        rng_ = e.m.ranges.get(action)
        print('    %3dx  action %-4d motion %-4s %-10s gate %s'
              % (n, action, mid or '-', name or '(none)',
                 '-' if rng_ is None else
                 ('any' if rng_ in UNUSED else '%.2f m' % rng_)))
    return 0


def _one_fight(tree, world, params, monster, frames, rng, spawn, hold=1.0):
    """The loop without the printing. `hold` scales the closing distance."""
    player = Actor(params, spawn[0], spawn[1], spawn[2], spawn[3])
    gen = [m for m in world.stage.markers if m.kind.startswith('emgen')]
    at = gen[0] if gen else world.stage.markers[0]
    ground = world.floor(at.position[0], at.position[2])
    e = Enemy(tree, monster, at.position[0],
              at.position[1] if ground is None else ground,
              at.position[2], (at.rotation[1] + 180.0) % 360.0)
    if e.actor is None:
        return None
    height = params.get('col_h', 1.6)
    pr = params.get('col_r', 0.5)
    close = closing_distance(e.m, pr, e.radius) * hold
    fired = touched = played = decided = 0
    nearest = 1e9
    for f in range(frames):
        d = math.dist((player.x, player.z), (e.x, e.z))
        if d > close:
            player.step(world, gait='run',
                        facing=bearing(player.x, player.z, e.x, e.z))
        fill(e.state, e, player.x, player.y, player.z, 100, f)
        e.state.rand = rng.randrange(10001)
        if e.move is None:
            g, action, mid, name = e.brain.act(e.state, rng)
            decided += 1
            if action is None:
                continue
            gate = e.m.ranges.get(action)
            if action == APPROACH or (gate is not None
                                      and 0 < gate < SENTINEL
                                      and e.state.target_range > gate):
                e.walk(player.x, player.z, world, 20)
                e.last_act, e.since = action, 0
                continue
            e.last_act, e.since = action, 0
            mv = e.resolve(action)
            if mv.frames:
                e.move, e.frame, played = mv, 0, played + 1
            continue
        e.since += 1
        for h, q in e.move.place(e.actor, e.frame):
            fired += 1
            pts = [e.world_point(p) for p in (q.p0, q.p1) if p is not None]
            miss = gap(pts, max(h.sizes[0], MIN_RADIUS), player.x, player.y,
                       player.z, pr, height)
            if miss <= 0:
                touched += 1
            else:
                nearest = min(nearest, miss)
        e.frame += 1
        if e.frame > e.move.frames:
            e.move = None
        else:
            e.face(player.x, player.z)
    return decided, played, fired, touched, nearest


def cmd_fights(tree, stage='010_01_01', json_path='job.cpk/sw/sw.json',
               frames='900', hold='1.0', want='*') -> int:
    """Every monster on the disc, fought on one stage.

    One stage and one class, so the only thing that varies is the monster.
    What the row says is whether its own tables, its own motions and its own
    hit records get it from standing there to touching the player."""
    root = pathlib.Path(tree)
    world = World(root / 'stage.cpk' / stage / 'param.pac')
    m0 = world.marker('appear01')
    spawn = (m0.position[0], m0.position[1], m0.position[2], m0.rotation[1])
    params = load_params(root / json_path)
    ran = acted = swung = landed = skipped = 0
    quiet = []
    for name in sorted(index(tree)):
        if not fnmatch.fnmatch(name, want):
            continue
        rng = random.Random(20260823)
        try:
            got = _one_fight(tree, world, params, name, int(frames), rng,
                             spawn, float(hold))
        except (ValueError, KeyError, IndexError) as exc:
            skipped += 1
            print('  %-24s %s' % (name, exc))
            continue
        if got is None:
            skipped += 1
            continue
        decided, played, fired, touched, nearest = got
        ran += 1
        acted += played > 0
        swung += fired > 0
        landed += touched > 0
        if not touched:
            quiet.append((name, played, fired, nearest))
    print('%d monsters fought on %s for %s frames each, the player closing '
          'to %s of the shortest range that monster gates an action at, '
          '%d skipped' % (ran, stage, frames, hold, skipped))
    print('  %d played a motion, %d fired a hit record, **%d reached the '
          'player**' % (acted, swung, landed))
    close_calls = sum(1 for _, _, f_, n in quiet if f_ and n < 1.0)
    if quiet:
        print('  %d never landed one, %d of which came within a metre:'
              % (len(quiet), close_calls))
        for name, played, fired, n in sorted(quiet, key=lambda t: t[3])[:10]:
            print('    %-24s %2d motions, %3d hit records, nearest %s'
                  % (name, played, fired,
                     '-' if n > 1e8 else '%.2f m' % n))
    return 0


# -- the two sweeps --------------------------------------------------------


def cmd_reach(tree, want='*') -> int:
    """`_act.par`'s range against the reach of the same action's hit volumes.

    Two files, two tools, the same metres. Nothing joins them but the action
    id, and the action id was read off a third."""
    root = pathlib.Path(tree)
    idx = hitbox.cnom_index(root)
    rows = []
    n_mon = 0
    no_anm = no_hit = sentinel = 0
    for name in sorted(index(tree)):
        if not fnmatch.fnmatch(name, want):
            continue
        m = Monster(tree, name)
        actor = hitbox.actor_for('monster.cpk/%s/x' % m.kind, root)
        if actor is None:
            continue
        n_mon += 1
        for action, gate in sorted(m.ranges.items()):
            if gate >= SENTINEL or gate <= 0:
                sentinel += 1
                continue
            mv = Move(m, action, root, idx)
            if mv.path is None:
                no_anm += 1
                continue
            r = mv.measure(actor)
            if r is None:
                no_hit += 1
                continue
            rows.append((m.name, action, gate, r))
    if not rows:
        print('nothing to compare')
        return 1
    gates = [g for _, _, g, _ in rows]
    reach = [r for _, _, _, r in rows]
    r = _r(gates, reach)
    print('%d monsters, %d actions with a real range in `_act.par` and a hit '
          'record on their motion' % (n_mon, len(rows)))
    print('  %d actions have a range but no `.anmcmd`, %d have one with no '
          'hit record; %d more carry a sentinel range of %g or more'
          % (no_anm, no_hit, sentinel, SENTINEL))
    print('  the gate runs %.2f to %.2f m, median %.2f; the reach %.2f to '
          '%.2f, median %.2f'
          % (min(gates), max(gates), _median(gates),
             min(reach), max(reach), _median(reach)))
    print('  **correlation %.3f** over %d pairs' % (r, len(rows)))
    shuffled = _control(gates, reach)
    print('  the same pairs reshuffled 200 times: %.3f on average, %.3f at '
          'the best' % (shuffled[0], shuffled[1]))
    near = sum(1 for _, _, g, rr in rows if abs(rr - g) <= 1.5)
    over = sum(1 for _, _, g, rr in rows if rr > g)
    print('  %d of %d land within 1.5 m of their gate, and the reach is '
          'shorter than the gate on %d' % (near, len(rows), len(rows) - over))
    band = collections.Counter()
    for _, _, g, rr in rows:
        band[max(-5, min(5, round(rr - g)))] += 1
    print('  reach minus gate, to the metre, clamped at 5:')
    for k in sorted(band):
        print('    %+3d m  %4d  %s' % (k, band[k], '#' * (band[k] // 4)))
    rows.sort(key=lambda t: -(t[3] - t[2]))
    print('  the four furthest over and the four furthest under:')
    for name, action, g, r in rows[:4] + rows[-4:]:
        print('    %-22s act %-4d gate %6.2f  reach %6.2f' % (name, action,
                                                              g, r))
    return 0


def _median(v):
    v = sorted(v)
    return v[len(v) // 2]


def _control(gates, reach, n=200):
    """The same two columns, paired at random. Two lists of distances will
    correlate a little whatever happens; this says how much."""
    rng = random.Random(20260823)
    best = total = 0.0
    for _ in range(n):
        shuffled = reach[:]
        rng.shuffle(shuffled)
        c = abs(_r(gates, shuffled))
        total += c
        best = max(best, c)
    return total / n, best


def _r(xs, ys) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def cmd_chain(tree) -> int:
    """Every link of action -> motion -> animation -> event list, counted."""
    root = pathlib.Path(tree)
    idx = hitbox.cnom_index(root)
    acts = named = with_anm = with_hit = 0
    mons = 0
    per = collections.Counter()
    for name in sorted(index(tree)):
        m = Monster(tree, name)
        mons += 1
        seen = set()
        for items in m.groups.values():
            for action, _ in items:
                if action in seen:
                    continue
                seen.add(action)
                acts += 1
                mid, mname = m.motion_of(action)
                if mname:
                    named += 1
                mv = Move(m, action, root, idx)
                if mv.path is not None:
                    with_anm += 1
                    if mv.hits:
                        with_hit += 1
                    else:
                        per['motion with an event list and no hit'] += 1
                elif mname:
                    per['motion with no event list'] += 1
                else:
                    per['action that names no motion'] += 1
    print('%d monsters, %d distinct actions their tables can pick' % (mons,
                                                                      acts))
    print('  %d name a motion in their own pac' % named)
    print('  %d of those have an `.anmcmd`, %d of which carry a hit record'
          % (with_anm, with_hit))
    for k, n in per.most_common():
        print('  %5d  %s' % (n, k))
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    cmd, rest = a[0], a[1:]
    if cmd == 'fight' and rest:
        return cmd_fight(*rest)
    if cmd == 'fights' and rest:
        return cmd_fights(*rest)
    if cmd == 'reach' and rest:
        return cmd_reach(*rest)
    if cmd == 'chain' and rest:
        return cmd_chain(*rest)
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
