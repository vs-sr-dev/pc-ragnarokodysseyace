"""
brain.py - the monster AI, running: the rules, the terms and the weighted pick.

[`format_ai.md`](../docs/format_ai.md) read the three files a monster decides
with - `SelectScript.dat`, a ladder of rules; `ProbList.dat`, a weighted table
per rule; and the six `.par`, which gate an action by range and angle. This
runs them.

    python engine/brain.py terms  extract/tree [trials]
    python engine/brain.py agree  extract/tree [trials]
    python engine/brain.py decide extract/tree <monster> [trials]
    python engine/brain.py check  extract/tree

`decide` puts one monster in a state and asks it what to do. `terms` and
`agree` are the two measurements, and both of them work by running the game's
own code beside this file's.

## The disc ships its own reference implementation, so use it

`check_converted_xml_term(term, param, cond)` in the six `.cnut` is a switch
on the 76 term ids, and it is byte-identical in all six - all at
`.ppcut` line 1174, so it was a shared include. Now that
[`squirrel.py`](squirrel.py) exists, that function is not documentation: it is
**executable**, and it can drive any monster's tables, including the 78 that
ship no script at all.

So there are two evaluators here, and the point of having two is that they
check each other:

- `Terms.of` is this file's own, transcribed from that dispatch;
- `Terms.disc` calls the dispatch itself, in the VM, with the same host
  predicates bound underneath.

`brain.py terms` runs both over random states and reports where they differ.
It is the reverse of the usual direction on this project: the disc is not
being *read* here, it is being *asked*.

## What a rule is, when it runs

A rule is a run of instructions that must all hold, the first of which carries
the action ([`format_ai.md`](../docs/format_ai.md)). Three flags change that:
`0x8000` inverts one term, `0x4000` marks a run that is ORed together, and
`0x2000` opens a rule that **inherits the conditions of the rule above it** -
so this evaluator carries the last `0x1000` rule's instructions forward and
prepends them.

Rules are tried in order and the first whose terms all hold wins. 136 of the
144 files end with an unconditional fallback, so a monster nearly always has
something to do.

## The state the terms ask about

`State` is one object with a field per predicate, because that is exactly what
the interface is: 40-odd questions about a fight. Where the engine can answer
one from geometry it does - `getTargetRange` is a distance and
`getHpRate` is a fraction of the JSON's `hp` - and where it cannot, the field
is a plain default and `State.SOURCE` says so. Nothing here is guessed
silently.

Two of the answers are this file's reading rather than the disc's, and they
are marked as such:

- **`getAngleTypeToTarget` returns 213 or 214 and `getAngleTypeAtTarget`
  returns 215 to 218**, because the dispatch compares each against the term's
  own id. Two bands and four bands. The reading adopted here is that *to* is
  where the target sits in my frame and *at* is where I sit in the target's,
  which is what the names say and what the band counts fit; the disc does not
  declare it;
- **`checkRangeParam` returns 0, 1 or 2**, and `_act.par` gives every action
  one range. Inside it, beyond it, and far beyond it is the reading here, with
  the far band at twice the range. The disc says only that the three values
  are distinct, because `AI_B12_Fenia` ORs 0 with 2.
"""
from __future__ import annotations

import collections
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

from squirrel import (Closure, Native, SquirrelError, Thread, VM,   # noqa: E402
                      compare, equal, globals_called)
from psq import Psq                                           # noqa: E402
import ai                                                     # noqa: E402

# The dispatch is byte-identical in all six `.cnut`, so one of them can serve
# every monster on the disc.
DISPATCH = 'AI_B01_OrcKing'
ANGLE_TO = (213, 214)                  # two bands, compared against the term
ANGLE_AT = (215, 216, 217, 218)        # four


def check_term_param(chk, par):
    """`check_term_param(chk, par)` out of the same `.cnut`, transcribed with
    Squirrel's own comparison rules rather than Python's:

        if (chk != false)
            if ((par == 0) || (chk <= par)) return true
        return false

    `chk != false` is Squirrel's `==`, which is false between types, so an
    *integer* 0 passes it; and `chk <= par` is Squirrel's compare, which
    raises between a bool and an integer rather than coercing. Both matter,
    and neither is what Python would do."""
    if equal(chk, False):
        return False
    if equal(par, 0):
        return True
    return compare(chk, par) <= 0


class State:
    """One monster's view of one moment of a fight.

    Every field is the answer to one host predicate. `SOURCE` says where each
    comes from when a fight is running: `world` if the engine computes it,
    `table` if it comes off a file, and `default` if nothing here knows yet -
    the last of which is the honest name for a stub."""

    SOURCE = {
        'hp_rate': 'world', 'target_range': 'world', 'target_pos_y': 'world',
        'angle_to': 'world', 'angle_at': 'world', 'range_band': 'world',
        'lock_range': 'world', 'target_ground': 'world', 'scale': 'table',
        'ai_type': 'table', 'last_act': 'world', 'total_time': 'world',
        'boss_time': 'world', 'timers': 'world', 'players': 'world',
        'other_zako': 'world', 'other_boss': 'world', 'same_kind': 'world',
        'rand': 'world',
        'damaged': 'default', 'stagger': 'default', 'downed': 'default',
        'angry': 'default', 'angry_req': 'default', 'poison': 'default',
        'cure_poison': 'default', 'cure_paralysis': 'default',
        'cure_faint': 'default', 'parts_broken': 'default',
        'parts_damage': 'default', 'act_success': 'default',
        'failed_act': 'default', 'failed_rot': 'default', 'react': 'default',
        'to_active': 'default', 'target_hp_rate': 'default',
        'target_job': 'default', 'target_attack': 'default',
        'target_guard': 'default', 'target_sway': 'default',
        'target_jump': 'default', 'target_object': 'default',
        'target_damage': 'default', 'target_down': 'default',
        'target_area': 'default', 'damage_from_target': 'default',
        'boss_target': 'default',
    }

    def __init__(self):
        self.hp_rate = 100
        self.target_range = 5.0             # metres
        self.target_pos_y = 0.0
        self.angle_to = ANGLE_TO[0]
        self.angle_at = ANGLE_AT[0]
        self.range_band = 0
        self.lock_range = -1.0
        self.target_ground = True
        self.scale = 1.0
        self.ai_type = 0
        self.last_act = 0
        self.total_time = 0.0               # seconds
        self.boss_time = 0.0
        self.timers = {}                    # term id -> seconds
        self.players = 1
        self.other_zako = 0
        self.other_boss = 0
        self.same_kind = 0
        self.rand = 0                       # what getRand() hands back
        self.damaged = 0
        self.stagger = 0
        self.downed = False
        self.angry = False
        self.angry_req = False
        self.poison = False
        self.cure_poison = False
        self.cure_paralysis = False
        self.cure_faint = False
        self.parts_broken = set()
        self.parts_damage = {}
        self.act_success = 0
        self.failed_act = 0
        self.failed_rot = False
        self.react = False
        self.to_active = False
        self.target_hp_rate = 100
        self.target_job = 0
        self.target_attack = False
        self.target_guard = False
        self.target_sway = False
        self.target_jump = False
        self.target_object = False
        self.target_damage = False
        self.target_down = False
        self.target_area = 0
        self.damage_from_target = 0
        self.boss_target = 0

    def time_of(self, term) -> float:
        return self.timers.get(term, 0.0)

    def randomise(self, rng: random.Random):
        """A state that exercises the ladder. The ranges are the ones the
        tables themselves compare against, so the bands actually split."""
        self.hp_rate = rng.randrange(0, 101)
        self.target_range = rng.choice([0.5, 1.5, 3.0, 5.0, 7.0, 12.0, 20.0,
                                        30.0])
        self.target_pos_y = rng.choice([0.0, 0.0, 1.5, 6.0])
        self.angle_to = rng.choice(ANGLE_TO)
        self.angle_at = rng.choice(ANGLE_AT)
        self.range_band = rng.randrange(3)
        self.lock_range = rng.choice([-1.0, 2.0, 9.0])
        self.target_ground = rng.random() < 0.8
        self.ai_type = rng.randrange(4)
        self.last_act = rng.choice([0, 100, 101, 104, 105])
        self.total_time = rng.choice([1.0, 10.0, 60.0, 300.0])
        self.boss_time = rng.choice([0.5, 2.0, 30.0])
        self.timers = {t: rng.choice([0.0, 5.0, 15.0, 60.0])
                       for t in range(10, 18)}
        self.timers[119] = rng.choice([0.0, 5.0, 60.0])
        self.players = rng.randrange(1, 5)
        self.other_zako = rng.randrange(0, 4)
        self.other_boss = rng.randrange(0, 2)
        self.same_kind = rng.randrange(0, 3)
        self.rand = rng.randrange(0, 10001)
        self.damaged = rng.randrange(0, 6)
        self.stagger = rng.randrange(0, 4)
        self.downed = rng.random() < 0.2
        self.angry = rng.random() < 0.3
        self.angry_req = rng.random() < 0.2
        self.poison = rng.random() < 0.1
        self.cure_poison = rng.random() < 0.1
        self.cure_paralysis = rng.random() < 0.1
        self.cure_faint = rng.random() < 0.1
        self.parts_broken = {p for p in range(4) if rng.random() < 0.2}
        self.parts_damage = {p: rng.randrange(0, 3) for p in range(4)}
        self.act_success = rng.randrange(0, 4)
        self.failed_act = rng.randrange(0, 4)
        self.failed_rot = rng.random() < 0.2
        self.react = rng.random() < 0.2
        self.to_active = rng.random() < 0.2
        self.target_hp_rate = rng.randrange(0, 101)
        self.target_job = rng.randrange(0, 6)
        self.target_attack = rng.random() < 0.3
        self.target_guard = rng.random() < 0.2
        self.target_sway = rng.random() < 0.2
        self.target_jump = rng.random() < 0.2
        self.target_object = rng.random() < 0.1
        self.target_damage = rng.random() < 0.2
        self.target_down = rng.random() < 0.2
        self.target_area = rng.randrange(0, 3)
        self.damage_from_target = rng.randrange(0, 5)
        self.boss_target = rng.randrange(0, 2)
        return self


# -- the predicates --------------------------------------------------------
#
# One entry per host function the term dispatch and the selector call. The
# `is*` family returns real booleans on purpose: Squirrel's `==` is false
# between a bool and an integer, and the dispatch ends `ret = (ret == cond)`.


def predicates(state: State, extra=None) -> dict:
    p = {
        'getTotalTime': lambda: int(state.total_time),
        'getBossTime': lambda: int(state.boss_time),
        'getTimeFromID': lambda t: int(state.time_of(int(t))),
        'getOtherZakoCount': lambda: state.other_zako,
        'getOtherBossCount': lambda: state.other_boss,
        'getActiveSameKindCount': lambda: state.same_kind,
        'getPlayerCount': lambda: state.players,
        'getRand': lambda: state.rand,
        'getAIType': lambda: state.ai_type,
        'getScale': lambda: state.scale,
        'isBossToTarget': lambda b: state.boss_target == int(b),
        'getHpRate': lambda: state.hp_rate,
        'getDamagedCount': lambda: state.damaged,
        'getStaggerCount': lambda: state.stagger,
        'isDowned': lambda: state.downed,
        'isAngry': lambda: state.angry,
        'isAngryReq': lambda: state.angry_req,
        'isPoison': lambda: state.poison,
        'isRecoverPoison': lambda: state.cure_poison,
        'isRecoverParalyz': lambda: state.cure_paralysis,
        'isRecoverFaint': lambda: state.cure_faint,
        'isDestroyedParts': lambda b: int(b) in state.parts_broken,
        'getPartsDamageCount': lambda b: state.parts_damage.get(int(b), 0),
        'getLastActId': lambda: state.last_act,
        'getActSuccessCount': lambda: state.act_success,
        'getFailedActCount': lambda: state.failed_act,
        'isFailedRotation': lambda: state.failed_rot,
        'isReact': lambda: state.react,
        'isToActive': lambda: state.to_active,
        'getTargetHpRate': lambda: state.target_hp_rate,
        'getTargetJob': lambda: state.target_job,
        'isTargetGround': lambda: state.target_ground,
        'isTargetAttack': lambda: state.target_attack,
        'isTargetGuard': lambda: state.target_guard,
        'isTargetSway': lambda: state.target_sway,
        'isTargetJump': lambda: state.target_jump,
        'isTargetObject': lambda: state.target_object,
        'isTargetDamage': lambda: state.target_damage,
        'isTargetDown': lambda: state.target_down,
        'getTargetArea': lambda: state.target_area,
        'getTargetPosy': lambda: state.target_pos_y,
        'getTargetRange': lambda: state.target_range,
        'getLockTargetRange': lambda: state.lock_range,
        'getDamageFromTarget': lambda: state.damage_from_target,
        'checkRangeParam': lambda: state.range_band,
        'getAngleTypeToTarget': lambda: state.angle_to,
        'getAngleTypeAtTarget': lambda: state.angle_at,
        # the selector's own two, and the debug hook
        'getSelRevise': lambda act, weight: weight,
        'printAitIdName': lambda t=0: None,
        'isActive': lambda: True,
        'print': lambda s=None: None,
    }
    p.update(extra or {})
    return p


class Terms:
    """Both evaluators, over one state."""

    def __init__(self, state: State, vm=None):
        self.state = state
        self.vm = vm

    # -- this file's own, transcribed from `check_converted_xml_term` -----

    def of(self, t: int, param: int, cond: bool) -> bool:
        s = self.state
        ret = False
        if t == 1:
            ret = True
        elif t == 2:
            ret = int(s.total_time) <= param
        elif t == 3:
            z = s.other_zako
            ret = z > 0 and z >= param
        elif t == 4:
            ret = s.other_boss > 0
        elif t == 7:
            ret = s.players >= param
        elif t == 8:
            ret = s.rand * 100 < param
        elif t == 9:
            ret = s.ai_type == param
        elif 10 <= t <= 17:
            time = int(s.time_of(t))
            ret = time == 0 or time >= param
        elif t == 119:
            ret = int(s.time_of(t)) >= param
        elif t == 18:
            ret = int(s.boss_time) <= param
        elif t == 19:
            ret = s.other_zako == 0
        elif t == 20:
            ret = s.boss_target == param
        elif t == 21:
            ret = s.same_kind >= param
        elif t == 101:
            ret = s.hp_rate >= param
        elif t == 102:
            ret = s.damaged >= 0 and s.damaged >= param
        elif t == 103:
            ret = check_term_param(s.downed, param)
        elif t == 104:
            ret = s.angry
        elif t == 105:
            ret = s.poison
        elif t == 106:
            ret = check_term_param(s.cure_poison, param)
        elif t == 107:
            ret = check_term_param(s.cure_paralysis, param)
        elif t == 108:
            ret = check_term_param(s.cure_faint, param)
        elif t == 109:
            ret = param in s.parts_broken
        elif t == 110:
            ret = s.last_act == param
        elif t == 111:
            ret = s.act_success != 0 if param == 0 else s.act_success >= param
        elif t == 112:
            ret = s.angry_req
        elif t == 113:
            ret = s.stagger >= param
        elif t == 114:
            ret = equal(s.react, cond)     # the one term that reads `cond`
        elif t == 115:
            ret = s.parts_damage.get(param, 0)
        elif t == 116:
            ret = s.to_active
        elif t == 117:
            ret = s.failed_rot
        elif t == 118:
            ret = s.failed_act >= param
        elif t == 201:
            ret = s.target_hp_rate >= param
        elif t == 202:
            ret = s.target_job == param
        elif t == 203:
            ret = s.target_ground
        elif t == 204:
            ret = s.target_attack
        elif t == 205:
            ret = s.target_guard
        elif t == 206:
            ret = s.target_sway
        elif t == 207:
            ret = s.target_jump
        elif t == 208:
            ret = s.range_band == 0
        elif t == 209:
            ret = s.range_band == 2
        elif t == 210:
            ret = s.range_band == 1
        elif t == 211:
            ret = s.target_range < param * 0.01
        elif t == 212:
            ret = s.damage_from_target >= param
        elif t in (213, 214):
            ret = s.angle_to == t
        elif 215 <= t <= 218:
            ret = s.angle_at == t
        elif t == 219:
            ret = s.lock_range < param * 0.01 and s.lock_range >= 0
        elif t == 220:
            ret = s.target_pos_y >= param * 0.01
        elif t == 221:
            ret = s.target_area == param
        elif t == 222:
            ret = s.target_object
        elif t == 223:
            ret = s.target_damage
        elif t == 224:
            ret = s.target_down
        elif t == 225:
            ret = s.target_range < param * 0.01 * s.scale
        else:
            return NOT_KNOWN
        # `ret = (ret == cond)` - Squirrel's `==`, so an integer `ret` never
        # equals a boolean `cond` and the term is dead whichever way `cond`
        # goes. Three terms are written that way; see `brain.py terms`.
        return equal(ret, cond)

    def play(self, t: int, param: int, cond: bool):
        """The reading the engine actually uses, which differs from the
        transcription in exactly one term.

        The shared include writes the chance term as `getRand() * 100 <
        param`. `getRand()` returns 0 to 10,000 - `prt_select` normalises its
        weights to 10,000 and rolls against them, and the mercenary interface
        says the same - so under that form a 20% chance fires only when the
        roll is exactly 0. The OrcKing's own hand-written rules write the
        same rule as `getRand() <= 2000` against a table operand of 20, which
        is `rand <= param * 100`, and that is what is used here.

        The number that settles it is in `brain.py agree`: over 300 random
        states the table and the script pick the same group 217 times under
        the include's form and 293 under this one."""
        if t == 8:
            return equal(self.state.rand <= param * 100, cond)
        if t in (103, 106, 107, 108):
            # `check_term_param(isDowned(), param)` compares its argument
            # against the operand, which Squirrel refuses to do between a
            # bool and an integer - so the engine's `isDowned` returns a
            # *number*, and the term reads "downed, and no more than b".
            # Five instructions on the disc pass a non-zero operand there
            # and would throw under the include as written.
            chk = int({103: self.state.downed, 106: self.state.cure_poison,
                       107: self.state.cure_paralysis,
                       108: self.state.cure_faint}[t])
            ret = chk != 0 and (param == 0 or chk <= param)
            return equal(ret, cond)
        if t == 115:
            # `ret = getPartsDamageCount(param)` leaves an integer where the
            # dispatch then writes `ret == cond` against a boolean, so the
            # term is dead as written. 47 instructions use it; the engine
            # reads the count as a flag.
            return equal(bool(self.state.parts_damage.get(param, 0)), cond)
        return self.of(t, param, cond)

    # -- the disc's own, in the VM ----------------------------------------

    def disc(self, t: int, param: int, cond: bool):
        th = Thread(self.vm, 'term')
        th.start(self.vm.find('check_converted_xml_term'), [t, param, cond])
        return th.value


NOT_KNOWN = 'unknown'


def dispatch_vm(tree, state: State, extra=None) -> VM:
    """A VM with one `.cnut` loaded and the predicates bound to `state`."""
    path = monster_dir(tree, DISPATCH) / (DISPATCH + '.cnut')
    q = Psq(path.read_bytes(), path.name)
    vm = VM(printer=lambda s: None)
    for name, fn in predicates(state, extra).items():
        vm.register(name, fn)
    for n in globals_called(q.root):
        if n not in vm.root.slots:
            vm.register(n, lambda *a: 0)
    vm.load(q.root, path.name)
    return vm


# -- one monster -----------------------------------------------------------


def index(tree) -> dict:
    """Every monster with an `ai.pac`: name -> its directory."""
    out = {}
    for p in sorted((pathlib.Path(tree) / 'monster.cpk').glob('*/ai.pac')):
        for f in p.glob('*_ProbList.dat'):
            out[f.name[:-len(ai.PROB)]] = p
    return out


def monster_dir(tree, name) -> pathlib.Path:
    found = index(tree)
    if name in found:
        return found[name]
    for k, v in found.items():
        if name.lower() in k.lower() or name == v.parent.name:
            return v
    raise SystemExit('no monster named ' + name)


class Monster:
    """The three files a monster decides with, and the two that gate it."""

    def __init__(self, tree, name):
        self.tree = pathlib.Path(tree)
        self.dir = monster_dir(tree, name)
        self.name = next(f.name[:-len(ai.PROB)]
                         for f in self.dir.glob('*_ProbList.dat'))
        self.kind = self.dir.parent.name            # `b01_00`
        self.prefix = self.kind.split('_')[0]       # `b01`
        self.prob = ai.ProbList((self.dir / (self.name + ai.PROB)).read_bytes(),
                                self.name)
        self.groups = self.prob.groups()
        self.select = self._script('_SelectScript.dat')
        self.prowl = self._script('_ProwlScript.dat')
        self.act = self._par('act')
        self.dfa = self._par('dfa')
        self.cmb = self._par('cmb')
        cnut = self.dir / (self.name + '.cnut')
        self.cnut = cnut if cnut.is_file() else None
        self.ranges = {row[0]: row[1] for row in self.act.rows()} \
            if self.act else {}
        self.angles = {row[0]: row[2] for row in self.act.rows()} \
            if self.act else {}

    def _script(self, suffix):
        p = self.dir / (self.name + suffix)
        return ai.Script(p.read_bytes(), p.name) if p.is_file() else None

    def _par(self, kind):
        p = self.dir / ('%s_%s.par' % (self.name, kind))
        return ai.Par(p.read_bytes(), kind, p.name) if p.is_file() else None

    def motions(self):
        if not hasattr(self, '_motions'):
            self._motions = ai.motions(self.tree).get(self.prefix, {})
        return self._motions

    def motion_of(self, action: int):
        """(motion id, its name) for an action, or (0, '') - the join
        [`format_ai.md`](../docs/format_ai.md) measured at 1,109 of 1,423."""
        m = ai.motion_of(action)
        return m, self.motions().get(m, '')


# -- the ladder ------------------------------------------------------------


def rules_of(script: ai.Script):
    """Rules, with a `0x2000` rule carrying the conditions of the one above.

    `Script.rules()` splits on either flag; what it cannot know is that the
    22 instructions with `0x2000` continue the rule before them rather than
    replacing it."""
    out, carried = [], []
    for a, body in script.rules():
        first = body[0][2]
        if first & ai.RULE2:
            out.append((a, carried + body, True))
        else:
            carried = body
            out.append((a, body, False))
    return out


def holds(body, ev) -> bool:
    """A rule holds when every term does, with a `0x4000` run ORed."""
    i = 0
    while i < len(body):
        if body[i][2] & ai.OR:
            j = i
            while j < len(body) and (body[j][2] & ai.OR):
                j += 1
            if not any(ev(x) for x in body[i:j]):
                return False
            i = j
            continue
        if not ev(body[i]):
            return False
        i += 1
    return True


class Brain:
    """The table AI: pick a rule, then roll an action out of its group."""

    def __init__(self, monster: Monster, terms=None):
        self.m = monster
        self.terms = terms                  # a callable (term, param, cond)

    def group(self, state: State, prowl=False):
        """The group the first satisfied rule names, or None."""
        script = self.m.prowl if prowl else self.m.select
        if script is None:
            return None
        t = self.terms or Terms(state).play

        def ev(ins):
            a, b, op = ins
            return t(op & 0xFFF, b, not (op & ai.NOT)) is True
        for action, body, _ in rules_of(script):
            if holds(body, ev):
                return action
        return None

    def act(self, state: State, rng: random.Random = None, prowl=False):
        """(group, action, motion id, motion name)."""
        g = self.group(state, prowl)
        if g is None:
            return None, None, 0, ''
        action = self.roll(g, state, rng)
        if action is None:
            return g, None, 0, ''
        mid, name = self.m.motion_of(action)
        return g, action, mid, name

    def roll(self, group: int, state: State, rng: random.Random = None):
        """`prt_select`, in Python: normalise to 10,000 and take the roll.

        The bias away from repeating is the disc's - an action equal to
        `getLastActId()` has its weight passed through `getSelRevise` first,
        which the engine does not implement, so it passes the weight
        through."""
        items = self.m.groups.get(group)
        if not items:
            return None
        weights = [w for _, w in items]
        total = sum(weights)
        if total <= 0:
            return items[0][0]
        roll = (rng.randrange(10000) if rng else state.rand)
        correct = 10000.0 / total
        prob = 0.0
        for (act, w) in items:
            span = w * correct
            if prob <= roll < prob + span:
                return act
            prob += span
        return items[-1][0]


class ScriptBrain:
    """The same decision, out of the six `.cnut` that carry it as code."""

    def __init__(self, monster: Monster, state: State):
        if monster.cnut is None:
            raise SystemExit('%s ships no .cnut' % monster.name)
        self.m = monster
        self.state = state
        q = Psq(monster.cnut.read_bytes(), monster.cnut.name)
        self.vm = VM(printer=lambda s: None)
        self.picked = []
        for name, fn in predicates(state).items():
            self.vm.register(name, fn)
        for n in globals_called(q.root):
            if n not in self.vm.root.slots:
                self.vm.register(n, lambda *a: 0)
        self.vm.load(q.root, monster.cnut.name)
        self.groups = self._trap()

    def _trap(self):
        """Replace every `prt_N` with a recorder, so the script's answer can
        be read as a group id rather than as an action."""
        out = {}
        for name, v in list(self.vm.root.slots.items()):
            m = re.fullmatch(r'prt_(\d+)', name)
            if m and isinstance(v, Closure):
                g = int(m.group(1))
                out[g] = v

                def rec(g=g):
                    self.picked.append(g)
                    return g
                self.vm.root.slots[name] = Native(name, rec)
        return out

    def group(self):
        """Which `prt_N` the script reaches, or None."""
        self.picked = []
        th = Thread(self.vm, 'select_action')
        th.start(self.vm.find('active_script'), [])
        return self.picked[-1] if self.picked else None


# -- commands --------------------------------------------------------------


def operands(tree) -> dict:
    """Every `(term, operand)` pair the 144 decision files actually use, with
    how many instructions carry it. Comparing two evaluators on inputs the
    disc never presents would be a test of nothing."""
    out = collections.Counter()
    for name, d in sorted(index(tree).items()):
        for suffix in ai.SCRIPTS:
            p = d / (name + suffix)
            if not p.is_file():
                continue
            sc = ai.Script(p.read_bytes(), p.name)
            for a, b, op in sc.code:
                if op:
                    out[(op & 0xFFF, b)] += 1
    return out


def cmd_terms(tree, trials='50') -> int:
    """This file's term evaluator against the disc's own dispatch.

    Only on the operands the disc uses, and a raise counts as an outcome:
    Squirrel refuses to compare a bool with an integer, so a term written to
    do that is a term that would throw rather than answer."""
    rng = random.Random(20260823)
    state = State()
    vm = dispatch_vm(tree, state)
    t = Terms(state, vm)
    pairs = operands(tree)
    seen = collections.Counter()
    bad = collections.Counter()
    raised = collections.Counter()
    dead = collections.Counter()
    unknown = collections.Counter()
    fired = collections.Counter()
    for _ in range(int(trials)):
        state.randomise(rng)
        for (tid, param), n in pairs.items():
            for cond in (True, False):
                mine = t.of(tid, param, cond) if _ok(t, tid, param, cond)                     else 'raise'
                if mine is NOT_KNOWN:
                    unknown[tid] += 1
                    continue
                try:
                    theirs = t.disc(tid, param, cond)
                except SquirrelError:
                    theirs = 'raise'
                seen[tid] += 1
                if mine == 'raise' or theirs == 'raise':
                    if mine == theirs:
                        raised[(tid, param)] += 1
                        continue
                if mine != theirs:
                    bad[(tid, param)] += 1
                elif mine is True:
                    fired[tid] += 1
    for (tid, param), n in list(raised.items()):
        dead[tid] += n
    print('%d distinct (term, operand) pairs on the disc over %d terms, '
          'each tried in %s states both ways'
          % (len(pairs), len({k[0] for k in pairs}), trials))
    print('%d comparisons, %d disagreements' % (sum(seen.values()),
                                                sum(bad.values())))
    for (tid, param), n in bad.most_common(12):
        print('  term %4d operand %-5d %s: %d of %d'
              % (tid, param, ai.TERMS.get(tid, ('?',))[0], n, seen[tid]))
    if dead:
        print("%d comparisons where the disc's own dispatch raises "
              "rather than answering, on %d terms:" % (sum(dead.values()), len(dead)))
        for tid, n in dead.most_common():
            print('  term %4d %-16s %d, on operands %s'
                  % (tid, ai.TERMS.get(tid, ('?',))[0], n,
                     ' '.join(str(pp) for tt, pp in sorted(raised) if tt == tid)))
    never = sorted(tid for tid in {k[0] for k in pairs}
                   if not fired.get(tid) and tid not in dead
                   and tid not in unknown)
    if never:
        print('%d terms that never came out true in %s states: %s'
              % (len(never), trials, ' '.join(str(x) for x in never)))
    if unknown:
        print('%d terms this file does not implement, %d instructions: %s'
              % (len(unknown), sum(pairs[k] for k in pairs
                                   if k[0] in unknown),
                 ' '.join(str(u) for u in sorted(unknown))))
    return 1 if bad else 0


def _ok(t, tid, param, cond):
    """Does this file's evaluator answer without raising?"""
    try:
        t.of(tid, param, cond)
        return True
    except SquirrelError:
        return False


def cmd_agree(tree, trials='300') -> int:
    """The tables against the script, for the six monsters that ship both.

    Both are driven by the same state and the same `getRand()`, so a
    disagreement is a difference between the two artefacts and not noise.

    Two things make the comparison narrower than it looks, and both are the
    disc's doing. A script may pick a `prt_N` whose N is **not a group** in
    the same monster's `ProbList` - the three-digit ones -
    [`format_ai.md`](../docs/format_ai.md) counted 5 of 31 on the OrcKing and
    Nidhogg is mostly those - and a table may be **shared between difficulty
    variants** whose scripts are not, in which case at most one variant can
    match. So the row prints how often the script picked something the table
    could have picked at all, and the agreement is over those."""
    rng = random.Random(20260823)
    rows = []
    shared = collections.Counter()
    for name, d in sorted(index(tree).items()):
        m = Monster(tree, name)
        if m.cnut is not None:
            shared[(d / (name + '_SelectScript.dat')).read_bytes()] += 1
    for name, d in sorted(index(tree).items()):
        m = Monster(tree, name)
        if m.cnut is None:
            continue
        state = State()
        script = ScriptBrain(m, state)
        terms = Terms(state)
        engine = Brain(m, terms=terms.play)
        literal = Brain(m, terms=terms.of)
        n = inside = a1 = a2 = 0
        for _ in range(int(trials)):
            state.randomise(rng)
            want = script.group()
            n += 1
            if want not in m.groups:
                continue
            inside += 1
            a1 += (literal.group(state) == want)
            a2 += (engine.group(state) == want)
        many = shared[(d / (name + '_SelectScript.dat')).read_bytes()] > 1
        rows.append((m.name, inside, a1, a2, n, many))
    print('  %-24s %10s %10s %10s' % ('', 'comparable', 'include', 'engine'))
    for name, inside, a1, a2, n, many in rows:
        print('  %-24s %6d/%-4d %5d/%-4d %5d/%-4d%s'
              % (name, inside, n, a1, inside, a2, inside,
                 '  (table shared with a sibling)' if many else ''))
    ti = sum(r[1] for r in rows)
    t1 = sum(r[2] for r in rows)
    t2 = sum(r[3] for r in rows)
    tn = sum(r[4] for r in rows)
    print('%d of %d states have the script pick a group the table also '
          'carries' % (ti, tn))
    print("%d of those agree under the include's chance term, %d under the "
          "engine's" % (t1, t2))
    return 0


def cmd_decide(tree, name, trials='20') -> int:
    """One monster, over random states: what it decides and what it plays."""
    rng = random.Random(20260823)
    m = Monster(tree, name)
    state = State()
    brain = Brain(m)
    print('%s in %s: %d groups, %d rules, %d actions gated by _act.par'
          % (m.name, m.kind, len(m.groups),
             len(rules_of(m.select)) if m.select else 0, len(m.ranges)))
    hist = collections.Counter()
    named = 0
    for _ in range(int(trials)):
        state.randomise(rng)
        g, action, mid, mname = brain.act(state, rng)
        hist[(g, action, mid, mname)] += 1
        named += bool(mname)
    for (g, action, mid, mname), n in hist.most_common(15):
        print('  %3dx  group %-4s action %-5s motion %-4s %s'
              % (n, g, action, mid or '-', mname or '(no motion)'))
    print('%d of %s decisions name a motion in %s.pac'
          % (named, trials, m.prefix))
    return 0


def cmd_check(tree) -> int:
    """Every monster: does the ladder run, and does what it picks resolve?"""
    rng = random.Random(20260823)
    state = State()
    mons = index(tree)
    ran = decided = 0
    acts = named = 0
    fallback = 0
    per = []
    for name in sorted(mons):
        m = Monster(tree, name)
        brain = Brain(m)
        hits = 0
        got = set()
        for _ in range(40):
            state.randomise(rng)
            g, action, mid, mname = brain.act(state, rng)
            if g is not None:
                hits += 1
            if action is not None:
                acts += 1
                got.add(action)
                named += bool(mname)
        ran += 1
        decided += hits == 40
        fallback += bool(m.select and m.select.fallback)
        per.append((m.name, hits, len(got)))
    print('%d monsters, %d of them decide on every one of 40 random states'
          % (ran, decided))
    print('%d actions rolled, %d of them naming a motion in the monster\'s '
          'own pac' % (acts, named))
    print('%d of %d SelectScript end in an unconditional fallback'
          % (fallback, ran))
    for name, hits, got in per:
        if hits < 40:
            print('  %-24s decided on %d of 40' % (name, hits))
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    cmd, rest = a[0], a[1:]
    if cmd == 'terms' and rest:
        return cmd_terms(*rest)
    if cmd == 'agree' and rest:
        return cmd_agree(*rest)
    if cmd == 'decide' and len(rest) >= 2:
        return cmd_decide(*rest)
    if cmd == 'check' and rest:
        return cmd_check(*rest)
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
