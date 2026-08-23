"""
combat.py - the joins behind [`combat_loop.md`](../docs/combat_loop.md).

That document traces one hit from the frame it fires to the number that comes
off a health bar, and every figure in it is a join between two things this
repository already read separately. This file is those joins, so that the
document can be re-derived rather than believed.

Six of them, and each is one table meeting another:

- **`hitlevel`** - `se_hitlevel_tbl`'s base ids against `common.acb`'s cue
  names, and `eff_hitlevel_tbl`'s last word against itself. The first shows the
  fifteen player entries **tile 1000..1089 exactly**, six cues apart, and that
  the six are `S M L` then `CS CM CL` - three sizes and a critical flag. The
  second shows the record is keyed `(level, kind)` in the open, so the effect
  ids carry no arithmetic;
- **`cues`** - the `.anmcmd` hit record's `+0x48` split by which side authored
  it. 747 of the player's 754 records carry the sentinel and 5,245 of the
  monsters' 5,439 carry a cue, and **neither side ever reaches into
  1000..1089**, which is the range the table above allocates. So the player's
  impact sound is computed and the monster's is written down;
- **`power`** - the same records' `+0x35`, whose two populations are an order
  of magnitude apart;
- **`weapons`** - `it_db_weapon.bin` against `it_db_name_weapon.rmsg`. Column 5
  is the weapon kind and it partitions 450 rows into **six values of seventy-
  five**; column 3 is the attack the player's JSON has not got;
- **`stop`** - `dmg_stop_mul`, which is zero on 23 monsters and non-zero on 59,
  and the 23 are exactly the `b*`. A boss takes no hit-stop;
- **`tension`** - the four `s_tension_revise_*` curves, printed six abreast
  because **the thresholds are shared and the multipliers are not**: the
  assassin earns 0.15 from a six-times hit where the warrior earns 0.4, half
  the tension from react damage, and none of the bonus above a full meter.
  Also the bow's two falloff curves, which no other class carries.

Nothing here parses a new format. `ELBN`, `ECH`, `TXT`, `.anmcmd` and the
`@UTF` inside an `.acb` all have readers already; this only puts their outputs
next to each other, which is where every finding in the document came from.

Usage:
  python combat.py hitlevel <dir>    the two hit-level tables, cues resolved
  python combat.py cues <dir>        `+0x48` by side, and the empty range
  python combat.py power <dir>       `+0x35` by side
  python combat.py weapons <dir>     `it_db_weapon.bin`, kinds and attacks
  python combat.py stop <dir>        the hit-stop split, boss against mob
  python combat.py tension <dir>     the four curves, and the bow's two
  python combat.py all <dir>         every one of them, in order
"""

import collections
import json
import pathlib
import statistics
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import anmcmd                                                  # noqa: E402
import ech                                                     # noqa: E402
import rmsg                                                    # noqa: E402
from elbn import Elbn                                          # noqa: E402

HEADER = 16               # the ELBN shell, so a payload offset can be read
CLASSES = ('as', 'cl', 'hs', 'ht', 'mg', 'sw')
PLAYER_BAND = range(1000, 1090)


# --------------------------------------------------------------------------
# small readers over things already read

def elbn_at(path: pathlib.Path) -> Elbn | None:
    try:
        return Elbn(path.read_bytes(), path.as_posix())
    except Exception:                                          # noqa: BLE001
        return None


def array_of(f: Elbn, name: str):
    """An ELBN `(count, pointer)` header, and where its array starts.

    Every table in this file is written that way; `format_elbn.md` calls it
    the shape that recurs."""
    e = f.by_name().get(name)
    if e is None or e.size < 8:
        return None
    count, ptr = struct.unpack_from('>II', f.buf, HEADER + e.offset)
    return count, ptr


def u32(f: Elbn, o: int) -> int:
    return struct.unpack_from('>I', f.buf, HEADER + o)[0]


def f32(f: Elbn, o: int) -> float:
    return struct.unpack_from('>f', f.buf, HEADER + o)[0]


def objbins(root: pathlib.Path):
    """Every `objbin.bin` on the disc, player classes first."""
    for p in sorted(root.glob('job.cpk/*/objbin.bin')):
        yield p.parts[-2], True, p
    for p in sorted(root.glob('monster.cpk/*/objbin.bin')):
        yield p.parts[-2], False, p


def side_of(path: str) -> str:
    """Which side of the fight authored a leaf. The `.cpk` says it."""
    p = path.lower()
    if p.startswith('job.cpk'):
        return 'player'
    if p.startswith('monster.cpk'):
        return 'monster'
    return p.split('/')[0]


def actors(root: pathlib.Path):
    """The 89 actor JSONs, keyed by directory - the identity is the
    directory and not the filename, which `params.md` had to learn twice."""
    for p in sorted(root.rglob('*.json')):
        s = p.as_posix()
        if 'job.cpk' not in s and 'monster.cpk' not in s:
            continue
        try:
            d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        except Exception:                                      # noqa: BLE001
            continue
        base = d.get('0')
        if base:
            yield p.parts[-2], base


# --------------------------------------------------------------------------

def cmd_hitlevel(root) -> int:
    """`se_hitlevel_tbl` against the cue names, and `eff_hitlevel_tbl`'s key.

    The first join is the one that pays: the fifteen player bases are six
    apart and run 1000 to 1084, so they tile a range of ninety cue ids with
    nothing left over, and the six names above each base say what the six
    are."""
    root = pathlib.Path(root)
    cues = anmcmd.cues(root)
    player, monster = [], []
    for who, is_player, path in objbins(root):
        f = elbn_at(path)
        got = array_of(f, 'se_hitlevel_tbl') if f else None
        if not got:
            continue
        count, ptr = got
        for i in range(count):
            a, base, sel = struct.unpack_from('>3I', f.buf,
                                              HEADER + ptr + 12 * i)
            (player if is_player else monster).append((who, a, base, sel))

    print('se_hitlevel_tbl - the player side')
    bases = sorted({b for _, _, b, _ in player})
    for who, _, base, sel in player:
        names = ' '.join(cues.get(base + k, '?') for k in range(6))
        print(f'  {who}  base {base}  selector {sel}   {names}')
    tiles = bases == list(range(1000, 1000 + 6 * len(bases), 6))
    print(f'  {len(player)} entries, {len(bases)} distinct bases')
    print(f'  six apart and starting at 1000, with no gap: {tiles}')
    print(f'  they cover {bases[0]}..{bases[-1] + 5}, and the monsters '
          f'begin at {bases[-1] + 6}')
    print('  so the block of six is  S M L  then  CS CM CL,  and')
    print('      cue = base + size + 3 * critical,  size in {0, 1, 2}')

    print('\nse_hitlevel_tbl - the monster side')
    by_base = collections.Counter(b for _, _, b, _ in monster)
    sels = collections.Counter(s for _, _, _, s in monster)
    for base in sorted(by_base):
        names = ' '.join(cues.get(base + k, '?') for k in range(4))
        print(f'  base {base}  x{by_base[base]:<3} {names}')
    print(f'  {len(monster)} entries, selector {dict(sels)} throughout')

    print('\neff_hitlevel_tbl - the key is the last word')
    n = same4 = 0
    levels, kinds = set(), set()
    for who, is_player, path in objbins(root):
        f = elbn_at(path)
        got = array_of(f, 'eff_hitlevel_tbl') if f else None
        if not got:
            continue
        count, ptr = got
        rows = []
        for i in range(count):
            w = struct.unpack_from('>10I', f.buf, HEADER + ptr + 40 * i)
            n += 1
            if len({(w[0], w[1]), (w[2], w[3]),
                    (w[4], w[5]), (w[6], w[7])}) == 1:
                same4 += 1
            lvl, kind = w[9] >> 16, w[9] & 0xFFFF
            levels.add(lvl)
            kinds.add(kind)
            rows.append((w[1], lvl, kind))
        shown = ', '.join(f'{i}=({l},{k})' for i, l, k in rows[:6])
        print(f'  {who}  {count} records   {shown}'
              + ('  ...' if count > 6 else ''))
    print(f'  {n} records; the four (2, id) pairs are identical on {same4}')
    print(f'  levels {sorted(levels)}, kinds {sorted(kinds)}')
    print('  so the id is a row in the class\'s own effect.bin and carries no')
    print('  arithmetic - the last word is (level, kind) and does')
    return 0


def cmd_cues(root) -> int:
    """`+0x48` by side. The interesting number is the one that is zero."""
    root = pathlib.Path(root)
    cues = anmcmd.cues(root)
    by_side = collections.defaultdict(collections.Counter)
    for path, blob in anmcmd.collect(root):
        try:
            a = anmcmd.Anmcmd(blob, path)
        except Exception:                                      # noqa: BLE001
            continue
        for blk in a.blocks():
            for cmd in blk['commands']:
                for h in anmcmd.hits_of(cmd):
                    by_side[side_of(path)][h.cue] += 1
    print(f'{"":12} {"records":>8} {"carry a cue":>12} {"in 1000..1089":>14}')
    for who in sorted(by_side, key=lambda k: -sum(by_side[k].values())):
        c = by_side[who]
        total = sum(c.values())
        named = total - c[0]
        band = sum(v for k, v in c.items() if k in PLAYER_BAND)
        print(f'{who:12} {total:8} {named:12} {band:14}')
    print('\nthe ids each side uses')
    for who in sorted(by_side, key=lambda k: -sum(by_side[k].values())):
        for k, v in sorted(by_side[who].items()):
            print(f'  {who:8} {k:6} x{v:<5} {cues.get(k, "-")}')
    print('\nzero is the sentinel: cue 0 is SYSTEM_CURSOR, a menu blip.')
    print('the player\'s sound is computed from se_hitlevel_tbl instead,')
    print('which is why nothing here lands in 1000..1089.')
    return 0


def cmd_power(root) -> int:
    """`+0x35` by side, as a five-number summary."""
    by_side = collections.defaultdict(list)
    for path, blob in anmcmd.collect(pathlib.Path(root)):
        try:
            a = anmcmd.Anmcmd(blob, path)
        except Exception:                                      # noqa: BLE001
            continue
        for blk in a.blocks():
            for cmd in blk['commands']:
                for h in anmcmd.hits_of(cmd):
                    by_side[side_of(path)].append(h.power)
    print(f'{"":12} {"records":>8} {"min":>5} {"p25":>5} {"med":>5} '
          f'{"p75":>5} {"max":>5} {"zeros":>7}')
    for who in sorted(by_side, key=lambda k: -len(by_side[k])):
        v = sorted(by_side[who])
        print(f'{who:12} {len(v):8} {v[0]:5} {v[len(v) // 4]:5} '
              f'{v[len(v) // 2]:5} {v[3 * len(v) // 4]:5} {v[-1]:5} '
              f'{v.count(0):7}')
    print('\ntwo populations an order of magnitude apart. what the byte is a')
    print('strength *of* is open: see combat_loop.md section 5.')
    return 0


def cmd_weapons(root) -> int:
    """`it_db_weapon.bin` against its names. Column 5 partitions it."""
    root = pathlib.Path(root)
    tbl = root / 'item.cpk/it_db.pac/it_db_weapon.bin'
    nms = root / 'item.cpk/it_db.en.pac/it_db_name_weapon.rmsg'
    if not tbl.is_file():
        raise SystemExit(f'not found: {tbl}')
    t = ech.Ech(tbl.read_bytes(), tbl.as_posix())
    names = ([m[1] for m in rmsg.Rmsg(nms.read_bytes(), nms.as_posix()).messages]
             if nms.is_file() else [])
    print(f'{t.rows} rows, {len(names)} names, '
          f'pairing positionally: {t.rows == len(names)}')

    def col(r, c):
        return struct.unpack_from('>i', t.row(r), 4 * c)[0]

    kinds = collections.defaultdict(list)
    for r in range(t.rows):
        kinds[col(r, 5)].append((col(r, 3), r))
    print('\ncolumn 5 - the weapon kind')
    for k in sorted(kinds):
        v = sorted(kinds[k])
        lo, hi = v[0], v[-1]
        print(f'  {k}  n={len(v):3}  attack {lo[0]}..{hi[0]}   '
              f'{names[lo[1]] if names else "":<26} .. '
              f'{names[hi[1]] if names else ""}')
    counts = {k: len(v) for k, v in kinds.items()}
    even = len(set(counts.values())) == 1
    print(f'  {len(kinds)} kinds, {sorted(set(counts.values()))} rows each, '
          f'an even partition: {even}')
    print('\nthe six starting weapons - column 3 is the attack the class '
          'JSON has not got')
    print(f'  {"#":>4} {"kind":>5} {"atk":>5} {"crit":>6}  name')
    for r in range(6):
        crit = struct.unpack_from('>f', t.row(r), 4 * 27)[0]
        print(f'  {r:4} {col(r, 5):5} {col(r, 3):5} {crit:6.2f}  '
              f'{names[r] if names else ""}')
    return 0


def cmd_stop(root) -> int:
    """The hit-stop families, and the split `dmg_stop_mul` makes."""
    zero, nonzero = [], []
    give = {}
    for who, base in actors(pathlib.Path(root)):
        v = base.get('dmg_stop_mul')
        if v is not None:
            (zero if v == 0 else nonzero).append(who)
        if base.get('stop_mul') is not None:
            give[who] = (base.get('stop_min'), base.get('stop_max'),
                         base.get('stop_mul'))
    zero = [a for a in zero if a not in CLASSES]
    nonzero = [a for a in nonzero if a not in CLASSES]
    print('dmg_stop_mul - the hit-stop an actor *suffers*, monsters only')
    print(f'  zero      {len(zero):3}   ' + ', '.join(sorted(zero)[:8]) + ' ...')
    print(f'  non-zero  {len(nonzero):3}   '
          + ', '.join(sorted(nonzero)[:8]) + ' ...')
    b = [a for a in zero if a.startswith('b')]
    z = [a for a in nonzero if a.startswith('z')]
    print(f'  every zero is a b* : {len(b)} of {len(zero)}')
    print(f'  every non-zero is a z* : {len(z)} of {len(nonzero)}')
    print('  so a boss takes no hit-stop, and the filename prefix agrees')
    print('\nstop_* - the hit-stop an actor *deals*, on the six classes')
    print(f'  {"":6} {"min":>5} {"max":>5} {"mul":>8}')
    for c in CLASSES:
        if c in give:
            lo, hi, mul = give[c]
            print(f'  {c:6} {lo:5} {hi:5} {mul:8}')
    print('  stop_mul is a thousandth, so its operand is damage and its')
    print('  result is frames; dmg_stop_mul is 1, so its operand is already')
    print('  frames. a giver and a taker of the same quantity.')
    return 0


def _pairs(f: Elbn, name: str, stride: int, wide: int = 2):
    got = array_of(f, name)
    if not got:
        return None
    count, ptr = got
    return [tuple(f32(f, ptr + stride * i + 4 * k) for k in range(wide))
            for i in range(count)]


def cmd_tension(root) -> int:
    """The four tension curves, and the two the bow alone carries.

    What has to be printed is not one curve but six, because **the thresholds
    are shared and the multipliers are not** - which is only visible with the
    six side by side, and is why this reads them all rather than one."""
    root = pathlib.Path(root)
    seen = {}
    for c in CLASSES:
        f = elbn_at(root / f'job.cpk/{c}/objbin.bin')
        if not f:
            continue
        for e in f.entries:
            if not e.name.startswith('s_tension_'):
                continue
            seen.setdefault(e.name, {})[c] = _pairs(f, e.name, 8)
    print('s_tension_revise_* - thresholds shared, multipliers per class')
    for name, per in sorted(seen.items()):
        thr = {tuple(round(a, 4) for a, _ in v) for v in per.values()}
        mul = {tuple(round(b, 4) for _, b in v) for v in per.values()}
        rows = next(iter(per.values()))
        print(f'\n  {name}   {len(rows)} pairs')
        print(f'    thresholds   same on all six: {len(thr) == 1}')
        print('      ' + ' '.join(f'{a:g}' for a, _ in rows))
        print(f'    multipliers  {len(mul)} distinct profile'
              f'{"" if len(mul) == 1 else "s"}')
        for c in CLASSES:
            if c in per:
                print(f'      {c}  ' + ' '.join(f'{b:g}' for _, b in per[c]))
    print('\n  the hp and damage curves descend and the react one ascends,')
    print('  so each is scanned in its own direction.')

    f = elbn_at(root / 'job.cpk/ht/objbin.bin')
    if f:
        print('\nthe bow\'s two, which no other class carries')
        react = _pairs(f, 'ht_react_revise_tbl', 8)
        atk = _pairs(f, 'ht_atk_revise_tbl', 12, 3)
        if react:
            print('  ht_react_revise_tbl   ' +
                  ' '.join(f'({a:g}, {b:g})' for a, b in react))
        if atk:
            print('  ht_atk_revise_tbl     ' +
                  ' '.join(f'({a:g}, {b:g})' for a, b, _ in atk))
            third = {round(c, 3) for _, _, c in atk}
            print(f'    the triple\'s third column is {third} on all '
                  f'{len(atk)} rows')
        print('  both hold at or above 1 to half way and then fall to a')
        print('  tenth, on an axis that runs 0 to 100.')
    return 0


def cmd_all(root) -> int:
    for name, fn in (('hitlevel', cmd_hitlevel), ('cues', cmd_cues),
                     ('power', cmd_power), ('weapons', cmd_weapons),
                     ('stop', cmd_stop), ('tension', cmd_tension)):
        print(f'\n{"=" * 74}\n== {name}\n{"=" * 74}')
        fn(root)
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    table = {'hitlevel': cmd_hitlevel, 'cues': cmd_cues, 'power': cmd_power,
             'weapons': cmd_weapons, 'stop': cmd_stop,
             'tension': cmd_tension, 'all': cmd_all}
    if cmd not in table:
        print(f'unknown command: {cmd}')
        return 1
    if not rest:
        print(f'{cmd} needs a directory')
        return 1
    return table[cmd](rest[0])


if __name__ == '__main__':
    raise SystemExit(main())
