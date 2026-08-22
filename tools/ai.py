"""
ai.py - reader for the monster AI: `ProbList.dat`, the decision scripts and
the six `.par`.

83 monsters ship an `ai.pac`, and what is in it is the whole of their
behaviour: **a table of weighted action lists, a list of rules that picks one,
and the parameters the chosen action runs with**. Six of them also ship the
same thing as compiled Squirrel - see [`psq.py`](psq.py) - and that is the
oracle every reading here is checked against.

**84 `ProbList.dat`, 3,269 groups, 19,707 items; 144 decision scripts, 29,100
instructions, 6,550 rules; 438 `.par`; 0 unreadable**, and every file consumed
to the byte.

## `<monster>_ProbList.dat` - the weighted action tables

    0x00  u32   zero on all 84
    0x04  u16   group count, the last group being a terminator
    0x06  u16   item count
    0x08  u32   zero
    0x0C  u32   zero
    0x10  (u16 group id, u16 first item) per group
          (u16 action id, u8 weight, u8 zero) per item

**The file ends exactly at `0x10 + 4 * groups + 4 * items` on all 84**, with no
padding and no slack, which is the arithmetic that makes the reading a fact
rather than a guess. The index is non-decreasing on all 84, the terminator's
offset equals the item count on all 84, and the fourth byte of an item is zero
on all 19,707.

`monster.cpk/b01_00` carries both `AI_B01_OrcKing_ProbList.dat` and
`AI_B01_OrcKing.cnut`, and the script's `prt_N` functions are the table's
groups - `prt_0() -> prt_select(rand, 1, 8500, 4, 1500)` against
`group 0 -> [(1, 85), (4, 15)]`. **The script's weights are the table's
multiplied by a hundred.** Of the 31 `prt_N` the OrcKing's script defines, 26
have a group in its table and **all 26 carry the same action ids in the same
order**. 2,386 of the 3,269 groups have weights summing to exactly 100 and the
rest do not, which is allowed because `prt_select` normalises with
`correct = 10000.0 / total`.

## `<monster>_SelectScript.dat` and `_ProwlScript.dat` - the rules

A stream of **six-byte instructions**, `u16 a, u16 b, u16 op`. The word count
divides by three on all 144 files and all 144 end with one all-zero
instruction; 136 close with a rule whose term is `0x001`, the unconditional
fallback.

`op`'s low twelve bits are a term and the top nibble is flags:

    0x1000   this instruction begins a rule, and `a` is the action it picks -
             the `ProbList` group id
    0x2000   so does this one, on 22 instructions, continuing the conditions
             of the rule above it
    0x4000   this term is ORed with its neighbours, on 421 instructions
    0x8000   the negative branch of the term

**`check_converted_xml_term(term, param, cond)` in the `.cnut` is the term
table.** It is a switch on exactly these ids, byte-identical in all six
`.cnut`, and its ten already-proven entries agree with the earlier alignment;
`cond` is the `0x8000` flag, since the function ends `ret = (ret == cond)`.
66 of the 76 terms the tables use are named off it, and they cover **27,862 of
the 29,100 instructions**. `ai.py terms` prints the whole vocabulary with the
host call each dispatches to. Every distance is in hundredths of a unit, the
same convention the stage `borderline` uses.

Two entries are subtler than a comparison and both were read out of the
bytecode rather than the decompiled statement: term 3 is
`zako > 0 && zako >= param`, and term 111 is
`param == 0 ? success != 0 : success >= param`. The OrcKing's script writes
`AIT_OTHER_ZAKO < 1` and `AIT_ACT_SUCCESS > 0` exactly where the table has a
zero operand, which is what confirms both.

**`0x2000` opens a rule.** Of the 22,428 instructions without `0x1000`,
exactly the 22 that carry `0x2000` have a non-zero `a`, and every one of the 22
is a valid group id in its own monster's `ProbList`. `AI_Z07_Angel` reads
`range < 4 -> group 1`, then `+ tgt_jump -> group 4`: a rule that inherits the
one above it and adds a term.

**`0x4000` is an OR**, in runs of two and three, and the disc proves it by
contradiction - the terms in a run are mutually exclusive, so an AND reading
would make every one of those rules dead. `angle_at == 217 or angle_at == 218`
cannot both hold; neither can `range_band == 0 or range_band == 2`.

Ten terms are left, 1,094 instructions. They are not in the dispatch
because **the tables are newer than the `.cnut`**: `b19_00` ships both, and
its `SelectScript.dat` uses term 1066 while its own dispatch stops at 1063.

## An action id names a motion

A motion file names itself - `monster.cpk/pac/z11.pac/z11501at1.CNOM` is a
three-digit id and a name - and an action id is that id less a constant:

    action    0 -  99   motion = action + 200    wait_1, wait_3, wait_5, down_f
    action  100 - 199   motion = action + 401    at1, at2, at3, ...
    action  200 - 299   motion = action + 301    the same at1, at2, at3, ...

**1,109 of the 1,423 action ids a `ProbList` picks name a motion in the
monster's own pac** - 927 an `at*`, 168 a `wait*`, 14 a `down*` - and the order
is exact: 100 is `at1`, 101 is `at2`, 102 is `at3`. Of the 314 that do not, 57
are action 4, which no monster resolves and which is a behaviour rather than a
motion. `ai.py acts` prints the whole table.

## The six `.par`

Four are arrays of fixed-width records closed by a sentinel, exact on all 308;
two are single structs.

    kind      files  record  sentinel     what it is
    <name>    82     64      0x7FFFFFFF   the per-action parameter block
    _act      82     32      0x00000000   a range and a facing angle per action
    _cmb      62     16      0x00000000   chains of up to three actions
    _dfa      82      4      0xFFFFFFFF   a list of motion ids
    _coop     71     20 or 60  -          three ids, a range and a time
    _prowl    59     16        -          one struct, the same on 57 of the 59

`_act.par` is `u32 action, f32 range, u16 angle, four bytes`; the OrcKing's own
debug print calls it `ct_act`, which is what ties it to the `act_time` terms.
`<name>.par` is addressed `0x2000 + 0x10 * k`, and **on 74 of the 82 monsters
the top-level slots are one per 1xx action in the same monster's `_act.par`**.
`_dfa.par` is a plain list of motion ids: **944 of its 1,007 entries name a
motion in the monster's own pac**, 778 an `at*` and 126 a `wait_*`.

Usage:
  python ai.py check <dir>            the arithmetic, every file
  python ai.py list <dir>             every monster, most rules first
  python ai.py probs <dir> <name>     the weighted action tables
  python ai.py rules <dir> <name>     the decision rules, as conditions
  python ai.py par <dir> <name>       the six `.par` of one monster
  python ai.py acts <dir>             every action id, and the motion it names
  python ai.py terms <dir>            the term vocabulary, with its host calls
  python ai.py ops <dir>              every term, most used first
"""
from __future__ import annotations

import collections
import fnmatch
import pathlib
import re
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

PROB = '_ProbList.dat'
SCRIPTS = ('_SelectScript.dat', '_ProwlScript.dat')

# The six `.par`: a fixed-width record and, for four of them, a sentinel that
# closes the file. `coop` and `prowl` are single structs and have neither.
PARS = ('', 'act', 'cmb', 'coop', 'dfa', 'prowl')
WIDTH = {'': 64, 'act': 32, 'cmb': 16, 'dfa': 4}
SENTINEL = {'': 0x7FFFFFFF, 'act': 0, 'cmb': 0, 'dfa': 0xFFFFFFFF}

# An action id names a motion, and the motion files name themselves. The 1xx
# block is the monster's own attacks and the 0xx block its idles.
MOTION = ((100, 200, 401), (200, 300, 301), (0, 100, 200))

RULE = 0x1000                       # this instruction starts a rule
RULE2 = 0x2000                      # so does this one, on 22 instructions
OR = 0x4000                         # this term is ORed with its neighbours
NOT = 0x8000                        # the negative branch of the term
END = 0x001                         # the op that ends a script
STARTS = RULE | RULE2               # either flag opens a rule

# The vocabulary, read out of `check_converted_xml_term` - the dispatch the
# six `.cnut` carry, which switches on exactly these ids. Each entry is the
# name this reader prints, the plain and the `0x8000` forms, and the host
# call the dispatch makes. `{b}` is the operand and `{r}` is the operand in
# hundredths, which is how every distance is written.
TERMS = {
    0x001: ('always', '', 'never', 'true'),
    0x002: ('total_time', '<= {b}s', '> {b}s', 'getTotalTime'),
    0x003: ('other_zako', '>= {b}', '< {b}', 'getOtherZakoCount'),
    0x004: ('other_boss', '> 0', '== 0', 'getOtherBossCount'),
    0x007: ('players', '>= {b}', '< {b}', 'getPlayerCount'),
    0x008: ('chance', 'rand < {b}%', None, 'getRand'),
    0x009: ('ai_type', '== {b}', '!= {b}', 'getAIType'),
    0x00A: ('act_time1', '>= {b}s', '< {b}s', 'getTimeFromID(10)'),
    0x00B: ('act_time2', '>= {b}s', '< {b}s', 'getTimeFromID(11)'),
    0x00C: ('act_time3', '>= {b}s', '< {b}s', 'getTimeFromID(12)'),
    0x00D: ('act_time4', '>= {b}s', '< {b}s', 'getTimeFromID(13)'),
    0x00E: ('act_time5', '>= {b}s', '< {b}s', 'getTimeFromID(14)'),
    0x00F: ('act_time6', '>= {b}s', '< {b}s', 'getTimeFromID(15)'),
    0x010: ('act_time7', '>= {b}s', '< {b}s', 'getTimeFromID(16)'),
    0x011: ('act_time8', '>= {b}s', '< {b}s', 'getTimeFromID(17)'),
    0x012: ('boss_time', '<= {b}s', '> {b}s', 'getBossTime'),
    0x013: ('no_zako', 'yes', 'no', 'getOtherZakoCount == 0'),
    0x014: ('boss_target', '== {b}', '!= {b}', 'isBossToTarget'),
    0x015: ('same_kind', '>= {b}', '< {b}', 'getActiveSameKindCount'),
    0x065: ('hp_rate', '>= {b}%', '< {b}%', 'getHpRate'),
    0x066: ('damaged', '>= {b}', '< {b}', 'getDamagedCount'),
    0x067: ('downed', '<= {b}', 'no', 'isDowned'),
    0x068: ('angry', 'yes', 'no', 'isAngry'),
    0x069: ('poison', 'yes', 'no', 'isPoison'),
    0x06A: ('cure_poison', '<= {b}', 'no', 'isRecoverPoison'),
    0x06B: ('cure_paralysis', '<= {b}', 'no', 'isRecoverParalyz'),
    0x06C: ('cure_faint', '<= {b}', 'no', 'isRecoverFaint'),
    0x06D: ('part_broken', '{b}', 'not {b}', 'isDestroyedParts'),
    0x06E: ('last_act', '== {b}', '!= {b}', 'getLastActId'),
    0x06F: ('act_success', '>= {b}', '< {b}', 'getActSuccessCount'),
    0x070: ('angry_req', 'yes', 'no', 'isAngryReq'),
    0x071: ('stagger', '>= {b}', '< {b}', 'getStaggerCount'),
    0x072: ('react', 'yes', 'no', 'isReact'),
    0x073: ('part_damage', '{b}', 'not {b}', 'getPartsDamageCount'),
    0x074: ('to_active', 'yes', 'no', 'isToActive'),
    0x075: ('failed_rot', 'yes', 'no', 'isFailedRotation'),
    0x076: ('failed_act', '>= {b}', '< {b}', 'getFailedActCount'),
    0x077: ('act_time119', '>= {b}s', '< {b}s', 'getTimeFromID(119)'),
    0x0C9: ('tgt_hp_rate', '>= {b}%', '< {b}%', 'getTargetHpRate'),
    0x0CA: ('tgt_job', '== {b}', '!= {b}', 'getTargetJob'),
    0x0CB: ('tgt_ground', 'yes', 'no', 'isTargetGround'),
    0x0CC: ('tgt_attack', 'yes', 'no', 'isTargetAttack'),
    0x0CD: ('tgt_guard', 'yes', 'no', 'isTargetGuard'),
    0x0CE: ('tgt_sway', 'yes', 'no', 'isTargetSway'),
    0x0CF: ('tgt_jump', 'yes', 'no', 'isTargetJump'),
    0x0D0: ('range_band', '== 0', '!= 0', 'checkRangeParam'),
    0x0D1: ('range_band', '== 2', '!= 2', 'checkRangeParam'),
    0x0D2: ('range_band', '== 1', '!= 1', 'checkRangeParam'),
    0x0D3: ('range', '< {r}', '>= {r}', 'getTargetRange'),
    0x0D4: ('dmg_from_tgt', '>= {b}', '< {b}', 'getDamageFromTarget'),
    0x0D5: ('angle_to', '== 213', '!= 213', 'getAngleTypeToTarget'),
    0x0D6: ('angle_to', '== 214', '!= 214', 'getAngleTypeToTarget'),
    0x0D7: ('angle_at', '== 215', '!= 215', 'getAngleTypeAtTarget'),
    0x0D8: ('angle_at', '== 216', '!= 216', 'getAngleTypeAtTarget'),
    0x0D9: ('angle_at', '== 217', '!= 217', 'getAngleTypeAtTarget'),
    0x0DA: ('angle_at', '== 218', '!= 218', 'getAngleTypeAtTarget'),
    0x0DB: ('lock_range', '< {r}', '>= {r}', 'getLockTargetRange'),
    0x0DC: ('tgt_pos_y', '>= {r}', '< {r}', 'getTargetPosy'),
    0x0DD: ('tgt_area', '== {b}', '!= {b}', 'getTargetArea'),
    0x0DE: ('tgt_object', 'yes', 'no', 'isTargetObject'),
    0x0DF: ('tgt_damage', 'yes', 'no', 'isTargetDamage'),
    0x0E0: ('tgt_down', 'yes', 'no', 'isTargetDown'),
    0x0E1: ('range_scaled', '< {r} x scale', '>= {r} x scale',
            'getTargetRange / getScale'),
    0x3E9: ('b15_term', '1001({b})', 'not 1001({b})', 'checkB15Term'),
    0x3EA: ('b15_term', '1002({b})', 'not 1002({b})', 'checkB15Term'),
    0x3EB: ('b15_term', '1003({b})', 'not 1003({b})', 'checkB15Term'),
    0x3EC: ('b15_term', '1004({b})', 'not 1004({b})', 'checkB15Term'),
    0x3ED: ('b15_term', '1005({b})', 'not 1005({b})', 'checkB15Term'),
    0x3F3: ('b09_term', '1011({b})', 'not 1011({b})', 'checkB09Term'),
    0x3FD: ('b11_term', '1021({b})', 'not 1021({b})', 'checkB11Term'),
    0x3FE: ('b11_term', '1022({b})', 'not 1022({b})', 'checkB11Term'),
    0x3FF: ('b11_term', '1023({b})', 'not 1023({b})', 'checkB11Term'),
    0x41B: ('b05_term', '1051({b})', 'not 1051({b})', 'checkB05Term'),
    0x425: ('b01_term', '1061({b})', 'not 1061({b})', 'checkB01Term'),
    0x426: ('b18_tire', 'yes', 'no', 'checkB18Term(1062)'),
    0x427: ('b19_term', '1063({b})', 'not 1063({b})', 'checkB19Term'),
    0x42A: ('b19_head', 'yes', 'no', 'checkB19Term(1066)'),
}

# The ten the dispatch does not carry, with what their operands look like.
# The tables are newer than the `.cnut`: `b19_00` ships both, and its
# `SelectScript.dat` uses 0x42a while its own `.cnut` dispatch stops at 1063.
UNNAMED = {
    0x0E2: 'a distance in hundredths, 0.15 to 4.50',
    0x0E3: 'an action id, 100 to 110',
    0x0E4: 'a count, 1 to 3',
    0x0E5: 'a distance in hundredths, 5.00 to 15.00',
    0x0E6: 'a count, 2 to 6',
    0x0E9: 'a distance in hundredths, 0.01 to 15.00',
    0x0F0: 'always 180 - an angle in degrees',
    0x0FA: '99 or 50 - a percentage',
    0x0FB: 'always 30',
    0x0FC: 'always 0',
}


class AiError(Exception):
    pass


class ProbList:
    """The weighted action tables: a group id, then (action, weight) pairs."""

    def __init__(self, blob: bytes, label: str = ''):
        self.label = label
        if len(blob) < 0x10:
            raise AiError('%s: %d bytes' % (label, len(blob)))
        self.head = struct.unpack_from('>I', blob, 0)[0]
        self.ngroup, self.nitem = struct.unpack_from('>2H', blob, 4)
        base = 0x10 + 4 * self.ngroup
        self.end = base + 4 * self.nitem
        if self.end > len(blob):
            raise AiError('%s: %d groups and %d items in %d bytes'
                          % (label, self.ngroup, self.nitem, len(blob)))
        self.size = len(blob)
        self.index = [struct.unpack_from('>2H', blob, 0x10 + 4 * k)
                      for k in range(self.ngroup)]
        self.item = [struct.unpack_from('>H2B', blob, base + 4 * k)
                     for k in range(self.nitem)]

    def groups(self) -> dict:
        out = {}
        for k in range(self.ngroup - 1):
            gid, start = self.index[k]
            out[gid] = [(a, w) for a, w, _ in
                        self.item[start:self.index[k + 1][1]]]
        return out


class Script:
    """The decision rules: six-byte instructions, `u16 a, u16 b, u16 op`."""

    def __init__(self, blob: bytes, label: str = ''):
        self.label = label
        self.size = len(blob)
        if len(blob) % 2:
            raise AiError('%s: %d bytes' % (label, len(blob)))
        w = struct.unpack('>%dH' % (len(blob) // 2), blob)
        if len(w) % 3:
            raise AiError('%s: %d words' % (label, len(w)))
        self.code = [w[i:i + 3] for i in range(0, len(w), 3)]

    @property
    def terminated(self) -> bool:
        """Every file ends with one all-zero instruction."""
        return bool(self.code) and self.code[-1] == (0, 0, 0)

    @property
    def fallback(self) -> bool:
        """136 of the 144 close with a rule whose term is 0x001."""
        return (len(self.code) >= 2 and self.code[-2][2] & STARTS
                and (self.code[-2][2] & 0xFFF) == END)

    def rules(self) -> list:
        """[(action, [(a, b, op), ...]), ...] - one entry per rule."""
        out = []
        body = self.code[:-1] if self.terminated else self.code
        for a, b, op in body:
            if op & STARTS:
                out.append((a, []))
            if out:
                out[-1][1].append((a, b, op))
        return out


class Par:
    """One `.par`: fixed-width records, the last of them a sentinel.

    `<name>.par` is the per-action parameter block, one 64-byte slot per 1xx
    action, addressed `0x2000 + 0x10 * k`; `_act.par` gives every action a
    range and a facing angle; `_cmb.par` chains up to three actions; and
    `_dfa.par` is a plain list of motion ids. `_coop.par` and `_prowl.par`
    are single structs, 20 and 16 bytes.
    """

    def __init__(self, blob: bytes, kind: str, label: str = ''):
        self.label, self.kind, self.blob = label, kind, blob
        self.size = len(blob)
        w = WIDTH.get(kind)
        if w is None:                       # coop and prowl: one struct
            self.rec = []
            self.exact = True
            return
        if (len(blob) - 4) % w:
            raise AiError('%s: %d bytes is not 4 + %d*n'
                          % (label, len(blob), w))
        self.rec = [blob[i:i + w] for i in range(0, len(blob) - 4, w)]
        self.exact = (struct.unpack_from('>I', blob, len(blob) - 4)[0]
                      == SENTINEL[kind])

    def rows(self) -> list:
        """One tuple per record, in the shape that kind of file uses."""
        out = []
        for r in self.rec:
            if self.kind == '':
                pid, a, v, lo = struct.unpack_from('>4I', r, 0)
                out.append((pid, a >> 24, (a >> 8) & 0xFFFF, v, lo))
            elif self.kind == 'act':
                aid, = struct.unpack_from('>I', r, 0)
                rng, = struct.unpack_from('>f', r, 4)
                ang, p0, p1, p2, p3 = struct.unpack_from('>H4B', r, 8)
                out.append((aid, rng, ang * 360.0 / 65536.0, p0, p1, p2, p3))
            elif self.kind == 'cmb':
                out.append(struct.unpack_from('>3I', r, 0)
                           + struct.unpack_from('>2H', r, 12))
            elif self.kind == 'dfa':
                out.append(struct.unpack_from('>HBB', r, 0))
        return out

    def coop(self) -> tuple:
        """(three action ids, three pairs, a distance, a time in ms)."""
        b = self.blob
        ids = struct.unpack_from('>3H', b, 0)
        flag = struct.unpack_from('>6B', b, 6)
        dist, = struct.unpack_from('>f', b, 12)
        time, = struct.unpack_from('>I', b, 16)
        return ids, flag, dist, time


# Two terms the dispatch writes as `x > 0 && x >= param`, so a zero operand
# means `> 0` and not `>= 0`. Both readings agree with the OrcKing's script,
# which writes `AIT_OTHER_ZAKO < 1` where the table has 0 under 0x8000.
ZERO = {
    0x003: ('> 0', '== 0'),
    0x06F: ('> 0', '== 0'),
}


def term(a: int, b: int, op: int) -> str:
    """One condition, in words."""
    code, flags = op & 0xFFF, op & 0xF000
    if code in TERMS:
        name, plain, neg, _ = TERMS[code]
        if b == 0 and code in ZERO:
            plain, neg = ZERO[code]
        form = neg if (flags & NOT) and neg is not None else plain
        if form is not None:
            return ('%s %s' % (name, form.format(b=b, r='%.2f' % (b / 100)))
                    ).rstrip()
    return 'op_%03x(%d, %d)%s' % (code, a, b, '!' if flags & NOT else '')


def conditions(body: list) -> str:
    """A rule's terms, with the 0x4000 runs joined by `or`."""
    out: list = []
    for a, b, op in body:
        text = term(a, b, op)
        if op & OR and out and out[-1][0]:
            out[-1] = (True, out[-1][1] + ' or ' + text)
        else:
            out.append((bool(op & OR), text))
    return ',  '.join(t for _, t in out)


# --------------------------------------------------------------------------

def collect(root, suffix: str):
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*' + suffix)):
            yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, ''):
        if path.endswith(suffix):
            yield path, blob


def monsters(root) -> dict:
    """basename without its suffix -> {suffix: bytes}."""
    out: dict = collections.defaultdict(dict)
    for suffix in (PROB,) + SCRIPTS:
        for path, blob in collect(root, suffix):
            out[path.rsplit('/', 1)[-1][:-len(suffix)]][suffix] = blob
    return out


def pars(root) -> dict:
    """basename without its suffix -> {kind: bytes}, for the six `.par`."""
    out: dict = collections.defaultdict(dict)
    for path, blob in collect(root, '.par'):
        stem = path.rsplit('/', 1)[-1][:-4]
        if '/ai.pac/' not in path and not path.startswith('ai.pac/'):
            continue
        kind = stem.rsplit('_', 1)[-1]
        if kind in PARS and kind:
            out[stem[:-len(kind) - 1]][kind] = blob
        else:
            out[stem][''] = blob
    return out


def motions(root) -> dict:
    """class prefix -> {motion id: the name the .CNOM gives itself}."""
    out: dict = collections.defaultdict(dict)
    root = pathlib.Path(root)
    if any(p.is_file() for p in root.glob('*.cpk')):
        names = (path for path, _ in leaves(root, ''))
    else:
        names = (p.as_posix() for p in root.rglob('*.CNOM'))
    for path in names:
        part = path.rsplit('/', 1)
        m = re.match(r'([a-z]\d\d)(\d{3})(.*)\.CNOM$', part[-1])
        if not m:
            continue
        # Three of the giants ship one another's motions - `z18.pac` holds
        # `z19*.CNOM` - so the directory names the monster and the file the
        # skeleton the motions were authored on. Index under both.
        keys = {m.group(1)}
        if len(part) > 1:
            d = re.search(r'([a-z]\d\d)\.pac(?:/[^/]+)?$', part[0])
            if d:
                keys.add(d.group(1))
        for k in keys:
            out[k].setdefault(int(m.group(2)), m.group(3))
    return out


def motion_of(action: int) -> int:
    """The motion id an action id names, or 0."""
    for lo, hi, off in MOTION:
        if lo <= action < hi:
            return action + off
    return 0


def _one(root, name):
    found = monsters(root)
    for key in found:
        if key == name or name.lower() in key.lower():
            return key, found[key]
    raise SystemExit('not found: ' + name)


def cmd_check(root) -> int:
    files = bad = groups = items = exact = rising = last = 0
    tail = insns = rules = div = scripts = sums = fall = 0
    for path, blob in collect(root, PROB):
        files += 1
        try:
            p = ProbList(blob, path)
        except AiError as e:
            bad += 1
            print('  %s' % e)
            continue
        groups += p.ngroup - 1
        items += p.nitem
        exact += p.end == p.size
        ids = [g for g, _ in p.index[:-1]]
        rising += all(ids[k] < ids[k + 1] for k in range(len(ids) - 1))
        last += p.index[-1][1] == p.nitem if p.ngroup else 0
        for g in p.groups().values():
            sums += sum(w for _, w in g) == 100
    print('%d ProbList, %d groups, %d items, %d unreadable'
          % (files, groups, items, bad))
    print('  %d end exactly at 0x10 + 4*groups + 4*items; %d have ascending '
          'group ids; %d have the terminator at the item count'
          % (exact, rising, last))
    print('  %d of %d groups have weights summing to 100' % (sums, groups))
    for suffix in SCRIPTS:
        for path, blob in collect(root, suffix):
            scripts += 1
            try:
                s = Script(blob, path)
            except AiError as e:
                bad += 1
                print('  %s' % e)
                continue
            div += 1
            tail += s.terminated
            fall += s.fallback
            insns += len(s.code)
            rules += len(s.rules())
    print('%d decision scripts, %d instructions, %d rules' % (scripts, insns,
                                                              rules))
    print('  %d divide into three-word instructions, %d end with an all-zero '
          'instruction, %d closing with a term 0x001 rule'
          % (div, tail, fall))
    kinds: collections.Counter = collections.Counter()
    exact: collections.Counter = collections.Counter()
    recs: collections.Counter = collections.Counter()
    for name, files in pars(root).items():
        for kind, blob in files.items():
            kinds[kind] += 1
            try:
                p = Par(blob, kind, name)
            except AiError as e:
                bad += 1
                print('  %s' % e)
                continue
            exact[kind] += p.exact
            recs[kind] += len(p.rec)
    print('%d .par' % sum(kinds.values()))
    for kind in PARS:
        if not kinds[kind]:
            continue
        label = '_' + kind if kind else 'main'
        if kind in WIDTH:
            print('  %-6s %3d files, %5d records of %2d bytes, %d closing on '
                  'the sentinel' % (label, kinds[kind], recs[kind],
                                    WIDTH[kind], exact[kind]))
        else:
            print('  %-6s %3d files, one struct each' % (label, kinds[kind]))
    return 1 if bad else 0


def cmd_list(root) -> int:
    rows = []
    for name, files in monsters(root).items():
        n = g = 0
        for suffix in SCRIPTS:
            if suffix in files:
                n += len(Script(files[suffix], name).rules())
        if PROB in files:
            g = ProbList(files[PROB], name).ngroup - 1
        rows.append((n, g, name))
    rows.sort(reverse=True)
    for n, g, name in rows:
        print('  %4d rules %4d action groups  %s' % (n, g, name))
    print('%d monsters' % len(rows))
    return 0


def cmd_probs(root, name) -> int:
    key, files = _one(root, name)
    if PROB not in files:
        raise SystemExit('%s has no %s' % (key, PROB))
    p = ProbList(files[PROB], key)
    print('%s   %d groups, %d items' % (key, p.ngroup - 1, p.nitem))
    for gid, g in sorted(p.groups().items()):
        total = sum(w for _, w in g)
        body = ', '.join('%d@%d' % (a, w) for a, w in g)
        print('  group %-4d total %4d  %s' % (gid, total, body))
    return 0


def cmd_rules(root, name) -> int:
    key, files = _one(root, name)
    for suffix in SCRIPTS:
        if suffix not in files:
            continue
        s = Script(files[suffix], key)
        rs = s.rules()
        print('%s%s   %d instructions, %d rules%s'
              % (key, suffix, len(s.code), len(rs),
                 '' if s.terminated else ', no terminator'))
        for i, (action, body) in enumerate(rs):
            cond = conditions(body)
            mark = '+' if body and body[0][2] & RULE2 else ' '
            print('  %3d %s-> group %-4d %s' % (i, mark, action, cond))
        print()
    return 0


def cmd_ops(root) -> int:
    c: collections.Counter = collections.Counter()
    for suffix in SCRIPTS:
        for path, blob in collect(root, suffix):
            for _, _, op in Script(blob, path).code:
                c[op & 0xFFF] += 1
    known = sum(v for k, v in c.items() if k in TERMS)
    for op, n in c.most_common():
        row = TERMS.get(op)
        print('  %#05x  %-14s %6d  %s'
              % (op, row[0] if row else '', n,
                 row[3] if row else UNNAMED.get(op, '')))
    print('%d distinct terms, %d instructions, %d of them a term this reader '
          'names' % (len(c), sum(c.values()), known))
    return 0


def cmd_terms(root) -> int:
    """The vocabulary, in id order, with the host call each dispatches to."""
    c: collections.Counter = collections.Counter()
    for suffix in SCRIPTS:
        for path, blob in collect(root, suffix):
            for _, _, op in Script(blob, path).code:
                c[op & 0xFFF] += 1
    for op in sorted(set(TERMS) | set(UNNAMED) | set(c)):
        row = TERMS.get(op)
        print('  %#05x %4d  %6d  %-14s %-15s %s'
              % (op, op, c.get(op, 0), row[0] if row else '',
                 row[1] if row else '', row[3] if row
                 else UNNAMED.get(op, '')))
    print('%d terms named off the dispatch, %d more the tables use that it '
          'does not carry, %d named but unused on the disc'
          % (len(TERMS), len([k for k in c if k not in TERMS and k]),
             len([k for k in TERMS if k not in c])))
    return 0


def cmd_par(root, name) -> int:
    """The six `.par` of one monster."""
    found = pars(root)
    key = None
    for k in found:
        if k == name or name.lower() in k.lower():
            key = k
            break
    if key is None:
        raise SystemExit('not found: ' + name)
    mot = motions(root)
    cls = re.search(r'AI_([A-Za-z]\d\d)_', key + '_')
    named = mot.get(cls.group(1).lower(), {}) if cls else {}
    for kind in PARS:
        if kind not in found[key]:
            continue
        p = Par(found[key][kind], kind, key)
        title = '%s%s.par' % (key, '_' + kind if kind else '')
        if kind in ('coop', 'prowl'):
            if kind == 'coop':
                ids, flag, dist, time = p.coop()
                print('%s   actions %s, flags %s, %.2f, %d ms'
                      % (title, ids, flag, dist, time))
            else:
                print('%s   %s' % (title, list(p.blob)))
            continue
        print('%s   %d records%s'
              % (title, len(p.rec), '' if p.exact else ', no sentinel'))
        for row in p.rows():
            if kind == '':
                print('    %04x  kind %-3d %-6d value %-8d %#010x'
                      % (row[0], row[1], row[2], row[3], row[4]))
            elif kind == 'act':
                m = motion_of(row[0])
                print('    act %-4d range %-8.2f angle %-7.2f %3d %3d %3d %3d'
                      '   -> %s'
                      % (row[0], row[1], row[2], row[3], row[4], row[5],
                         row[6], named.get(m, m or '-')))
            elif kind == 'cmb':
                chain = ' -> '.join(str(x) for x in row[:3] if x)
                print('    %-20s %d %d' % (chain, row[3], row[4]))
            elif kind == 'dfa':
                print('    motion %-5d %s   %s'
                      % (row[0], row[1], named.get(row[0], '-')))
        print()
    return 0


def cmd_acts(root) -> int:
    """Every action id a table picks, and the motion it names."""
    mot = motions(root)
    hit = miss = 0
    seen: collections.Counter = collections.Counter()
    for name, files in sorted(monsters(root).items()):
        if PROB not in files:
            continue
        cls = re.search(r'AI_([A-Za-z]\d\d)_', name + '_')
        named = mot.get(cls.group(1).lower(), {}) if cls else {}
        acts: set = set()
        for g in ProbList(files[PROB], name).groups().values():
            acts.update(a for a, _ in g)
        row = []
        for a in sorted(acts):
            m = motion_of(a)
            if m in named:
                hit += 1
                seen[re.sub(r'[0-9_].*$', '', named[m])] += 1
                row.append('%d=%s' % (a, named[m]))
            else:
                miss += 1
                row.append('%d=?' % a)
        print('  %-28s %s' % (name, ' '.join(row)))
    print('%d action ids name a motion in the monster own pac, %d do not; '
          'they are %s' % (hit, miss, seen.most_common(6)))
    return 0


def cmd_find(root, pattern) -> int:
    n = 0
    for name in sorted(monsters(root)):
        if fnmatch.fnmatch(name, pattern):
            n += 1
            print('  ' + name)
    print('%d match' % n)
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'list':
        return cmd_list(rest[0])
    if cmd == 'probs':
        return cmd_probs(rest[0], rest[1])
    if cmd == 'rules':
        return cmd_rules(rest[0], rest[1])
    if cmd == 'ops':
        return cmd_ops(rest[0])
    if cmd == 'terms':
        return cmd_terms(rest[0])
    if cmd == 'par':
        return cmd_par(rest[0], rest[1])
    if cmd == 'acts':
        return cmd_acts(rest[0])
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
