# The quest catalog, and what a finished quest pays

**Status: read.** 431 quests named, 553 objectives, 38,025 reward entries,
3,771 breakable crates. Reader: [`../tools/reward.py`](../tools/reward.py).
[`format_quest.md`](format_quest.md) reads the four tables that put the
monsters in the room; this reads the nine that say what the room is *for*.

    python tools/reward.py check   extract/tree
    python tools/reward.py xref    extract/tree
    python tools/reward.py catalog extract/tree
    python tools/reward.py card    extract/tree q01015
    python tools/reward.py drops   extract/tree q00106
    python tools/reward.py props   extract/tree q00106

A quest `.pac` ships up to nine more [`ECH`](format_ech.md) tables beside the
four, and `quest.cpk/common.pac` ships a tenth that covers all of them:

```
common.pac/chapter.bin      the catalog: every quest, once, with its name
q<NNNNN>.bin                where the quest starts                     431
item_reward.bin             the drops                                  233
item_reward_multi.bin       the same drops, multiplayer odds           233
item_reward_region.bin      the drops off a broken part                138
weapon_decost.bin           four numbers, twice                        233
destructible.bin            the breakable scenery                      262
mapexception.bin            a route this quest reroutes                 29
enemy_ref.bin               which enemy table a generator reads          11
enemy02..04.bin             those tables                                11
```

None of them was described. Every join below is measured by `reward.py xref`,
and they all print together:

```
chapter row -> a quest pac                   431 resolve,    0 do not
objective -> a monster directory             553 resolve,    0 do not
message id -> msg_quest.bin                 3448 resolve,    0 do not
prerequisite -> another quest's flag         139 resolve,   44 do not
quest item -> it_db_name_quest.rmsg           15 resolve,    0 do not
reward item -> an it_db row                38018 resolve,    7 do not
kind 4 -> it_db_weapon.bin column 5         1644 resolve,    0 do not
region reward -> a monster directory         396 resolve,    0 do not
mapexception from -> the quest's piecelist    61 resolve,    0 do not
mapexception to   -> the quest's piecelist    60 resolve,    1 do not
enemy_ref -> a generator of the quest        137 resolve,    0 do not
enemy_ref -> a table the pac ships           137 resolve,    0 do not
destructible -> an ATIH marker of its stage  3770 resolve,    1 do not
destructible -> an it_drop_db table         3707 resolve,    1 do not
region slots == the monster breakable parts   298 resolve,    0 do not
quest header stage -> the quest piecelist    427 resolve,    4 do not
quest header appear -> that stage ATIH       429 resolve,    1 do not
```

## `chapter.bin` is the catalog, and the join is one byte pair

711 rows of 92 bytes, no string pool. **Byte 0 is a record kind: 431 rows
carry 0 and 280 carry 1**, and a kind-1 row is a continuation of the kind-0
row above it — every string field blank, only its objective slots filled. On a
kind-0 row the next two bytes are a chapter and an index, and

    q0<chapter><index>

**names a quest pac on all 431, and the 431 pacs are each named exactly
once.** A closed bijection, with nothing left over on either side, and the
only reading of those two bytes that produces one. Chapter 76 index 1 is
`q07601`; chapter 99 index 99 is `q09999`.

```
+0x00  u8    0 a quest, 1 a continuation of the one above
+0x01  u8    the chapter: 0..15, 19..22, 29, 30, 71..76 and 99
+0x02  u8    the index inside it
+0x03  u8    0, 1 or 2
+0x04  u16   the quest flag this one requires, or 0xFFFF for none
+0x06  u16   its own quest flag
+0x08  u16   a story-progress threshold: 0, or 11000..24000
+0x0a  u8×2  (9, 3) on 387 of the 431
+0x0c  u16   the time limit in seconds
+0x0e  u8    a rank, 1..15
+0x0f  u8    0, 1 or 2
+0x10  u32   a quest item to collect, 100001..100010, or 0xFFFFFFFF
+0x14  u8    how many of it
+0x15  u8×3  three small numbers, unread
+0x18  ×4    four objectives: u32 monster, u16 how many, u16 pad
+0x38  i32   the zeny it pays, 100 .. 50,000, 45 distinct values
+0x3c  i32×8 eight message ids into msg_quest.bin
```

The time limit is **600, 900, 1200 or 1800 seconds** — ten, fifteen, twenty
and thirty minutes, 1800 on 399 of the 431 — and 0 on the debug row.

### The objective is written the way `enemy.bin` writes a monster

An objective word is `01 hh h0 00`: the same **twelve-bit monster id**
[`format_quest.md`](format_quest.md) found in `enemy.bin`, with the low nibble
zero. **553 of 553 name a `monster.cpk` directory**, over the kind-0 rows and
the kind-1 rows together. A second table, a second consumer, one namespace —
and no way to arrange the agreement, since the split was settled elsewhere.

Where the objective is not a monster it is a **quest item**: an id 100001 to
100010 and a count. `it_db_name_quest.rmsg` holds exactly **ten** messages —
`Rare Flower`, `Strange Emveretarcon`, `Enormous Yew Berry`, … — and the
catalog uses exactly those ten ids. Ten and ten, closed.

### The eight message ids name the quest

`menu.cpk/msg_field.en.pac/msg_quest.bin` holds **1,478 messages**, and
**all 3,448 ids the catalog writes are inside it**, the largest being 1,477 —
the last message in the file. The eight are, in order:

```
0  the title            "Orcish Stars"
1  the client           "Eadgils"
2  the briefing         "Reports say the Orc heads are gathering ..."
3  the place            "Sograt Desert"
4  a target's name      "Orc King"
5  a second target      "Orc Hero"
6  a target's name      "Orc Shaman"
7  a second target      "Orc Hero"
```

Slots 4 and 6 carry the same id on **421 of 431** and slots 5 and 7 on **427
of 431**, so the second pair is a duplicate of the first that a handful of
quests override. Of the 370 quests with exactly one objective, **250 carry a
slot-4 string that is verbatim a `msg_enemy.bin` message**; the rest are
bosses, whose names `msg_enemy.bin` does not hold, plus `Debug` and
`All Enemies`.

`python tools/reward.py card extract/tree q01015` prints one:

```
q01015   chapter 10, index 15   (chapter.bin row 204)
  title          Orcish Stars
  client         Eadgils
  place          Sograt Desert
  target 0       Orc King
  brief          Reports say the Orc heads
                 are gathering somewhere
                 beneath the Sograt Desert.
  time limit     1800 s
  rank           15
  pays           9000 zeny
  needs progress 20000
  needs          flag 356
  sets           flag 384
  objective      b01_00 x1
  objective      b01_01 x1
  objective      b01_02 x1
```

### The quest flag is what the scripts ask about

`+0x06` is a `u16`, 239 real values over the 431 rows plus 0 and 0xFFFF,
near-consecutive inside a chapter, and `+0x04` is the flag the quest waits
for — usually the one the row above sets. **139 of the 183 rows that name a
prerequisite name a flag another row defines.**

The scripts read the same space. `checkQuestClearByIDFlag` is called 54 times
and the values it is handed are 297, 461..479, 486, 487, 493, 494, 498, 499
and 1235..1239; **five of those thirty are catalog flags** — 297 is `q00408`,
1235..1239 are `q01507`..`q01511` — and the rest fall in gaps no row uses. The
44 unresolved prerequisites fall in the same gaps. So the flag space is wider
than the catalog: the game has quest flags for things that are not quests.

## `q<NNNNN>.bin` says where the quest starts

One row of 24 bytes with a two- or three-string pool, in all 431 pacs.

```
+0x00  u32   a story-progress value, or 0xFFFFFFFF on 370 of the 431
+0x04  str   the stage the quest starts in
+0x08  str   an `appear` marker of that stage
+0x0c  str   a second stage, empty on 316
+0x10  u8×4  (1, a, b, c)
+0x14  u32   0xFFFFFFFF on all 431
```

**427 of the 431 start stages are in the quest's own `piecelist.bin`**, and
**429 of the 430 appear markers name an `ATIH` marker of that stage** — the
same marker table [`format_stage.md`](format_stage.md) reads. There are only
five: `appear01` on 313 quests, `appear04` on 89, then `appear03`, `appear05`
and `appear02`. The second stage is *not* usually in the piecelist — 29 of
115 — and on 85 of them it is `900_01_02`, so it reads as where the quest
sends the player afterwards.

`+0x00` carries 61 distinct five-digit values, **11100 to 23810**, ascending
with the quest number, one per story quest and the sentinel everywhere else.
It is the same number space `chapter.bin` `+0x08` requires and the reward
blocks below are keyed on, which is what says it is a story-progress counter:
finishing this quest moves the player to that value.

## A reward entry is sixteen bytes, and byte 7 says what the next word is

`item_reward.bin` and `item_reward_multi.bin` are 164 bytes a row: a `u32`
head and then **ten entries of sixteen**. `item_reward_region.bin` is 92:
three `u32` of head and then **ten entries of eight**, which is the same entry
with its tail cut off.

```
+0x00  u32   the item id
+0x04  u16   its chance, in ten-thousandths — 10000 is certain
+0x06  u8    how many
+0x07  u8    a kind, and it says what the word after it means
+0x08  u32   on kind 4 a player class; on kind 2 a round number; else 0
+0x0c  u32   zero on all 34,605 wide entries
```

The head is written once at the top of a block and **inherited down it**, the
way `enemy_gen.bin` writes a stage.

### Every item id resolves, because the bands are disjoint

The `it_db_*.bin` tables number their rows in bands that do not overlap —
10001..11204 weapons, 20001.. hair, 30001.. costumes, 40001.. hairgear,
50001..50422 materials, 60001.. bottles, 80001..83233 cards, 90001..
instants, 110001.. card skills — so one dictionary of 4,210 ids covers them
all. **38,018 of the 38,025 entries across the three tables name a row**, and
**every one of the seven that do not has item id 0**: an empty slot with a
leftover chance in it. Nothing real is unresolved.

`python tools/reward.py drops extract/tree q00106`:

```
    -- from 11000
       60001   bottle    Green Potion S               x3    50.00%
       50049   material  Horo Horo Down               x3    40.00%
       10007   weapon    Thorn Katar                  x1    10.00%
       80221   card      Killer Ant Card              x1     3.00%
```

### Kind 4 is a class restriction, and the disc proves it twice

`it_db_weapon.bin` column 5 is the player class in the numbering
[`combat_loop.md`](combat_loop.md) named off the starting weapons — **0, 1, 3,
4, 5, 7, seventy-five weapons each**: katar, mace, hammer, bow, staff,
two-handed sword. The word after a kind-4 selector takes **those same six
values**, and

**the weapon's own class column equals the reward entry's word on 822 of 822
entries, in each of the two files.**

Two files, two readers, one of them an `ECH` lane and the other a column of a
different `ECH`, and no way to arrange the agreement from either side. A
kind-4 entry is the quest's guaranteed weapon for one class.

Kind 2's word is a round number, 0 to 300 in steps of ten with 100 on 705 of
the 2,288 kind-2 entries and constant down a row on most rows. It reads as a
percentage and the disc offers no second consumer to say of what. Kinds 0 and
3 leave the word zero, and what separates them is unread.

### The multiplayer table is the same table with different odds

`item_reward_multi.bin` aligns with `item_reward.bin` row for row and slot for
slot: **17,229 of 17,300 aligned entries carry the same item, count, kind and
word, and only the chance differs** — on 12,153 of them. Its non-empty row
count matches on 231 of the 233 quests. The multiplayer chance is the
**better** one: it rises on 10,730 of the 12,153 and falls on 1,404.

`item_reward_region.bin` does the same trick inside one file. Its block head
is `(progress, monster, region)` and **the region id is even for one table and
odd for the other**: 396 blocks, **198 even and 198 odd, and every even block
has an odd partner**, with 1,706 of the 1,710 aligned entries identical bar
the chance. Which of the pair is the multiplayer one is read off the same
direction the two files show — the odd member's chance rises on 488 of the
693 that differ.

### The region reward is the broken part, and `ELBN` says which

The monster word in a region block is the same twelve-bit field — **396 of 396
name a directory**. What the entry's byte 7 selects is the *part*:

**over the 298 blocks that carry entries, the set of byte-7 values is exactly
`{0 .. n-1}` where `n` is the monster's `region_data_brk` record count — 298
of 298, none missing and none over.**

`region_data_brk` is read in [`format_elbn.md`](format_elbn.md), out of a
different container by a different reader, and its record count is the
monster's breakable-part list. So a region reward row is one part per slot, in
that list's order. `b01_00` breaks head and body and drops `Broken Horn` and
`King's Breastplate`; `b10_00` breaks three parts and each drops one of six
`Fake` weapons, one per class, at a sixth apiece.

And the chances behave like a distribution: grouping a block's entries by
part, **1,106 of the 1,110 groups sum to at most 10,000 and 568 of them to
exactly 10,000**.

This is the quest's half of a mechanic `format_elbn.md` had the other half of.
`it_drop_break` is the monster's own break drop, indexed by the same list;
`item_reward_region.bin` is the one the quest overrides it with.

### The block id is a story-progress threshold

The head of an `item_reward.bin` block is a five-digit number, **46 distinct
across the disc, 10000 to 24000**, and it **ascends inside all 233 files** —
200 files carry one block, 33 carry two. **32 of the 46 are also written
either as a `q<NNNNN>.bin` progress value or as a `chapter.bin` requirement**,
so the three fields share one number space; and on 17 of the 33 two-block
files the second block is exactly that quest's own progress value. Read as a
threshold — the game takes the last block at or below where the player is —
which is what makes a quest's drops change as the story advances. The disc has
no second reader to confirm it.

## `destructible.bin` is the breakable scenery, and it answers a stage question

262 quests, **3,771 rows of 72 bytes**, the stage inherited down a block the
same way.

```
+0x00  str   the stage, on the first row of its block
+0x08  str   the kind: kibako, kibako_bomb, taru, taru_bomb, tsubo, …
+0x0c  str   this one's name: kibako1, taru9
+0x10  str   an `obj*` marker of that stage
+0x28  u32   a drop table, or 0xFFFFFFFF
+0x38  str   a script callback, on 20 rows: `Enemypop`, `TsuboBreak1`
```

`kibako` is a wooden crate, `taru` a barrel and `tsubo` a pot, and the `_bomb`
variants explode. Two joins:

- **3,770 of the 3,771 rows name an `ATIH` marker of their own stage.** The
  one that does not is `test_motion_pos03` in `q00000`, the debug quest. This
  settles [`format_stage.md`](format_stage.md)'s open question of **what
  places the object an `obj*` marker marks**: a crate does, and the quest
  says which;
- **3,707 of the 3,771 name an `it_drop_db_<id>.bin`** in
  `item.cpk/it_drop.pac/it_drop_table.pac`, and the 64 that do not are the
  sentinel 0xFFFFFFFF on 63 rows and a zero on one. So a crate carries its own
  drop table, out of the same 579 the monsters draw from.

What is left of it: the two lanes at `+0x1c` and `+0x44` that hold the number
50 on 3,642 rows and a *string* on the rest — the same selector trap
[`format_ech.md`](format_ech.md) warns about — and the numbers at `+0x2c` and
`+0x30`.

## The three small tables

**`mapexception.bin`**, 29 quests and 61 rows of 16 bytes, is a pair of stage
names and two numbers. **All 61 "from" stages and 60 of the 61 "to" stages are
in the quest's own `piecelist.bin`**, so it is a **route override**: an edge
of the stage graph this quest replaces. That is the other half of session 24's
finding that `piecelist.bin` is a graph and that the `170_*` floors branch on
`getQuestName()` — the script asks, and this is where the answer is written.

**`enemy_ref.bin`**, 11 quests and 137 rows of 12 bytes, is
`(stage, generator, table)`. **It names 137 of those quests' 137 generators,
and every table it names — `enemy`, `enemy02`, `enemy03`, `enemy04` — is a
file the same pac ships.** So it is the index for `changeEnemySet`: which of
up to four `enemy.bin`-shaped tables a given spawner reads its monster from.
`enemy02..04.bin` are byte-for-byte the same 116-byte layout as `enemy.bin`.

**`weapon_decost.bin`**, 233 quests, one row of eight `u32` and **only six
distinct rows on the whole disc**. It is two groups of four and the first
group is `(400, 50, 500, 100)` on 231 of them; the second varies with the
quest — `(300, 30, 400, 60)` on 23, `(600, 75, 750, 150)` on four,
`(650, 100, 800, 175)` on four — with two quests whose first group differs
too. Measured, not named.

## Still open

- **`chapter.bin`'s three bytes at `+0x15`**, a triple like `(1, 0, 6)` or
  `(12, 0, 18)` with 45 distinct values, and `+0x03` and `+0x0f`, both 0, 1
  or 2.
- **What kinds 0, 2 and 3 of a reward entry separate**, and what kind 2's
  round number is a percentage of. Kind 4 is settled.
- **What an `item_reward.bin` row is.** The entries inside one are candidates
  with independent chances; what makes a row a row is not visible — its count
  tracks neither the quest's stages, nor its monsters, nor its generators.
- **The region group id**, 0..7 and 20..25 once the solo/multi digit is
  removed, which is not the part and does not track the quest's rank.
- **The 44 prerequisite flags and the 25 script flags that name no catalog
  row** — the flag space is wider than the 431 quests.
- **`weapon_decost.bin`'s four numbers**, and `destructible.bin`'s numeric
  lanes.
