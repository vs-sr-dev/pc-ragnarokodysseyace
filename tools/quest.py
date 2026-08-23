"""
quest.py - the four tables a quest `.pac` ships, and how they join.

A quest is a spawn system, and it is spread over four [`ECH`](format_ech.md)
tables in `quest.cpk/q<NNNNN>.pac`. None of them was described; the container
was read in session 6 and the columns were left to a type inference that reads
a four-byte lane as one `u32`, which is wrong here in two different ways.

    piecelist.bin   the stages this quest visits, one string per row
    enemy.bin       one row per stage, eight slots, each a monster id
    enemy_gen.bin   one row per spawner
    piecelock.bin   one row per arena lock

**The monster id is twelve bits, not sixteen and not thirty-two.** A filled
`enemy.bin` slot is `01 hh h0 00`: a byte 1, a 12-bit id, and a zero byte, and
the low nibble of the third byte is 0 on all 2,503 filled slots. Read that way
the id is `1000 + 10*N + M` for `monster.cpk/zNN_MM` and `2000 + ...` for
`bNN_MM`, and **2,503 of 2,503 slots name a directory that exists, 83 ids and
83 directories, neither with anything left over**. It is the same numbering
the scripts use: `getLatestKilled() == 2000 + 10 * (37 - (28 - 1))` is `b10_00`,
so the AI's monster *kind* k is `b(k - 27)`.

## How the four join

    piecelist.bin  -> a stage, and the `.psq` of that name in the same pac
    enemy.bin      -> that stage's eight monster slots
    enemy_gen.bin  -> a spawner: the stage, an `emgen_pos` marker of that
                      stage, the `emgen` name the scripts call it by, which
                      of the eight slots it spawns, and up to two callbacks
    piecelock.bin  -> a lock: the stage, the `pl_` name `cfStartPieceLock`
                      asks for, the `lockarea` and `lock_line` fences it
                      raises, the `pl_q` hit area that trips it, and the
                      `emgen` names it covers

Every one of those arrows is checked by `xref`, and the numbers are in
[`format_quest.md`](../docs/format_quest.md).

Usage:
  python quest.py check <dir>          every table parses, with counts
  python quest.py list <dir>           every quest, largest first
  python quest.py dump <dir> <quest>   the four tables of one quest
  python quest.py xref <dir>           do the columns name what they must?
  python quest.py enemies <dir>        every monster id, and where it is used
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ech import Ech                                            # noqa: E402

TABLES = ('piecelist.bin', 'enemy.bin', 'enemy_gen.bin', 'piecelock.bin')
SLOTS = range(3, 11)                       # enemy.bin's eight monster lanes
NONE = 0xFFFFFFFF


def monster_id(lane: bytes):
    """A filled `enemy.bin` slot is `01 hh h0 00` - a 12-bit id."""
    if lane == b'\xff\xff\xff\xff':
        return None
    return (lane[1] << 4) | (lane[2] >> 4)


def monsters(root) -> dict:
    """`monster.cpk/zNN_MM` is id 1000 + 10*NN + MM, and `bNN_MM` is 2000."""
    out = {}
    for p in (pathlib.Path(root) / 'monster.cpk').iterdir():
        m = re.fullmatch(r'([zb])(\d\d)_(\d\d)', p.name)
        if m and p.is_dir():
            out[(1000 if m.group(1) == 'z' else 2000)
                + 10 * int(m.group(2)) + int(m.group(3))] = p.name
    return out


class Table:
    """One `ECH` with its pool, and its rows as words and as bytes."""

    def __init__(self, blob: bytes, label: str = ''):
        self.ech = Ech(blob, label)
        self.rows = [self.ech.row(i) for i in range(self.ech.rows)]

    def text(self, off: int):
        pool = self.ech.pool
        if off >= len(pool):
            return None
        end = pool.find(b'\0', off)
        return pool[off:end if end >= 0 else len(pool)].decode('ascii',
                                                              'replace')

    def word(self, row: int, col: int) -> int:
        return int.from_bytes(self.rows[row][col * 4:col * 4 + 4], 'big')

    def string(self, row: int, col: int):
        return self.text(self.word(row, col))


class Quest:
    """One `q<NNNNN>.pac`, as far as the four tables describe it."""

    def __init__(self, name: str, files: dict):
        self.name = name
        self.files = files
        for t in TABLES:
            setattr(self, t.split('.')[0],
                    Table(files[t], f'{name}/{t}') if t in files else None)

    @property
    def stages(self) -> list:
        t = self.piecelist
        return [t.string(i, 0) for i in range(len(t.rows))] if t else []

    def slots(self) -> dict:
        """stage -> the eight monster ids of its `enemy.bin` row, None where
        the lane is empty. The lane number is what a generator indexes."""
        out = {}
        t = self.enemy
        for i in range(len(t.rows) if t else 0):
            out[t.string(i, 0)] = [monster_id(t.rows[i][c * 4:c * 4 + 4])
                                   for c in SLOTS]
        return out

    def generators(self) -> list:
        """A spawner. The stage is written once and inherited down the block,
        which is how the table is laid out."""
        out, stage = [], None
        t = self.enemy_gen
        for i in range(len(t.rows) if t else 0):
            stage = t.string(i, 0) or stage
            out.append(dict(stage=stage, marker=t.string(i, 1),
                            name=t.string(i, 2), slot=t.rows[i][16],
                            on_kill=t.string(i, 14), on_end=t.string(i, 13)))
        return out

    def locks(self) -> list:
        out = []
        t = self.piecelock
        for i in range(len(t.rows) if t else 0):
            name = t.string(i, 1)
            if not name:
                continue                    # 281 rows of 842 are placeholders
            out.append(dict(stage=t.string(i, 0), name=name,
                            id=t.word(i, 2) >> 16,
                            area=t.string(i, 3),
                            lines=[x for x in (t.string(i, 4) or '').split('\n')
                                   if x],
                            trigger=t.string(i, 6),
                            gens=[x for x in (t.string(i, 7) or '').split('\n')
                                  if x],
                            gens2=[x for x in (t.string(i, 9) or '').split('\n')
                                   if x]))
        return out


def collect(root, want: str = ''):
    import psq                                                # noqa: PLC0415
    found = collections.defaultdict(dict)
    for path, blob in psq.walk(root):
        m = re.search(r'quest\.cpk/(q\d+)\.pac/([^/]+)$', path)
        if m and m.group(2) in TABLES and (not want or want in m.group(1)):
            found[m.group(1)][m.group(2)] = blob
    for name in sorted(found):
        yield Quest(name, found[name])


# -- the commands ----------------------------------------------------------

def cmd_check(root) -> int:
    n = collections.Counter()
    for q in collect(root):
        n['quests'] += 1
        n['stages'] += len(q.stages)
        n['generators'] += len(q.generators())
        n['locks'] += len(q.locks())
        for ids in q.slots().values():
            n['slots'] += sum(x is not None for x in ids)
    known = monsters(root)
    print('%d quests, %d stages, %d enemy slots, %d generators, %d locks'
          % (n['quests'], n['stages'], n['slots'], n['generators'],
             n['locks']))
    print('%d monster directories carry an id' % len(known))
    return 0


def cmd_list(root) -> int:
    rows = [(len(q.generators()), len(q.locks()), len(q.stages), q.name)
            for q in collect(root)]
    for g, k, s, name in sorted(rows, reverse=True):
        print('  %-8s %3d stages %4d generators %3d locks' % (name, s, g, k))
    print('%d quests' % len(rows))
    return 0


def cmd_dump(root, want) -> int:
    known = monsters(root)
    for q in collect(root, want):
        print('%s   %s' % (q.name, ' '.join(q.stages)))
        for stage, ids in q.slots().items():
            print('  %s  %s' % (stage, '  '.join(
                '%d:%s' % (i + 1, known.get(v, v)) if v is not None else ''
                for i, v in enumerate(ids)).rstrip()))
        for g in q.generators():
            here = q.slots().get(g['stage'], [])
            got = here[g['slot'] - 1] if 1 <= g['slot'] <= len(here) else None
            print('    gen %-10s %-12s %-13s slot %-2s %-9s %s %s'
                  % (g['stage'], g['name'], g['marker'],
                     g['slot'] if g['slot'] != 0xFF else '-',
                     known.get(got, '') if got else '',
                     g['on_kill'] or '', g['on_end'] or ''))
        for k in q.locks():
            print('    lock %-18s id %-3d %s %s -> %s | %s'
                  % (k['name'], k['id'], k['area'], ','.join(k['lines']),
                     k['trigger'], ','.join(k['gens'])))
    return 0


def cmd_enemies(root) -> int:
    known, use = monsters(root), collections.Counter()
    for q in collect(root):
        for ids in q.slots().values():
            for v in ids:
                if v is not None:
                    use[v] += 1
    for v, n in sorted(use.items()):
        print('  %4d  %-10s %5d slots' % (v, known.get(v, '?'), n))
    print('%d ids, %d of them naming a directory; %d directories unused'
          % (len(use), sum(1 for v in use if v in known),
             sum(1 for v in known if v not in use)))
    return 0


def cmd_xref(root) -> int:
    import psq                                                # noqa: PLC0415
    import stage as stagemod                                  # noqa: PLC0415

    marker, line = {}, {}
    for st in stagemod.stages(root):
        marker[st.name] = set(m.name for m in st.markers)
        line[st.name] = set(pl.name.lower() for pl in st.lines)
    script = collections.defaultdict(set)
    psqs = collections.defaultdict(set)
    for path, blob in psq.collect(root):
        m = re.search(r'quest\.cpk/(q\d+)\.pac/([^/]+)\.psq$', path)
        if m:
            psqs[m.group(1)].add(m.group(2))
            for f in psq.Psq(blob, path).functions():
                script[m.group(1)].add(f.name)
    known = monsters(root)

    tally = collections.Counter()

    def run(label, it):
        hit = miss = skip = 0
        for ok in it:
            if ok is None:
                skip += 1
            else:
                hit += ok
                miss += not ok
        print('  %-30s %5d resolve, %4d do not, %4d not testable'
              % (label, hit, miss, skip))
        tally[label] = (hit, miss)

    quests = list(collect(root))
    run('piecelist -> its own .psq',
        (s in psqs.get(q.name, ()) for q in quests for s in q.stages))
    run('enemy.bin slot -> monster',
        (v in known for q in quests for ids in q.slots().values()
         for v in ids if v is not None))
    run('enemy_gen -> emgen_pos marker',
        (None if g['stage'] not in marker or not g['marker']
         else g['marker'] in marker[g['stage']]
         for q in quests for g in q.generators()))
    run('enemy_gen -> an enemy slot',
        (None if g['slot'] == 0xFF or g['stage'] not in q.slots()
         else q.slots()[g['stage']][g['slot'] - 1] is not None
         for q in quests for g in q.generators()))
    run('enemy_gen -> kill callback',
        (None if not g['on_kill'] else g['on_kill'] in script.get(q.name, ())
         for q in quests for g in q.generators()))
    run('enemy_gen -> end callback',
        (None if not g['on_end'] else g['on_end'] in script.get(q.name, ())
         for q in quests for g in q.generators()))
    run('piecelock -> lockarea',
        (None if k['stage'] not in line or not k['area']
         else k['area'].lower() in line[k['stage']]
         for q in quests for k in q.locks()))
    run('piecelock -> lock lines',
        (None if k['stage'] not in line
         else n.lower() in line[k['stage']]
         for q in quests for k in q.locks() for n in k['lines']))
    run('piecelock -> hit area',
        (None if k['stage'] not in marker or not k['trigger']
         else all(n in marker[k['stage']] for n in k['trigger'].split('\n'))
         for q in quests for k in q.locks()))
    run('piecelock -> its generators',
        (n in set(g['name'] for g in q.generators())
         for q in quests for k in q.locks() for n in k['gens'] + k['gens2']))

    # and the calls that address these tables by name
    _, sites = psq.call_sites(root)
    here = re.compile(r'quest\.cpk/(q\d+)\.pac')
    byname = {q.name: q for q in quests}

    def call(fn, pick):
        """A stage script ships in every quest that visits the stage - up to
        89 pacs for `900_01_01` - so a name it asks for may belong to another
        quest's table. Count the three cases apart."""
        every = set().union(*(pick(q) for q in quests))
        own = other = nowhere = 0
        for path, _, args, _ in sites.get(fn, ()):
            m = here.search(path)
            a = psq.text_arg(args[0]) if args else None
            q = byname.get(m.group(1)) if m else None
            if not q or a is None:
                continue
            own += a in pick(q)
            other += a not in pick(q) and a in every
            nowhere += a not in every
        print('  %-30s %5d in its own quest, %4d in another, %4d nowhere'
              % (fn, own, other, nowhere))

    call('cfStartPieceLock', lambda q: {k['name'] for k in q.locks()})
    call('cfSetEnableEmGen', lambda q: {g['name'] for g in q.generators()})
    call('cfReviveEmGen', lambda q: {g['name'] for g in q.generators()})
    call('cfAddEmGenWait', lambda q: {g['name'] for g in q.generators()})
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
    if cmd == 'xref':
        return cmd_xref(rest[0])
    if cmd == 'enemies':
        return cmd_enemies(rest[0])
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
