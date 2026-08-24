# Milestone 7 — a quest pays

**Status: reached, session 28.** [`milestone_quest.md`](milestone_quest.md)
got a quest to finish itself: the arena closed because the quest's own script
counted the kills. It finished with nothing in its hands. This is the other
half — **what came out** — and it is drawn against the disc's own chances,
one column at a time.

Code: [`../engine/purse.py`](../engine/purse.py), with the draw itself in
[`../tools/reward.py`](../tools/reward.py) and four call sites in
[`../engine/mission.py`](../engine/mission.py) and
[`../engine/host.py`](../engine/host.py).

```
python engine/purse.py   draw  extract/tree q01015 7
python engine/purse.py   rolls extract/tree q00102 7 2000
python engine/mission.py run   extract/tree q00102 sw
python engine/mission.py runs   extract/tree
python tools/reward.py   sources extract/tree
```

## The reading this needed, and it had been sitting in plain sight

`item_reward.bin` was read three sessions ago except for one thing, and the
one thing was the shape of it: a block carries three rows or forty-eight, and
the count tracks nothing — not the quest's stages, not its monsters, not its
generators. [`format_reward.md`](format_reward.md) called it open.

It tracks nothing because **a row is not a unit**. Ten slots of sixteen bytes
are ten *columns*, and the entries down one column are alternatives with one
distribution between them. Group by `(column, kind)` and

```
  item_reward.bin        4022 columns,  4022 under 10,000,  561 on it
  item_reward_multi.bin  4022 columns,  4018 under 10,000,  566 on it
  item_reward_region.bin 1122 columns,  1122 under 10,000,  572 on it
```

**4,022 of 4,022.** The control is the same test on the grouping the document
had before — by kind alone, **244 of 644**. And the region table, which was
already grouped by the byte that says which part broke, improves on its own
number: 1,106 of 1,110 became **1,122 of 1,122** once the column was allowed
in beside the part.

The endless dungeon is the fourth file built this way and it agrees without
being asked: `yggdrasill_reward_item.bin` is the same sixteen-byte entry
under a head one word wider, and **277 of 277, 278 of 278 and 326 of 326** of
its columns fit under 10,000, with all 3,572 of their entries naming an
`it_db` row.

So a pay-out is one roll per column and the leftover is the chance nothing
comes out — and the six rows at the foot of a block that hold a katar, a
mace, a hammer, a bow, a staff and a two-handed sword at ten per cent each
stop being six rows and become **one column offering one weapon per class**.
397 of the 564 weapon columns are exactly that.

## The same grid, in a file nobody had opened

`it_drop_db_<id>.bin` was a join target: `destructible.bin` points at one and
so does every monster's JSON, in a field called `it_drop`. 579 of them, and
they are built the same way — eight columns instead of ten — with two things
written once at the top of a column and inherited down it:

- **the kind**, on 4,369 of 4,369 columns, and not one column repeats it
  lower down;
- **the gate.** A column whose top entry names no item is a two-step draw:
  that chance is whether the column fires, and the entries beneath it are
  what comes out. **All 1,930 gated columns sum to exactly 10,000 under the
  gate** — which is what a second step has to do — and all 2,439 ungated ones
  to at most 10,000.

**26,237 of the 26,251 item ids name an `it_db` row, and the fourteen that do
not are the ten quest items** the catalog collects. The file is closed.

## And the game says, in English, whether any of this is right

Every material's encyclopedia entry ends in a tagged block — `{{Dropped by}}`
and a monster, `{{Acquired from}}` and a place — on **411 of 411**. The text
pairs positionally with `it_db_material.bin`, so the tag lands on an item id;
and `dc_db_monster.bin`'s second word is **the same twelve-bit monster id**
`enemy.bin` and `chapter.bin` write, which gives 82 monsters a name.

That is a third source, written for the player by the people who wrote the
tables, and it was never going to agree by accident:

```
python tools/reward.py sources extract/tree

  "Quest Reward" -> an item_reward entry        47 of    47
  "boxes, barrels" -> a crate drop table        37 of    54
  a named monster gives it, some way           292 of   298
       a quest that fields it pays it            255
       its own region reward pays it             113
       its own it_drop_db table has it           279
```

**47 of 47** materials the game calls a quest reward are in an
`item_reward.bin`. **292 of 298** materials the game says a monster drops are
given by that monster — by a quest that fields it, by its own broken-part
table, or by its own drop table. The six that miss are the text calling a
family what the table calls a variant: `Domovoi` against `z11_02`, the Desert
Domovoi. The seventeen crate materials that miss are all in
`it_drop_db_9500..9505`, six tables no quest's `destructible.bin` names and
only the endless dungeon's own two do.

## Four things pay, and the run has all four

```
the quest finishes    item_reward.bin           one roll per column
a part breaks off     item_reward_region.bin    byte 7 indexes region_data_brk
a monster dies        its own it_drop table     out of the JSON's it_drop
a script says so      cfAddItem(id, n)          ten call sites, now bound
```

Every one is a join an earlier session measured, and one of them turned out
to have been read wrong. A region block's head is `(progress, monster,
region)`, its region ids pair up even with odd, and the odd member always
pays better — which reads as solo against multiplayer, and is not. **The
region id is the monster's difficulty tier**, in the numbering
[`params.md`](params.md) read off the monster JSON's own record keys: 0/1,
10/11, 20/21 … 250/251, and **194 of 194 monster blocks name tiers that
monster declares**. The pair is one monster at two difficulties, `hp` ×1.5
between them, and the harder one dropping better is what a difficulty is for.
The tower says it a second time: its region blocks are keyed 100, 101, 110
and 111, which are tier keys and cannot be a solo/multiplayer bit.

The part index is the one worth naming.
[`format_elbn.md`](format_elbn.md) read `region_data_brk` as the monster's
breakable-part list out of an `ELBN`, and a region reward's byte 7
is a position in that list — 298 of 298 blocks carry exactly `0 .. n-1`. So a
volume that lands on a capsule a `region_data_brk` row owns has a *number*,
and that number is a row of the quest's own table. The fight already knew
which capsule it hit; it had nowhere to send it.

## The chance is read back out

Nothing on the disc says what a table means by 10,000. `rolls` pays the same
quest two thousand times and prints the written expectation beside the drawn
one:

```
python engine/purse.py rolls extract/tree q00102 7 2000

    item    table     name                          written    drawn
    60013   bottle    Antidote                        3.000    3.000
    50010   material  MoiMoi's Tail                   1.200    1.151
    50061   material  Honey                           0.600    0.599
    50013   material  Strange Mushroom                0.400    0.391
    10007   weapon    Thorn Katar                     0.100    0.101
    80041   card      Spore Card                      0.030    0.031
```

## Over the disc, and what did not happen

```
python engine/mission.py runs extract/tree

431 quests run, 247 of them finished
  252 walked their whole stage list, 1105 of 1708 stages in all
  272 arenas armed by a quest script, 229 started, 210 ended by the script's
      own kill count
  1594 monsters spawned, 1534 killed
  179 quests paid something: 568,871 zeny and 2762 items of 279 kinds
    out of a monster 2211, the quest 551
```

The first five lines are [`milestone_quest.md`](milestone_quest.md)'s to the
digit — 252, 229, 210, 1,534 — which is the point of printing them. The run
now sets `cfGetMainCounter` from the catalog instead of holding it at 11000,
and 181 call sites across the scripts branch on that number; **nothing
moved.**

**One of the four ways to pay never fired, and the disc says why.** Not one
part came off in 431 quests, and it is not the rule that is wrong: of the 83
monsters the quests field, **23 carry a `region_data_brk` record and all 23
of them are bosses** — no `z*` monster has a breakable part at all. A boss
does not stand inside a `piecelock` arena; `q01015` sends the player at three
of them and declares no lock. So the path is exercised by hand instead, and
it lands where `format_reward.md` says it should:

```
b01_00's region_data_brk    ['head', 'body']
q01015 broke(b01_00, 0)  -> 50124  Broken Horn
q01015 broke(b01_00, 1)  -> 50237  Rare Elunium
```

What stands between that and a run doing it by itself is the boss fight, and
before the boss fight the walk: 125 runs still end with *the body stopped
walking*. A pay-out is only as good as the quests that reach it.

## What is the run's and what is the disc's

Two numbers here are policy and they are declared beside `BLOWS`: **how many
landed volumes break a part** (`BREAKS`, 2), and **which kinds a pay-out
draws** — kind 0, and kind 4 for the player's own class, because what picks
between kinds 0, 2 and 3 is not read.

A third looks like policy and is not. The block head is a story-progress
threshold in the number space `cfGetMainCounter` returns, and the run puts
the counter at the quest's own requirement out of `chapter.bin` `+0x08`. On
that footing **no quest reaches its second block**, which is the disc's
arrangement and not this file's: of the 22 two-block quests that grant a
progress value of their own, **17 have their second block at exactly that
value.** The later block is what a replay pays, and a first run cannot be
standing there.
