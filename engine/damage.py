"""
damage.py - the expression, and the numbers on both sides of it.

This is [`combat_loop.md`](../docs/combat_loop.md) ledger items 1 and 2,
implemented. Both were read out of the EBOOT in session 31 and the reading is
in [`eboot.md`](../docs/eboot.md), with an address on every term; nothing here
is a policy, and the two constants in it - `1.0` and `0.0` - are the two
floats the binary loads out of its own TOC.

    python engine/damage.py show extract/tree [class]
    python engine/damage.py table extract/tree
    python engine/damage.py against extract/tree <monster> [class] [tier]

Until this file existed a monster died on its third landed volume, which is
what [`parity.md`](../docs/parity.md) called `BLOWS` and counted as three of
its seven stand-ins. Now it dies when its own `hp` runs out.

## The expression

`FUN_00622fe4` builds two structures, hands both to the listener chain, and
multiplies. Every `add` is zero and every `rate` is one on a bare hit,
because the adds and the rates exist for the listeners - a card, an ability,
a buff - and not for the arithmetic:

    attack  = clamp>=1( (a0 + a2) * a3 + a1 )    the attack, modified
            * max0( a4 + a5 )                    the hit's own ratio
            * max0( d3 + d4 )                    what the target takes
            * a8
            * ( critical ? a6 + a7 + 1 : 1 )     dmg_critical_factor

    defence = max0( d0 * d2 + d1 )               def, modified

    damage  = attack - defence
    if damage > 0:  damage *= 1 + f ; damage -= damage * max0(d5)
    damage  = max( damage, 1 )

**The defence is subtracted and the floor is 1.** Neither is on the disc.

## Where each term comes from, and which are readings

| term | what | where |
|---|---|---|
| `a0` | the attacker's `atk` | its JSON at its tier; a player's from the growth table |
| `a2` | the add | a player's weapon, `it_db_weapon.bin` column 3 |
| `a4` | the hit's ratio | `.anmcmd` `+0x30` |
| `a6` | `dmg_critical_factor` | the attacker's own parameters |
| `d0` | the target's `def` | its JSON at its tier |
| `d1` | a flat modifier | `region_data`'s `+0x9C[region_lv]` - **a reading** |
| `d3` | a multiplier | `region_data`'s `+0xE4[class]` - **a reading** |

The binary settles `a4`. The runtime hit record's first float is what the
attack builder's first argument is, and `FUN_0060fe50` - which copies a
116-byte `.anmcmd` record into the 0x130-byte runtime one - assigns it from
**`+0x30`**, the field [`format_anmcmd.md`](../docs/format_anmcmd.md) had
already measured as *"a ratio, near 1 whatever the actor's size"*, median
1.00 and uncorrelated with the actor (r = -0.04). The same function assigns
`+0x103` from **`+0x35`**, which is the byte the hit level is computed from,
so `+0x35` is not this.

The two marked **a reading** are the open half of ledger item 5. What the
binary shows is that `d1` defaults to `0.0` and `d3` to `1.0`; what the disc
shows is that `region_data`'s flat modifier is `0.0` on the median of 315
regions and its six multipliers are `1.000` on the median of 1,890, with 581
of them exactly `1.0`. **The disc's neutral values are the builder's
defaults**, the six multipliers are six and the classes are six, and that is
the argument. It is not a proof and it is marked here and in `parity.md`.

The per-node factor `f` is **not applied**: `FUN_00622c7c` looks the target's
node up in a twelve-byte table the runtime hit record carries at `+0x8c`, and
that table is built from something this repository has not found. It is 0 on
a target the table does not name, so leaving it out is the same as every
lookup missing, which is honest and is stated where it is skipped.
"""
from __future__ import annotations

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

from ech import Ech                                             # noqa: E402
from elbn import Elbn, region_rows                              # noqa: E402

# The two floats `FUN_00622fe4` loads out of TOC 0x113b7e0, at -0x55c4 and
# -0x55c0. They are the only constants in the expression.
ONE, ZERO = 1.0, 0.0
# `ccparamobj.bin`'s six tables, and the job id each class is numbered with
# in `it_db_weapon.bin` column 5 - which is `job_par`'s own slot for it.
JOBS = {'as': 0, 'cl': 1, 'hs': 3, 'ht': 4, 'mg': 5, 'sw': 7}
# `player.py` and `mission.py` disagree on two of the six abbreviations.
ALIAS = {'ha': 'hs', 'hu': 'ht', 'ma': 'mg'}
# The six multipliers of a region are six, and the six classes are the disc's
# only six. This is the order `it_db_weapon.bin` column 5 sorts them into,
# which is the order `job_par` uses and the one the EBOOT's own job-name run
# is written in: assassin, cleric, (gunner), hammersmith, hunter, mage,
# (ninja), sword, with the two that did not ship removed.
BYCLASS = ('as', 'cl', 'hs', 'ht', 'mg', 'sw')


def _class(cls: str) -> str:
    cls = (cls or 'sw').lower()
    return ALIAS.get(cls, cls)


# -- the player's own three numbers -----------------------------------------


class Growth:
    """`misc.cpk/ccparamobj.bin`: `atk`, `def` and `hp` by class and level.

    Six tables of fourteen sixteen-byte rows, with an eight-byte
    `<class>_par` beside each reading `(14, offset)`, and a
    `(threshold, row)` table that turns story progress into a row. See
    [`eboot.md`](../docs/eboot.md); `tools/elbn.py levels` prints it.
    """

    def __init__(self, tree):
        path = pathlib.Path(tree) / 'misc.cpk' / 'ccparamobj.bin'
        self.rows: dict[str, list[tuple]] = {}
        self.steps: list[tuple[int, int]] = []
        if not path.is_file():
            return
        f = Elbn(path.read_bytes(), path.name)
        by = f.by_name()
        for cls in BYCLASS:
            head, table = by.get('%s_par' % cls), by.get('%s_lv_par' % cls)
            if head is None or table is None:
                continue
            n, at = struct.unpack_from('>II', f.buf, 16 + head.offset)
            if at != table.offset or n * 16 != table.size:
                continue
            self.rows[cls] = [
                struct.unpack_from('>ffII', f.buf, 16 + table.offset + i * 16)
                for i in range(n)]
        root = by.get('s_job_data')
        if root is not None:
            w = struct.unpack_from('>6I', f.buf, 16 + root.offset)
            for i in range(w[2] + 1):
                t, lv = struct.unpack_from('>Ii', f.buf, 16 + w[3] + i * 8)
                self.steps.append((t, lv))

    def level(self, progress: int) -> int:
        """The row story progress puts a player on. The table is written
        high to low and the engine takes the first threshold it reaches."""
        for threshold, row in self.steps:
            if progress >= threshold:
                return row
        return 0

    def row(self, cls: str, progress: int) -> tuple:
        rows = self.rows.get(_class(cls))
        if not rows:
            return (ZERO, ZERO, 0, 0)
        return rows[min(self.level(progress), len(rows) - 1)]


class Weapons:
    """`it_db_weapon.bin` column 3, for the six starting weapons.

    Column 5 partitions the 450 rows into six kinds of 75 and rows 0 to 5 are
    the six a class begins with - see
    [`combat_loop.md`](../docs/combat_loop.md) section 3. A weapon's attack
    is the `add` the growth table's `atk` is added to, which is what the
    attack builder's second virtual call reads at `parameters + 0x2c0` - the
    one field the parameter reader does not parse.
    """

    def __init__(self, tree):
        path = (pathlib.Path(tree) / 'item.cpk' / 'it_db.pac'
                / 'it_db_weapon.bin')
        self.start: dict[str, float] = {}
        if not path.is_file():
            return
        t = Ech(path.read_bytes(), path.as_posix())
        first: dict[int, float] = {}
        for r in range(t.rows):
            row = t.row(r)
            kind = struct.unpack_from('>i', row, 4 * 5)[0]
            first.setdefault(kind, float(struct.unpack_from('>i', row,
                                                            4 * 3)[0]))
        for cls, job in JOBS.items():
            if job in first:
                self.start[cls] = first[job]

    def attack(self, cls: str) -> float:
        return self.start.get(_class(cls), ZERO)


# -- the two structures -----------------------------------------------------


def attack_terms(base: float, add: float, ratio: float,
                 critical_factor: float) -> list[float]:
    """`FUN_00245870`, with the listener chain empty.

    Eleven floats; the builder writes `a1 = a5 = a7 = a10 = 0` and
    `a3 = a8 = 1`, reads `a0` and `a2` from two virtual calls, `a4` and `a9`
    from the hit record, and `a6` by name from the actor's parameters.
    """
    return [float(base), ZERO, float(add), ONE,
            max(float(ratio), ZERO), ZERO,
            float(critical_factor), ZERO, ONE, ZERO, ZERO]


def defence_terms(defence: float, flat: float = ZERO,
                  multiplier: float = ONE) -> list[float]:
    """`FUN_00245678`, with the listener chain empty.

    Six floats; the builder writes `d0` from `parameters + 0x2c4`, `d2` and
    `d3` as `1.0` and the other three as `0.0`. `flat` and `multiplier` are
    where the region's own two numbers arrive - see the header.
    """
    return [float(defence), ZERO, ONE, float(multiplier), ZERO, ZERO]


def resolve(a: list[float], d: list[float], critical: bool = False,
            node: float = ONE) -> float:
    """The expression itself. `FUN_00622fe4`, line for line."""
    attack = max((a[0] + a[2]) * a[3] + a[1], ONE)
    attack *= max(a[4] + a[5], ZERO)
    attack *= max(d[3] + d[4], ZERO)
    attack *= a[8]
    if critical:
        attack *= a[6] + a[7] + ONE
    defence = max(d[0] * d[2] + d[1], ZERO)
    out = attack - defence
    if out > ZERO:
        out *= node
        out -= out * max(d[5], ZERO)
    return max(out, ONE)


# -- what a run holds on to -------------------------------------------------


class Fighter:
    """One side's numbers, built once per run rather than per swing."""

    def __init__(self, tree, cls: str = 'sw', progress: int = 0):
        self.cls = _class(cls)
        self.growth, self.weapons = Growth(tree), Weapons(tree)
        row = self.growth.row(self.cls, progress)
        self.atk, self.def_, self.hp = float(row[0]), float(row[1]), int(row[2])
        self.add = self.weapons.attack(self.cls)
        self.level = self.growth.level(progress)
        self.critical_factor = ZERO
        self.critical_rate = ZERO

    def parameters(self, p: dict) -> None:
        """The class JSON's own two critical numbers."""
        self.critical_factor = float(p.get('dmg_critical_factor', ZERO) or 0)
        self.critical_rate = float(p.get('cri', ZERO) or 0)

    def attack_on(self, ratio: float) -> list[float]:
        return attack_terms(self.atk, self.add, ratio, self.critical_factor)


def region_of(regions: list, part: str) -> dict | None:
    for r in regions:
        if r['name'] == part:
            return r
    return None


def region_terms(region: dict | None, level: int, cls: str) -> tuple:
    """A region's flat modifier and its multiplier for this class.

    Both are readings; see the header. `region_lv` picks the row of the
    eight, and the six multipliers are taken in the class order the disc's
    own job numbering sorts them into.
    """
    if region is None:
        return ZERO, ONE
    lv = max(0, min(int(level), 7))
    flat = float(region['defence'][lv])
    who = _class(cls)
    at = BYCLASS.index(who) if who in BYCLASS else 0
    mul = float(region['byclass'][at])
    return flat, mul


# -- the tool ---------------------------------------------------------------


def cmd_table(tree) -> int:
    g = Growth(tree)
    print('ccparamobj.bin: %d classes, %d thresholds' % (len(g.rows),
                                                         len(g.steps)))
    for cls in BYCLASS:
        rows = g.rows.get(cls, [])
        if rows:
            print('  %-3s row 0 %6.0f %6.0f %6d   row %d %6.0f %6.0f %6d'
                  % (cls, rows[0][0], rows[0][1], rows[0][2], len(rows) - 1,
                     rows[-1][0], rows[-1][1], rows[-1][2]))
    return 0


def cmd_show(tree, cls='sw', progress='11000') -> int:
    f = Fighter(tree, cls, int(progress))
    print('%s at progress %s: row %d' % (f.cls, progress, f.level))
    print('  atk %.0f from the growth table, %.0f from the starting weapon'
          % (f.atk, f.add))
    print('  def %.0f, hp %d' % (f.def_, f.hp))
    a = f.attack_on(ONE)
    d = defence_terms(80.0)
    print('  against def 80 with a ratio of 1: %.1f' % resolve(a, d))
    return 0


def cmd_against(tree, kind, cls='sw', tier='0', progress='11000') -> int:
    """One class against one monster, part by part."""
    from fight import load_json                                # noqa: PLC0415
    root = pathlib.Path(tree)
    js = root / 'monster.cpk' / kind / (kind + '.json')
    ob = root / 'monster.cpk' / kind / 'objbin.bin'
    if not js.is_file() or not ob.is_file():
        print('no such monster: %s' % kind)
        return 1
    p = load_json(js, tier)
    regions = region_rows(Elbn(ob.read_bytes(), ob.name))
    f = Fighter(tree, cls, int(progress))
    lv = int(p.get('region_lv', 0) or 0)
    hp = float(p.get('hp', 0) or 0)
    print('%s tier %s: hp %.0f  def %.0f  region_lv %d'
          % (kind, tier, hp, float(p.get('def', 0) or 0), lv))
    print('%s: atk %.0f + %.0f' % (f.cls, f.atk, f.add))
    a = f.attack_on(ONE)
    for r in regions:
        flat, mul = region_terms(r, lv, cls)
        d = defence_terms(float(p.get('def', 0) or 0), flat, mul)
        one = resolve(a, d)
        print('  %-16s flat %7.0f  mul %5.2f  ->  %8.1f a hit, %6.0f hits'
              % (r['name'], flat, mul, one, hp / one if one else 0))
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'table' and len(rest) == 1:
        return cmd_table(*rest)
    if cmd == 'show' and 1 <= len(rest) <= 3:
        return cmd_show(*rest)
    if cmd == 'against' and 2 <= len(rest) <= 5:
        return cmd_against(*rest)
    print(__doc__)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
