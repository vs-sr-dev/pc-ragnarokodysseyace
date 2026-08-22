"""
merc.py - reader for the mercenary AI: the four `ELBN` tables in
`mercenary.cpk` and the script that indexes them.

The mercenaries are the party members the player fights beside, and they are
**the six player classes over again** - `mercenary.cpk` holds one `.pac` per
class per sex, and the six prefixes are `job.cpk`'s own: `as`, `cl`, `hs`,
`ht`, `mg`, `sw`. Each names itself through a skill motion it ships:
`cl` has `magnus_exorcismus`, `sw` has `mastersword`, `ht` has `arrow_storm`
and `sharp_shooting`, `hs` has `drill_cannon`.

**12 classes, 4 tables each, 0 unreadable**: 454 probability tables, 350
command lists, 1,549 command steps and 166 target records, every one of them
consumed to the byte.

This is a second AI system, independent of the monsters' - see
[`ai.py`](ai.py) - and it is built the other way round. The monsters keep
their rules in a table and their parameters in a script; the mercenaries keep
their rules in a **script** and their parameters in a **table**.

## The four files

Each class `.pac` holds `consider_action.cnut` and four `ELBN`, which
[`elbn.py`](elbn.py) already opens. `ELBN` names its own entries, so the
structure is declared:

    select_action.bin    prt00 .. prtNN  +  select_prt    22 to 30 tables
    select_target.bin    prt00 .. prtNN  +  select_prt    12 to 16 tables
    command_data.bin     act_cmd_00 .. act_cmd_NN  +  act_cmd_data
    target_data.bin      target_00 .. target_NN    +  target_data

`select_prt`, `act_cmd_data` and `target_data` are arrays of pointers, one per
numbered entry, and every one of those pointers is in the file's own `POF0`
relocation list.

## How a mercenary decides

`consider_action.cnut` defines three functions, suffixed with the class:

    check_active_<cls>()    -1 or 1     engage, or hold off
    select_target_<cls>()   an index into select_target.bin
    select_action_<cls>()   an index into select_action.bin

**The index is the proof.** On all 12 classes and both functions - 24
comparisons - the set of values the script returns lies inside the set of
`prt` indices the table defines, and **`max(return)` equals the last table
index exactly**: no overrun, and no unused tail.

A `prtNN` is a weighted list, `(u32 id, u32 weight)` closed by
`(0xFFFFFFFF, 0)`, and **all 454 of them are closed that way and all 454 sum
to exactly 10000** - the same per-ten-thousand convention the monsters'
`prt_select` uses. The id is an `act_cmd_NN` or a `target_NN`.

So the whole loop is

    check_active  ->  select_target  ->  prtNN  ->  target_NN
                  ->  select_action  ->  prtNN  ->  act_cmd_NN  ->  steps

## `act_cmd_NN` - a scripted input sequence

A list of **20-byte steps** closed by a step whose first word is
`0xFFFFFFFF`. All 350 are exactly that.

    0x00  u32   a command id: 0, 3, 5, 8, 9, 12, 14, 15, 16, 19, 20, 21, 22
    0x04  u32   a duration in milliseconds
    0x08  u32   flags, 12 distinct values, near-determined by the command
    0x0C  u32   zero on 1,457 of the 1,549 steps
    0x10  f32   a distance

Thirteen command ids occur and their operands separate them cleanly:

    0   345 uses, 333 of them the last step, 10 ms, distance 0 - the close
    14  444 uses, always mid-sequence, always 600 ms, always flags 0x4082000
    15  248 uses, the same shape as 14
    12  174 uses, first or mid, 3000 ms or 90/180, distance 3.5
    8   102 uses, **always the first step**, 3000 ms, distance 3.5
    5    86 uses, almost always first, 150 ms, distance 15 to 33 - long range
    3   106 uses, first or mid, 40 to 660 ms, distance 0.5 to 3.0
    9, 16, 19, 20, 21, 22 - between 2 and 18 uses each

Only `mg` uses 16, only `cl` and `mg` use 21 and 22, and only `as` uses 9.

## 14 and 15 are the two attack buttons

A run of 14s and 15s is a **string of button presses**, and `job.cpk` names
its combo motions by exactly that string: `sw311at_s`, `sw312at_ss`,
`sw343at_ssl`, `sw325at_ssssl`, `sw355at_sllll`, `sw361at_l`. Write 14 as `s`
and 15 as `l` and the tables read straight into the animation:

    (14, 14, 14, 14, 15)  ->  ssssl  ->  sw325at_ssssl
    (14, 15, 15, 15, 15)  ->  sllll  ->  sw355at_sllll
    (15,)                 ->  l      ->  sw361at_l

**168 of the 188 runs on the disc name a combo motion the same class ships**,
and no run is longer than five presses, which is the depth of the combo tree.
The 20 that do not are the Mage and the Hammersmith, whose trees are shallower
than the tables written for them - `mg` has no `at_ssssl`. `merc.py combos`
prints the check.

## `target_NN` - who to attack

28 bytes, seven `u32`, and the last three are zero on all 166. `+0x00` takes
5 values and `+0x04` eight; `+0x08` is a distance where it is not zero (15.0,
19.25, 25.0).

## What the host has to provide

`psq.py api` over `mercenary.cpk` gives the whole interface: **19 predicates
and `print`**, and every one is already in the disc-wide 289.

    getPlaneRange(n)          getNearestBossKind()      getRange(n)
    getNearestBossAction()    getTargetActId()          getRand()
    getTargetType()           getNumOfEnemy(a, b)       getHpRate(n)
    getTargetMonsterKind()    getNumOfBoss(a, b)        getHeight(n)
    getActionLastFrame(n)     isAbnormal(a, b)          isActive()
    isAvailableAceSkill(n)    getLatestFinishReason()
    getPartyMemberHpRate(n)   getNumOfUnderHpRate(a, b)

`getHpRate` is the one name the two AI systems share, and the arity differs:
the monsters call it with none and the mercenaries with one.

`getNearestBossAction()` and `getTargetActId()` return the **monster's own
action id**, and the disc says so: across the twelve scripts those two are
compared against 21 distinct values and every one is between 102 and 125,
inside the 100-to-128 block [`ai.py`](ai.py) reads as the monster's attacks.
So the two systems meet there - a mercenary holds off because the boss has
started action 108, which is its motion 509.

## What the tables share

Within a job the male and the female share their tables and, in five jobs of
six, their script as well: `swm` and `sww` decompile to the same statements
and differ by one source line number. The Cleric is the exception, and its two
scripts genuinely differ. That is the same arrangement the monsters use -
shared tables, per-variant scripts - reached independently.

57 of the 227 `prt` tables a job defines are never named by either of its
scripts, and the pattern is regular: **`prt00` and `prt04` of `select_action`
are unreachable in all six jobs**, as are `prt01`, `prt09` and `prt10` of
`select_target` in five of the six. The script never returns 0, so `prt00`
reads as the engine's own default.

## The roster

`common.pac` carries three `ECH` tables, which [`ech.py`](ech.py) opens:
`mercenary_universal_db` (13 rows x 8 - an id, four message ids and an RGBA),
`mercenary_special_db` (169 rows x 28 - four floats and eight message ids per
row) and `mercenary_common_db` (one row of 18 constants: twelve 1.0, then
700, 1.1, 1000, 15, 25, 30). `common_script.cnut` holds only
`print_root_table`.

Usage:
  python merc.py check <dir>           the arithmetic, every class
  python merc.py list <dir>            the twelve, and what they share
  python merc.py dump <dir> <cls>      one class, from prt to command step
  python merc.py commands <dir>        the command vocabulary, with operands
  python merc.py targets <dir>         the target records
  python merc.py combos <dir>          the command runs, as button presses
"""
from __future__ import annotations

import collections
import pathlib
import re
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402
from elbn import Elbn                                         # noqa: E402

TABLES = ('select_action', 'select_target', 'command_data', 'target_data')
NUMBERED = re.compile(r'^(prt|act_cmd_|target_)\d\d$')
END = 0xFFFFFFFF
STEP = 20
TARGET = 28

# The six prefixes are `job.cpk`'s own classes, and each is named by a skill
# motion its own `animcmd.pac` ships.
JOBS = {
    'as': 'Assassin', 'cl': 'Cleric', 'hs': 'Hammersmith',
    'ht': 'Hunter', 'mg': 'Mage', 'sw': 'Sword Warrior',
}

# A run of these commands is a string of button presses, and the string names
# the combo motion the class plays - `(14, 14, 14, 14, 15)` is `at_ssssl`.
PRESS = {14: 's', 15: 'l', 16: '?'}
COMBO = re.compile(r'at_([sl]+)(?:_|\.)')


class MercError(Exception):
    pass


class Merc:
    """One mercenary class: the four `ELBN` of its own `.pac`."""

    def __init__(self, files: dict, name: str = ''):
        self.name = name
        self.job = JOBS.get(name[:2], '?')
        self.sex = name[2:] if len(name) > 2 else ''
        self.tab = {k: Elbn(v, '%s/%s' % (name, k)) for k, v in files.items()}

    def _numbered(self, table: str, prefix: str) -> list:
        e = self.tab.get(table)
        if e is None:
            return []
        return [x for x in e.entries
                if x.name.startswith(prefix) and NUMBERED.match(x.name)]

    def prt(self, table: str) -> dict:
        """index -> [(id, weight), ...]; the weights are per ten thousand."""
        e, out = self.tab[table], {}
        for x in self._numbered(table, 'prt'):
            w = struct.unpack('>%dI' % (x.size // 4), e.data(x.offset, x.size))
            if len(w) < 2 or len(w) % 2 or w[-2] != END or w[-1]:
                raise MercError('%s/%s: not closed by (0xffffffff, 0)'
                                % (self.name, x.name))
            out[int(x.name[3:])] = list(zip(w[:-2:2], w[1:-2:2]))
        return out

    def commands(self) -> dict:
        """index -> [(command, milliseconds, flags, word, distance), ...]."""
        e, out = self.tab['command_data'], {}
        for x in self._numbered('command_data', 'act_cmd_'):
            b = e.data(x.offset, x.size)
            if x.size % STEP or not x.size:
                raise MercError('%s/%s: %d bytes' % (self.name, x.name,
                                                     x.size))
            if struct.unpack_from('>I', b, x.size - STEP)[0] != END:
                raise MercError('%s/%s: no terminator' % (self.name, x.name))
            rows = []
            for i in range(0, x.size - STEP, STEP):
                a, ms, fl, y = struct.unpack_from('>4I', b, i)
                d, = struct.unpack_from('>f', b, i + 16)
                rows.append((a, ms, fl, y, d))
            out[int(x.name[-2:])] = rows
        return out

    def targets(self) -> dict:
        """index -> seven words; the last three are zero on all 166."""
        e, out = self.tab['target_data'], {}
        for x in self._numbered('target_data', 'target_'):
            if x.size != TARGET:
                raise MercError('%s/%s: %d bytes' % (self.name, x.name,
                                                     x.size))
            out[int(x.name[-2:])] = struct.unpack(
                '>7I', e.data(x.offset, TARGET))
        return out

    def index(self, table: str, entry: str) -> list:
        """The pointer array that heads a table, and whether it relocates."""
        e = self.tab[table]
        x = e.by_name().get(entry)
        if x is None:
            return []
        return [(x.offset + 4 * k, e.word(x.offset + 4 * k),
                 (x.offset + 4 * k) in e.reloc)
                for k in range(x.size // 4)]


# --------------------------------------------------------------------------

def classes(root) -> dict:
    """class name -> {table: bytes}, for the twelve mercenary classes."""
    out: dict = collections.defaultdict(dict)
    root = pathlib.Path(root)

    def wanted(path):
        part = path.split('/')
        if len(part) < 2 or not part[-2].endswith('.pac'):
            return None
        cls, stem = part[-2][:-4], part[-1]
        if stem.endswith('.bin') and stem[:-4] in TABLES and cls[:2] in JOBS:
            return cls, stem[:-4]
        return None

    if any(p.is_file() for p in root.glob('*.cpk')):
        for path, blob in leaves(root, ''):
            hit = wanted(path)
            if hit:
                out[hit[0]][hit[1]] = blob
    else:
        for p in root.rglob('*.bin'):
            hit = wanted(p.relative_to(root).as_posix())
            if hit:
                out[hit[0]][hit[1]] = p.read_bytes()
    return {k: v for k, v in sorted(out.items()) if len(v) == len(TABLES)}


def combo_motions(root) -> dict:
    """class prefix -> the press strings `job.cpk` ships a motion for."""
    out: dict = collections.defaultdict(set)
    root = pathlib.Path(root)
    if any(p.is_file() for p in root.glob('*.cpk')):
        names = (path for path, _ in leaves(root, ''))
    else:
        names = (p.as_posix() for p in root.rglob('*.anmcmd'))
    for path in names:
        base = path.rsplit('/', 1)[-1]
        m = COMBO.search(base)
        if m and base[:2] in JOBS:
            out[base[:2]].add(m.group(1))
    return out


def runs(rows: list) -> list:
    """The press strings in one `act_cmd`, in order."""
    out, run = [], []
    for step in list(rows) + [(None,)]:
        if step[0] in PRESS:
            run.append(PRESS[step[0]])
        elif run:
            out.append(''.join(run))
            run = []
    return out


def _one(root, name):
    found = classes(root)
    for k in found:
        if k == name or name.lower() == k.lower():
            return Merc(found[k], k)
    raise SystemExit('not found: %s (have %s)'
                     % (name, ', '.join(sorted(found))))


def cmd_check(root) -> int:
    found = classes(root)
    bad = 0
    prt = pairs = ten = cmds = steps = tgts = ptr = reloc = 0
    for name, files in found.items():
        m = Merc(files, name)
        for table, head in (('select_action', 'select_prt'),
                            ('select_target', 'select_prt'),
                            ('command_data', 'act_cmd_data'),
                            ('target_data', 'target_data')):
            arr = m.index(table, head)
            ptr += len(arr)
            reloc += sum(1 for _, _, r in arr if r)
        try:
            for table in ('select_action', 'select_target'):
                for body in m.prt(table).values():
                    prt += 1
                    pairs += len(body)
                    ten += sum(w for _, w in body) == 10000
            c = m.commands()
            cmds += len(c)
            steps += sum(len(v) for v in c.values())
            tgts += len(m.targets())
        except MercError as e:
            bad += 1
            print('  %s' % e)
    print('%d mercenary classes, %d unreadable' % (len(found), bad))
    print('  %d prt tables, all closed by (0xffffffff, 0), %d of them summing '
          'to exactly 10000, %d (id, weight) pairs' % (prt, ten, pairs))
    print('  %d act_cmd lists, all 20-byte steps closed by 0xffffffff, %d '
          'steps' % (cmds, steps))
    print('  %d target records of %d bytes' % (tgts, TARGET))
    print('  %d index pointers, %d of them in the file own POF0'
          % (ptr, reloc))
    return 1 if bad else 0


def cmd_list(root) -> int:
    found = classes(root)
    same: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    for name, files in found.items():
        for table, blob in files.items():
            same[table][blob].append(name)
    for name, files in found.items():
        m = Merc(files, name)
        print('  %-4s %-14s %-6s %2d action prt, %2d target prt, %2d commands,'
              ' %2d targets'
              % (name, m.job, m.sex, len(m.prt('select_action')),
                 len(m.prt('select_target')), len(m.commands()),
                 len(m.targets())))
    print('%d classes' % len(found))
    for table in TABLES:
        groups = [v for v in same[table].values()]
        print('  %-14s %d distinct: %s'
              % (table, len(groups),
                 '  '.join('+'.join(g) for g in sorted(groups))))
    return 0


def cmd_dump(root, name) -> int:
    m = _one(root, name)
    print('%s   %s, %s' % (m.name, m.job, m.sex))
    cmds, tgts = m.commands(), m.targets()
    print('\nselect_action -> act_cmd')
    for i, body in sorted(m.prt('select_action').items()):
        pick = ', '.join('act_cmd_%02d @%d%%' % (a, w // 100)
                         for a, w in body)
        print('  prt%02d  %s' % (i, pick))
    print('\nselect_target -> target')
    for i, body in sorted(m.prt('select_target').items()):
        pick = ', '.join('target_%02d @%d%%' % (a, w // 100) for a, w in body)
        print('  prt%02d  %s' % (i, pick))
    print('\nact_cmd - the command steps')
    for i, rows in sorted(cmds.items()):
        print('  act_cmd_%02d' % i)
        for a, ms, fl, y, d in rows:
            print('    cmd %-3d %6d ms  %#010x  %d  %.2f' % (a, ms, fl, y, d))
    print('\ntarget')
    for i, w in sorted(tgts.items()):
        print('  target_%02d  %s' % (i, '  '.join(str(x) for x in w[:4])))
    return 0


def cmd_commands(root) -> int:
    prof: dict = collections.defaultdict(
        lambda: {'n': 0, 'ms': collections.Counter(),
                 'fl': collections.Counter(), 'd': collections.Counter(),
                 'pos': collections.Counter(),
                 'cls': collections.Counter()})
    for name, files in classes(root).items():
        m = Merc(files, name)
        for rows in m.commands().values():
            for k, (a, ms, fl, _, d) in enumerate(rows):
                p = prof[a]
                p['n'] += 1
                p['ms'][ms] += 1
                p['fl'][fl] += 1
                p['d'][d] += 1
                p['cls'][name[:2]] += 1
                p['pos']['first' if k == 0 else
                         ('last' if k == len(rows) - 1 else 'mid')] += 1
    for a in sorted(prof):
        p = prof[a]
        print('  cmd %-3d %4d uses  %s' % (a, p['n'], dict(p['pos'])))
        print('          ms %s' % p['ms'].most_common(4))
        print('          distance %s' % p['d'].most_common(4))
        print('          flags %s' % [('%#x' % k, v)
                                      for k, v in p['fl'].most_common(3)])
        print('          jobs %s' % sorted(p['cls']))
    print('%d command ids, %d steps' % (len(prof),
                                        sum(p['n'] for p in prof.values())))
    return 0


def cmd_targets(root) -> int:
    cols: dict = collections.defaultdict(collections.Counter)
    n = 0
    for name, files in classes(root).items():
        for w in Merc(files, name).targets().values():
            n += 1
            for j, v in enumerate(w):
                cols[j][v] += 1
    print('%d target records' % n)
    for j in sorted(cols):
        print('  +%02x  %s' % (j * 4, cols[j].most_common(8)))
    return 0


def cmd_combos(root) -> int:
    """Every command run, against the combo motions its class ships."""
    have = combo_motions(root)
    hit = miss = 0
    missing: collections.Counter = collections.Counter()
    for name, files in classes(root).items():
        m = Merc(files, name)
        seen: set = set()
        for rows in m.commands().values():
            for r in runs(rows):
                seen.add(r)
                if r in have.get(name[:2], ()):
                    hit += 1
                else:
                    miss += 1
                    missing[(name[:2], r)] += 1
        print('  %-4s %-14s plays %s'
              % (name, m.job, ' '.join(
                     ('%s' if r in have.get(name[:2], ()) else '%s?') % r
                     for r in sorted(seen, key=lambda x: (len(x), x)))))
    for cls in sorted(have):
        print('  %s ships at_%s' % (cls, ', at_'.join(
            sorted(have[cls], key=lambda x: (len(x), x)))))
    odd = ' '.join('%s/%s' % k for k, _ in missing.most_common(8))
    print('%d command runs name a combo motion their own class ships, %d do '
          'not: %s' % (hit, miss, odd))
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
    if cmd == 'dump':
        return cmd_dump(rest[0], rest[1])
    if cmd == 'commands':
        return cmd_commands(rest[0])
    if cmd == 'targets':
        return cmd_targets(rest[0])
    if cmd == 'combos':
        return cmd_combos(rest[0])
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
