"""
reward.py - the quest catalog, and what finishing a quest pays.

[`quest.py`](format_quest.md) reads the four tables that put the monsters in
the room. It stops where the fight does: the quest completes and hands back
nothing. What it hands back is in nine more tables, eight of them in the
quest's own `.pac` and one shared. Full write-up in
[`format_reward.md`](../docs/format_reward.md); the joins are all in `xref`.

    common.pac/chapter.bin   the catalog: every quest, once, with its name
    q<NNNNN>.bin             where the quest starts
    item_reward.bin          the drops, and item_reward_multi.bin the same
                             table with multiplayer odds
    item_reward_region.bin   the drops off a broken part
    destructible.bin         the breakable scenery, and its drop table
    mapexception.bin         a route this quest reroutes
    enemy_ref.bin            which of enemy02..04 a generator reads
    weapon_decost.bin        four numbers, twice

## `chapter.bin` is the catalog and the join is a byte pair

711 rows of 92 bytes. Byte 0 is a record kind - **431 rows carry 0 and 280
carry 1**, a kind-1 row being a continuation of the one above - and on a
kind-0 row the next two bytes are a chapter and an index. `q0<chapter><index>`
**names a quest pac on all 431, and the 431 pacs are named exactly once
each**: a closed bijection, and the only reading of those two bytes that gives
one. The rest of the row:

    +0x04  u16   the quest flag this one requires, or 0xFFFF
    +0x06  u16   its own quest flag - what checkQuestClearByIDFlag asks about
    +0x08  u16   a story-progress threshold: 0, or 11000 .. 24000
    +0x0C  u16   the time limit in seconds: 600, 900, 1200, 1800
    +0x0E  u8    a rank, 1..15
    +0x10  u32   a quest item to collect, 100001..100010, or 0xFFFFFFFF
    +0x14  u8    how many of it
    +0x18  x4    four objectives: u32 monster, u16 how many, u16 pad
    +0x38  i32   the zeny it pays, 100 .. 50,000
    +0x3C  i32   eight message ids into `msg_quest.bin`

The **monster word is the same `01 hh h0 00` twelve-bit field `enemy.bin`
uses** - 553 of 553 name a `monster.cpk` directory, with the low nibble zero
on all 553. Two tables, two consumers, one namespace.

## A reward entry is sixteen bytes, and byte 7 says what the next word is

`item_reward.bin` is 164 bytes a row: a `u32` head and then **ten entries of
sixteen**. `item_reward_region.bin` is 92: three `u32` of head and then ten
entries of **eight**, which is the same entry with the tail cut off. The head
is written once at the top of a block and inherited down it.

    +0x00  u32   the item id
    +0x04  u16   its chance, in ten-thousandths
    +0x06  u8    how many
    +0x07  u8    a kind; in a region table, which broken part
    +0x08  u32   on kind 4 a player class; on kind 2 a round number; else 0

**38,018 of the 38,025 item ids name a row of an `it_db_*.bin`**, whose bands
the disc keeps disjoint - and every one of the seven that do not is item id 0.

**Kind 4's word is the player class, and the item is that class's weapon.**
`it_db_weapon.bin` column 5 is 0, 1, 3, 4, 5 or 7, seventy-five weapons each;
the word after the selector takes those same six values, and the two agree on
**822 of 822** entries in each of the two files.

**A region entry's byte 7 is the broken part.** Over the 298 blocks that carry
entries, its values are exactly `0 .. n-1` for the monster's own
`region_data_brk` record count, read out of an `ELBN` by a different reader -
298 of 298, none missing and none over.

## The multiplayer table is the same table with different odds

`item_reward_multi.bin` aligns with `item_reward.bin` row for row and slot for
slot: **17,229 of 17,300 aligned entries carry the same item, count, kind and
word, and only the chance differs**, on 12,153 of them - and it is the better
chance on 10,730 of those. `item_reward_region.bin` does the same inside one
file: its region id is even for one table and odd for the other, 198 blocks
each and every even one paired.

Usage:
  python reward.py check   <dir>          every table parses, with counts
  python reward.py xref    <dir>          the joins, one line each
  python reward.py catalog <dir>          all 431 quests, named
  python reward.py card    <dir> <quest>  one quest: its brief and its pay
  python reward.py drops   <dir> <quest>  its reward tables, item by item
  python reward.py items   <dir>          the reward item ids, by table
  python reward.py props   <dir> [quest]  the breakable scenery, with its drops
  python reward.py draw    <dir> <quest> [class] [seed]   one pay-out, drawn
  python reward.py sources <dir>          the encyclopedia against the tables
"""

from __future__ import annotations

import collections
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import rmsg                                                    # noqa: E402
from ech import Ech                                            # noqa: E402

CATALOG = 'quest.cpk/common.pac/chapter.bin'
MESSAGES = 'menu.cpk/msg_field.en.pac/msg_quest.bin'
ITEM_DB = 'item.cpk/it_db.pac'
ITEM_NAMES = 'item.cpk/it_db.en.pac'
DROP_TABLES = 'item.cpk/it_drop.pac/it_drop_table.pac'
DICTIONARY = 'dictionary.cpk/dc_db.pac/dc_db_monster.bin'
DICTIONARY_TEXT = 'dictionary.cpk/dc_db.en.pac/dc_db_text_monster.rmsg'
ITEM_TEXT = 'item.cpk/it_db.en.pac'
NONE32 = 0xFFFFFFFF
NONE16 = 0xFFFF

# The it_db tables whose first column is a disjoint id band. The others -
# ability, myorder, skill_group, the evolution tables - number their rows from
# zero, so an id resolves against them by accident and never on purpose.
BANDS = ('weapon', 'hair', 'equip', 'hg', 'material', 'bottle', 'card',
         'instant', 'skill', 'skin', 'voice', 'face', 'bgm', 'ace_skill',
         'charge')

REWARDS = ('item_reward.bin', 'item_reward_multi.bin',
           'item_reward_region.bin')

# `it_db_weapon.bin` column 5, named by its own weapons - see
# combat_loop.md. Kind 4 of a reward entry writes the same six numbers.
CLASSES = {0: 'assassin', 1: 'cleric', 3: 'hammersmith', 4: 'hunter',
           5: 'mage', 7: 'warrior'}
OTHERS = ('weapon_decost.bin', 'destructible.bin', 'mapexception.bin',
          'enemy_ref.bin')


# --------------------------------------------------------------------------
# the pieces

def monster_of(word: int):
    """`01 hh h0 00`, the twelve-bit monster id `enemy.bin` writes."""
    if word == NONE32 or word == 0 or (word >> 24) != 1 or (word & 0xF):
        return None
    return (word >> 12) & 0xFFF


def monster_dir(mid: int) -> str:
    base, tag = (2000, 'b') if mid >= 2000 else (1000, 'z')
    return '%s%02d_%02d' % (tag, (mid - base) // 10, (mid - base) % 10)


class Entry:
    """One reward slot: an item, its odds, and a selector that says what the
    word after it means."""

    __slots__ = ('item', 'rate', 'count', 'kind', 'arg')

    def __init__(self, buf: bytes, off: int, wide: bool = True):
        self.item, self.rate, self.count, self.kind = struct.unpack_from(
            '>IHBB', buf, off)
        self.arg = struct.unpack_from('>I', buf, off + 8)[0] if wide else 0

    def __bool__(self) -> bool:
        return bool(self.item or self.rate or self.count or self.kind
                    or self.arg)

    @property
    def player_class(self):
        """Kind 4 restricts the item to one class - `it_db_weapon.bin`
        column 5's own numbering."""
        return self.arg if self.kind == 4 else None

    def text(self, items=None) -> str:
        who = ('' if self.player_class is None else
               ' %s only' % CLASSES.get(self.arg, self.arg))
        if self.kind == 2 and self.arg:
            who = ' [%d]' % self.arg
        name = (items or {}).get(self.item, ('?', ''))
        return '%-7d %-9s %-28.28s x%-3d %6.2f%%%s' % (
            self.item, name[0], name[1], self.count, self.rate / 100.0, who)


class Card:
    """One kind-0 row of `chapter.bin`: a quest, as the catalog has it."""

    def __init__(self, row: bytes, index: int):
        self.row, self.at = row, index
        self.chapter, self.index = row[1], row[2]
        self.quest = 'q0%02d%02d' % (self.chapter, self.index)
        self.needs, self.flag = struct.unpack_from('>HH', row, 4)
        self.progress = struct.unpack_from('>H', row, 8)[0]
        self.time = struct.unpack_from('>H', row, 12)[0]
        self.rank = row[14]
        item = struct.unpack_from('>I', row, 16)[0]
        self.item = None if item == NONE32 else (item, row[20])
        self.zeny = struct.unpack_from('>i', row, 56)[0]
        self.msg = list(struct.unpack_from('>8i', row, 60))
        self.targets = []
        for k in range(4):
            word, n = struct.unpack_from('>IH', row, 24 + 8 * k)
            mid = monster_of(word)
            if mid is not None:
                self.targets.append((mid, n))
        self.extra = []                     # the kind-1 rows underneath


def _leaf(root, path: str):
    p = pathlib.Path(root) / path
    return p.read_bytes() if p.is_file() else None


def catalog(root) -> list:
    """Every quest the catalog lists, with the continuation rows folded into
    the quest above - which is what the kind byte is for."""
    blob = _leaf(root, CATALOG)
    if blob is None:
        raise SystemExit('not found: ' + CATALOG)
    t = Ech(blob, CATALOG)
    out, last = [], None
    for i in range(t.rows):
        row = t.row(i)
        if row[0] == 0:
            last = Card(row, i)
            out.append(last)
        elif last is not None:
            last.extra.append(Card(row, i))
    return out


def messages(root) -> list:
    blob = _leaf(root, MESSAGES)
    return [m[1] for m in rmsg.Rmsg(blob, MESSAGES).messages] if blob else []


def items(root) -> dict:
    """id -> (which it_db table, the game's own English for it). The id bands
    are disjoint, so one dictionary is enough."""
    base = pathlib.Path(root) / ITEM_DB
    out = {}
    for kind in BANDS:
        p = base / ('it_db_%s.bin' % kind)
        if not p.is_file():
            continue
        ids = Ech(p.read_bytes(), p.name).lane(0)
        nm = pathlib.Path(root) / ITEM_NAMES / ('it_db_name_%s.rmsg' % kind)
        names = ([m[1] for m in rmsg.Rmsg(nm.read_bytes(), nm.name).messages]
                 if nm.is_file() else [])
        for k, v in enumerate(ids):
            out[v] = (kind, names[k] if k < len(names) else '')
    return out


def quests(root, want: str = ''):
    """Every `q<NNNNN>.pac` that ships any of the tables here."""
    base = pathlib.Path(root) / 'quest.cpk'
    for pac in sorted(base.glob('q*.pac')):
        name = pac.name[:-4]
        if want and want not in name:
            continue
        files = {p.name: p for p in pac.iterdir() if p.is_file()}
        yield name, pac, files


def reward_rows(path: pathlib.Path, wide: bool = True):
    """A reward table as (head, entries). The head is written once at the top
    of a block and inherited down it, the way `enemy_gen.bin` writes a stage:
    for `item_reward.bin` it is one progress threshold, for
    `item_reward_region.bin` a monster and a region."""
    t = Ech(path.read_bytes(), path.name)
    step, first = (16, 4) if wide else (8, 12)
    head = (0,) if wide else (0, 0, 0)
    for i in range(t.rows):
        row = t.row(i)
        got = struct.unpack_from('>I' if wide else '>III', row, 0)
        if wide:
            if got[0]:
                head = got
        elif got[1]:
            # the progress id is written once at the top of the file, the
            # monster and the region once at the top of each block
            head = (got[0] or head[0], got[1], got[2])
        ent = [Entry(row, o, wide)
               for o in range(first, t.row_size - step + 1, step)]
        ent = [e for e in ent if e]
        if ent or any(got):
            yield head, row, ent


# --------------------------------------------------------------------------
# the grid: a reward table read down its columns rather than across its rows


def selector(e: Entry, wide: bool = True) -> tuple:
    """What splits a column into draws that are independent of each other.

    In `item_reward.bin` it is the kind byte, with **kind 4 split further by
    the class it names**: six class-restricted weapons stacked in one column
    are six certainties, not one distribution that sums to six. In a region
    table byte 7 is the broken part instead, and that is the whole selector.
    """
    if not wide:
        return (e.kind,)
    return (e.kind, e.arg) if e.kind == 4 else (e.kind, 0)


class Block:
    """One block of a reward table, as a grid instead of as a list of rows.

    The head is written once at the top and inherited down it. What is under
    it is ten **columns** of sixteen bytes, and the column is the unit: the
    entries down one are alternatives with one distribution between them, and
    a row is one alternative of each. See `format_reward.md`.
    """

    __slots__ = ('head', 'columns', 'rows')

    def __init__(self, head):
        self.head = head
        self.rows = 0
        self.columns: dict = {}

    @property
    def progress(self) -> int:
        return self.head[0]

    @property
    def monster(self):
        """The region table's block head names one; `item_reward.bin`'s does
        not."""
        return monster_of(self.head[1]) if len(self.head) > 1 else None

    def add(self, col: int, e: Entry, wide: bool) -> None:
        self.columns.setdefault((col,) + selector(e, wide), []).append(e)

    def total(self, key) -> int:
        return sum(e.rate for e in self.columns[key])


def blocks(path: pathlib.Path, wide: bool = True):
    """A reward table as `Block`s.

    The entry is sixteen bytes wide and eight in a region table, and there
    are always ten of them, so the head is whatever the row has left over -
    four bytes in a quest's `item_reward.bin` and eight in the endless
    dungeon's, which is the same record with a wider head.
    """
    t = Ech(path.read_bytes(), path.name)
    step = 16 if wide else 8
    first = t.row_size - 10 * step
    if first < 4:
        raise ValueError('%s: %d bytes a row is not ten entries of %d'
                         % (path.name, t.row_size, step))
    words = first // 4
    head = (0,) * max(words, 1)
    cur = None
    for i in range(t.rows):
        row = t.row(i)
        got = struct.unpack_from('>%dI' % words, row, 0)
        # `item_reward.bin` writes one number at the top of a block;
        # `item_reward_region.bin` writes the progress once at the top of the
        # file and the monster and the region at the top of each block.
        if (got[1] if words > 1 else got[0]):
            if cur is not None:
                yield cur
            head = (got[0] or head[0],) + got[1:] if words > 1 else got
            cur = Block(head)
        elif words > 1 and got[0]:
            head = (got[0],) + head[1:]
        if cur is None:
            cur = Block(head)
        cur.rows += 1
        for c in range(10):
            e = Entry(row, first + step * c, wide)
            if e:
                cur.add(c, e, wide)
    if cur is not None:
        yield cur


def at_progress(bs: list, progress: int):
    """The block the player is in: the last one at or below where they are.

    The head is a story-progress threshold in the same number space
    `cfGetMainCounter` returns, so this is a lookup and not a policy - except
    for a player standing below every threshold, who gets the first block
    because a quest that pays nothing at all is not a reading anyone would
    write.
    """
    got = None
    for b in bs:
        if b.progress <= progress:
            got = b
    return got or (bs[0] if bs else None)


def draw(block: Block, rng, keep=None) -> list:
    """One pay-out of a block: **at most one item out of each column**.

    A column's entries are alternatives in row order and their chances are
    one distribution over ten thousand - 4,022 of 4,022 columns of
    `item_reward.bin` sum to at most 10,000 and 561 to exactly it - so the
    roll lands in one entry's window or in none of them, and the leftover is
    the chance that the column pays nothing.

    `keep(kind, arg)` says which of a column's draws this pay-out takes: the
    kind byte selects a variant of the same column, and what its values 0, 2
    and 3 mean is not read. Returns `(key, entry)` pairs in column order.
    """
    out = []
    for key, ents in block.columns.items():
        kind = key[1]
        arg = key[2] if len(key) > 2 else 0
        if keep is not None and not keep(kind, arg):
            continue
        roll = rng.randrange(10000)
        at = 0
        for e in ents:
            at += e.rate
            if roll < at:
                out.append((key, e))
                break
    return out


# --------------------------------------------------------------------------
# the encyclopedia, which says in English where a thing comes from


def named_monsters(root) -> dict:
    """`monster.cpk` directory -> the name the encyclopedia gives it.

    `dc_db_monster.bin`'s second word is the same `01 hh h0 00` twelve-bit
    monster id `enemy.bin` and `chapter.bin` write, and
    `dc_db_text_monster.rmsg` holds twice as many messages as the table has
    rows: the names first and the descriptions after, in the same order.
    """
    blob = _leaf(root, DICTIONARY)
    txt = _leaf(root, DICTIONARY_TEXT)
    if blob is None or txt is None:
        return {}
    t = Ech(blob, DICTIONARY)
    names = [m[1] for m in rmsg.Rmsg(txt, DICTIONARY_TEXT).messages]
    out = {}
    for i in range(t.rows):
        mid = monster_of(struct.unpack_from('>I', t.row(i), 4)[0])
        if mid is not None and i < len(names):
            out.setdefault(monster_dir(mid), names[i].strip())
    return out


def sources(root) -> dict:
    """item id -> (the tag, the names under it), off `it_db_text_*.rmsg`.

    An item's encyclopedia entry ends in a tagged block - `{{Dropped by}}`
    and a monster, `{{Acquired from}}` and a place. The text files pair
    positionally with the `it_db_*.bin` they describe, which is how a row
    gets its name at all, so the tag lands on an item id.
    """
    base = pathlib.Path(root) / ITEM_DB
    txt = pathlib.Path(root) / ITEM_TEXT
    out = {}
    for kind in BANDS:
        tab, doc = base / ('it_db_%s.bin' % kind), txt / (
            'it_db_text_%s.rmsg' % kind)
        if not (tab.is_file() and doc.is_file()):
            continue
        ids = Ech(tab.read_bytes(), tab.name).lane(0)
        ts = [m[1] for m in rmsg.Rmsg(doc.read_bytes(), doc.name).messages]
        if len(ids) != len(ts):
            continue                    # `card`: 1,471 rows and 677 texts
        for i, item in enumerate(ids):
            head, _, tail = ts[i].partition('{{')
            tag, _, body = tail.partition('}}')
            if not tag:
                continue
            who = [ln.strip() for ln in body.strip().split('\n')
                   if ln.strip()]
            out[item] = (tag, who)
    return out


class Drops:
    """`it_drop_db_<id>.bin` - what a monster drops, and what is in a crate.

    579 tables, and every one is the same grid `item_reward.bin` is: a `u32`
    id and then **eight columns** of `(kind, item, chance)`, with the rows
    under a column its alternatives. Two things are written once and
    inherited down a column, the way a block head is inherited down a block:

    - **the kind**, on 4,369 of 4,369 columns, and no column repeats it
      lower down;
    - **the gate.** A column whose top entry names no item is a two-step
      draw: that entry's chance is whether the column pays at all, and the
      entries under it are what comes out. **On all 1,930 gated columns the
      entries under the gate sum to exactly 10,000** - a closed
      distribution - and on all 2,439 ungated ones the whole column sums to
      at most 10,000.

    Kinds 1, 3 and 5 are the ones that gate, and they are the columns that
    pay a weapon or a card; 0, 2, 4 and 8 never gate and pay a material or a
    bottle. **26,237 of the 26,251 item ids name an `it_db` row and the
    fourteen that do not are the ten quest items** 100001..100010, which
    `it_db_name_quest.rmsg` holds and the catalog collects.
    """

    __slots__ = ('id', 'columns')

    def __init__(self, path: pathlib.Path):
        t = Ech(path.read_bytes(), path.name)
        self.id = struct.unpack_from('>I', t.row(0), 0)[0]
        self.columns = []
        for c in range(8):
            col = []
            for i in range(t.rows):
                kind, item, rate = struct.unpack_from(
                    '>3I', t.row(i), 4 + 12 * c)
                if item == NONE32 and rate in (0, NONE32):
                    continue
                col.append((None if kind == NONE32 else kind, item, rate))
            if not col:
                continue
            gate = col[0][2] if col[0][1] == NONE32 else None
            self.columns.append({
                'kind': col[0][0], 'gate': gate,
                'entries': [(i, r) for _, i, r in
                            (col[1:] if gate is not None else col)]})

    def items(self) -> set:
        return {i for c in self.columns for i, _ in c['entries']}

    def draw(self, rng) -> list:
        """One drop: at most one item out of each column."""
        out = []
        for c in self.columns:
            if c['gate'] is not None and rng.randrange(10000) >= c['gate']:
                continue
            roll, at = rng.randrange(10000), 0
            for item, rate in c['entries']:
                at += rate
                if roll < at:
                    out.append((c['kind'], item))
                    break
        return out


def drop_table(root, table: int):
    p = pathlib.Path(root) / DROP_TABLES / ('it_drop_db_%d.bin' % table)
    return Drops(p) if p.is_file() else None


def drop_items(root, table: int) -> set:
    d = drop_table(root, table)
    return d.items() if d is not None else set()


def props(path: pathlib.Path):
    """`destructible.bin` - the breakable scenery. The stage is written once
    at the head of a block and inherited down it, the way `enemy_gen.bin`
    writes one."""
    t = Ech(path.read_bytes(), path.name)
    stage = None
    for i in range(t.rows):
        row = t.row(i)

        def st(o):
            v = struct.unpack_from('>I', row, o)[0]
            return t.text(v) if t.pool and t.is_pool_offset(v) else None

        stage = st(0) or stage
        yield dict(stage=stage, kind=st(8), name=st(12), marker=st(16),
                   drop=struct.unpack_from('>I', row, 0x28)[0],
                   on_break=st(0x38))


# --------------------------------------------------------------------------
# the commands

def cmd_check(root) -> int:
    cards = catalog(root)
    msgs = messages(root)
    known = {name for name, _, _ in quests(root)}
    named = sum(1 for c in cards if c.quest in known)
    print('chapter.bin: %d quests, %d continuation rows'
          % (len(cards), sum(len(c.extra) for c in cards)))
    print('  chapter/index names a quest pac  %4d of %4d, and %d pacs are'
          ' not named' % (named, len(cards), len(known - {c.quest
                                                         for c in cards})))
    print('  %d messages in msg_quest.bin; ids out of range %d'
          % (len(msgs), sum(1 for c in cards for v in c.msg
                            if not 0 <= v < len(msgs))))
    tab = collections.Counter()
    for name, _, files in quests(root):
        for leaf in REWARDS + OTHERS + ('%s.bin' % name,):
            if leaf in files:
                tab[leaf if not leaf.startswith('q0') else
                    'q<NNNNN>.bin'] += 1
    print()
    for leaf, n in sorted(tab.items(), key=lambda kv: -kv[1]):
        print('  %-24s %4d quests' % (leaf, n))
    it = items(root)
    print()
    print('it_db ids in a disjoint band: %d over %d tables' % (len(it),
                                                              len(BANDS)))
    n = collections.Counter()
    for name, _, files in quests(root):
        for leaf in REWARDS:
            if leaf not in files:
                continue
            wide = leaf != 'item_reward_region.bin'
            for _, _, ent in reward_rows(files[leaf], wide):
                for e in ent:
                    n[leaf] += 1
                    n[leaf + ':resolved'] += e.item in it
    for leaf in REWARDS:
        print('  %-24s %6d entries, %6d name an it_db row'
              % (leaf, n[leaf], n[leaf + ':resolved']))

    # The column is the draw - in all three of the tables that are written
    # this way. See `format_reward.md`.
    print()
    g = collections.Counter()
    for name, _, files in quests(root):
        for leaf in REWARDS:
            if leaf not in files:
                continue
            for b in blocks(files[leaf], leaf != 'item_reward_region.bin'):
                for key in b.columns:
                    g[leaf] += 1
                    g[leaf + ':<='] += b.total(key) <= 10000
                    g[leaf + ':=='] += b.total(key) == 10000
    for leaf in REWARDS:
        print('  %-22s %4d columns, %5d under 10,000, %4d on it'
              % (leaf, g[leaf], g[leaf + ':<='], g[leaf + ':==']))

    d = collections.Counter()
    for p in sorted((pathlib.Path(root) / DROP_TABLES).glob(
            'it_drop_db_*.bin')):
        t = Drops(p)
        d['tables'] += 1
        d['named after themselves'] += t.id == int(p.stem.split('_')[-1])
        for c in t.columns:
            d['columns'] += 1
            d['a kind at the head'] += c['kind'] is not None
            tot = sum(r for _, r in c['entries'])
            if c['gate'] is None:
                d['plain'] += 1
                d['plain <= 10,000'] += tot <= 10000
            else:
                d['gated'] += 1
                d['gated == 10,000'] += tot == 10000
            for item, _ in c['entries']:
                d['entries'] += 1
                d['resolved'] += item in it
    print()
    print('  %-24s %5d tables, %5d named after their own file'
          % ('it_drop_db_<id>.bin', d['tables'],
             d['named after themselves']))
    print('  %-24s %5d columns, %5d carry a kind at the head'
          % ('', d['columns'], d['a kind at the head']))
    print('  %-24s %5d gated, %5d of them sum to exactly 10,000'
          % ('', d['gated'], d['gated == 10,000']))
    print('  %-24s %5d plain, %5d of them to at most 10,000'
          % ('', d['plain'], d['plain <= 10,000']))
    print('  %-24s %5d entries, %5d name an it_db row'
          % ('', d['entries'], d['resolved']))
    return 0


def cmd_xref(root) -> int:
    cards = catalog(root)
    msgs = messages(root)
    it = items(root)
    known = {name for name, _, _ in quests(root)}
    mons = {p.name for p in (pathlib.Path(root) / 'monster.cpk').iterdir()
            if p.is_dir()}
    flags = {c.flag for c in cards if c.flag not in (0, NONE16)}

    def line(what, ok, bad):
        print('  %-42s %5d resolve, %4d do not' % (what, ok, bad))

    ok = sum(1 for c in cards if c.quest in known)
    line('chapter row -> a quest pac', ok, len(cards) - ok)
    tgt = [(m, n) for c in cards for m, n in c.targets]
    tgt += [(m, n) for c in cards for e in c.extra for m, n in e.targets]
    ok = sum(1 for m, _ in tgt if monster_dir(m) in mons)
    line('objective -> a monster directory', ok, len(tgt) - ok)
    ids = [v for c in cards for v in c.msg]
    ok = sum(1 for v in ids if 0 <= v < len(msgs))
    line('message id -> msg_quest.bin', ok, len(ids) - ok)
    need = [c.needs for c in cards if c.needs not in (0, NONE16)]
    ok = sum(1 for v in need if v in flags)
    line('prerequisite -> another quest\'s flag', ok, len(need) - ok)
    qi = [c.item for c in cards if c.item] + [e.item for c in cards
                                              for e in c.extra if e.item]
    nm = pathlib.Path(root) / ITEM_NAMES / 'it_db_name_quest.rmsg'
    n = (len(rmsg.Rmsg(nm.read_bytes(), nm.name).messages)
         if nm.is_file() else 0)
    ok = sum(1 for v, _ in qi if 100001 <= v <= 100000 + n)
    line('quest item -> it_db_name_quest.rmsg', ok, len(qi) - ok)

    ent = collections.Counter()
    wclass = {}
    p = pathlib.Path(root) / ITEM_DB / 'it_db_weapon.bin'
    if p.is_file():
        w = Ech(p.read_bytes(), p.name)
        wclass = dict(zip(w.lane(0), w.lane(5)))
    stages = {}
    gens = {}
    for name, pac, files in quests(root):
        for leaf in REWARDS:
            if leaf not in files:
                continue
            for _, _, es in reward_rows(files[leaf],
                                        leaf != 'item_reward_region.bin'):
                for e in es:
                    ent['item'] += 1
                    ent['item:ok'] += e.item in it
                    if e.kind == 4 and leaf != 'item_reward_region.bin':
                        ent['class'] += 1
                        ent['class:ok'] += wclass.get(e.item) == e.arg
        if 'item_reward_region.bin' in files:
            seen = None
            for head, row, _ in reward_rows(files['item_reward_region.bin'],
                                            False):
                if head == seen:
                    continue
                seen = head
                m = monster_of(head[1])
                if m is not None:
                    ent['region'] += 1
                    ent['region:ok'] += monster_dir(m) in mons
        if 'piecelist.bin' in files:
            t = Ech(files['piecelist.bin'].read_bytes(), 'piecelist')
            stages[name] = {t.text(struct.unpack_from('>I', t.row(i), 0)[0])
                            for i in range(t.rows)}
        if 'enemy_gen.bin' in files:
            t = Ech(files['enemy_gen.bin'].read_bytes(), 'enemy_gen')
            gens[name] = {t.text(struct.unpack_from('>I', t.row(i), 8)[0])
                          for i in range(t.rows)}
        for leaf, col, want in (('mapexception.bin', 0, stages),
                                ('mapexception.bin', 1, stages),
                                ('enemy_ref.bin', 1, gens)):
            if leaf not in files:
                continue
            t = Ech(files[leaf].read_bytes(), leaf)
            for i in range(t.rows):
                s = t.text(struct.unpack_from('>I', t.row(i), 4 * col)[0])
                key = '%s:%d' % (leaf, col)
                ent[key] += 1
                ent[key + ':ok'] += s in want.get(name, ())
        if 'enemy_ref.bin' in files:
            t = Ech(files['enemy_ref.bin'].read_bytes(), 'enemy_ref')
            for i in range(t.rows):
                s = t.text(struct.unpack_from('>I', t.row(i), 8)[0])
                ent['enemy_ref:table'] += 1
                ent['enemy_ref:table:ok'] += ('%s.bin' % s) in files

    line('reward item -> an it_db row', ent['item:ok'],
         ent['item'] - ent['item:ok'])
    line('kind 4 -> it_db_weapon.bin column 5', ent['class:ok'],
         ent['class'] - ent['class:ok'])
    line('region reward -> a monster directory', ent['region:ok'],
         ent['region'] - ent['region:ok'])
    line('mapexception from -> the quest\'s piecelist',
         ent['mapexception.bin:0:ok'],
         ent['mapexception.bin:0'] - ent['mapexception.bin:0:ok'])
    line('mapexception to   -> the quest\'s piecelist',
         ent['mapexception.bin:1:ok'],
         ent['mapexception.bin:1'] - ent['mapexception.bin:1:ok'])
    line('enemy_ref -> a generator of the quest', ent['enemy_ref.bin:1:ok'],
         ent['enemy_ref.bin:1'] - ent['enemy_ref.bin:1:ok'])
    line('enemy_ref -> a table the pac ships', ent['enemy_ref:table:ok'],
         ent['enemy_ref:table'] - ent['enemy_ref:table:ok'])

    import stage as stagemod                                   # noqa: PLC0415
    mk = {st.name: {m.name for m in st.markers}
          for st in stagemod.stages(root)}
    tables = {int(p.name[11:-4]) for p in
              (pathlib.Path(root) / DROP_TABLES).glob('it_drop_db_*.bin')}
    n = collections.Counter()
    for name, pac, files in quests(root):
        if 'destructible.bin' not in files:
            continue
        for d in props(files['destructible.bin']):
            n['marker'] += 1
            n['marker:ok'] += d['marker'] in mk.get(d['stage'], ())
            if d['drop'] != NONE32:
                n['drop'] += 1
                n['drop:ok'] += d['drop'] in tables
    line('destructible -> an ATIH marker of its stage', n['marker:ok'],
         n['marker'] - n['marker:ok'])
    line('destructible -> an it_drop_db table', n['drop:ok'],
         n['drop'] - n['drop:ok'])

    import elbn                                                # noqa: PLC0415
    parts = {}
    for d in (pathlib.Path(root) / 'monster.cpk').iterdir():
        ob = d / 'objbin.bin'
        if ob.is_file():
            f = elbn.Elbn(ob.read_bytes(), str(ob))
            parts[d.name] = len(elbn.region_rows(f, 'region_data_brk'))
    ok = bad = 0
    for name, pac, files in quests(root):
        f = files.get('item_reward_region.bin')
        if not f:
            continue
        block = collections.defaultdict(set)
        for h, row, es in reward_rows(f, False):
            for e in es:
                block[h].add(e.kind)
        for h, slots in block.items():
            m = monster_of(h[1])
            if m is None:
                continue
            if slots == set(range(parts.get(monster_dir(m), -1))):
                ok += 1
            else:
                bad += 1
    line('region slots == the monster breakable parts', ok, bad)

    a = b = c = d = 0
    for name, pac, files in quests(root):
        f = files.get('%s.bin' % name)
        if not f:
            continue
        t = Ech(f.read_bytes(), name)
        row = t.row(0)

        def st(o, t=t, row=row):
            v = struct.unpack_from('>I', row, o)[0]
            return t.text(v) if t.is_pool_offset(v) else None

        where, appear = st(4), st(8)
        a += where in stages.get(name, ())
        b += where not in stages.get(name, ())
        if appear:
            c += appear in mk.get(where, ())
            d += appear not in mk.get(where, ())
    line('quest header stage -> the quest piecelist', a, b)
    line('quest header appear -> that stage ATIH', c, d)
    return 0


def _msg(msgs, i, n=44):
    if not 0 <= i < len(msgs):
        return ''
    return msgs[i][:n].replace('\n', ' ')


def cmd_catalog(root) -> int:
    msgs = messages(root)
    for c in catalog(root):
        tgt = ' '.join('%s x%d' % (monster_dir(m), n) for m, n in c.targets)
        if c.item:
            tgt += ' item %d x%d' % c.item
        print('  %-8s ch%-3d rank %-3d %5ds %6d z  %-30.30s %-14.14s %s'
              % (c.quest, c.chapter, c.rank, c.time, c.zeny,
                 _msg(msgs, c.msg[0], 30), _msg(msgs, c.msg[1], 14), tgt))
    return 0


def cmd_card(root, want) -> int:
    msgs = messages(root)
    for c in catalog(root):
        if want not in c.quest:
            continue
        print('%s   chapter %d, index %d   (chapter.bin row %d)'
              % (c.quest, c.chapter, c.index, c.at))
        print('  %-14s %s' % ('title', _msg(msgs, c.msg[0], 60)))
        print('  %-14s %s' % ('client', _msg(msgs, c.msg[1], 60)))
        print('  %-14s %s' % ('place', _msg(msgs, c.msg[3], 60)))
        for k in (4, 5, 6, 7):
            if c.msg[k]:
                print('  %-14s %s' % ('target %d' % (k - 4),
                                      _msg(msgs, c.msg[k], 60)))
        brief = msgs[c.msg[2]] if 0 <= c.msg[2] < len(msgs) else ''
        for k, ln in enumerate(brief.split('\n')):
            print('  %-14s %s' % ('brief' if k == 0 else '', ln))
        print('  %-14s %d s' % ('time limit', c.time))
        print('  %-14s %d' % ('rank', c.rank))
        print('  %-14s %d zeny' % ('pays', c.zeny))
        if c.progress:
            print('  %-14s %d' % ('needs progress', c.progress))
        if c.needs != NONE16:
            print('  %-14s flag %d' % ('needs', c.needs))
        print('  %-14s flag %d' % ('sets', c.flag))
        for m, n in c.targets:
            print('  %-14s %s x%d' % ('objective', monster_dir(m), n))
        if c.item:
            print('  %-14s item %d x%d' % ('objective', *c.item))
        for e in c.extra:
            for m, n in e.targets:
                print('  %-14s %s x%d' % ('also', monster_dir(m), n))
            if e.item:
                print('  %-14s item %d x%d' % ('also', *e.item))
    return 0


def cmd_drops(root, want) -> int:
    it = items(root)
    for name, pac, files in quests(root, want):
        head = False
        for leaf in REWARDS:
            if leaf not in files:
                continue
            if not head:
                print(name)
                head = True
            print('  %s' % leaf)
            wide = leaf != 'item_reward_region.bin'
            block = None
            for h, row, ent in reward_rows(files[leaf], wide):
                if h != block:
                    block = h
                    if wide:
                        print('    -- from %d' % h[0])
                    else:
                        m = monster_of(h[1])
                        print('    -- %s region %d (%s)'
                              % (monster_dir(m) if m else '?', h[2] // 10,
                                 'multi' if h[2] % 10 else 'solo'))
                for e in ent:
                    print('       part %d  %s' % (e.kind, e.text(it))
                  if leaf == 'item_reward_region.bin'
                  else '       %s' % e.text(it))
        for leaf in OTHERS:
            if leaf not in files:
                continue
            t = Ech(files[leaf].read_bytes(), leaf)
            print('  %s  %d rows' % (leaf, t.rows))
            for i in range(t.rows):
                row = t.row(i)
                cols = []
                for k in range(t.row_size // 4):
                    v = struct.unpack_from('>I', row, 4 * k)[0]
                    s = t.text(v) if t.pool and t.is_pool_offset(v) else None
                    cols.append(s if s else str(v))
                print('       %s' % '  '.join(cols))
    return 0


def cmd_props(root, want) -> int:
    for name, pac, files in quests(root, want):
        if 'destructible.bin' not in files:
            continue
        print(name)
        for d in props(files['destructible.bin']):
            print('  %-12s %-14s %-12s %-9s drop %-6s %s'
                  % (d['stage'] or '', d['kind'] or '', d['name'] or '',
                     d['marker'] or '',
                     '' if d['drop'] == NONE32 else d['drop'],
                     d['on_break'] or ''))
    return 0


def cmd_items(root) -> int:
    it = items(root)
    use = collections.Counter()
    kinds = collections.Counter()
    for name, pac, files in quests(root):
        for leaf in REWARDS:
            if leaf not in files:
                continue
            for _, _, ent in reward_rows(files[leaf],
                                         leaf != 'item_reward_region.bin'):
                for e in ent:
                    use[e.item] += 1
                    kinds[it.get(e.item, ('unresolved', ''))[0]] += 1
    for k, n in kinds.most_common():
        print('  %-12s %6d entries' % (k, n))
    print('%d distinct ids, %d of them naming an it_db row'
          % (len(use), sum(1 for v in use if v in it)))
    return 0


def cmd_draw(root, want, cls='7', seed='1') -> int:
    """One pay-out of one quest, drawn against the chances."""
    import random                                              # noqa: PLC0415
    rng = random.Random(int(seed))
    who = int(cls)
    it = items(root)
    card = next((c for c in catalog(root) if c.quest == want), None)
    files = next((f for n, _, f in quests(root, want) if n == want), None)
    if files is None:
        raise SystemExit('no quest %s under %s' % (want, root))
    progress = card.progress if card and card.progress else 11000
    print('  %s at progress %d, as the %s'
          % (want, progress, CLASSES.get(who, who)))
    if card:
        print('  %d zeny' % card.zeny)
    for leaf in ('item_reward.bin', 'item_reward_multi.bin'):
        p = files.get(leaf)
        if p is None:
            continue
        bs = list(blocks(p, True))
        b = at_progress(bs, progress)
        if b is None:
            continue
        print('  %-24s block %d of %d, from %d, %d columns'
              % (leaf, bs.index(b) + 1, len(bs), b.progress, len(b.columns)))
        got = draw(b, rng, lambda k, a: k == 0 or (k == 4 and a == who))
        for key, e in got:
            print('      column %-2d %s' % (key[0], e.text(it)))
        if not got:
            print('      nothing came out')
    p = files.get('item_reward_region.bin')
    if p is None:
        return 0
    for b in blocks(p, False):
        if b.monster is None or b.head[2] % 2:
            continue                    # the odd member of the pair is multi
        parts = sorted({k[1] for k in b.columns})
        print('  a broken part of %s: %d of them'
              % (monster_dir(b.monster), len(parts)))
        for part in parts:
            got = draw(b, rng, lambda k, a, want=part: k == want)
            for key, e in got:
                print('      part %-2d column %-2d %s' % (part, key[0],
                                                          e.text(it)))
    return 0


def cmd_sources(root) -> int:
    """The encyclopedia against the tables: does the thing it names give it?"""
    src = sources(root)
    named = named_monsters(root)
    by_name = collections.defaultdict(set)
    for d, n in named.items():
        by_name[n].add(d)
    import quest as qtables                                    # noqa: PLC0415
    kinds = qtables.monsters(root)
    paid, crate, fielded = set(), set(), collections.defaultdict(set)
    region = collections.defaultdict(set)
    for name, pac, files in quests(root):
        q = qtables.Quest(name, {t: (pac / t).read_bytes()
                                 for t in qtables.TABLES
                                 if (pac / t).is_file()})
        here = set()
        for _, ids in q.slots().items():
            here |= {kinds[m] for m in ids if m in kinds}
        mine = set()
        for leaf in ('item_reward.bin', 'item_reward_multi.bin'):
            if leaf in files:
                for b in blocks(files[leaf], True):
                    for ents in b.columns.values():
                        mine |= {e.item for e in ents}
        paid |= mine
        for item in mine:
            fielded[item] |= here
        if 'item_reward_region.bin' in files:
            for b in blocks(files['item_reward_region.bin'], False):
                if b.monster is None:
                    continue
                for ents in b.columns.values():
                    region[monster_dir(b.monster)] |= {e.item for e in ents}
        if 'destructible.bin' in files:
            for d in props(files['destructible.bin']):
                if d['drop'] != NONE32:
                    crate |= drop_items(root, d['drop'])
    own = {}
    for d in (pathlib.Path(root) / 'monster.cpk').iterdir():
        js = d / (d.name + '.json')
        if not js.is_file():
            continue
        import json                                            # noqa: PLC0415
        o = json.loads(js.read_text(encoding='utf-8', errors='replace'))
        got = set()
        for v in o.values():
            if not isinstance(v, dict):
                continue
            for key in ('it_drop', 'it_drop_break'):
                val = v.get(key)
                for tid in (val if isinstance(val, list)
                            else [] if val is None else [val]):
                    got |= drop_items(root, int(tid))
        own[d.name] = got
    n = collections.Counter()
    for item, (tag, who) in src.items():
        for w in who:
            n[tag] += 1
            if tag == 'Acquired from' and w == 'Quest Reward':
                n['quest'] += 1
                n['quest:ok'] += item in paid
            elif tag == 'Acquired from' and 'ox' in w:
                n['crate'] += 1
                n['crate:ok'] += item in crate
            elif tag == 'Dropped by' and w in by_name:
                ds = by_name[w]
                n['monster'] += 1
                n['monster:quest'] += bool(ds & fielded.get(item, set()))
                n['monster:region'] += any(item in region.get(x, ())
                                           for x in ds)
                n['monster:own'] += any(item in own.get(x, ()) for x in ds)
                n['monster:ok'] += (bool(ds & fielded.get(item, set()))
                                    or any(item in region.get(x, ())
                                           for x in ds)
                                    or any(item in own.get(x, ())
                                           for x in ds))
            else:
                n['unjoined'] += 1
    print('%d items carry a tagged source, over %d it_db tables'
          % (len(src), len(BANDS)))
    print('  %d monsters are named by dc_db_monster.bin' % len(named))
    for k in ('Dropped by', 'Acquired from', 'Traded at'):
        if n[k]:
            print('  %-16s %4d' % (k, n[k]))
    print()
    print('  %-42s %5d of %5d' % ('"Quest Reward" -> an item_reward entry',
                                  n['quest:ok'], n['quest']))
    print('  %-42s %5d of %5d' % ('"boxes, barrels" -> a crate drop table',
                                  n['crate:ok'], n['crate']))
    print('  %-42s %5d of %5d' % ('a named monster gives it, some way',
                                  n['monster:ok'], n['monster']))
    print('       %-39s %5d' % ('a quest that fields it pays it',
                                n['monster:quest']))
    print('       %-39s %5d' % ('its own region reward pays it',
                                n['monster:region']))
    print('       %-39s %5d' % ('its own it_drop_db table has it',
                                n['monster:own']))
    print('  %d tagged with a name no join reaches' % n['unjoined'])
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
    if cmd == 'xref':
        return cmd_xref(rest[0])
    if cmd == 'catalog':
        return cmd_catalog(rest[0])
    if cmd == 'card':
        return cmd_card(rest[0], rest[1])
    if cmd == 'drops':
        return cmd_drops(rest[0], rest[1])
    if cmd == 'items':
        return cmd_items(rest[0])
    if cmd == 'props':
        return cmd_props(rest[0], rest[1] if rest[1:] else '')
    if cmd == 'draw':
        return cmd_draw(rest[0], *rest[1:])
    if cmd == 'sources':
        return cmd_sources(rest[0])
    print('unknown command: ' + cmd)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
