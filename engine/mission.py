"""
mission.py - a quest that finishes, and pays.

[`host.py`](host.py) runs a stage: the script initialises it, a body walks it
and the trigger volumes fire. [`fight.py`](fight.py) and
[`player.py`](player.py) run a fight in both directions. What was missing
between them is the **state that changes** - the spawners, the arena lock and
the kill count - and it is exactly the state
[`format_quest.md`](../docs/format_quest.md)'s four tables describe.

    python engine/mission.py run    extract/tree q00102 [class] [blows]
    python engine/mission.py runs   extract/tree [glob] [class]
    python engine/mission.py counts extract/tree
    python engine/mission.py area   extract/tree
    python engine/mission.py route  extract/tree

The four tables themselves are read by
[`../tools/quest.py`](../tools/quest.py), and this file is named apart from
it so that both can be imported into the same program - which is what it
does.

`run` plays one quest and `runs` plays all of them. `counts`, `area` and
`route` are the three measurements that need no run at all, and `counts` is
the one that could have failed.

## The loop the disc closes by itself

    a trigger volume       pl_q00102_a      trigger.trg
      -> a quest function  sfEnmGenStart    the quest's own .psq
      -> a lock            pl_010_01_02     piecelock.bin
      -> its fences        lockarea01, lock_line01..03
      -> its generators    emgen01..06, 11, 12
      -> a monster each    enemy.bin slot 2 -> z02_00
      -> a fight           player.py, both halves
      -> a kill callback   sfKill_Generator('emgen03')   enemy_gen.bin
      -> a counter         cntGenKill++
      -> the lock opens    cfEndPieceLock()

Every arrow but two is a join some earlier session measured. The two that are
new are the last three lines, and they are the point of this file: **the
script counts the kills and decides for itself when the arena is over.**
Nothing here tells it how many to expect.

## The count is the disc's, twice, and the two agree

A `sfKill_Generator` ends `if (cntGenKill >= 8) sfEnmGenEnd()`, and the 8 is a
constant compiled into the bytecode. The number of generators the lock covers
is a newline-separated string in `piecelock.bin` lane `+0x1c`. They come from
different files, are read by different tools and neither knows about the
other.

**527 of 527 locks whose generators name a counting callback agree, with
nothing left over** - `counts` is that measurement. It is what says the
lock-to-generator join is right, and it says it without running anything.

## What a kill is, and what it is not

The monster's hit points are on the disc - `hp` in its own JSON - and what a
blow takes off is not: that is [`combat_loop.md`](../docs/combat_loop.md)
ledger item 1, and it is the EBOOT's. So this file does **not** compute
damage. It declares a number of landed volumes a monster survives, the way
[`host.py`](host.py) declares how long a talk line stays up, and prints it
with every run:

    a monster dies on its `blows`-th landed volume; the default is 3

Nothing else in the loop is a policy. The spawn points are markers, the
monsters are the table's, the fences are polylines, the counting is the
script's own and the threshold is the script's own - and since session 30 so
is **which of a monster's difficulty tiers is standing there**, which used to
be a flat record 0. `enemy.bin` `+0x37` names it and it moves `hp`, `atk`,
`region_lv` and the drop table: see
[`../tools/quest.py`](../tools/quest.py)'s `tiers`.

## And now it pays

Session 28 gave the loop its far end. [`purse.py`](purse.py) holds what came
out and draws it against the disc's own chances, and this file calls it from
four places: a corpse (`Spawner.kill`, out of the monster's own `it_drop`), a
part that comes off (`Field._break`, out of the quest's
`item_reward_region.bin`), the quest finishing (`play`, out of
`item_reward.bin` and `chapter.bin`'s zeny) and `cfAddItem`, which
[`host.py`](host.py) routes. The second policy this file needs is declared
there: how many landed volumes take a part off. See
[`milestone_reward.md`](../docs/milestone_reward.md).
"""
from __future__ import annotations

import collections
import fnmatch
import math
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

import quest as qtables                                        # noqa: E402
from actor import FPS, Actor, bearing                          # noqa: E402
from brain import Brain, State                                 # noqa: E402
from fight import (MIN_RADIUS, SENTINEL, Enemy, fill,          # noqa: E402
                   load_json)
from host import Host                                          # noqa: E402
from player import (CLASSES, Arsenal, Target, against,         # noqa: E402
                    place, turn, volley)
from psq import Psq, PsqError, Structure, Trace                # noqa: E402
from damage import (Fighter, defence_terms, region_of,        # noqa: E402
                    region_terms, resolve)
from purse import BREAKS, PROGRESS, Purse                      # noqa: E402
from squirrel import SquirrelError, VMError                    # noqa: E402

# How many landed volumes a monster survives. Policy, and the only one this
# file declares - `purse.py` declares the second, `BREAKS`. See the header.
BLOWS = 3
# How long a stage gets before the run gives up on it. 30 fps, so this is
# four minutes, and the longest arena on the disc is nowhere near it.
STAGE_FRAMES = 7200
# The player stops running at `col_r + col_r` and swings from there, which is
# where `player.py` stands to measure a landing.
COMBO = 'sssss'
# `sfKill_Generator` counts in a local named for the job. The threshold is
# the constant it compares that local against.
COUNTER = re.compile(r'(\w*[Kk]ill\w*)\s*>=\s*(\d+)')
# The player's class, as `it_db_weapon.bin` column 5 numbers it, for the six
# `player.py` names. A kind-4 reward entry is that class's guaranteed weapon.
PAYS = {'as': 0, 'cl': 1, 'ha': 3, 'hu': 4, 'ma': 5, 'sw': 7}


# -- the four tables, for one quest ----------------------------------------


class Tables:
    """One quest's `.pac`, read straight off the disc.

    [`../tools/quest.py`](../tools/quest.py) reads the same four tables by
    walking the whole asset tree, which is right for a survey and much too
    slow to do 430 times. This opens one directory.
    """

    def __init__(self, tree, name: str):
        self.tree = pathlib.Path(tree)
        self.name = name
        d = self.tree / 'quest.cpk' / (name + '.pac')
        if not d.is_dir():
            raise SystemExit('no quest %s under %s' % (name, tree))
        self.dir = d
        self.q = qtables.Quest(name, {t: (d / t).read_bytes()
                                      for t in qtables.TABLES
                                      if (d / t).is_file()})
        self.stages = self.q.stages
        self.slots = self.q.slots()
        self.tiers = self.q.tiers()
        self.gens = self.q.generators()
        self.locks = self.q.locks()
        self.kinds = qtables.monsters(self.tree)

    def tier(self, stage: str) -> str:
        """The difficulty record this quest's rooms on that stage spawn at.

        `enemy.bin` `+0x37`, which is a record key of the monster's own
        `.json` - see [`../tools/quest.py`](../tools/quest.py)'s `tiers` for
        what says so. `'0'` where the stage has no row, which is what a
        monster met outside a quest is.
        """
        lo, _ = self.tiers.get(stage, (0, None))
        return str(lo)

    def generators(self, stage: str) -> list:
        return [g for g in self.gens if g['stage'] == stage]

    def locks_of(self, stage: str) -> list:
        return [k for k in self.locks if k['stage'] == stage]

    def lock(self, name: str):
        for k in self.locks:
            if k['name'] == name:
                return k
        return None

    def monster(self, stage: str, slot: int):
        """The directory a generator's slot names, or None if the lane is
        empty - which is what a disabled spawner looks like."""
        ids = self.slots.get(stage) or []
        if not 1 <= slot <= len(ids):
            return None, None
        mid = ids[slot - 1]
        return mid, self.kinds.get(mid)

    def thresholds(self, stage: str) -> dict:
        """`function -> the count it stops at`, off the quest's own script.

        The bytecode is the source: [`../tools/psq.py`](../tools/psq.py)
        structures the function and the threshold is the constant in the one
        comparison it makes against its kill counter.
        """
        p = self.dir / (stage + '.psq')
        out = {}
        if not p.is_file():
            return out
        try:
            q = Psq(p.read_bytes(), p.name)
        except (PsqError, OSError):
            return out
        for f in q.functions():
            try:
                body = '\n'.join(Structure(f, Trace(f).run()).render())
            except Exception:                        # noqa: BLE001
                continue
            m = COUNTER.search(body)
            if m:
                out[f.name] = int(m.group(2))
        return out


# -- what a generator puts on the stage ------------------------------------


class Spawn:
    """One monster, standing on the marker its generator names."""

    def __init__(self, gen: dict, mid: int, kind: str, marker, world=None,
                 tier: str = '0'):
        self.gen, self.id, self.kind = gen, mid, kind
        self.tier = str(tier)               # its `enemy.bin` row's `+0x37`
        self.marker = marker
        self.x, self.y, self.z = marker.position
        # A monster stands on the ground under its marker, not at the
        # marker's own Y - see `world.stand`. 183 of the disc's 2,123
        # `emgen_pos` are more than `col_r` below their own floor, one of
        # them by fifteen metres, and a monster down there is a monster the
        # player's swing cannot reach: `against` is a test between two
        # capsules in three dimensions, and the arena never opens.
        if world is not None:
            y = world.stand(self.x, self.z, self.y)
            if y is not None:
                self.y = y
        self.heading = marker.rotation[1]
        self.enemy = None                   # the brain, built when it fights
        self.hits = 0
        # Its own hit points, at its own tier, and what is left of
        # them. `damage.py` takes them down; before session 31 this
        # was `hits >= BLOWS` and the pool was never read.
        self.hp = 0.0
        self.left = 0.0
        self.broke: dict = {}       # part -> hit points left, -1 once off
        self.brk_hits: dict = {}    # and the landings, for the fallback
        self.alive = True

    @property
    def name(self) -> str:
        return self.gen['name']

    def __repr__(self):
        return '<%s %s at %s>' % (self.name, self.kind, self.marker.name)


class Spawner:
    """The quest state, and the nine host calls that move it.

    [`host.py`](host.py) holds this as `self.spawner` and routes
    `cfSetEnableEmGen`, `cfReviveEmGen`, `cfStartPieceLock`,
    `cfEndPieceLock`, `cfSetEnemyMax`, `cfGetCntKillGenPieceLockOnly`,
    `getLatestKilled`, `getNumOfEnemy` and `getNumOfBoss` into it. Without
    one they are what they were: recorders that return zero.
    """

    def __init__(self, tables: Tables):
        self.t = tables
        self.host = None                    # host.py fills this in
        self.world = None
        self.stage = ''
        self.live: list[Spawn] = []
        self.lock = None
        self.kills = 0                      # inside the current lock
        self.total_kills = 0
        self.latest_killed = 0
        self.at_once = 0                    # cfSetEnemyMax, 0 for no cap
        self.at = None                      # where the body is, set by `play`
        self.radius = 0.5                   # and how wide it is
        self.opened: list[str] = []         # locks the script itself ended
        self.started: list[str] = []
        self.here: set = set()              # and the ones done on this stage
        self.purse = None                   # `play` puts one here
        self.log = collections.Counter()

    # -- what host.py calls ------------------------------------------------

    def enter(self, stage: str, world):
        self.stage, self.world = stage, world
        self.live = []
        self.lock = None
        self.kills = 0
        self.here = set()
        world.raised = set()

    def enable(self, name: str, on: bool):
        if on:
            self._spawn(name)
        else:
            self.live = [s for s in self.live if s.name != name]

    def start_lock(self, name: str):
        k = self.t.lock(name)
        if k is None:
            self.log['lock not in the table'] += 1
            return
        if name in self.here:
            # A **cleared** arena does not close again on the same visit.
            # Walking back into the volume genuinely does re-arm one on the
            # disc - the scripts never turn a `pl_q` hit area off, and
            # `sfEnmGenStart` sets its own counter back to zero - so this is
            # the run's rule rather than the script's, and it is the narrow
            # one: an arena that is still running may be re-entered, an arena
            # the script has already finished may not. Without it a body that
            # steps out of the room it just cleared starts the fight over.
            # Per *visit*, because a route may cross the same room twice.
            self.log['a cleared arena, entered again'] += 1
            return
        self.lock = k
        self.started.append(name)
        self.kills = 0
        # The fences the lock raises. `sfStageInit` put them down; this is
        # what puts them up, and `world.py` reads the set every step.
        for n in [k['area']] + list(k['lines']):
            if n:
                self.world.raised.add(n)
        for g in k['gens']:
            self._spawn(g)
        self._let_in()

    def _let_in(self):
        """A lock never fences the body away from its own monsters.

        A `pl_q` trigger is a slab thrown across a corridor, and it is not
        always inside the `lockarea` it arms: 3 of 575 sit outside it. A body
        that trips one of those from the near side would be sealed *out* of
        the room it was walking into, which the game plainly does not do -
        the arena closes behind the player, not in front of it. Nothing on
        the disc says so in words, so the rule is the run's, and it is the
        weakest one that gets it right: after the fences go up, if no route
        over the ground reaches the first monster, the area comes back down,
        and then the gates, until one does.
        """
        if self.at is None or not self.live:
            return
        s = self.live[0]
        k = self.lock
        for drop in ([], [k['area']], [k['area']] + list(k['lines'])):
            for n in drop:
                self.world.raised.discard(n)
            if self.world.path(self.at(), (s.x, s.z), self.radius):
                if drop:
                    self.log['a fence between the body and the fight'] += 1
                return
        self.log['no route to the fight at all'] += 1

    def end_lock(self):
        if self.lock is not None:
            self.opened.append(self.lock['name'])
            self.here.add(self.lock['name'])
            for n in [self.lock['area']] + list(self.lock['lines']):
                self.world.raised.discard(n)
            # Only what this lock put out: a generator enabled by a bare
            # `cfSetEnableEmGen` is not the arena's and does not go with it.
            gens = set(self.lock['gens'])
            self.live = [s for s in self.live if s.name not in gens]
        self.lock = None

    # -- what the fight calls ----------------------------------------------

    def kill(self, s: Spawn):
        """One generator done: the table names the function, the script counts.

        The generator's `+0x38` is the callback and it is handed the
        generator's own name - which is what `sfKill_Generator(gen_name)`
        takes and prints. 3,067 of 3,067 of those names are functions the
        quest's own `.psq` defines, so this call finds one.

        It fires once per **generator**, not once per corpse: the line the
        script prints is `--- generator [emgen01] End ---`, and on 36 of the
        527 locks `counts` matches, `enemy.bin`'s population is twice the
        threshold. A generator here produces one monster, so the two
        coincide; when the second monster is modelled this is the call that
        must not move.
        """
        if not s.alive:
            return
        s.alive = False
        self.live = [x for x in self.live if x is not s]
        # A corpse pays before the callback runs: the monster's own `it_drop`
        # table, out of its JSON and read the same way a reward block is.
        if self.purse is not None:
            self.purse.killed(s.kind, s.tier)
        self.total_kills += 1
        self.latest_killed = s.id
        if self.lock is not None:
            self.kills += 1
        fn = s.gen.get('on_kill')
        if not fn:
            self.log['no kill callback'] += 1
            return
        if self.host.vm.find(fn) is None:
            self.log['kill callback undefined'] += 1
            return
        self.log['kill callback called'] += 1
        self.host.call(fn, [s.name], why='%s killed' % s.name)

    # -- the numbers the scripts ask for -----------------------------------

    @property
    def num_enemy(self) -> int:
        return sum(1 for s in self.live if s.id < 2000)

    @property
    def num_boss(self) -> int:
        return sum(1 for s in self.live if s.id >= 2000)

    # -- spawning ----------------------------------------------------------

    def _spawn(self, name: str):
        if any(s.name == name for s in self.live):
            return
        for g in self.t.generators(self.stage):
            if g['name'] != name:
                continue
            mid, kind = self.t.monster(self.stage, g['slot'])
            if kind is None:
                self.log['generator names an empty lane'] += 1
                return
            m = self.world.stage.atih.by_name().get(g['marker'])
            if m is None:
                self.log['generator names no marker'] += 1
                return
            s = Spawn(g, mid, kind, m, self.world,
                      tier=self.t.tier(self.stage))
            if self.at_once and len(self.live) >= self.at_once:
                self.log['held back by cfSetEnemyMax'] += 1
                return
            self.live.append(s)
            self.log['spawned'] += 1
            return
        self.log['no generator of that name'] += 1


# -- the fight, with a crowd in it -----------------------------------------


class Field:
    """The player and everything alive, one frame at a time.

    This is [`player.py`](player.py)'s duel with the one-against-one taken
    out of it. Both halves are the same code and the same records; what is
    new is that a monster now answers `getOtherZakoCount` and
    `getActiveSameKindCount` with a number that is not zero, because for the
    first time there is more than one of them on the stage.
    """

    def __init__(self, tree, arsenal: Arsenal, spawner: Spawner, seed=1,
                 blows=BLOWS, breaks=BREAKS):
        self.tree = pathlib.Path(tree)
        self.ar = arsenal
        self.sp = spawner
        self.blows = blows
        self.breaks = breaks
        # The player's own three numbers, and the monsters'. See
        # `damage.py`: `blows` and `breaks` survive only as the
        # fallback for an actor whose tables would not read.
        # The row of the growth table is the **story progress** the run is
        # at, which is the quest's own requirement out of `chapter.bin` where
        # it has one and `PROGRESS` where it does not - the same number the
        # purse already uses to pick its reward block, and the same number
        # space `ccparamobj.bin`'s fourteen thresholds are written in. See
        # `damage.py` and `eboot.md`.
        self.me = Fighter(tree, getattr(arsenal, 'cls', 'sw'),
                          getattr(spawner.purse, 'progress', PROGRESS)
                          if spawner.purse is not None else PROGRESS)
        self.me.parameters(getattr(arsenal, 'params', {}) or {})
        self.stats: dict = {}          # (kind, tier) -> its JSON
        self.rng = random.Random(seed)
        self.body = place(arsenal.actor)     # the player's own capsules
        self.proto: dict = {}           # (kind, tier) -> an Enemy to copy
        self.targets: dict = {}              # kind -> its col_hit capsules
        self.player = None
        self.attack = None                   # what the player is swinging
        self.frame = 0
        self.walk: list = []
        self.step = 0
        self.route: list = []                # where it is going, and how
        self.to = None
        self.was = None
        self.still = 0
        self.since = 0
        self.stood = None
        self.frame_in = 0
        self.where = ''                      # what `play` is steering at
        self.host = None
        self.n = collections.Counter()

    # -- the two bodies ----------------------------------------------------

    def _target(self, kind: str) -> Target:
        if kind not in self.targets:
            self.targets[kind] = Target(self.tree, kind)
        return self.targets[kind]

    def _enemy(self, s: Spawn):
        """The brain and the skeleton, one build per kind.

        An `Enemy` reads the AI tables, the model and the animation index,
        which is two thirds of a second - too much to pay per monster when a
        lock puts eight of the same kind on the floor. The heavy half is
        shared and the state that a fight moves is not. The key is the kind
        **and its tier**, because the tier is what the numbers on it are.
        """
        if s.enemy is not None:
            return s.enemy
        key = (s.kind, s.tier)
        if key not in self.proto:
            try:
                self.proto[key] = Enemy(self.tree, s.kind, tier=s.tier)
            except (SystemExit, StopIteration, OSError, ValueError):
                self.proto[key] = None
        p = self.proto[key]
        if p is None or p.actor is None:
            return None
        e = Enemy.__new__(Enemy)
        e.__dict__.update(p.__dict__)
        e.brain = Brain(p.m)
        e.state = State()
        e.moves = dict(p.moves)             # the resolved motions are shared
        e.move, e.frame, e.since, e.last_act = None, 0, 0, 0
        e.log = collections.Counter()
        e.x, e.y, e.z, e.heading = s.x, s.y, s.z, s.heading
        s.enemy = e
        return e

    # -- one frame ---------------------------------------------------------

    def nearest(self):
        best, d0 = None, 1e9
        for s in self.sp.live:
            d = math.dist((self.player.x, self.player.z), (s.x, s.z))
            if d < d0:
                best, d0 = s, d
        return best, d0

    def steer(self, world, to):
        """The heading that gets the body to `to`, across the ground.

        A straight line at the goal walks into the first wall the room has,
        and 010_01_02 has one 25 metres short of its own exit. The route is
        [`world.py`](world.py)'s path over the collision mesh, recomputed
        when the destination changes and when the body has stopped moving.
        """
        here = (self.player.x, self.player.z)
        stuck = (self.was is not None
                 and math.dist(here, self.was) < 0.02)
        self.still = self.still + 1 if stuck else 0
        self.since += 1
        self.was = here
        if (to != self.to or self.still > 15 or self.since > 120
                or (not self.route and self.since > 30)):
            self.to, self.still, self.since = to, 0, 0
            self.route = world.path(here, to,
                                    self.ar.params.get('col_r', 0.5)) or [to]
            self.n['paths'] += 1
        while self.route and math.dist(here, self.route[0]) < 1.0:
            self.route.pop(0)
        w = self.route[0] if self.route else to
        return bearing(here[0], here[1], w[0], w[1])

    def tick(self, world, goal):
        """One frame: the player acts, then everything alive does.

        The player fights what is in front of it and walks to `goal` when
        nothing is. `goal` is the run's, not the disc's - it stands in for a
        pad - and it is the only steering in the file.
        """
        self.frame += 1
        self._on_ground(world)
        target, d = self.nearest()
        close = self.ar.params.get('col_r', 0.5) + (
            self._target(target.kind).radius if target else 0.0)
        # -- the player
        if self.attack is not None:
            self._swing(target)
        elif target is not None and d <= close + 0.05:
            self._press(target)
        elif target is not None:
            # A monster is chased over the ground too, on a destination
            # rounded to the metre so the route is not rebuilt every frame.
            self._move(world, self.steer(world, (round(target.x),
                                                 round(target.z))))
        else:
            self._move(world, self.steer(world, goal))
        # -- everything alive
        for s in list(self.sp.live):
            self._monster(s, world)
        return target

    def _on_ground(self, world):
        """A body that has fallen out of the world goes back where it stood.

        [`actor.py`](actor.py) drops a body that steps off the mesh and keeps
        dropping it, which is right - the disc says nothing about a floor
        under the floor. Over a quest that is a run lost to one bad step, so
        the run keeps the last square metre the body was standing on and puts
        it back there. The engine's rule, and counted where it happens.
        """
        p = self.player
        if p is None:
            return
        if p.grounded:
            self.stood = (p.x, p.y, p.z)
            return
        if self.stood is not None and p.y < world.lo[1] - 2.0:
            p.x, p.y, p.z = self.stood
            p.vy, p.grounded, p.speed = 0.0, True, 0.0
            self.route, self.to = [], None
            self.n['fell out of the world'] += 1

    def _move(self, world, facing):
        """A step that does not walk off the ground.

        [`format_ccls.md`](../docs/format_ccls.md) reached the conclusion
        that **the edge of the walkable region is the fence** - there are not
        enough vertical triangles on the disc to wall a level, so the mesh
        boundary is what stops a body. [`actor.py`](actor.py) reports the
        step off it and falls, which is the right thing for a body that has
        been pushed; a body that is *walking* stops instead, and this is
        where that is decided.
        """
        p = self.player
        was = (p.x, p.y, p.z)
        r = p.step(world, gait='run', facing=facing)
        if r['event'].startswith('off') and p.grounded is False:
            p.x, p.y, p.z = was
            p.vy, p.grounded, p.speed = 0.0, True, 0.0
            self.n['stopped at the edge of the ground'] += 1
            if self.route:
                self.route.pop(0)

    def _press(self, target: Spawn):
        if self.step >= len(self.walk):
            self.step, self.walk = 0, self.ar.press(
                self.ar.combo_of(COMBO))
        if not self.walk:
            return
        node, _ = self.walk[self.step]
        self.step += 1
        a = self.ar.at_node(node)
        if a is None:
            return
        volley(self.ar, a)                  # so `lasts` knows the flight
        self.attack, self.frame_in = a, 0
        self.n['swings'] += 1
        self.player.heading = bearing(self.player.x, self.player.z,
                                      target.x, target.z)

    def _swing(self, _target):
        """The volumes of the frame, against everything alive.

        A volume is tested against every monster, not only the nearest: a
        swing that reaches two bodies lands on two, which is the whole point
        of a weapon with a reach.
        """
        a = self.attack
        for fr, pts, r, h in volley(self.ar, a):
            if fr != self.frame_in:
                continue
            world_pts = [turn(q, self.player.x, self.player.y,
                              self.player.z, self.player.heading)
                         for q in pts]
            for s in list(self.sp.live):
                tg = self._target(s.kind)
                got = against(tg.parts, (s.x, s.y, s.z, s.heading),
                              world_pts, r)
                if got and got[0][0] <= 0:
                    c = got[0][1]
                    self.n['landed'] += 1
                    self.n[('part', c['part'])] += 1
                    s.hits += 1
                    took = self._damage(s, tg, c['part'], h)
                    if c['break']:
                        self._break(s, tg, c['part'], took)
                    if s.left > 0.0:
                        s.left -= took
                        if s.left <= 0.0:
                            self.sp.kill(s)
                    elif s.hits >= self.blows:
                        self.sp.kill(s)      # only when its tables would
                        # not read: `arm` leaves `left` at zero and says so
        self.frame_in += 1
        if self.frame_in > a.lasts:
            self.attack = None

    def _stats(self, s: Spawn) -> dict:
        """One monster's own parameters, at its own tier, cached by both."""
        key = (s.kind, s.tier)
        if key not in self.stats:
            p = self.tree / 'monster.cpk' / s.kind / (s.kind + '.json')
            try:
                self.stats[key] = load_json(p, s.tier) if p.is_file() else {}
            except (OSError, ValueError):
                self.stats[key] = {}
        return self.stats[key]

    def arm(self, s: Spawn) -> None:
        """Give a spawn the hit points its own JSON carries.

        Done on the first landing rather than at the spawn, because a
        monster nobody reaches never needs them and the JSON is a file read.
        """
        if s.hp:
            return
        s.hp = s.left = float(self._stats(s).get('hp', 0) or 0)
        if s.hp <= 0.0:
            self.n['a monster whose hp would not read'] += 1

    def _region(self, tg: Target, part: str):
        return (region_of(tg.regions, part)
                or region_of(tg.broken, part))

    def _damage(self, s: Spawn, tg: Target, part: str, h) -> float:
        """One landed volume, through `damage.py`.

        The hit's own ratio is the `.anmcmd` record's `+0x30`, which is what
        `FUN_0060fe50` copies into the runtime record's first float and what
        the attack builder reads as its first argument. The region supplies
        the two terms the defence structure defaults to 0 and 1.
        """
        self.arm(s)
        p = self._stats(s)
        lv = int(p.get('region_lv', 0) or 0)
        flat, mul = region_terms(self._region(tg, part), lv, self.me.cls)
        d = defence_terms(float(p.get('def', 0) or 0), flat, mul)
        crit = (self.me.critical_rate > 0.0
                and self.rng.random() < self.me.critical_rate)
        a = self.me.attack_on(h.sizes[1])
        took = resolve(a, d, crit)
        if crit:
            self.n['critical'] += 1
        self.n['damage dealt'] += int(took)
        return took

    def _break(self, s: Spawn, tg: Target, part: str, took: float):
        """A landing on a part that comes off, and what comes off it.

        `region_data_brk` is the monster's breakable-part list and its
        **order** is what a region reward's byte 7 indexes - 298 of 298
        blocks carry exactly `0 .. n-1` for that list's length. So the part a
        volume landed on has a number, and that number is a row of the
        quest's own `item_reward_region.bin`.

        Since session 31 the part has a **pool** rather than a count:
        `region_data_brk` carries its own hit points, an order of magnitude
        larger than the body's, indexed by `region_lv` like everything else
        in the record. `BREAKS` survives only for a part whose pool is zero.
        """
        at = next((i for i, r in enumerate(tg.broken) if r['name'] == part),
                  None)
        if at is None:
            self.n['a part with no region_data_brk row'] += 1
            return
        if part not in s.broke:
            lv = int(self._stats(s).get('region_lv', 0) or 0)
            pool = tg.broken[at].get('brk_hp', [])
            s.broke[part] = (float(pool[max(0, min(lv, 7))])
                             if len(pool) > lv else 0.0)
            s.brk_hits[part] = 0
        if s.broke[part] < 0:
            return                          # already off
        s.brk_hits[part] += 1
        if s.broke[part] > 0.0:
            s.broke[part] -= took
            if s.broke[part] > 0.0:
                return
        elif s.brk_hits[part] < self.breaks:
            return                          # its pool would not read
        s.broke[part] = -1
        self.n['parts broken off'] += 1
        if self.sp.purse is not None:
            self.sp.purse.broke(s.kind, at, s.tier)

    def _monster(self, s: Spawn, world):
        e = self._enemy(s)
        if e is None:
            return
        fill(e.state, e, self.player.x, self.player.y, self.player.z,
             100, self.frame)
        # The three predicates a duel could not answer, and a crowd can.
        e.state.rand = self.rng.randrange(10001)
        e.state.other_zako = sum(1 for x in self.sp.live
                                 if x is not s and x.id < 2000)
        e.state.other_boss = sum(1 for x in self.sp.live
                                 if x is not s and x.id >= 2000)
        e.state.same_kind = sum(1 for x in self.sp.live
                                if x is not s and x.kind == s.kind)
        e.state.players = 1
        if e.move is None:
            _, action, _, _ = e.brain.act(e.state, self.rng)
            if action is None:
                return
            gate = e.m.ranges.get(action)
            if gate is not None and 0 < gate < SENTINEL \
                    and e.state.target_range > gate:
                e.walk(self.player.x, self.player.z, world, 20)
                e.last_act, e.since = action, 0
                s.x, s.y, s.z, s.heading = e.x, e.y, e.z, e.heading
                return
            e.last_act, e.since = action, 0
            mv = e.resolve(action)
            if mv.frames:
                e.move, e.frame = mv, 0
            return
        e.since += 1
        for h, q in e.move.place(e.actor, e.frame):
            pts = [e.world_point(v) for v in (q.p0, q.p1) if v is not None]
            if not pts:
                continue
            self.n['thrown'] += 1
            got = against(self.body, (self.player.x, self.player.y,
                                      self.player.z, self.player.heading),
                          pts, max(h.sizes[0], MIN_RADIUS))
            if got and got[0][0] <= 0:
                self.n['taken'] += 1
        e.frame += 1
        if e.frame > e.move.frames:
            e.move = None
        else:
            e.face(self.player.x, self.player.z)
        s.x, s.y, s.z, s.heading = e.x, e.y, e.z, e.heading


# -- the run ---------------------------------------------------------------


def _goal(host, t: Tables, stage: str, done: set, want: list, running='',
          at=None):
    """Where the player is trying to get to, as `(name, (x, z))`.

    First any arena the quest has armed on this stage and not yet cleared -
    the `pl_q<quest>` hit area is the lock's own `+0x18`, and the stage
    script turned it on. Then the way out, which is a `jump_` marker naming
    a stage of `piecelist.bin` that has not been walked yet.

    **The list is not a path.** 767 of the 1,280 consecutive pairs carry a
    jump from the first to the second, but 398 of the 428 lists are
    *connected* under those jumps, so the order is a reading order and the
    route is the graph - `route` measures both. `want` is what is left of the
    list, in the order it is written.

    An arena's destination is **the middle of its `lockarea`, not its
    trigger**. The trigger is a wide slab across a corridor and a body that
    stops at the near edge of it is still outside the fence the lock is about
    to raise; the middle of the area is a place the body can only be by
    having gone in. That the area *is* the arena is measurable and measured:
    2,813 of 2,817 spawners a lock covers and 572 of 575 triggers that close
    one lie inside its own `lockarea` polygon - `area` reports it.
    """
    by_name = host.world.stage.atih.by_name()
    lines = {ln.name: ln for ln in host.world.stage.lines}
    for k in t.locks_of(stage):
        if k['name'] in done:
            continue
        for name in (k['trigger'] or '').split('\n'):
            name = name.strip()
            m = by_name.get(name)
            if m is None or not host.hit_areas.get(name, True):
                continue
            if k['name'] == running and k['area'] in lines:
                # Inside the polygon rather than at the middle of it. The
                # middle is not always a place: `lockarea05` on `010_01_02`
                # is 54 by 87 metres with a lake in it and its centroid has
                # no ground under it at all, so a body sent there walks into
                # the fence around the water and stands until the run gives
                # the stage up. `world.into` answers with ground the polygon
                # encloses, nearest the body - and a body already in the
                # arena is already there.
                got = host.world.into(k['area'], at)
                if got is not None:
                    return k['area'], got, k
            return name, (m.position[0], m.position[2]), k
    # `jump_next` is the tower's exit: the 170 stages are interchangeable
    # floors, so the marker does not name where it goes and the stage's own
    # `MapJump()` branches on `getQuestName()` to decide where it leads.
    names = ['jump_' + s for s in want] + ['jump_next']
    # Reachability was tried here and it lost. `route` established that
    # `piecelist.bin` is a graph rather than a path, so passing over an exit
    # the mesh cannot reach in favour of one it can looked free - and on the
    # four quests it was aimed at, `070_01_02`'s exit up a 0.61 m riser, it
    # changed nothing, while `q00306` went from finishing to walking between
    # two rooms for the rest of the run. A* is conservative about a fence
    # and says None for places a body does get to, so a wrong "unreachable"
    # sends the body the wrong way. The order the list is written in is left
    # to decide.
    for name in names:
        m = by_name.get(name)
        if m is not None and host.hit_areas.get(name, True):
            return name, (m.position[0], m.position[2]), None
    for m in host.world.stage.markers:
        if m.name.startswith('jump_') and host.hit_areas.get(m.name, True):
            return m.name, (m.position[0], m.position[2]), None
    return None, None, None


def play(tree, name: str, cls='sw', blows=BLOWS, seed=1, verbose=True,
         limit=STAGE_FRAMES, breaks=BREAKS):
    """One quest, until every stage on its list has been walked and every
    arena on those stages opened.

    The route is `piecelist.bin`'s, and the jump is the stage's own trigger:
    the run steers the body at the marker and the disc's own `cfMapJump` does
    the loading, exactly as in [`host.py`](host.py)'s `stage`. The list is
    walked as a graph rather than as a path, because it is one - see `route`
    - so a room may be crossed twice on the way to one that only opens off
    it.
    """
    t = Tables(tree, name)
    sp = Spawner(t)
    host = Host(tree, quest=name, seed=seed, verbose=verbose, spawner=sp)
    # What the quest pays, and where the player stands in the story. The
    # block head of `item_reward.bin` is a threshold in the same number space
    # `cfGetMainCounter` returns, and `chapter.bin` says what this quest
    # requires - so the counter is the catalog's, not a guess.
    purse = Purse(tree, name, cls=PAYS.get(cls, 7), seed=seed)
    host.purse = sp.purse = purse
    host.main_counter = purse.progress
    host.load_common()
    ar = Arsenal(tree, cls)
    out = {'quest': name, 'class': cls, 'stages': [], 'want': list(t.stages),
           'locks': len(t.locks), 'frames': 0, 'blows': blows,
           'spawner': sp, 'host': host, 'n': collections.Counter(),
           'purse': purse, 'breaks': breaks, 'me': None,
           'armable': [], 'cleared': [], 'visited': [], 'done': False}
    if not t.stages:
        return out
    field = Field(tree, ar, sp, seed=seed, blows=blows, breaks=breaks)
    field.host = host
    out['me'] = field.me
    sp.at = lambda: (field.player.x, field.player.z)
    sp.radius = ar.params.get('col_r', 0.5)
    stage = t.stages[0]
    cleared: set = set()
    armable: set = set()          # a lock whose trigger the scripts turned on
    finished = False
    for i in range(2 * len(t.stages) + 6):
        try:
            host.enter_stage(stage)
        except (SystemExit, SquirrelError, VMError, ValueError) as e:
            out['error'] = '%s: %s' % (stage, e)
            break
        out['stages'].append(stage)
        spawn = host.world.marker('appear01')
        # The same rule as a monster's: the body stands on the ground under
        # the marker. Seven stages spawn the player more than `col_r` under
        # their own floor, and on those the body fell out of the world on
        # frame one and `_on_ground` put it back exactly where it fell from.
        floor = host.world.stand(spawn.position[0], spawn.position[2],
                                 spawn.position[1])
        field.player = Actor(ar.params, spawn.position[0],
                             spawn.position[1] if floor is None else floor,
                             spawn.position[2], spawn.rotation[1])
        field.attack, field.walk, field.step = None, [], 0
        field.route, field.to, field.was = [], None, None
        field.still, field.since, field.stood = 0, 0, None
        inside_now: set = set()
        jumped = False
        idle, mark = 0, None
        for _ in range(limit):
            host.frame += 1
            out['frames'] += 1
            host.tick_threads()
            # A lock that is *running* is still where the player is going:
            # the arena is what it walked in for.
            busy = {sp.lock['name']} if sp.lock is not None else set()
            left = [s for s in t.stages if s not in out['stages']]
            where, goal, arena = _goal(host, t, stage,
                                       cleared | (set(sp.started) - busy),
                                       left,
                                       sp.lock['name'] if sp.lock else '',
                                       (field.player.x, field.player.z))
            if goal is None:
                break
            field.where = where
            field.tick(host.world, goal)
            p = field.player
            now = {x.name: x for x in host.triggers_at(p.x, p.y, p.z)}
            for tn, tr in now.items():
                if tn in inside_now:
                    continue
                if tr.kind in (0, 1):
                    host.note('trigger', 'entered %s: %s' % (tn, tr.script))
                    host.run_source(tr.script)
            for tn in list(inside_now):
                if tn not in now:
                    tr = next((x for x in host.world.stage.triggers
                               if x.name == tn), None)
                    if tr is not None and tr.kind == 2:
                        host.run_source(tr.script)
            inside_now = set(now)
            cleared |= set(sp.opened)
            for k in t.locks_of(stage):
                # An arena only exists for a quest whose script turns its own
                # hit area on. A stage script ships in every quest that
                # visits the stage and disables all of them; each quest's
                # `sfQuestInit` enables the one it owns. A lock nothing arms
                # is not part of this quest, however plainly its table names
                # it.
                if any(host.hit_areas.get(x.strip())
                       for x in (k['trigger'] or '').split('\n')
                       if x.strip()):
                    armable.add(k['name'])
            # And any lock a script started by name, which need not be one of
            # this stage's: `format_quest.md` counted 309 `cfStartPieceLock`
            # calls naming a lock another quest declares.
            armable |= set(sp.started)
            # The end of a quest: every stage of `piecelist.bin` walked, and
            # every arena the scripts armed opened by the script itself.
            if set(t.stages) <= set(out['stages']) and armable <= cleared:
                finished = True
                break
            # A body that has gone nowhere for half a minute with nothing
            # left alive is not going to: give the stage up rather than
            # spend the rest of its budget on it.
            at = (round(field.player.x), round(field.player.z))
            idle = idle + 1 if at == mark and not sp.live else 0
            mark = at
            if idle > 900:
                out.setdefault('error', '%s: the body stopped walking'
                               % stage)
                break
            if host.pending_jump:
                to, _ = host.pending_jump
                host.pending_jump = None
                if not (host.tree / 'stage.cpk' / to / 'param.pac').is_dir():
                    out['error'] = '%s is not on the disc' % to
                    break
                stage, jumped = to, True
                break
        if finished or not jumped or 'error' in out:
            break
    out['n'] = field.n
    out['cleared'] = sorted(cleared)
    out['visited'] = out['stages']
    out['armable'] = sorted(armable)
    out['done'] = finished or (set(t.stages) <= set(out['stages'])
                               and armable <= cleared)
    # A quest pays when it is over, once - `item_reward.bin` is the results
    # screen and the item text calls it "Quest Reward" in so many words.
    if out['done']:
        purse.finish()
    return out


# -- the commands ----------------------------------------------------------


def cmd_run(tree, name='q00102', cls='sw', blows=str(BLOWS),
            verbose='1') -> int:
    """One quest, end to end, with the whole log."""
    if cls not in CLASSES:
        raise SystemExit('class must be one of %s' % ', '.join(CLASSES))
    r = play(tree, name, cls, int(blows), verbose=verbose != '0')
    sp, n = r['spawner'], r['n']
    t = Tables(tree, name)
    print()
    print('  %s as the %s, %d frames = %.1f s'
          % (name, CLASSES[cls][0], r['frames'], r['frames'] / FPS))
    print('  route wanted   %s' % ' -> '.join(r['want']))
    print('  route walked   %s' % ' -> '.join(r['visited']))
    # The difficulty tier each room spawns at, which is the disc's and not
    # this file's - `enemy.bin` `+0x37`, and `+0x57` where it names a second.
    print('  the tier       %s'
          % ', '.join('%s %d%s' % (st, lo, '' if hi is None else '/%d' % hi)
                      for st, (lo, hi) in sorted(t.tiers.items())))
    print('  %d locks in the quest, %d started, %d the script ended itself: %s'
          % (r['locks'], len(sp.started), len(sp.opened),
             ', '.join(sp.opened) or '-'))
    for k in t.locks:
        want = t.thresholds(k['stage'])
        fns = {g['on_kill'] for g in t.generators(k['stage'])
               if g['name'] in k['gens'] and g['on_kill']}
        got = [want[f] for f in fns if f in want]
        print('    %-20s %-12s %d generators, the script stops at %s'
              % (k['name'], k['stage'], len(k['gens']),
                 ', '.join(str(x) for x in got) or '-'))
    print('  %d monsters spawned, %d killed, the last of them id %d'
          % (sp.log['spawned'], sp.total_kills, sp.latest_killed))
    print('  %d volumes swung landed, %d of the monsters\' landed on the '
          'player' % (n['landed'], n['taken']))
    parts = [(v, k[1]) for k, v in n.items()
             if isinstance(k, tuple) and k[0] == 'part']
    if parts:
        parts.sort(reverse=True)
        print('  where they landed: %s'
              % ', '.join('%s %d' % (p, c) for c, p in parts[:8]))
    me = r.get('me')
    if me is not None:
        print('  a monster dies of its own hp: %d damage dealt, %d of it '
              'critical' % (n['damage dealt'], n['critical']))
        print('    the player is %s at row %d - atk %.0f + %.0f from its '
              'weapon, def %.0f, hp %d'
              % (me.cls, me.level, me.atk, me.add, me.def_, me.hp))
    if n['a monster whose hp would not read']:
        print('    and %d landing%s on a monster whose hp would not read, '
              'which fall back on the %d volumes this used to use'
              % (n['a monster whose hp would not read'],
                 '' if n['a monster whose hp would not read'] == 1 else 's',
                 r['blows']))
    r['purse'].report()
    if sp.log:
        print('  the spawner: %s' % ', '.join(
            '%s %d' % (k, v) for k, v in sorted(sp.log.items())))
    if r['host'].arity:
        print('  called with the wrong number of arguments: %s'
              % ', '.join('%s %d' % (k, v)
                          for k, v in sorted(r['host'].arity.items())))
    print('  %s' % ('the quest finished' if r['done']
                    else 'the quest did not finish: ' + r.get('error', 'the '
                         'route or a lock was left open')))
    return 0 if r['done'] else 1


def cmd_runs(tree, want='*', cls='sw', blows=str(BLOWS), quiet='0') -> int:
    """Every quest on the disc, and how far each one gets.

    Two numbers, and they measure different things. **How many arenas the
    script closed by itself** is the state machine, and it is the milestone:
    the run never tells a script how many monsters to expect. **How many
    quests walked their whole stage list** is the navigation, and it is this
    file's own steering rather than anything the disc says - a body that
    walks into a corner and stays there is a bad walker, not a wrong reading.
    """
    root = pathlib.Path(tree) / 'quest.cpk'
    names = sorted(p.name[:-4] for p in root.iterdir()
                   if re.fullmatch(r'q\d+\.pac', p.name)
                   and fnmatch.fnmatch(p.name[:-4], want))
    done = ran = walked = 0
    fights = fought = 0
    armed = opened = started = 0
    kills = spawns = 0
    routed = wanted = 0
    zeny = paid = 0
    took = collections.Counter()
    why = collections.Counter()
    fails = collections.Counter()
    slips = collections.Counter()
    for name in names:
        try:
            r = play(tree, name, cls, int(blows), verbose=False)
        except (SystemExit, SquirrelError, VMError, ValueError, TypeError,
                AttributeError, OSError, KeyError, IndexError) as e:
            # One quest must not end a sweep of 430. What raised is counted
            # by its type and named in the summary rather than swallowed.
            fails['%s: %s' % (type(e).__name__, e)] += 1
            continue
        ran += 1
        sp = r['spawner']
        armed += len(r['armable'])
        started += len(set(sp.started))
        opened += len(set(sp.opened))
        kills += sp.total_kills
        spawns += sp.log['spawned']
        wanted += len(r['want'])
        routed += len([s for s in r['want'] if s in r['visited']])
        walked += set(r['want']) <= set(r['visited'])
        for k in r['host'].arity:
            slips[k] += r['host'].arity[k]
        done += bool(r['done'])
        pu = r['purse']
        zeny += pu.zeny
        paid += bool(pu.items)
        took.update(pu.items)
        for w, item, n in pu.took:
            why[w] += n
        if r['armable']:
            fights += 1
            fought += bool(r['done'])
        if quiet == '0':
            print('  %-8s %2d/%-2d stages  %2d/%-2d arenas closed  %3d '
                  'killed  %s'
                  % (name, len(set(r['visited']) & set(r['want'])),
                     len(r['want']), len(set(sp.opened)), len(r['armable']),
                     sp.total_kills,
                     'finished' if r['done'] else r.get('error', '')))
    print()
    print('%d quests run, %d of them finished' % (ran, done))
    print('  %d of the %d that arm an arena at all, %d of the %d that do not'
          % (fought, fights, done - fought, ran - fights))
    print('  %d walked their whole stage list, %d of %d stages in all'
          % (walked, routed, wanted))
    print('  %d arenas armed by a quest script, %d started, %d ended by the '
          'script\'s own kill count' % (armed, started, opened))
    print('  %d monsters spawned, %d killed' % (spawns, kills))
    print('  %d quests paid something: %s zeny and %d items of %d kinds'
          % (paid, '{:,}'.format(zeny), sum(took.values()), len(took)))
    if why:
        print('    out of %s' % ', '.join(
            '%s %d' % (k, v) for k, v in why.most_common()))
    if slips:
        print('  %d calls with the wrong number of arguments, which the host '
              'adapts: %s' % (sum(slips.values()), dict(slips.most_common(4))))
    if fails:
        print('  %d quests raised: %s' % (sum(fails.values()),
                                          dict(fails.most_common())))
    return 0


def cmd_counts(tree) -> int:
    """Does the script's own kill count equal the lock's generator list?

    Two files, two readers, no shared assumption. The threshold is a
    constant compiled into `.psq` bytecode; the generator list is a
    newline-separated string in `piecelock.bin` lane `+0x1c`. If the lane is
    read wrong the two disagree, and there is no way to arrange the
    agreement from either side.
    """
    root = pathlib.Path(tree) / 'quest.cpk'
    names = sorted(p.name[:-4] for p in root.iterdir()
                   if re.fullmatch(r'q\d+\.pac', p.name))
    hit = miss = nofn = nokill = locks = 0
    off = collections.Counter()
    shown = []
    for name in names:
        t = Tables(tree, name)
        cache = {}
        for k in t.locks:
            locks += 1
            covered = [g for g in t.generators(k['stage'])
                       if g['name'] in k['gens']]
            fns = sorted({g['on_kill'] for g in covered if g['on_kill']})
            if not fns:
                nokill += 1
                continue
            if k['stage'] not in cache:
                cache[k['stage']] = t.thresholds(k['stage'])
            want = cache[k['stage']]
            for fn in fns:
                if fn not in want:
                    nofn += 1
                    if len(shown) < 8:
                        shown.append('%s %s -> %s counts nothing'
                                     % (name, k['name'], fn))
                    continue
                if want[fn] == len(covered):
                    hit += 1
                else:
                    miss += 1
                    off[want[fn] - len(covered)] += 1
                    if len(shown) < 8:
                        shown.append('%s %s -> %s stops at %d, the lock '
                                     'covers %d' % (name, k['name'], fn,
                                                    want[fn], len(covered)))
    print('%d locks over %d quests' % (locks, len(names)))
    print('  %d name a generator with a counting callback' % (hit + miss
                                                              + nofn))
    print('  the script\'s threshold equals the generators the lock covers')
    print('    %d yes, %d no' % (hit, miss))
    print('  %d locks whose generators name no callback at all' % nokill)
    print('  %d callbacks that count nothing' % nofn)
    if off:
        print('  the differences: %s' % dict(off.most_common(10)))
    for s in shown:
        print('    %s' % s)
    return 1 if miss else 0


def _stages(tree, cache={}):
    """Every stage's marker names and polylines, loaded once."""
    import stage as stagelib                                # noqa: PLC0415

    def get(s):
        if s not in cache:
            d = pathlib.Path(tree) / 'stage.cpk' / s / 'param.pac'
            if not d.is_dir():
                cache[s] = None
            else:
                files = {p.name: p.read_bytes() for p in d.iterdir()
                         if p.is_file()}
                st = stagelib.Stage(s, files)
                cache[s] = ({m.name: m for m in st.markers},
                            {ln.name: [(p[0], p[2]) for p in ln.world()]
                             for ln in st.lines})
        return cache[s]
    return get


def _quests(tree):
    root = pathlib.Path(tree) / 'quest.cpk'
    return sorted(p.name[:-4] for p in root.iterdir()
                  if re.fullmatch(r'q\d+\.pac', p.name))


def _in_polygon(p, poly) -> bool:
    """Even-odd, in the XZ plane."""
    x, z = p
    out, j = False, len(poly) - 1
    for i in range(len(poly)):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if (zi > z) != (zj > z) and \
                x < (xj - xi) * (z - zi) / ((zj - zi) or 1e-12) + xi:
            out = not out
        j = i
    return out


def cmd_route(tree) -> int:
    """Is `piecelist.bin` a route, or only a set?

    The only thing that moves a body between two stages is a `jump_` trigger,
    so the list is a route if its stages are connected under those markers.
    They are - but **not in the order the list is written**, which is worth
    separating: the consecutive pair is the strong claim and it fails often
    enough to matter, while the connectivity is the one the run needs.
    """
    get = _stages(tree)
    names = _quests(tree)
    pairs = direct = 0
    lists = whole = 0
    for name in names:
        st = Tables(tree, name).stages
        if not st:
            continue
        lists += 1
        for a, b in zip(st, st[1:]):
            pairs += 1
            ma = get(a)
            if ma and 'jump_' + b in ma[0]:
                direct += 1
        want = set(st)
        seen, stack = {st[0]}, [st[0]]
        while stack:
            u = stack.pop()
            here = get(u)
            for v in want - seen:
                if here and 'jump_' + v in here[0]:
                    seen.add(v)
                    stack.append(v)
        whole += seen == want
    print('%d quests with a stage list, %d consecutive pairs in them'
          % (lists, pairs))
    print('  %d pairs where the first carries a jump marker naming the second'
          % direct)
    print('  %d lists reachable end to end from their own first stage'
          % whole)
    return 0


def cmd_area(tree) -> int:
    """Is a lock's `lockarea` the arena it locks?

    `piecelock.bin` gives a lock one `lockarea` polyline and a list of
    `lock_line`s, and nothing says which is the room and which are the doors.
    The test needs no run: put the lock's own generators and the trigger that
    closes it against the polygon and see whether they are inside it.
    """
    get = _stages(tree)
    n = collections.Counter()
    for name in _quests(tree):
        t = Tables(tree, name)
        for k in t.locks:
            st = get(k['stage'])
            if st is None:
                continue
            poly = st[1].get(k['area'])
            if not poly or len(poly) < 4:
                n['locks with no area polyline'] += 1
                continue
            n['locks with an area polyline'] += 1
            for who in (k['trigger'] or '').split('\n'):
                m = st[0].get(who.strip())
                if m is None:
                    continue
                n['triggers'] += 1
                n['triggers inside' if _in_polygon(
                    (m.position[0], m.position[2]), poly)
                  else 'triggers outside'] += 1
            for g in t.generators(k['stage']):
                if g['name'] not in k['gens']:
                    continue
                m = st[0].get(g['marker'])
                if m is None:
                    continue
                n['spawners'] += 1
                n['spawners inside' if _in_polygon(
                    (m.position[0], m.position[2]), poly)
                  else 'spawners outside'] += 1
    print('%d locks with an area polyline, %d without'
          % (n['locks with an area polyline'], n['locks with no area '
                                                 'polyline']))
    print('  the spawners it covers   %d of %d inside'
          % (n['spawners inside'], n['spawners']))
    print('  the trigger that closes it   %d of %d inside'
          % (n['triggers inside'], n['triggers']))
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    cmd, rest = a[0], a[1:]
    if cmd == 'run' and rest:
        return cmd_run(*rest)
    if cmd == 'runs' and rest:
        return cmd_runs(*rest)
    if cmd == 'counts' and rest:
        return cmd_counts(*rest)
    if cmd == 'route' and rest:
        return cmd_route(*rest)
    if cmd == 'area' and rest:
        return cmd_area(*rest)
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
