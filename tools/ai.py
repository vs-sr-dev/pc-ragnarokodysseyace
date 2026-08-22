"""
ai.py - reader for the monster AI: `ProbList.dat` and the decision scripts.

83 monsters ship an `ai.pac`, and what is in it is the whole of their
behaviour: **a table of weighted action lists and a list of rules that picks
one**. Six of them also ship the same thing as compiled Squirrel - see
[`psq.py`](psq.py) - and that is the oracle every reading here is checked
against.

**84 `ProbList.dat`, 3,269 groups, 19,707 items; 144 decision scripts, 29,100
instructions, 6,528 rules; 0 unreadable**, and every file consumed to the byte.

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

Group ids ascend on 79 of the 84; the five that do not repeat an id rather than
descend. **2,386 of the 3,269 groups have weights summing to exactly 100** and
the rest do not, which is allowed because the selector normalises by the total
- `prt_select` in the script does exactly that, with `correct = 10000.0 /
total`.

## The oracle

`monster.cpk/b01_00` carries both `AI_B01_OrcKing_ProbList.dat` and
`AI_B01_OrcKing.cnut`, and the script's `prt_N` functions are the table's
groups:

    prt_0()  ->  prt_select(rand, 1, 8500, 4, 1500)
    group 0  ->  [(1, 85), (4, 15)]

**The script's weights are the table's multiplied by a hundred.** Of the 31
`prt_N` the OrcKing's script defines, 26 have a group in its table and **all 26
carry the same action ids in the same order**; 17 of them carry the same
weights too, and the remaining five `prt_N` are three-digit names the table
does not have.

Where the weights differ, the disc says why: `b18_00` and `b18_01` ship the
**same** `ProbList.dat` and different `.cnut`, so the table is shared between a
monster's difficulty variants and the script is not.

## `<monster>_SelectScript.dat` and `_ProwlScript.dat` - the rules

A stream of **six-byte instructions**, `u16 a, u16 b, u16 op`. The word count
divides by three on all 144 files and all 144 end with one all-zero
instruction; 136 close with a rule whose term is `0x001`, which is the
unconditional fallback.

`op`'s low twelve bits are a term and the top nibble is flags:

    0x1000   this instruction begins a rule, and `a` is the action it picks -
             the `ProbList` group id
    0x8000   the negative branch of the term: `<` where the plain form is
             `>=`, `!=` where it is `==`

A rule is a run of instructions, all of which must hold, and the first one
carries the action. The terms proven against the script:

    op     term              plain              with 0x8000
    0x03   other zako count  > b                <= b
    0x08   probability       rand <= b percent
    0x09   AI type           == b               != b
    0x0a   action timer 1    >= b seconds
    0x65   HP rate           >= b percent       < b percent
    0x66   damage count      >= b               < b
    0x68   angry             is angry           is not angry
    0x6e   last action id    == b               != b
    0x6f   action successes  > b                <= b
    0xd3   range to target   <= b/100 metres    > b/100

Ten terms cover **19,435 of the 29,100 instructions**, and 77 distinct terms
appear in all. `b` is written in hundredths for the range, which is the same
convention the stage `borderline` uses - see
[`format_stage.md`](../docs/format_stage.md).

Every one of the ten was read off `AI_B01_OrcKing`, instruction against
decompiled line. The first rule of its table is

    (8, 0, 0x1009) (0, 15, 0x000a) (0, 0, 0x0068)
    (0, 75, 0x8065) (0, 700, 0x00d3) (0, 20, 0x0008)

and the script's first branch is

    if (AIT_TYPE == 0) if (AIT_ANGRY == true) if (AIT_HP_CHK < 75)
    if (AIT_RANGE <= 7) if (ACT_TIME1 >= 15) if (getRand() <= 2000)
        return prt_8()

- term by term, in order, with 75 against 75, 7 against 700, 15 against 15 and
  2000 against 20.

**The OrcKing's first 56 rules pick the same action as the script's, in the
same order**, and the first that does not is rule 56, where the table picks
group 14 and the script `prt_140` - one of the five three-digit groups the
table does not carry. The other five monsters with both disagree from the first
rule or the third, which is the same story as their weights: the tables are
shared between difficulty variants, the scripts are not.

`0x2000` and `0x4000` also occur, on 434 instructions between them, and what
they mean is not established. Neither is the remaining two thirds of the term
table, and the way to get at it is the way these ten came: align a monster that
has both forms, rule by rule.

Usage:
  python ai.py check <dir>            the arithmetic, every file
  python ai.py list <dir>             every monster, most rules first
  python ai.py probs <dir> <name>     the weighted action tables
  python ai.py rules <dir> <name>     the decision rules, as conditions
  python ai.py ops <dir>              every term, named where it is known
"""
from __future__ import annotations

import collections
import fnmatch
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                     # noqa: E402

PROB = '_ProbList.dat'
SCRIPTS = ('_SelectScript.dat', '_ProwlScript.dat')

RULE = 0x1000                       # this instruction starts a rule
NOT = 0x8000                        # the negative branch of the term
END = 0x001                         # the op that ends a script

# Term, then how the plain and the 0x8000 forms read. `b` is the operand;
# `%` divides it by 100. Everything here was read off AI_B01_OrcKing.
TERMS = {
    0x03: ('other_zako', '> {b}', '<= {b}'),
    0x08: ('chance', 'rand <= {b}%', None),
    0x09: ('ai_type', '== {b}', '!= {b}'),
    0x0A: ('act_time1', '>= {b}s', None),
    0x65: ('hp_rate', '>= {b}%', '< {b}%'),
    0x66: ('damaged', '>= {b}', '< {b}'),
    0x68: ('angry', 'yes', 'no'),
    0x6E: ('last_act', '== {b}', '!= {b}'),
    0x6F: ('act_success', '> {b}', '<= {b}'),
    0xD3: ('range', '<= {r}', '> {r}'),
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
        return (len(self.code) >= 2 and self.code[-2][2] & RULE
                and (self.code[-2][2] & 0xFFF) == END)

    def rules(self) -> list:
        """[(action, [(a, b, op), ...]), ...] - one entry per rule."""
        out = []
        body = self.code[:-1] if self.terminated else self.code
        for a, b, op in body:
            if op & RULE:
                out.append((a, []))
            if out:
                out[-1][1].append((a, b, op))
        return out


def term(a: int, b: int, op: int) -> str:
    """One condition, in words where the term is known."""
    code, flags = op & 0xFFF, op & 0xF000
    if code in TERMS:
        name, plain, neg = TERMS[code]
        form = neg if (flags & NOT) and neg else plain
        if form is not None:
            return '%s %s' % (name, form.format(b=b, r='%.2f' % (b / 100)))
    extra = ''
    if flags & ~(RULE | NOT):
        extra = ' +%04x' % (flags & ~(RULE | NOT))
    return 'op_%03x(%d, %d)%s%s' % (code, a, b,
                                    '!' if flags & NOT else '', extra)


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
            cond = ',  '.join(term(*x) for x in body)
            print('  %3d  -> group %-4d %s' % (i, action, cond))
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
        print('  %#05x  %-14s %6d' % (op, TERMS.get(op, ('',))[0], n))
    print('%d distinct terms, %d instructions, %d of them a term this reader '
          'names' % (len(c), sum(c.values()), known))
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
    if cmd == 'find':
        return cmd_find(rest[0], rest[1])
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
