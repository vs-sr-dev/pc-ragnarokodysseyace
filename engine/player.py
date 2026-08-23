"""
player.py - the player's half of the fight: a class presses a button, swings,
and the blow lands on a named part of a monster's body.

[`fight.py`](fight.py) runs the monster's half - it decides out of its own
tables, closes, plays a motion and fires the hit records on it into a volume
that reaches the player. This file is the same machinery pointed the other
way, and the two halves meet in the middle: **the same 116-byte hit record,
the same `col_hit` capsules, the same metres**. What is different is who
chooses, and that turns out to be the disc's business too.

    python engine/player.py combo   extract/tree [class]
    python engine/player.py swing   extract/tree sw sss z01_00
    python engine/player.py swings  extract/tree [hold] [class]
    python engine/player.py parts   extract/tree
    python engine/player.py arrows  extract/tree
    python engine/player.py reach   extract/tree
    python engine/player.py duel    extract/tree 010_01_01 AI_Z01_Orc sw
    python engine/player.py duels   extract/tree sw

## The player decides too, and the table is `s_combo_graph`

A monster picks its action out of `ProbList` with a weighted roll. A player
picks it with a button - and the class's own `objbin.bin` ships the graph that
says which button leads where: **189 nodes over the six classes**, each a
motion and its outgoing edges, each edge a button, a target and the frame
window the input is taken in. [`elbn.py`](../tools/elbn.py) reads it and
checks it twice; this file *walks* it, so a combo here is a button string and
not a file name.

## Where a blow lands

The target side is already read. `region_data` in a monster's `objbin.bin`
names its body parts and says which `col_hit` capsules each one owns, and
`region_data_brk` does the same for the parts that break off. So a volume that
reaches a capsule reaches a **named part**, and that is what
[`combat_loop.md`](../docs/combat_loop.md) step 2 needs before the damage
expression - which is the EBOOT's, and is not here.

## What is the player's and what is the monster's

Both bodies stand on flat ground, the monster in its rest pose and the player
animated by the class's own `CNOM`. The player stands at `col_r + col_r`, both
numbers off the two JSONs, which is as close as two capsules can get. Nothing
about that distance is fitted: it is where a body ends up when it walks into
another one.

The monster does not flinch, dodge or turn, exactly as the player did not in
[`milestone_fight.md`](../docs/milestone_fight.md) - so a landed hit is a
**connection** and not a number, and a miss by a hair is reported as a miss.
"""
from __future__ import annotations

import collections
import fnmatch
import itertools
import math
import pathlib
import random
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

import anmcmd                                                  # noqa: E402
import hitbox                                                  # noqa: E402
from actor import FPS, Actor, bearing, load as load_params     # noqa: E402
from brain import index as ai_index                            # noqa: E402
from cmdl import Cmdl                                          # noqa: E402
from cnom import Cnom                                          # noqa: E402
from elbn import (Elbn, arrow_rows, capsules,               # noqa: E402
                  combo_nodes, region_rows)
from fight import (MIN_RADIUS, SENTINEL, Enemy,                # noqa: E402
                   fill, load_json)
from pose import Play                                          # noqa: E402
from world import World                                        # noqa: E402

# The six classes, their weapon prefix in `character.cpk/weapon.cpk`, and the
# kind `it_db_weapon.bin` column 5 gives them - see combat_loop.md section 3,
# where the six starting weapons partition the table 75 rows apiece.
CLASSES = {
    'as': ('assassin', 0, 'katar'),
    'cl': ('cleric', 1, 'mace'),
    'hs': ('hammersmith', 3, 'hammer'),
    'ht': ('hunter', 4, 'bow'),
    'mg': ('mage', 5, 'staff'),
    'sw': ('warrior', 7, 'two-handed sword'),
}
AIR = (3, 4, 5)
LETTER = {0: 's', 1: 'l', 2: 't', 3: 's', 4: 'l', 5: 't'}


# -- geometry ---------------------------------------------------------------


def segment_gap(p0, p1, q0, q1) -> float:
    """The closest distance between two segments.

    A hit volume is a point or a pair of points with a radius, and a
    `col_hit` capsule is a pair of points with a radius, so every test in
    this file is this function minus the two radii.
    """
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = q1[0] - q0[0], q1[1] - q0[1], q1[2] - q0[2]
    wx, wy, wz = p0[0] - q0[0], p0[1] - q0[1], p0[2] - q0[2]
    a = ux * ux + uy * uy + uz * uz
    b = ux * vx + uy * vy + uz * vz
    c = vx * vx + vy * vy + vz * vz
    d = ux * wx + uy * wy + uz * wz
    e = vx * wx + vy * wy + vz * wz
    den = a * c - b * b
    if den < 1e-12:                      # parallel, or one of them a point
        s = 0.0
        t = (e / c) if c > 1e-12 else 0.0
    else:
        s = (b * e - c * d) / den
        t = (a * e - b * d) / den
    s = max(0.0, min(1.0, s))
    t = max(0.0, min(1.0, t))
    # one Gauss-Seidel pass is enough once both are clamped
    if c > 1e-12:
        t = max(0.0, min(1.0, (e + b * s) / c))
    if a > 1e-12:
        s = max(0.0, min(1.0, (b * t - d) / a))
    return math.dist((p0[0] + ux * s, p0[1] + uy * s, p0[2] + uz * s),
                     (q0[0] + vx * t, q0[1] + vy * t, q0[2] + vz * t))


def turn(p, x, y, z, heading):
    """A point in a body's own space, put where that body stands."""
    a = math.radians(heading)
    ca, sa = math.cos(a), math.sin(a)
    return (x + p[0] * ca + p[2] * sa, y + p[1], z - p[0] * sa + p[2] * ca)


# -- a body, on either side of the fight ------------------------------------


def place(actor, owner=None) -> list[dict]:
    """An actor's `col_hit` capsules, in its own space, turned by their bones.

    The same function for the monster and for the player, because it is the
    same record: [`format_elbn.md`](../docs/format_elbn.md)'s `col_hit`, a
    bone and two endpoints and a radius. The rest pose is enough - the
    numbers are body-sized, and [`hitbox.py`](hitbox.py) settled the reading
    that stands a body up against the one that lays it on the floor.
    """
    out: list[dict] = []
    if actor is None:
        return out
    rest = actor.cmdl.world()
    for i, (bone, va, vb, r0, r1) in enumerate(actor.col_hit):
        n = actor.node(bone)
        if n is None:
            continue
        m = rest[n]
        name, brk = (owner or {}).get(i, ('-', False))
        out.append({'i': i, 'bone': actor.names[n], 'part': name,
                    'break': brk, 'r': max(r0, r1),
                    'a': hitbox.apply(m, va), 'b': hitbox.apply(m, vb)})
    return out


def against(parts, at, points, r):
    """Which of a body's capsules a volume reaches, deepest first.

    `points` are already in the world and `at` is where the body stands. The
    number returned with each capsule is the overlap in metres, which is what
    makes a near miss legible next to a solid hit.
    """
    p0 = points[0]
    p1 = points[1] if len(points) > 1 and points[1] is not None else p0
    x, y, z, heading = at
    out = []
    for c in parts:
        d = segment_gap(p0, p1, turn(c['a'], x, y, z, heading),
                        turn(c['b'], x, y, z, heading))
        out.append((d - r - c['r'], c))
    out.sort(key=lambda t: t[0])
    return out


# -- the target -------------------------------------------------------------


class Target:
    """A monster standing still: its `col_hit` capsules, and the part each
    one belongs to.

    `region_data` and `region_data_brk` both index `col_hit` positionally, and
    between them they own most of it - what is left over is a capsule no
    region claims, which `swings` counts rather than hides.
    """

    def __init__(self, tree, kind: str, x=0.0, y=0.0, z=0.0, heading=0.0):
        self.tree, self.kind = pathlib.Path(tree), kind
        self.actor = hitbox.actor_for('monster.cpk/%s/x' % kind, self.tree)
        self.x, self.y, self.z, self.heading = x, y, z, heading
        ob = self.tree / 'monster.cpk' / kind / 'objbin.bin'
        self.owner: dict[int, tuple[str, bool]] = {}
        self.regions: list = []
        self.broken: list = []
        if ob.is_file():
            f = Elbn(ob.read_bytes(), ob.name)
            self.regions = region_rows(f)
            self.broken = region_rows(f, 'region_data_brk')
            for r in self.regions:
                for i in r['hit']:
                    self.owner.setdefault(i, (r['name'], False))
            for r in self.broken:
                for i in r['hit']:
                    self.owner[i] = (r['name'], True)
        js = self.tree / 'monster.cpk' / kind / (kind + '.json')
        self.p = load_json(js) if js.is_file() else {}
        self.radius = self.p.get('col_r', 1.0)
        self.parts = self._place()

    def _place(self):
        return place(self.actor, self.owner)

    def world(self, p):
        return turn(p, self.x, self.y, self.z, self.heading)

    @property
    def height(self) -> float:
        top = 0.0
        for c in self.parts:
            top = max(top, c['a'][1] + c['r'], c['b'][1] + c['r'])
        return top

    def struck(self, points, r):
        return against(self.parts, (self.x, self.y, self.z, self.heading),
                       points, r)


# -- the attacker -----------------------------------------------------------


class Attack:
    """One `.anmcmd` list of a player class, resolved to what it swings."""

    def __init__(self, cls: str, path: pathlib.Path, root, index_):
        self.cls, self.path = cls, path
        self.stem = path.stem
        m = re.match(r'^%s(\d+)(.*)$' % cls, self.stem)
        if m:
            self.motion, self.verb = int(m.group(1)), m.group(2)
        elif re.fullmatch(r'\d+', self.stem):
            # The hunter names 115 of its lists with a bare number and no
            # class prefix, and `Arsenal.shots` reads them.
            self.motion, self.verb = int(self.stem), ''
        else:
            self.motion, self.verb = 0, self.stem
        self.anm = anmcmd.Anmcmd(path.read_bytes(), path.name)
        self.hits = [(f, h) for f, op, h in hitbox.records_of(self.anm)]
        self.cnom = None
        self.frames = 0
        self.play = None
        cn = hitbox.motion_for(path.name, root, index_)
        if cn is not None:
            self.cnom = Cnom(cn.read_bytes(), cn.name)
            self.frames = self.cnom.frames
        self.reach = None
        self.volley = None
        self.lasts = self.frames

    def volumes(self, actor):
        """Every volume this list fires, in the player's own space.

        A list with no animation still fires: 132 of the 391 player lists
        that carry a hit record have no `CNOM` of their own - the hunter's
        arrows and the bullet lists are named by number - and those are
        placed in the rest pose, which is the frame the record's own bone
        offsets are written against.
        """
        if self.play is None and self.cnom is not None:
            self.play = Play(actor.body, self.cnom, sorted(set(actor.names)))
        out = []
        for f, h in self.hits:
            if self.play is None:
                m = actor.cmdl.world()

                class _Rest:                      # the rest pose as a `Play`
                    @staticmethod
                    def matrix(name, frame):
                        return m[actor.names.index(name)]
                q = hitbox.Placed(h, actor, _Rest, 0.0, 'turned')
            else:
                if f > self.frames:
                    continue
                q = hitbox.Placed(h, actor, self.play, float(f), 'turned')
            if q.p0 is None:
                continue
            pts = [q.p0] + ([q.p1] if q.p1 is not None else [])
            out.append((f, pts, max(h.sizes[0], MIN_RADIUS), h))
        return out

    def flies(self) -> bool:
        """A list with no animation of its own and a bare number for a name
        is a projectile: it is spawned by the motion that names it and then
        it travels, which is why it has nothing to be posed against."""
        return self.cnom is None and self.verb == '' and self.motion >= 1000

    def measure(self, actor) -> float | None:
        """How far from the body's own origin this list's volumes get.

        The same measure [`fight.py`](fight.py) `reach` takes on the monster
        side, so the two numbers can be put in one table: the horizontal
        distance to the furthest point of a volume, plus its radius.
        """
        best = None
        for f, pts, r, h in self.volumes(actor):
            for p in pts:
                d = math.hypot(p[0], p[2]) + r
                best = d if best is None else max(best, d)
        self.reach = best
        return best


class Arsenal:
    """One class: its skeleton, its combo graph and its animation lists."""

    def __init__(self, tree, cls: str):
        self.tree, self.cls = pathlib.Path(tree), cls
        self.name, self.kind, self.weapon = CLASSES[cls]
        self.actor = hitbox.actor_for('job.cpk/%s/x' % cls, self.tree)
        self.params = load_params(self.tree / 'job.cpk' / cls /
                                  ('%s.json' % cls))
        ob = self.tree / 'job.cpk' / cls / 'objbin.bin'
        f = Elbn(ob.read_bytes(), ob.name)
        self.nodes = {n['index']: n for n in combo_nodes(f)}
        self.body = capsules(f, 'col_hit')
        self.arrows = arrow_rows(f)
        self.index = hitbox.cnom_index(self.tree)
        self.lists: dict[int, list[Attack]] = {}
        for p in sorted((self.tree / 'job.cpk' / cls /
                         'animcmd.pac').glob('*.anmcmd')):
            a = Attack(cls, p, self.tree, self.index)
            if a.hits:
                self.lists.setdefault(a.motion, []).append(a)

    def flight(self) -> dict | None:
        """The flight this file gives an arrow.

        `ht_arrow_tbl` has 42 rows and nothing yet says which of them a
        given list uses - the id is presumably in the opcode that spawns it,
        and that opcode is one of the thirty `.anmcmd` still unread. What
        the choice does *not* change is whether the arrow reaches a body
        standing two metres away, because every row with a speed at all
        covers that in its first two frames: see `arrows`. So the row taken
        is the one 17 of the 42 agree on, and it is named where it is used.
        """
        live = [a for a in self.arrows if a['speed'] > 0]
        if not live:
            return None
        common = collections.Counter(
            (a['life'], round(a['speed'], 3), round(a['gravity'], 3))
            for a in live).most_common(1)[0][0]
        return {'life': common[0], 'speed': common[1], 'gravity': common[2]}

    def attack(self, motion: int) -> Attack | None:
        """The plain list for a motion - not its `_g2` or `_just` twin."""
        got = self.lists.get(motion)
        if not got:
            return None
        got = sorted(got, key=lambda a: (len(a.verb), a.verb))
        return got[0]

    def shots(self, motion: int) -> list[Attack]:
        """The projectile lists a motion fires, if it fires any.

        The hunter puts almost nothing on its combo animations: 27 of its 29
        graph nodes carry no hit record at all, because a bow does its damage
        with an arrow that has already left. Those arrows are lists named
        with a bare number, and the number is **`1` then the motion then an
        optional variant digit** - `ht1311` and `ht13110` to `ht13114` for
        motion 311. `combo` counts the rule rather than assuming it.
        """
        out = []
        for i, v in self.lists.items():
            if i < 1000:
                continue
            text = str(i)
            if text[:1] != '1':
                continue
            if int(text[1:]) == motion or (len(text) == 5
                                           and int(text[1:4]) == motion):
                out.extend(v)
        return out

    def at_node(self, node: int) -> Attack | None:
        """What a node swings. A node can name more than one motion - a hold
        is `_st`, then the loop, then `_en` - and the records are on whichever
        of them is the swing, so the first that carries any is the answer
        rather than the first named."""
        for m in self.nodes.get(node, {}).get('motions', []):
            a = self.attack(m)
            if a is not None:
                return a
        for m in self.nodes.get(node, {}).get('motions', []):
            got = self.shots(m)
            if got:
                return sorted(got, key=lambda a: a.motion)[0]
        return None

    def press(self, buttons, node=0):
        """Walk the graph. Returns the nodes visited, in order.

        `buttons` are the codes `s_combo_graph` uses - 0, 1, 2 on the ground
        and 3, 4, 5 in the air - or the letters `s`, `l` and `t`, which this
        file maps onto them. An input the current node has no edge for ends
        the combo, which is what a graph with no edge means.
        """
        out = []
        for b in buttons:
            n = self.nodes.get(node)
            if n is None:
                break
            want = [e for e in n['edges'] if e['button'] == b]
            if not want:
                break
            node = want[0]['to']
            out.append((node, want[0]))
        return out

    def combo_of(self, text: str, air=False):
        """A button string as button codes: `ssl` on the ground, `sl` in the
        air. The first press is what puts the combo in the air, so an aerial
        combo is the same string with the aerial codes."""
        base = 3 if air else 0
        return [base + {'s': 0, 'l': 1, 't': 2}[c] for c in text]

    def attacks(self):
        """Every motion the graph can reach, with its list. This is the class's
        action set - the same thing `_act.par` is for a monster."""
        out = []
        for i in sorted(self.nodes):
            a = self.at_node(i)
            if a is not None:
                out.append((i, a.motion, a))
        return out


def volley(ar: Arsenal, a: Attack):
    """Every volume an attack puts in the world, in the player's own space.

    For everything that swings, that is the record placed on the animated
    skeleton. For a projectile it is the same volume carried forward along
    the body's own +Z at the table's speed, one step a frame, falling at the
    table's gravity - which is the only way a bow does damage at all.
    """
    if a.volley is not None:
        return a.volley
    base = a.volumes(ar.actor)
    fl = ar.flight() if a.flies() else None
    if fl is None:
        a.volley = base
        return base
    out = []
    for f, pts, r, h in base:
        y, v = 0.0, 0.0
        for step in range(fl['life'] + 1):
            out.append((f + step,
                        [(p[0], p[1] + y, p[2] + fl['speed'] * step)
                         for p in pts], r, h))
            v += fl['gravity']
            y += v
    a.volley = out
    a.lasts = max(a.lasts, fl['life'])
    return out


# -- one swing --------------------------------------------------------------


def stand_off(arsenal: Arsenal, target: Target, hold=1.0) -> float:
    """Where the player stands: as close as two capsules get.

    `col_r` on both sides, and nothing else. A player who has walked into a
    monster is exactly this far from it.
    """
    return (arsenal.params.get('col_r', 0.5) + target.radius) * hold


def cmd_swing(tree, cls='sw', combo='sss', kind='z01_00', hold='1.0') -> int:
    """One combo, one monster, and what each volume in it lands on."""
    ar = Arsenal(tree, cls)
    tg = Target(tree, kind)
    if tg.actor is None:
        raise SystemExit('%s: no model' % kind)
    air = combo.startswith('a')
    text = combo[1:] if air else combo
    d = stand_off(ar, tg, float(hold))
    walk = ar.press(ar.combo_of(text, air))
    print('%s (%s, %s) against %s: %d capsules, %d regions, %d breakable'
          % (cls, ar.name, ar.weapon, kind, len(tg.parts), len(tg.regions),
             len(tg.broken)))
    print('  the player stands %.2f m away, col_r %.2f against col_r %.2f, '
          'and presses %s' % (d, ar.params.get('col_r', 0.5), tg.radius,
                              ' '.join(text)))
    if len(walk) < len(text):
        print('  the graph has no edge for press %d: the combo ends there'
              % (len(walk) + 1))
    fired = landed = 0
    parts: collections.Counter = collections.Counter()
    for step, (node, edge) in enumerate(walk, 1):
        motions = ar.nodes[node]['motions']
        a = ar.at_node(node)
        if a is None:
            print('  %d. node %d motion %s: no hit record' % (step, node,
                                                              motions))
            continue
        print('  %d. %-22s motion %s, %d frames, window %d..%d%s'
              % (step, a.stem, motions, a.frames, edge['open'], edge['close'],
                 ', just %d..%d' % edge['just'] if any(edge['just']) else ''))
        for f, pts, r, h in volley(ar, a):
            fired += 1
            world = [turn(p, 0.0, 0.0, d, 180.0) for p in pts]
            got = tg.struck(world, r)
            if not got:
                continue
            depth, c = got[0]
            if depth <= 0:
                landed += 1
                parts[(c['part'], c['break'])] += 1
                print('      f%-3d slot %d %-9s r %.2f -> %-10s %-14s '
                      'capsule %d on %s, %.2f m in'
                      % (f, h.slot, h.shape, r,
                         'breaks' if c['break'] else 'hits', c['part'],
                         c['i'], c['bone'], -depth))
            else:
                print('      f%-3d slot %d %-9s r %.2f -> misses by %.2f m, '
                      'nearest %s' % (f, h.slot, h.shape, r, depth,
                                      c['part']))
    print('  %d volumes fired, %d landed' % (fired, landed))
    for (name, brk), n in parts.most_common():
        print('    %3dx  %s%s' % (n, name, '  (breakable)' if brk else ''))
    return 0


# -- every class against every monster --------------------------------------


def monsters(tree):
    """Every monster that has a body to be hit on."""
    out = []
    for d in sorted((pathlib.Path(tree) / 'monster.cpk').iterdir()):
        if (d / 'objbin.bin').is_file() and any(d.rglob('*.CMDL')):
            out.append(d.name)
    return out


def cmd_swings(tree, hold='1.0', want='*') -> int:
    """Six classes against every monster on the disc.

    One posture, one distance, no dodging on either side: what the row says
    is whether a class's own animations put a volume on a body part of that
    monster, and which part.
    """
    tree = pathlib.Path(tree)
    kinds = monsters(tree)
    targets = {}
    for k in kinds:
        t = Target(tree, k)
        if t.actor is not None and t.parts:
            targets[k] = t
    print('%d monsters with a body, %d capsules in all, %d of them owned by '
          'a region' % (len(targets), sum(len(t.parts) for t in
                                          targets.values()),
                        sum(1 for t in targets.values()
                            for c in t.parts if c['part'] != '-')))
    named: collections.Counter = collections.Counter()
    total_reached = 0
    for cls in sorted(CLASSES):
        if not fnmatch.fnmatch(cls, want):
            continue
        ar = Arsenal(tree, cls)
        shots = []
        for node, motion, a in ar.attacks():
            for f, pts, r, h in volley(ar, a):
                shots.append((a, f, pts, r, h))
        reached = 0
        landed = 0
        quiet = []
        for k, t in targets.items():
            d = stand_off(ar, t, float(hold))
            hits = 0
            nearest = 1e9
            for a, f, pts, r, h in shots:
                world = [turn(p, 0.0, 0.0, d, 180.0) for p in pts]
                got = t.struck(world, r)
                if not got:
                    continue
                depth, c = got[0]
                if depth <= 0:
                    hits += 1
                    named[(c['part'], c['break'])] += 1
                else:
                    nearest = min(nearest, depth)
            landed += hits
            if hits:
                reached += 1
            else:
                quiet.append((k, nearest, t.height))
        total_reached += reached
        print('  %-3s %-12s %3d lists, %4d volumes: reaches %2d of %d '
              'monsters, %d landings'
              % (cls, ar.name, len(set(a.stem for a, _, _, _, _ in shots)),
                 len(shots), reached, len(targets), landed))
        if quiet:
            quiet.sort(key=lambda t_: t_[1])
            print('       misses %d, nearest %s'
                  % (len(quiet), ', '.join('%s %.2f m' % (q[0], q[1])
                                           for q in quiet[:4])))
    print('  %d of %d class-monster pairs land a blow'
          % (total_reached, 6 * len(targets)))
    print('\n  where the blows land, over the whole disc:')
    brk = sum(n for (nm, b), n in named.items() if b)
    for (nm, b), n in named.most_common(12):
        print('    %6d  %-16s%s' % (n, nm, '  (breakable)' if b else ''))
    print('    %d landings in all, %d of them on a part that breaks off, '
          '%d on a capsule no region owns'
          % (sum(named.values()), brk, named.get(('-', False), 0)))
    return 0


def cmd_arrows(tree) -> int:
    """`ht_arrow_tbl`, and the two numbers it is checked against.

    The hunter is the one class whose combo graph carries almost no hit
    record: 27 of its 29 nodes have none, because a bow does its damage with
    something that has already left the bow. Those projectiles are the lists
    named with a bare number, and `ht_arrow_tbl` is how they move.

    Nothing in the table says which column is which. Two things say it from
    outside:

    - **a speed times a life is a distance**, and the hunter's own JSON asks
      for targets inside `cmb_hmg_search_radius`;
    - **the rows that do not move** are the ones whose launch angle is -90
      degrees, which is a thing dropped rather than shot - and the hunter is
      the class with four traps in its skill list.
    """
    tree = pathlib.Path(tree)
    ar = Arsenal(tree, 'ht')
    rows = ar.arrows
    if not rows:
        raise SystemExit('no ht_arrow_tbl')
    seen: collections.Counter = collections.Counter()
    for a in rows:
        seen[(a['life'], round(a['speed'], 2), round(a['gravity'], 3),
              round(a['pitch'], 1))] += 1
    print('ht_arrow_tbl: %d records of %d bytes, %d distinct flights'
          % (len(rows), 80, len(seen)))
    print('  %-5s %-6s %-9s %-9s %-8s %s'
          % ('rows', 'life', 'speed', 'gravity', 'pitch', 'it covers'))
    for (life, speed, grav, pitch), n in seen.most_common():
        print('  %-5d %-6d %-9.2f %-9.3f %-8.1f %.1f m'
              % (n, life, speed, grav, pitch, life * speed))
    live = [a for a in rows if a['speed'] > 0]
    reach = sorted(a['life'] * a['speed'] for a in live)
    still = [a for a in rows if a['speed'] == 0]
    print('  %d of the %d rows move: they cover %.1f to %.1f m, median %.1f'
          % (len(live), len(rows), reach[0], reach[-1],
             statistics.median(reach)))
    print('    and the class asks for a target inside '
          '`cmb_hmg_search_radius` = %.1f m'
          % ar.params.get('cmb_hmg_search_radius', 0.0))
    down = [a for a in still if a['pitch'] < 0]
    print('  %d of the %d that do not move carry pitch %.0f - straight down, '
          'which is a thing dropped and not a thing shot, and the hunter is '
          'the class with four traps in its skills'
          % (len(down), len(still), down[0]['pitch'] if down else 0.0))
    close = ar.params.get('col_r', 0.5) + 1.0
    steps = [next(k for k in range(a['life'] + 1)
                  if a['speed'] * k >= close) for a in live
             if a['speed'] * a['life'] >= close]
    print('  every moving row passes a body %.1f m away, and %d of the %d '
          'do it within %d frames' % (close, len(steps), len(live),
                                      max(steps) if steps else 0))
    lists = [a for m, v in ar.lists.items() for a in v if a.flies()]
    flying = sum(1 for i in ar.nodes
                 if ar.at_node(i) is not None and ar.at_node(i).flies())
    print('  %d of the hunter\'s lists fly, and %d of its %d graph nodes '
          'resolve to one by the `1` + motion + variant rule'
          % (len(lists), flying, len(ar.nodes)))
    return 0


# -- what the parts are, and where they sit ---------------------------------


# A reader's grouping of the artists' words, not the disc's - the same device
# `elbn.py`'s `SYNONYM` is, and it is printed with every word it fails to
# place so that a table which is too narrow shows up as a gap.
FAMILY = (
    ('head', r'head|horn|jaw|eye'),
    ('wing', r'wing'),
    ('body', r'body|hara|spine|chest|neck|toge|thorn|shoulder|sholder'
            r'|hip|all'),
    ('tail', r'tail'),
    ('arm', r'arm|hand|wrist|claw'),
    ('leg', r'leg|foot|thigh|calf|toe'),
)


def family(name: str) -> str | None:
    key = re.sub(r'[^a-z]', '', name.lower())
    for f, pat in FAMILY:
        if re.search(pat, key):
            return f
    return None


def cmd_parts(tree) -> int:
    """Where a monster's named body parts are, measured against their names.

    This is the check behind "which capsule a blow lands on". `region_data`
    gives a part an English name and a list of `col_hit` capsules; nothing in
    the file says a part called `HEAD` should be near the top of the body or
    one called `LEG_R_F` near the floor. The capsules are geometry and the
    names are language, and they were written by different hands.

    So: place every capsule of every monster in its rest pose, take the
    height of its centre as a fraction of that monster's own height, and ask
    whether the words come out in the order the words mean. The comparison is
    **within a monster** - a tall boss and a small wolf are never put in one
    column - so what is counted is a sign, on every monster that carries both
    parts of the pair.
    """
    tree = pathlib.Path(tree)
    pooled: dict[str, list[float]] = {}
    per: dict[str, dict[str, float]] = {}
    stray: collections.Counter = collections.Counter()
    capsule_count = owned = 0
    for k in monsters(tree):
        t = Target(tree, k)
        if not t.parts or t.height <= 0:
            continue
        got: dict[str, list[float]] = {}
        for c in t.parts:
            capsule_count += 1
            if c['part'] == '-':
                continue
            owned += 1
            y = (c['a'][1] + c['b'][1]) / 2.0 / t.height
            f = family(c['part'])
            if f is None:
                stray[c['part']] += 1
                continue
            got.setdefault(f, []).append(y)
            pooled.setdefault(f, []).append(y)
        per[k] = {f: sum(v) / len(v) for f, v in got.items()}
    print('%d monsters, %d capsules, %d of them owned by a named part'
          % (len(per), capsule_count, owned))
    print('  where each word sits, as a fraction of the body it is on:')
    for f, _ in FAMILY:
        v = pooled.get(f)
        if v:
            print('    %-5s %4d capsules   mean %.2f   median %.2f'
                  % (f, len(v), sum(v) / len(v), statistics.median(v)))
    print('  and within one monster at a time, which is the test:')
    for a, b in (('head', 'leg'), ('body', 'leg'), ('arm', 'leg'),
                 ('wing', 'leg'), ('head', 'body'), ('head', 'tail')):
        both = [v for v in per.values() if a in v and b in v]
        ok = sum(1 for v in both if v[a] > v[b])
        if both:
            print('    %-5s sits above %-5s on %2d of the %2d monsters that '
                  'have both' % (a, b, ok, len(both)))
    if stray:
        print('  words the reader has no family for: %d of them, %d capsules'
              % (len(stray), sum(stray.values())))
        print('    ' + ', '.join('%s x%d' % kv for kv in
                                 stray.most_common(12)))
    return 0


# -- the reach, against the weapon that does it -----------------------------


def weapon_reach(tree, cls: str) -> list[tuple[str, float]]:
    """How far each of a class's weapons gets from the hand that holds it.

    The model's own vertices, measured from its origin - which is the point
    it hangs off `node_r_weapon` by. Nothing is fitted: it is the length of
    the object.
    """
    out = []
    d = pathlib.Path(tree) / 'character.cpk' / 'weapon.cpk'
    for p in sorted(d.rglob('wp_%s[0-9]*.CMDL' % cls)):
        if not re.fullmatch(r'wp_%s\d+' % cls, p.stem):
            continue
        m = Cmdl(p.read_bytes(), p.name)
        best = 0.0
        for i in range(m.meshes):
            mesh = m.mesh(i)
            if not mesh.drawable:
                continue
            for v in m.positions(mesh):
                best = max(best, math.dist((0.0, 0.0, 0.0), v))
        out.append((p.stem, best))
    return out


def _r(xs, ys) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def _exact(xs, ys) -> tuple[float, int, int]:
    """Six points is few, so the control is every one of the 720 ways the
    two columns could have been paired instead of an approximation to it."""
    got = _r(xs, ys)
    beat = 0
    perms = list(itertools.permutations(ys))
    for q in perms:
        if _r(xs, list(q)) >= got - 1e-12:
            beat += 1
    return got, beat, len(perms)


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return out


def cmd_reach(tree) -> int:
    """The player's reach, against the weapon that does it.

    `_act.par` gives a monster's action one distance and nothing on the disc
    says what it measures; [`fight.py`](fight.py) `reach` answered that by
    putting it beside the reach of the same action's hit volumes. The player
    has no `_act.par`, so the question turns around: **the volumes are the
    known quantity here, and what they can be checked against is the object
    the class is holding.**

    A player's melee volume hangs off `node_r_weapon` or `node_l_weapon`, and
    so does the weapon model. Neither file mentions the other: the volume is
    in an `.anmcmd` under `job.cpk` and the weapon is a `CMDL` under
    `character.cpk`, and the only thing they share is the bone. If the
    reading is right, a class that swings a two-handed sword should reach
    further than one that swings a pair of katars, and by about the amount the
    models differ by.

    The class JSON's `cmb_hmg_search_angle` is the second column here and it
    is weaker evidence - six classes and three distinct values - so it is
    reported with what does and does not hold.
    """
    tree = pathlib.Path(tree)
    rows = []
    for cls in sorted(CLASSES):
        ar = Arsenal(tree, cls)
        arm, all_, ang = [], [], []
        for node, motion, a in ar.attacks():
            for f, pts, r, h in a.volumes(ar.actor):
                bone = ar.actor.name_of(h.bone)
                d = max(math.hypot(p[0], p[2]) for p in pts) + r
                all_.append(d)
                if 'weapon' in bone:
                    arm.append(d)
                ang.append(abs(math.degrees(math.atan2(pts[0][0],
                                                       pts[0][2]))))
        wp = [v for _, v in weapon_reach(tree, cls)]
        rows.append({
            'cls': cls, 'name': ar.name, 'weapon': ar.weapon,
            'arm': arm, 'all': all_, 'wp': wp, 'ang': ang,
            'search': ar.params.get('cmb_hmg_search_radius', 0.0),
            'angle': ar.params.get('cmb_hmg_search_angle', 0.0),
        })
    print('%-4s %-12s %-17s %-19s %-19s %-10s %s'
          % ('', 'class', 'weapon', 'off the weapon bone', 'the weapon itself',
             'its angle', 'the JSON asks for'))
    for r in rows:
        arm = ('%3d vols, med %.2f' % (len(r['arm']),
                                       statistics.median(r['arm']))
               if r['arm'] else 'none')
        print('%-4s %-12s %-17s %-19s %d models, med %.2f  med %4.1f d  '
              '%5.1f m, %3.0f deg'
              % (r['cls'], r['name'], r['weapon'], arm, len(r['wp']),
                 statistics.median(r['wp']), statistics.median(r['ang']),
                 r['search'], r['angle']))
    melee = [r for r in rows if r['arm']]
    xs = [statistics.median(r['arm']) for r in melee]
    ys = [statistics.median(r['wp']) for r in melee]
    got, beat, n = _exact(xs, ys)
    print('\n  the volumes on the weapon bone against the weapons that hang '
          'off it:')
    print('    correlation %.3f over the %d classes that have both, and %d '
          'of the %d ways' % (got, len(melee), beat, n))
    print('    the classes could have been paired with the weapons do as '
          'well or better')
    xs = _ranks([statistics.median(r['ang']) for r in rows])
    ys = _ranks([r['angle'] for r in rows])
    got, beat, n = _exact(xs, ys)
    print('  the angle a class swings at against `cmb_hmg_search_angle`:')
    bands: dict[float, list[float]] = {}
    for r in rows:
        bands.setdefault(r['angle'], []).append(statistics.median(r['ang']))
    print('    ' + ';  '.join('%.0f deg -> %s' % (k, ' '.join('%.1f' % v for v
                                                              in sorted(x)))
                              for k, x in sorted(bands.items())))
    print('    the three bands do not overlap, Spearman %.3f, and %d of the '
          '%d pairings do' % (got, beat, n))
    print('    as well or better - which is the floor the ties in the JSON '
          'put there, so no pairing does better')
    thin = []
    for r in rows:
        v = [a for a, d in zip(r['ang'], r['all']) if d > 0.5]
        thin.append(statistics.median(v) if v else 0.0)
    print('    dropping every volume within half a metre of the body leaves '
          'Spearman %.3f' % _r(_ranks(thin), ys))
    print('  and `cmb_hmg_search_radius`, which is the one that reads like '
          '`_act.par`:')
    xs = [statistics.median(r['all']) for r in melee]
    ys2 = [r['search'] for r in melee]
    got, beat, n = _exact(xs, ys2)
    print('    over the five that swing something, correlation %.3f with %d '
          'of the %d pairings at least as good' % (got, beat, n))
    ht = [r for r in rows if r['cls'] == 'ht'][0]
    print('    the hunter is not in that column at all: it asks for 20 m and '
          'fires nothing off a')
    print('    weapon bone, because its damage leaves the bow - and what does '
          'match its 20 m is')
    print('    `ht_arrow_tbl`, whose commonest flight covers 21.3 m. See '
          '`arrows`.')
    return 0


# -- both halves at once ----------------------------------------------------


def _duel(world, ar: Arsenal, tree, monster: str, frames: int,
          hp_rate=100, combo='sssss'):
    """One monster and one class on one stage, both halves running.

    [`fight.py`](fight.py) `fight` runs the monster against a capsule that
    only walks. Here the capsule swings back: it closes, presses the combo
    its own graph gives it, and its volumes are tested against the monster's
    `col_hit` capsules - while the monster's volumes are tested against the
    player's own `col_hit`, by the same function, which is what
    [`milestone_fight.md`](../docs/milestone_fight.md)'s upright cylinder was
    standing in for. Both sides read their own tables and neither is told
    about the other.
    """
    spawn = world.marker('appear01')
    player = Actor(ar.params, spawn.position[0], spawn.position[1],
                   spawn.position[2], spawn.rotation[1])
    gen = [m for m in world.stage.markers if m.kind.startswith('emgen')]
    at = gen[0] if gen else world.stage.markers[0]
    ground = world.floor(at.position[0], at.position[2])
    e = Enemy(tree, monster, at.position[0],
              at.position[1] if ground is None else ground,
              at.position[2], (at.rotation[1] + 180.0) % 360.0)
    if e.actor is None:
        return None
    tg = Target(tree, e.m.kind)
    body = place(ar.actor)
    rng = random.Random(20260823)
    close = ar.params.get('col_r', 0.5) + e.radius
    keys = ar.combo_of(combo)
    walk = ar.press(keys)
    step, frame = 0, 0
    mine = None
    out = {'e': e, 'tg': tg, 'body': body, 'close': close, 'swings': 0,
           'swung': 0, 'struck': 0, 'thrown': 0, 'taken': 0,
           'nearest': 1e9, 'parts': collections.Counter(),
           'mine': collections.Counter()}
    for f in range(frames):
        d = math.dist((player.x, player.z), (e.x, e.z))
        # -- the player
        if mine is None:
            if d > close:
                player.step(world, gait='run',
                            facing=bearing(player.x, player.z, e.x, e.z))
            else:
                if step >= len(walk):
                    step, walk = 0, ar.press(keys)
                if not walk:
                    break
                node, edge = walk[step]
                step += 1
                mine, frame = ar.at_node(node), 0
                if mine is not None:
                    volley(ar, mine)        # so `lasts` knows the flight
                    out['swings'] += 1
                    player.heading = bearing(player.x, player.z, e.x, e.z)
        else:
            for fr, pts, r, h in volley(ar, mine):
                if fr != frame:
                    continue
                out['swung'] += 1
                world_pts = [turn(q, player.x, player.y, player.z,
                                  player.heading) for q in pts]
                got = against(tg.parts, (e.x, e.y, e.z, e.heading),
                              world_pts, r)
                if got and got[0][0] <= 0:
                    out['struck'] += 1
                    out['parts'][(got[0][1]['part'], got[0][1]['break'])] += 1
                elif got:
                    out['nearest'] = min(out['nearest'], got[0][0])
            frame += 1
            if frame > mine.lasts:
                mine = None
        # -- the monster, exactly as `fight.py` runs it
        fill(e.state, e, player.x, player.y, player.z, hp_rate, f)
        e.state.rand = rng.randrange(10001)
        if e.move is None:
            g, action, mid, name = e.brain.act(e.state, rng)
            if action is None:
                continue
            gate = e.m.ranges.get(action)
            if gate is not None and 0 < gate < SENTINEL \
                    and e.state.target_range > gate:
                e.walk(player.x, player.z, world, 20)
                e.last_act, e.since = action, 0
                continue
            e.last_act, e.since = action, 0
            mv = e.resolve(action)
            if mv.frames:
                e.move, e.frame = mv, 0
            continue
        e.since += 1
        for h, q in e.move.place(e.actor, e.frame):
            pts = [e.world_point(v) for v in (q.p0, q.p1) if v is not None]
            if not pts:
                continue
            out['thrown'] += 1
            got = against(body, (player.x, player.y, player.z,
                                 player.heading), pts,
                          max(h.sizes[0], MIN_RADIUS))
            if got and got[0][0] <= 0:
                out['taken'] += 1
                out['mine'][got[0][1]['bone']] += 1
        e.frame += 1
        if e.frame > e.move.frames:
            e.move = None
        else:
            e.face(player.x, player.z)
    return out


def cmd_duel(tree, stage='010_01_01', monster='AI_Z01_Orc', cls='sw',
             frames='900', hp_rate='100') -> int:
    """One duel, printed."""
    root = pathlib.Path(tree)
    world = World(root / 'stage.cpk' / stage / 'param.pac')
    ar = Arsenal(tree, cls)
    got = _duel(world, ar, tree, monster, int(frames), int(hp_rate))
    if got is None:
        raise SystemExit('%s: no model' % monster)
    e, tg = got['e'], got['tg']
    print('%s (%s) against %s on %s' % (cls, ar.name, e.m.name, stage))
    print('  the player closes to %.2f m - col_r %.2f and col_r %.2f - and '
          'runs its combo graph from node 0'
          % (got['close'], ar.params.get('col_r', 0.5), e.radius))
    print('  the monster has %d capsules over %d regions and %d breakable '
          'parts' % (len(tg.parts), len(tg.regions), len(tg.broken)))
    print('\n  %d frames = %.1f s' % (int(frames), int(frames) / FPS))
    print('  the player started %d attacks, fired %d volumes and landed %d'
          % (got['swings'], got['swung'], got['struck']))
    if got['nearest'] < 1e8:
        print('    the nearest miss passed %.2f m off the body'
              % got['nearest'])
    for (nm, b), n in got['parts'].most_common(8):
        print('      %3dx  %s%s' % (n, nm, '  (breakable)' if b else ''))
    print('  the monster fired %d hit records at the player and landed %d, '
          'on its %d capsules'
          % (got['thrown'], got['taken'], len(got['body'])))
    for bone, n in got['mine'].most_common(4):
        print('      %3dx  %s' % (n, bone))
    return 0


def cmd_duels(tree, cls='sw', stage='010_01_01', frames='900',
              want='*') -> int:
    """Every monster on the disc, duelled by one class on one stage.

    The sweep [`fight.py`](fight.py) `fights` runs, with the player swinging
    back. What a row says is whether both halves of one fight work at once:
    the monster deciding out of its tables and the player pressing its way
    through its graph, each testing its own hit records against the other's
    own capsules.
    """
    root = pathlib.Path(tree)
    world = World(root / 'stage.cpk' / stage / 'param.pac')
    ar = Arsenal(tree, cls)
    ran = mine = theirs = both = skipped = 0
    named: collections.Counter = collections.Counter()
    swung = struck = thrown = taken = 0
    for name in sorted(ai_index(tree)):
        if not fnmatch.fnmatch(name, want):
            continue
        try:
            got = _duel(world, ar, tree, name, int(frames))
        except (ValueError, KeyError, IndexError) as exc:
            skipped += 1
            print('  %-24s %s' % (name, exc))
            continue
        if got is None:
            skipped += 1
            continue
        ran += 1
        mine += got['struck'] > 0
        theirs += got['taken'] > 0
        both += got['struck'] > 0 and got['taken'] > 0
        swung += got['swung']
        struck += got['struck']
        thrown += got['thrown']
        taken += got['taken']
        named.update(got['parts'])
    print('%s (%s) duelled %d monsters on %s for %s frames each, %d skipped'
          % (cls, ar.name, ran, stage, frames, skipped))
    print('  the player landed on %d of them, the monster landed on the '
          'player in %d, and **both landed in %d**' % (mine, theirs, both))
    print('  %d volumes fired by the player, %d landed; %d fired by the '
          'monsters, %d landed' % (swung, struck, thrown, taken))
    print('  the parts the player hit, over the whole disc:')
    for (nm, b), n in named.most_common(10):
        print('    %5d  %-16s%s' % (n, nm, '  (breakable)' if b else ''))
    brk = sum(n for (nm, b), n in named.items() if b)
    print('    %d landings on %d distinct parts, %d of them on a part that '
          'breaks off' % (sum(named.values()), len(named), brk))
    return 0


# -- the combo tree, walked -------------------------------------------------


def cmd_combo(tree, cls='sw') -> int:
    """The class's action set, as the graph gives it and as it swings.

    Every path from node 0 is a button string, and each node it passes is a
    motion with an animation and a list of hit records on it. This is the
    player's `_act.par`: the set of things it can do, with what each one
    swings.
    """
    ar = Arsenal(tree, cls)
    print('%s (%s, %s): %d nodes, %d lists with a hit record'
          % (cls, ar.name, ar.weapon, len(ar.nodes),
             sum(len(v) for v in ar.lists.values())))
    seen: dict[int, str] = {0: ''}
    order = [0]
    queue = [0]
    while queue:
        i = queue.pop(0)
        for e in ar.nodes.get(i, {}).get('edges', []):
            if e['to'] in seen:
                continue
            air = e['button'] in AIR
            seen[e['to']] = ('a' if air and not seen[i] else '') \
                + seen[i] + LETTER[e['button']]
            order.append(e['to'])
            queue.append(e['to'])
    reach_total = []
    for i in order:
        n = ar.nodes.get(i)
        if n is None or not n['motions']:
            continue
        a = ar.at_node(i)
        if a is None:
            print('  %-8s node %2d motion %-18s no list'
                  % (seen[i], i, n['motions']))
            continue
        r = a.measure(ar.actor)
        if r:
            reach_total.append(r)
        bones = collections.Counter(ar.actor.name_of(h.bone)
                                    for _, h in a.hits)
        print('  %-8s node %2d %-22s %3d frames, %2d records, reach %s   %s'
              % (seen[i], i, a.stem, a.frames, len(a.hits),
                 '%.2f m' % r if r else '  -  ',
                 ' '.join('%s x%d' % (k.replace('node_', ''), v)
                          for k, v in bones.most_common(3))))
    print('  %d reachable motions swing something, median reach %.2f m'
          % (len(reach_total), statistics.median(reach_total)))
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'combo':
        return cmd_combo(rest[0], *rest[1:2])
    if cmd == 'swing':
        return cmd_swing(rest[0], *rest[1:5])
    if cmd == 'swings':
        return cmd_swings(rest[0], *rest[1:3])
    if cmd == 'arrows':
        return cmd_arrows(rest[0])
    if cmd == 'parts':
        return cmd_parts(rest[0])
    if cmd == 'reach':
        return cmd_reach(rest[0])
    if cmd == 'duel':
        return cmd_duel(rest[0], *rest[1:6])
    if cmd == 'duels':
        return cmd_duels(rest[0], *rest[1:5])
    print('unknown command: %s' % cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
