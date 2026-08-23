"""
mkc.py - reader for `.mkc`, the presentation track of an animation.

2,690 files, 256 of them nothing but a terminator; **2,690 read, 19,724
records, 0 unreadable**, every file landing exactly on its `0xffff`.

A [`CNOM`](cnom.py) moves the bones and an [`.anmcmd`](anmcmd.py) says what the
motion *does* - where the hit box is, when the actor may be cancelled. This
file says what the motion *sounds and looks like*: which sound cue fires on
which frame, which voice the actor grunts, when a foot touches the ground and
which effect is spawned. It is named after the motion, sits in the pac's
`<name>.mkc.pac`, and 2,304 of the 2,690 share their stem with a `CNOM` sitting
one directory up.

## The stream

There is no header. A file is a flat list of records, big-endian `u16`
throughout, closed by a lone `0xffff`:

    u16   frame
    u16   opcode
    u16   argument count
    u16   arguments[count]
    ...
    0xffff

The count is explicit, which is why the records do not have to be a fixed
width - the same opcode takes one argument here and three there. Walking the
stream by that count lands exactly on the terminator on all 2,690 files, and
**frames never step backwards**, on any file. The frame is absolute, not a
delta: read as absolute it stays within the paired `CNOM`'s declared length on
1,971 of the 1,978 files that have one, read as a delta it overruns on 1,390.

## Sound

    7ff9 (bank, cue, emitter)   play a cue
    7ffd (bank, cue, emitter)   the same, second form
    7ffc (cue)                  play the actor's own voice

A **bank** is an `.acb`, and the id says which one:

    100          sound.cpk/common.acb
    200 + 10*k   job.cpk/<class>/se.acb, k over as cl cm hs ht mg nn sw
    3000 + 10*n  monster.cpk/b<nn>/se.acb
    4000 + 10*n  monster.cpk/z<nn>/se.acb

A **cue** is a `CueId` from that table's `CueTable` - not a row number: 225 of
`common.acb`'s 529 rows carry an id that is not their index, and the ids run to
3104. Resolve them properly and the disc reads back in plain words:

    mht361at_l   0 open a bracket, 4 DRAW_L, 18 close it, 18 voice ATK_L,
                 19 STRONG_REACTION_S, 20 ARROW_DUMMY_L, 35 and 47 footsteps

which is a bow being drawn, released and stepped away from. `mht301jump` fires
`JUMP`, `mht220escape_f_st` fires `AVOID`, `com060emo_10` claps four times.

`7ffc`'s argument is a cue of `sound.cpk/<lang>/v{m,f}NN.acb`, the 57-cue
player voice bank - **23 `ATK_S`, 24 `ATK_M`, 25 `ATK_L`, 22 `JUMP`, 15
`DASH`, 17 `DMG_S`** and so on down the list. It is used by the player and by
the shared emote set and by nothing else, which is what a player voice is.

The third argument is an **emitter**: where on the body the sound comes from.
It is 0 for four records in five, and where it is not it comes in left/right
pairs - on Hraesvelgr `BLAST_L` and `SWOOPED_L` take 1100 while `BLAST_R` and
`SWOOPED_R` take 1200, every `_V_` voice cue takes 1300, `STEP` alternates
1700 and 1800, and the three tail sounds take 10100. The vocabulary is 23
values wide; see `docs/format_mkc.md` for what is still open about it.

## Effect

    0801 (index)     spawn effect `index`
    080e (index, 0)  the same, second form

The index is **1-based into the `effect.bin` sitting beside the `.mkc.pac`** -
an `ECH` table of 60-byte rows, one per effect the motion set can spawn. On 29
of the 54 pacs that use the opcode the largest index is exactly the row count,
and the index is never 0 on any of the 2,690 files.

## Ground contact

    7ffa (kind)   foot down
    7ffb (kind)   the matching second event

`kind` is 0 to 3 and picks a cue from the character model's own four-cue
`.acb`: **WALK, RUN, LANDING, DRESS**. A walk cycle fires `7ffa(0)` and
`7ffb(0)` one frame apart at each step, a run fires them with `kind = 1`, and
`mht303landing` opens with `kind = 2`.

Usage:
  python mkc.py check <dir>              the grammar, every file
  python mkc.py census <dir>             every opcode, by actor kind
  python mkc.py survey <dir>             every file, one line each
  python mkc.py list <dir> <name>        one file, with the cue names
  python mkc.py banks <dir>              bank ids and the `.acb` they name
  python mkc.py cues <dir> <bank>        one bank's cue list
  python mkc.py effects <dir>            indices against `effect.bin`
"""

import collections
import fnmatch
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from assets import leaves                                       # noqa: E402
from cpk import Utf                                             # noqa: E402

SUFFIX = '.mkc'
END = 0xFFFF

CLASSES = ('as', 'cl', 'cm', 'hs', 'ht', 'mg', 'nn', 'sw')

# The player voice banks are 60 files with one name list between them; any one
# of them names the cues `7ffc` selects.
VOICE = 'sound.cpk/en/vm01.acb'

SOUND_OPS = (0x7FF9, 0x7FFD)
EFFECT_OPS = (0x0801, 0x080E)

# What each opcode is taken to be. Anything absent is still unread; the counts
# and the evidence are in ../docs/format_mkc.md.
NAMES = {
    0x7FF9: 'sound',
    0x7FFD: 'sound2',
    0x7FFC: 'voice',
    0x7FFA: 'foot',
    0x7FFB: 'foot2',
    0x0801: 'effect',
    0x080E: 'effect2',
    0x0404: 'on',
    0x0405: 'off',
    0x0802: 'shake?',
}


# --------------------------------------------------------------------------
# the stream

class Record:
    __slots__ = ('frame', 'op', 'args')

    def __init__(self, frame: int, op: int, args: tuple):
        self.frame, self.op, self.args = frame, op, args

    def __str__(self) -> str:
        name = NAMES.get(self.op, '')
        head = f'{self.op:04x}' + (f' {name}' if name else '')
        return f'{self.frame:5d}  {head:<14} ' \
               f'({", ".join(str(a) for a in self.args)})'


class Mkc:
    """One `.mkc` read whole. Raises when the stream does not close."""

    def __init__(self, blob: bytes, path: str = ''):
        self.path = path
        if len(blob) % 2:
            raise ValueError(f'{path}: odd length {len(blob)}')
        v = struct.unpack(f'>{len(blob) // 2}H', blob)
        self.records: list[Record] = []
        i = 0
        while True:
            if i >= len(v):
                raise ValueError(f'{path}: ran off the end with no terminator')
            if v[i] == END:
                if i != len(v) - 1:
                    raise ValueError(f'{path}: terminator at {i} of {len(v)}')
                break
            if i + 3 > len(v):
                raise ValueError(f'{path}: truncated record header at {i}')
            frame, op, n = v[i], v[i + 1], v[i + 2]
            if i + 3 + n > len(v):
                raise ValueError(f'{path}: record at {i} wants {n} arguments')
            self.records.append(Record(frame, op, v[i + 3:i + 3 + n]))
            i += 3 + n

    @property
    def last(self) -> int:
        return max((r.frame for r in self.records), default=0)

    def monotonic(self) -> bool:
        f = [r.frame for r in self.records]
        return all(a <= b for a, b in zip(f, f[1:]))


# --------------------------------------------------------------------------
# the disc around it

WANTED = (SUFFIX, '.acb', 'effect.bin')


def collect(root, want: str = ''):
    """The leaves this reader needs, whether `root` is a directory of `.cpk`
    files or an already unpacked tree."""
    root = pathlib.Path(root)
    if not any(p.is_file() for p in root.glob('*.cpk')):
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.name.lower().endswith(WANTED):
                yield p.relative_to(root).as_posix(), p.read_bytes()
        return
    for path, blob in leaves(root, want):
        if path.lower().endswith(WANTED):
            yield path, blob


class Disc:
    """The three tables a `.mkc` reaches into: the `.acb` sound banks, the
    `effect.bin` beside each `.mkc.pac`, and the files themselves."""

    def __init__(self, root):
        self.mkc: list[tuple[str, bytes]] = []
        self.acb: dict[str, bytes] = {}
        self.effect: dict[str, int] = {}
        for path, blob in collect(root):
            low = path.lower()
            if low.endswith(SUFFIX):
                self.mkc.append((path, blob))
            elif low.endswith('.acb'):
                self.acb[path] = blob
            elif low.endswith('effect.bin') and blob[:4] == b'ECH\0':
                self.effect[path] = struct.unpack_from('>I', blob, 0x10)[0]
        self._cues: dict[str, dict] = {}

    # -- sound banks

    def bank_path(self, bank: int) -> str:
        """The `.acb` a bank id names, by the rule the ids follow."""
        if bank == 100:
            return 'sound.cpk/common.acb'
        if 200 < bank <= 280 and bank % 10 == 0:
            return f'job.cpk/{CLASSES[bank // 10 - 21]}/se.acb'
        if 3000 < bank < 4000 and bank % 10 == 0:
            return f'monster.cpk/b{(bank - 3000) // 10:02d}/se.acb'
        if 4000 < bank < 5000 and bank % 10 == 0:
            return f'monster.cpk/z{(bank - 4000) // 10:02d}/se.acb'
        return ''

    def _find(self, tail: str) -> str:
        for path in self.acb:
            if path.endswith(tail):
                return path
        return ''

    def cues(self, tail: str) -> dict:
        """`CueId` -> cue name for one `.acb`, empty when it is not here."""
        if tail in self._cues:
            return self._cues[tail]
        path = self._find(tail)
        out: dict = {}
        if path:
            head = Utf(self.acb[path]).rows[0]
            names = {r['CueIndex']: r['CueName']
                     for r in Utf(head['CueNameTable']).rows}
            out = {r['CueId']: names.get(i, '?')
                   for i, r in enumerate(Utf(head['CueTable']).rows)}
        self._cues[tail] = out
        return out

    def cue(self, bank: int, cue: int) -> str:
        tail = self.bank_path(bank)
        return self.cues(tail).get(cue, '') if tail else ''

    def voice(self, cue: int) -> str:
        return self.cues(VOICE).get(cue, '')

    # -- the effect table beside a pac

    def rows(self, mkc_path: str) -> int:
        """Rows in the `effect.bin` two levels above a `.mkc`, or -1."""
        parts = mkc_path.split('/')
        if len(parts) < 3:
            return -1
        want = '/'.join(parts[:-2] + ['effect.bin'])
        return self.effect.get(want, -1)


def _one(disc: Disc, name: str) -> tuple[str, Mkc]:
    for path, blob in disc.mkc:
        leaf = path.rsplit('/', 1)[-1]
        if name in (path, leaf, leaf[:-4]) or fnmatch.fnmatch(path, name):
            return path, Mkc(blob, path)
    raise SystemExit(f'not found: {name}')


def kind_of(path: str) -> str:
    """Which sort of actor a pac belongs to, for the census."""
    parts = path.split('/')
    pac = next((p[:-8] for p in parts if p.endswith('.mkc.pac')), '')
    if len(pac) == 3 and pac[0] in 'bz' and pac[1:].isdigit():
        return 'monster' if pac[0] == 'b' else 'small'
    if len(pac) == 3 and pac[0] in 'fm':
        return 'player'
    return 'other'


# --------------------------------------------------------------------------
# commands

def cmd_check(root) -> int:
    disc = Disc(root)
    files = empty = bad = records = back = 0
    widths: collections.Counter = collections.Counter()
    errs: list[str] = []
    for path, blob in disc.mkc:
        files += 1
        try:
            m = Mkc(blob, path)
        except Exception as exc:                              # noqa: BLE001
            bad += 1
            errs.append(str(exc))
            continue
        records += len(m.records)
        empty += not m.records
        back += not m.monotonic()
        for r in m.records:
            widths[(r.op, len(r.args))] += 1
    print(f'{files} files, {records} records, {empty} with nothing but the '
          f'terminator, {bad} unreadable')
    print(f'frames never step backwards: {files - back} of {files}')
    for line in errs[:20]:
        print(f'  {line}')
    print(f'{len(widths)} (opcode, argument count) pairs, '
          f'{len({op for op, _ in widths})} distinct opcodes')
    return 1 if bad else 0


def cmd_census(root) -> int:
    disc = Disc(root)
    by: dict[tuple, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for path, blob in disc.mkc:
        k = kind_of(path)
        for r in Mkc(blob, path).records:
            by[(r.op, len(r.args))][k] += 1
    print(f'{"op":<6} {"args":>4} {"total":>7} {"player":>7} {"monster":>8} '
          f'{"small":>6} {"other":>6}  reading')
    for (op, n), c in sorted(by.items()):
        print(f'{op:04x}   {n:>4} {sum(c.values()):>7} {c["player"]:>7} '
              f'{c["monster"]:>8} {c["small"]:>6} {c["other"]:>6}  '
              f'{NAMES.get(op, "")}')
    return 0


def cmd_survey(root) -> int:
    disc = Disc(root)
    for path, blob in sorted(disc.mkc):
        m = Mkc(blob, path)
        ops = collections.Counter(NAMES.get(r.op, f'{r.op:04x}')
                                  for r in m.records)
        print(f'{path.rsplit("/", 1)[-1]:<40} {len(m.records):>4} records  '
              f'last frame {m.last:>4}  '
              f'{" ".join(f"{k}x{v}" for k, v in ops.most_common())}')
    return 0


def cmd_list(root, name) -> int:
    disc = Disc(root)
    path, m = _one(disc, name)
    rows = disc.rows(path)
    print(path)
    print(f'{len(m.records)} records, last frame {m.last}' +
          (f', effect.bin has {rows} rows' if rows >= 0 else ''))
    for r in m.records:
        note = ''
        if r.op in SOUND_OPS and len(r.args) == 3:
            bank = disc.bank_path(r.args[0])
            cue = disc.cue(r.args[0], r.args[1])
            note = f'   {bank or "?"}  {cue or "?"}'
        elif r.op == 0x7FFC and len(r.args) == 1:
            note = f'   {VOICE}  {disc.voice(r.args[0]) or "?"}'
        elif r.op in EFFECT_OPS and r.args:
            note = f'   effect.bin row {r.args[0]}'
            if 0 <= rows < r.args[0]:
                note += f' - past the end, the table has {rows}'
        print(f'{r}{note}')
    return 0


def cmd_banks(root) -> int:
    disc = Disc(root)
    use: dict[int, collections.Counter] = collections.defaultdict(
        collections.Counter)
    hit: collections.Counter = collections.Counter()
    miss: collections.Counter = collections.Counter()
    for path, blob in disc.mkc:
        pac = next((p[:-8] for p in path.split('/') if p.endswith('.mkc.pac')),
                   '?')
        for r in Mkc(blob, path).records:
            if r.op in SOUND_OPS and len(r.args) == 3:
                use[r.args[0]][pac] += 1
                if disc.cue(r.args[0], r.args[1]):
                    hit[r.args[0]] += 1
                else:
                    miss[r.args[0]] += 1
    print(f'{"bank":>6} {"refs":>6} {"named":>6}  {"acb":<34} used by')
    for bank in sorted(use):
        tail = disc.bank_path(bank)
        n = hit[bank] + miss[bank]
        print(f'{bank:>6} {n:>6} {hit[bank]:>6}  {tail or "-":<34} '
              f'{" ".join(sorted(use[bank]))[:60]}')
    print(f'{sum(hit.values())} of {sum(hit.values()) + sum(miss.values())} '
          f'references land on a cue that exists')
    return 0


def cmd_cues(root, bank) -> int:
    disc = Disc(root)
    bank = int(bank)
    tail = disc.bank_path(bank) if bank else VOICE
    cues = disc.cues(tail)
    print(f'{tail}: {len(cues)} cues')
    for cue in sorted(cues):
        print(f'  {cue:>5}  {cues[cue]}')
    return 0


def cmd_effects(root) -> int:
    disc = Disc(root)
    per: dict[str, list] = collections.defaultdict(list)
    for path, blob in disc.mkc:
        parts = path.split('/')
        pac = '/'.join(parts[:-1])
        for r in Mkc(blob, path).records:
            if r.op in EFFECT_OPS and r.args:
                per[pac].append(r.args[0])
    exact = under = over = 0
    print(f'{"pac":<26} {"rows":>5} {"refs":>6} {"lowest":>7} {"highest":>8}')
    for pac in sorted(per):
        rows = disc.rows(pac + '/x')
        v = per[pac]
        exact += max(v) == rows
        under += max(v) < rows
        over += max(v) > rows
        print(f'{"/".join(pac.split("/")[-2:]):<26} {rows:>5} {len(v):>6} '
              f'{min(v):>7} {max(v):>8}'
              + ('   <- past the end' if max(v) > rows else ''))
    print(f'{exact} pacs where the highest index is exactly the row count, '
          f'{under} below it, {over} above')
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'check':
        return cmd_check(rest[0])
    if cmd == 'census':
        return cmd_census(rest[0])
    if cmd == 'survey':
        return cmd_survey(rest[0])
    if cmd == 'list':
        return cmd_list(rest[0], rest[1])
    if cmd == 'banks':
        return cmd_banks(rest[0])
    if cmd == 'cues':
        return cmd_cues(rest[0], rest[1])
    if cmd == 'effects':
        return cmd_effects(rest[0])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
