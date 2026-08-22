"""
params.py - the actor parameter files, and what is in them.

89 JSON files sit on the disc uncompressed and pretty-printed: six in
`job.cpk`, one per player class, and 83 in `monster.cpk`, one per monster
directory - though three of those directories name their file after a
different monster, so the directory is the identity and the filename is not.
They hold the numbers that decide how the game moves and hits - acceleration,
run speed, turn rate, hit-stop windows, stagger thresholds, status resistances,
drop rates. No parsing is required to read them. What is required is working
out what the names mean, which is what this tool is for.

## The shape

Each file is a dictionary of **records** keyed by a number, and record `"0"` is
the base. The others are variants that merge over it - they may override a
field or introduce one the base never set, so it is a merge and not a subset
overlay (440 of the 980 non-base records add at least one field).

For a monster the key is a **difficulty tier**, and the pairing is regular:
key `n` and key `n+1`, for even `n`, are the same monster at a higher
`region_lv`. Across the 168 such pairs on the disc the level step is +3 in 123
of them and +1 in 44, and `hp` is **exactly 1.5x** in 138. `atk` is tuned by
hand - 1.2x is the most common ratio but far from the only one.

For a player class there are three records. Record 1 raises `acc`, `run_sp`,
`fast_acc` and `fast_sp`, drops stun to zero and lifts every status resistance
from 7 to 9: a buffed state rather than a difficulty. Record 2 nudges four
movement fields. Neither is named anywhere in the file, so this tool reports
what they change and does not claim to know what they are.

## The naming convention

The suffix carries the unit, consistently enough to rely on:

    _f      frames        integral in 1,926 of 1,932 occurrences
    _sp     speed         small floats, ~0.05 to 0.6
    _acc    acceleration  smaller floats
    _r      radius or ratio
    _p      points        integral in all 4,490 occurrences
    _y      a vertical component
    ab_*    abnormal status - poison, paralysis, freeze, burn and so on
    stg_*   stagger
    prob_*  drop probability
    cmb_*   combo
    es_*    evade / escape
    jg_*    guard, and only the two shield classes have them

Usage:
  python params.py census <dir>              files, records, field populations
  python params.py show <dir> <name> [key]   one record, merged over the base
  python params.py diff <dir> <name> <a> <b> what one variant changes
  python params.py classes <dir> [fields]    the six player classes side by side
  python params.py tiers <dir>               the difficulty pairing, measured
  python params.py field <dir> <name>        where a field occurs, and its range
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict

CLASSES = ('as', 'cl', 'hs', 'ht', 'mg', 'sw')


def collect(root) -> dict[str, dict]:
    """Every parameter file, keyed by its actor name (`as`, `b01_00`, ...).

    The key is the **directory**, not the file stem. Three monsters break the
    naming convention: `z12_00`, `z12_01` and `z12_02` each hold a file called
    `z10_00.json`, with different contents in each. Keying on the stem quietly
    loses three of the 89 files and leaves whichever was read last."""
    root = pathlib.Path(root)
    out = {}
    for p in sorted(root.rglob('*.json')):
        out[p.parent.name] = json.loads(p.read_text(encoding='utf-8'))
    return out


def merged(doc: dict, key: str) -> dict:
    """A record as the game would see it: the base, then the variant on top."""
    out = dict(doc.get('0', {}))
    if key != '0':
        out.update(doc.get(key, {}))
    return out


def is_monster(name: str) -> bool:
    return name not in CLASSES


def human(v) -> str:
    if isinstance(v, list):
        return '[' + ', '.join(human(x) for x in v) + ']'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# --------------------------------------------------------------------------

def cmd_census(root) -> int:
    docs = collect(root)
    jobs = {k: v for k, v in docs.items() if not is_monster(k)}
    mons = {k: v for k, v in docs.items() if is_monster(k)}
    records = sum(len(d) for d in docs.values())
    fields = Counter()
    owners = defaultdict(set)
    for name, d in docs.items():
        for rec in d.values():
            for f in rec:
                fields[f] += 1
                owners[f].add(name)
    print(f'{len(docs)} files, {records} records, {len(fields)} distinct fields')
    print(f'  {len(jobs)} player classes: {", ".join(sorted(jobs))}')
    print(f'  {len(mons)} monsters')

    core = sorted(f for f in fields if len(owners[f]) >= len(mons) * 0.8)
    tail = [f for f in fields if len(owners[f]) <= 2]
    print()
    print(f'The shared actor model is {len(core)} fields, present in 80% or '
          f'more of the monsters:')
    line = '   '
    for f in core:
        if len(line) + len(f) > 76:
            print(line)
            line = '   '
        line += f + ' '
    print(line)
    print()
    print(f'{len(tail)} fields appear in at most two actors. Those are the '
          f'per-move')
    print('parameters, and they are named after the move or the monster:')
    pre = Counter(f.split('_')[0] for f in tail)
    print('   ' + ', '.join(f'{k}_* ({v})' for k, v in pre.most_common(10)))
    return 0


def cmd_show(root, name, key='0') -> int:
    docs = collect(root)
    if name not in docs:
        raise SystemExit(f'not found: {name}')
    doc = docs[name]
    rec = merged(doc, key)
    own = doc.get(key, {})
    print(f'{name} record {key} - {len(rec)} fields '
          f'({len(own)} set by this record, the rest inherited from 0)')
    for f in sorted(rec):
        mark = '*' if f in own and key != '0' else ' '
        print(f' {mark} {f:<28} {human(rec[f])}')
    return 0


def cmd_diff(root, name, a, b) -> int:
    docs = collect(root)
    if name not in docs:
        raise SystemExit(f'not found: {name}')
    ra, rb = merged(docs[name], a), merged(docs[name], b)
    keys = sorted(set(ra) | set(rb))
    n = 0
    for f in keys:
        if ra.get(f) != rb.get(f):
            print(f'  {f:<28} {human(ra.get(f))}  ->  {human(rb.get(f))}')
            n += 1
    print(f'{n} fields differ between record {a} and record {b}')
    return 0


def cmd_classes(root, only='') -> int:
    """The six player classes side by side. The interesting part is how much
    is *not* different."""
    docs = collect(root)
    base = {c: docs[c]['0'] for c in CLASSES if c in docs}
    if not base:
        raise SystemExit('no player class files found')
    fields = sorted(set().union(*(set(r) for r in base.values())))
    wanted = [f for f in fields if only in f] if only else fields
    same = [f for f in wanted
            if len({json.dumps(base[c].get(f)) for c in base}) == 1]
    diff = [f for f in wanted if f not in same]
    print(f'{len(wanted)} fields: {len(same)} identical across all '
          f'{len(base)} classes, {len(diff)} not')
    print()
    print(f'{"field":<30}' + ''.join(f'{c:>10}' for c in base))
    for f in diff:
        print(f'{f:<30}' + ''.join(f'{human(base[c].get(f)):>10}'
                                  for c in base))
    return 0


def cmd_tiers(root) -> int:
    """The difficulty pairing, measured rather than assumed. For every even
    key with an odd partner, how far the level moves and how the stats scale."""
    docs = collect(root)
    steps = Counter()
    hp_ratio = Counter()
    atk_ratio = Counter()
    pairs = 0
    for name, doc in docs.items():
        if not is_monster(name):
            continue
        for k in doc:
            if int(k) % 2:
                continue
            partner = str(int(k) + 1)
            if partner not in doc:
                continue
            a, b = merged(doc, k), merged(doc, partner)
            if 'region_lv' not in a or 'region_lv' not in b:
                continue
            pairs += 1
            steps[b['region_lv'] - a['region_lv']] += 1
            if a.get('hp'):
                hp_ratio[round(b['hp'] / a['hp'], 3)] += 1
            if a.get('atk'):
                atk_ratio[round(b['atk'] / a['atk'], 3)] += 1
    print(f'{pairs} (n, n+1) key pairs across the monsters')
    print('  region_lv step: '
          + ', '.join(f'+{k} x{v}' for k, v in steps.most_common()))
    print('  hp ratio      : '
          + ', '.join(f'{k}x x{v}' for k, v in hp_ratio.most_common(5)))
    print('  atk ratio     : '
          + ', '.join(f'{k}x x{v}' for k, v in atk_ratio.most_common(5)))
    return 0


def cmd_field(root, field) -> int:
    """Where a field occurs and what values it takes - the evidence for what
    it might mean."""
    docs = collect(root)
    vals = []
    owners = []
    for name, doc in docs.items():
        seen = False
        for rec in doc.values():
            if field in rec:
                vals.append(rec[field])
                seen = True
        if seen:
            owners.append(name)
    if not vals:
        raise SystemExit(f'no actor has a field named {field!r}')
    print(f'{field}: {len(vals)} occurrences in {len(owners)} actors')
    print(f'  actors: ' + ', '.join(sorted(owners)[:14])
          + (' ...' if len(owners) > 14 else ''))
    if all(isinstance(v, list) for v in vals):
        widths = Counter(len(v) for v in vals)
        print(f'  lists, lengths: {dict(widths)}')
        for i in range(max(widths)):
            col = [v[i] for v in vals if len(v) > i]
            print(f'    [{i}] {min(col)} .. {max(col)}, '
                  f'{len(set(map(str, col)))} distinct')
        return 0
    nums = [v for v in vals if isinstance(v, (int, float))]
    if nums:
        whole = sum(1 for v in nums if float(v).is_integer())
        print(f'  {min(nums)} .. {max(nums)}, '
              f'{len(set(nums))} distinct, {whole}/{len(nums)} whole')
    common = Counter(map(str, vals)).most_common(6)
    print('  most common: ' + ', '.join(f'{k} x{v}' for k, v in common))
    return 0


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'census':
        return cmd_census(rest[0])
    if cmd == 'show':
        return cmd_show(rest[0], rest[1], rest[2] if len(rest) > 2 else '0')
    if cmd == 'diff':
        return cmd_diff(rest[0], rest[1], rest[2], rest[3])
    if cmd == 'classes':
        return cmd_classes(rest[0], rest[1] if len(rest) > 1 else '')
    if cmd == 'tiers':
        return cmd_tiers(rest[0])
    if cmd == 'field':
        return cmd_field(rest[0], rest[1])
    print(f'unknown command: {cmd}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
