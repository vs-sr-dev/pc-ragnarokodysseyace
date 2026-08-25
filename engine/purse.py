"""
purse.py - what a quest pays, drawn.

[`mission.py`](mission.py) closes an arena and hands back nothing: the script
counts the kills, opens the gate, and the run walks on with empty hands. This
is the other half - the nine tables
[`format_reward.md`](../docs/format_reward.md) reads, turned into a draw
against their own chances.

    python engine/purse.py draw  extract/tree q00102 [class] [seed]
    python engine/purse.py rolls extract/tree q00102 [class] [times]

Four things pay, and every one of them is a table the disc already joins to
something the run has:

    the quest finishes    item_reward.bin      one column at a time
    a part breaks off     item_reward_region.bin  indexed by region_data_brk
    a monster dies        its own it_drop table, out of its JSON
    a script says so      cfAddItem(id, n), ten call sites

## The column is the draw, and the row is one of its alternatives

A reward block is ten columns wide, and **the entries down a column are
alternatives with one distribution between them**: 4,022 of 4,022 columns of
`item_reward.bin` sum to at most 10,000 and 561 to exactly it. So a pay-out
is one roll per column, and the part of the column that is left over is the
chance it pays nothing. `it_drop_db_<id>.bin` is built the same way with
eight columns, and 1,930 of its columns are **gated**: a top entry that names
no item, whose chance is whether the column fires at all, over entries that
sum to exactly 10,000.

## What the run declares, and what it reads

Three things here are the run's and the rest is the disc's:

- **which block.** The head of an `item_reward.bin` block is a story-progress
  threshold in the same number space `cfGetMainCounter` returns, and the
  player takes the last block at or below where they are. Where they are is
  the quest's own requirement out of `chapter.bin` `+0x08`, or the host's
  floor of 11000 where the quest requires nothing - so **no quest reaches its
  second block on a first run**, and that is the disc's arrangement rather
  than this file's: of the 22 two-block quests that grant a progress value of
  their own, **17 have their second block at exactly that value**. The later
  block is what a replay pays;
- **which kinds.** Byte 7 of an entry selects a *variant of the same column*
  - kind 2's and kind 3's items are a subset of kind 0's on 1,510 of 1,527
  columns, at 0.40 and 0.60 of kind 0's chance and in equal or bigger stacks
  - and what picks between them is not read. This draws **kind 0**, and kind
  4 for the player's own class, which is the one selector the disc names;
- **how many landings break a part.** The same shape as `mission.py`'s
  `BLOWS`, and declared beside it.

Everything else is the table's: the item, the count, the chance, which part a
region slot is, and which drop table a monster carries.

**And one of the three used to be four.** Which *difficulty tier* a monster
pays out at was this file's `TIER = '0'` until session 30, and it is now the
disc's: a quest's `enemy.bin` row names the tier its rooms spawn at, and the
same number picks the monster's `it_drop` and the `item_reward_region.bin`
block. See [`../tools/quest.py`](../tools/quest.py)'s `tiers`.
"""
from __future__ import annotations

import collections
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'tools'))

import reward                                                  # noqa: E402

# How many landed volumes a breakable part survives. Policy, like `BLOWS`.
BREAKS = 2
# Where the story counter starts, which is `host.py`'s own floor.
PROGRESS = 11000
# The monster JSON record to fall back to when nothing names a tier. It is
# not a policy any more: a quest's `enemy.bin` row names the tier its rooms
# spawn at - see `quest.py`'s `tiers` - and the engine passes it in. This is
# what a monster met outside a quest is.
TIER = '0'

_ITEMS: dict = {}
_CARDS: dict = {}


def items_of(tree) -> dict:
    """`reward.items` reads fifteen tables and their message files; a run of
    431 quests must not pay for that 431 times."""
    key = str(tree)
    if key not in _ITEMS:
        _ITEMS[key] = reward.items(tree)
    return _ITEMS[key]


def card_of(tree, quest: str):
    key = str(tree)
    if key not in _CARDS:
        _CARDS[key] = {c.quest: c for c in reward.catalog(tree)}
    return _CARDS[key].get(quest)


def drops_of(tree, kind: str, tier: str = TIER):
    """A monster's own drop table, off the `it_drop` of the tier it is at.

    The record is the base merged with the tier, the way the game reads one,
    and a tier that carries no `it_drop` of its own inherits the base's.
    """
    p = pathlib.Path(tree) / 'monster.cpk' / kind / (kind + '.json')
    if not p.is_file():
        return None
    try:
        rec = json.loads(p.read_text(encoding='utf-8', errors='replace'))
    except ValueError:
        return None
    got = dict(rec.get('0') or {})
    if str(tier) != '0':
        got.update(rec.get(str(tier)) or {})
    if 'it_drop' not in got:
        got = next((v for v in rec.values()
                    if isinstance(v, dict) and 'it_drop' in v), None) or {}
    if 'it_drop' not in got:
        return None
    return reward.drop_table(tree, int(got['it_drop']))


class Purse:
    """One player's take from one quest.

    Holds what came out and where from, and nothing else: the rolling is
    here, the deciding is the caller's.
    """

    def __init__(self, tree, quest: str, cls: int = 7, seed: int = 1,
                 multi: bool = False, progress: int = 0):
        self.tree = pathlib.Path(tree)
        self.quest = quest
        self.cls = cls
        self.multi = multi
        self.rng = random.Random(seed)
        self.items: collections.Counter = collections.Counter()
        self.zeny = 0
        self.took: list = []            # (why, item, count)
        self.log: collections.Counter = collections.Counter()
        self.card = card_of(tree, quest)
        self.progress = progress or (self.card.progress if self.card
                                     and self.card.progress else PROGRESS)
        pac = self.tree / 'quest.cpk' / (quest + '.pac')
        leaf = ('item_reward_multi.bin' if multi else 'item_reward.bin')
        p = pac / leaf
        self.blocks = list(reward.blocks(p, True)) if p.is_file() else []
        self.block = reward.at_progress(self.blocks, self.progress)
        self.regions: dict = {}
        p = pac / 'item_reward_region.bin'
        if p.is_file():
            by_kind: dict = {}
            for b in reward.blocks(p, False):
                if b.monster is None:
                    continue
                by_kind.setdefault(reward.monster_dir(b.monster),
                                   {})[b.head[2]] = b
            # A region block's third head word is the monster's **difficulty
            # tier**, in the same numbering its own JSON keys use - 194 of
            # 194 monster blocks name tiers that monster declares, and the
            # table ships one block per tier. So the block to take is the
            # tier the fight is playing, which `enemy.bin` now names: 159 of
            # 168 monsters here carry exactly the pair their own row does.
            # The whole set is kept and `broke` picks out of it.
            self.regions = by_kind
        self._drops: dict = {}
        self._paid = False

    # -- the four things that pay ------------------------------------------

    def add(self, item: int, count: int = 1, why: str = 'a script') -> None:
        """`cfAddItem(id, n)`, and the tail of every draw below."""
        self.items[item] += count
        self.took.append((why, item, count))
        self.log[why] += 1

    def finish(self) -> list:
        """The quest is over: its zeny and one pay-out of its block."""
        if self._paid:
            return []
        self._paid = True
        if self.card:
            self.zeny += self.card.zeny
        if self.block is None:
            self.log['the quest ships no reward table'] += 1
            return []
        got = reward.draw(self.block, self.rng,
                          lambda k, a: k == 0 or (k == 4 and a == self.cls))
        for _, e in got:
            self.add(e.item, e.count, 'the quest')
        return [e for _, e in got]

    def broke(self, kind: str, part: int, tier: str = TIER) -> list:
        """A breakable part came off: the quest's own override for that slot.

        `part` is the index into the monster's `region_data_brk`, which is
        exactly what byte 7 of a region entry holds - 298 of 298 blocks carry
        the values `0 .. n-1` and no others. `tier` picks between the blocks
        the table ships for this monster; where it names none, the lowest.
        """
        got = self.regions.get(kind)
        if not got:
            self.log['a part broke and no region table names it'] += 1
            return []
        want = int(tier) if int(tier) in got else min(got)
        if int(tier) not in got:
            self.log['a part broke at a tier its table does not block'] += 1
        b = got[want]
        got = reward.draw(b, self.rng, lambda k, a, w=part: k == w)
        for _, e in got:
            self.add(e.item, e.count, 'a broken part')
        return [e for _, e in got]

    def killed(self, kind: str, tier: str = TIER) -> list:
        """A monster died: its own `it_drop` table, gates and all.

        `tier` is the difficulty record the quest spawned it at, and it is
        part of the key because two rooms of one quest may want two tiers.
        """
        key = (kind, str(tier))
        if key not in self._drops:
            self._drops[key] = drops_of(self.tree, kind, tier)
        d = self._drops[key]
        if d is None:
            self.log['a monster died and carries no drop table'] += 1
            return []
        got = d.draw(self.rng)
        for _, item in got:
            self.add(item, 1, 'a monster')
        return got

    def crate(self, table: int) -> list:
        """A crate was broken: `destructible.bin` `+0x28` names the table."""
        if table in (0, reward.NONE32):
            return []
        key = 'crate:%d' % table
        if key not in self._drops:
            self._drops[key] = reward.drop_table(self.tree, table)
        d = self._drops[key]
        if d is None:
            return []
        got = d.draw(self.rng)
        for _, item in got:
            self.add(item, 1, 'a crate')
        return got

    # -- what came out -----------------------------------------------------

    def lines(self) -> list:
        it = items_of(self.tree)
        why = collections.defaultdict(collections.Counter)
        for w, item, n in self.took:
            why[w][item] += n
        out = []
        for w in sorted(why):
            for item, n in why[w].most_common():
                kind, name = it.get(item, ('?', ''))
                out.append('%-14s %-7d %-9s %-28.28s x%d'
                           % (w, item, kind, name, n))
        return out

    def report(self, show=print) -> None:
        show('  the purse: %d zeny, %d items of %d kinds'
             % (self.zeny, sum(self.items.values()), len(self.items)))
        if self.block is not None:
            show('    the block from %d, of %d, at progress %d'
                 % (self.block.progress, len(self.blocks), self.progress))
        for ln in self.lines():
            show('    ' + ln)
        if self.log:
            show('    %s' % ', '.join('%s %d' % (k, v)
                                      for k, v in sorted(self.log.items())))


# -- the commands -----------------------------------------------------------


def cmd_draw(tree, quest='q00102', cls='7', seed='1') -> int:
    """One quest paid once, as if it had just been finished."""
    p = Purse(tree, quest, int(cls), int(seed))
    print()
    print('  %s as the %s, seed %s'
          % (quest, reward.CLASSES.get(int(cls), cls), seed))
    p.finish()
    for kind, b in sorted(p.regions.items()):
        for part in sorted({k[1] for k in b.columns}):
            p.broke(kind, part)
    p.report()
    return 0


def cmd_rolls(tree, quest='q00102', cls='7', times='1000') -> int:
    """The same quest paid many times, which is how a chance is read back.

    Nothing on the disc says what a table means by 10,000; this is the check
    that the reading gives back the number that was written.
    """
    n = int(times)
    got: collections.Counter = collections.Counter()
    zeny = 0
    for i in range(n):
        p = Purse(tree, quest, int(cls), seed=i + 1)
        p.finish()
        zeny += p.zeny
        got.update(p.items)
    it = items_of(tree)
    ref = Purse(tree, quest, int(cls))
    want = {}
    if ref.block is not None:
        for key, ents in ref.block.columns.items():
            if key[1] not in (0, 4) or (key[1] == 4 and key[2] != int(cls)):
                continue
            for e in ents:
                want[e.item] = want.get(e.item, 0) + e.rate * e.count
    print()
    print('  %s paid %d times as the %s: %d zeny a run'
          % (quest, n, reward.CLASSES.get(int(cls), cls), zeny // max(n, 1)))
    print('    %-7s %-9s %-28s %8s %8s' % ('item', 'table', 'name',
                                           'written', 'drawn'))
    for item, total in sorted(want.items(), key=lambda kv: -kv[1]):
        kind, name = it.get(item, ('?', ''))
        print('    %-7d %-9s %-28.28s %8.3f %8.3f'
              % (item, kind, name, total / 10000.0, got[item] / n))
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    cmd, rest = a[0], a[1:]
    if cmd == 'draw':
        return cmd_draw(*rest)
    if cmd == 'rolls':
        return cmd_rolls(*rest)
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
