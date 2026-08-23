# The quest tables — where the monsters come from

**Status: read.** 430 quests, 1,708 stage entries, 2,503 monster slots, 8,024
generators, 567 arena locks. Reader:
[`../tools/quest.py`](../tools/quest.py).

    python tools/quest.py dump extract/tree q01104
    python tools/quest.py xref extract/tree

A quest `.pac` ships four [`ECH`](format_ech.md) tables and nothing had
described any of them. The container has been readable since session 6; what
was missing was the columns, and — for the one that matters most — the
observation that a field here is **twelve bits wide**, which no lane-based
reading can see.

## The four tables, and how they join

```
piecelist.bin   the stages this quest visits, one string per row
enemy.bin       one row per stage; eight slots, each a monster
enemy_gen.bin   one row per spawner
piecelock.bin   one row per arena lock
```

and the chain runs

    a quest -> a stage -> that stage's eight monster slots
                       -> a spawner: a marker, and which of the eight
                       -> a lock: which fences it raises, and which spawners
                          it covers

Every arrow is checked below.

## The monster id is twelve bits

A filled `enemy.bin` slot is four bytes and reads `01 hh h0 00`. **The low
nibble of the third byte is zero on all 2,503 filled slots**, which is what
says the payload is a 12-bit field and not a `u16` — and the ids that fall out
are decimal-looking in a way that a wrong split never is:

```
1010 1011 1012 1020 1030 1031 1032 1040 1041 1042 1050 … 1271
2010 2011 2012 2020 2030 2050 2051 2070 … 2190 2191
```

`monster.cpk` holds directories named `zNN_MM` and `bNN_MM`, and

    id = 1000 + 10*NN + MM   for z      (the small monsters)
    id = 2000 + 10*NN + MM   for b      (the bosses)

**2,503 of 2,503 slots name a directory that exists — 83 ids against 83
directories, with nothing left over on either side.** A closed bijection, and
the only reading of those four bytes that produces one.

It is also the numbering the scripts already use. `q00505`'s cutscene branch
reads

```
if (getLatestKilled() == ((2000 + (10 * (37 - (28 - 1)))) + 0))
```

which is 2100, which is `b10_00`. So the AI's monster **kind** — the 28..46
that [`format_merc.md`](format_merc.md) found `getNearestBossKind()` returning
— is `b(kind - 27)`, and the quest tables, the AI and the model directories are
one namespace.

## `enemy.bin`

29 lanes, 116 bytes, one row per stage of the quest.

```
+0x00  str   the stage
+0x04  u8×4  (n, 1, 0, 2) — n is 1..15
+0x08  u32   0x0202FFFF on all 1,386 rows
+0x0c  ×8    eight monster slots, `01 hh h0 00`, 0xFFFFFFFF for empty
+0x2c  u8×8  eight counts, one per slot, 99 where the slot is empty
+0x34  u8    at +0x37: 0, 10, 20, 30, 40, 250
+0x54  u8    at +0x57: 0xFF, or 1, 11, 21, 31, 41 …
```

**`+0x2c` is eight bytes and not two lanes, one byte per slot.** The tell is
that it agrees with the slots: a byte is 99 exactly where its slot is empty, on
**11,040 of 11,088** slot-and-byte pairs. Where the slot is filled the byte is
1 to 16, and it is the **count of that monster in that room** — it equals the
number of generators aimed at the slot on **2,275 of 2,503**, is exactly double
it on another 91, where each generator produces two, and is ragged on the
remaining 137. So 99 is the empty sentinel and the field is a population.

`+0x37`'s ten-step values and `+0x57`'s `10k + 1` are unread.

## `enemy_gen.bin` — one row per spawner

15 lanes, 60 bytes, 8,024 rows. The stage is written once at the head of each
block and inherited down it, which is how the table is laid out and how
`quest.py` reads it.

```
+0x00  str   the stage, on the first row of its block
+0x04  str   an `emgen_pos` marker of that stage
+0x08  str   the `emgen` name the scripts call it by
+0x0c  f32   0.0 on 7,822 rows of 8,024
+0x10  u8×4  (slot, ?, ?, 0xFF) — slot is 1..8, the lane in `enemy.bin`
+0x14  u32   0xFFFFFFFF on 6,971; a u16 on the rest
+0x18  u8×4  0xFF unless set; the same shape as +0x10
+0x1c  u32   0xFFFFFFFF on all 8,024
+0x20  u8×4  0xFF except 66 rows
+0x24  u8×4  0xFF except 71 rows, where the last byte is 1, 2, 30 or 60
+0x28  u8×4  (0xFF, n, m, k) — n is 8..80, k is 0, 5, 10, 15, 30, 60, 90
+0x2c  f32   0.0 except 5 rows, which carry 0.1
+0x30  u8×4  (k, a, b, 0xFF) — k is 1 on 7,643 rows, a and b run 1..255
+0x34  str   a second script callback: `GenEnd`, `bosskill_01`
+0x38  str   the kill callback: `sfKill_Generator`, `sfKill_GeneratorA`
```

**The slot at `+0x10` is a lane number, not a position in a compacted list.**
Both readings resolve, but the lane reading resolves better — 7,976 against
7,944 — and the 35 rows that still miss point at a lane their stage leaves
empty, which is a disabled spawner rather than a wrong reading.

`+0x28`'s `k` is 0, 5, 10, 15, 30, 60 or 90, which are halves and multiples of
a second at 30 fps and read as a respawn delay; `n` runs 8 to 80 in multiples
of four. Neither is confirmed and neither is named by a consumer, so they stay
where they are.

## `piecelock.bin` — one row per arena lock

11 lanes, 44 bytes, 842 rows of which **281 are empty placeholders** — every
string blank, the id `0xFFFF`, every byte `0xFF`. The 561 real rows are

```
+0x00  str   the stage
+0x04  str   the lock's own name, `pl_<stage>[_a]` — what cfStartPieceLock asks
+0x08  u8×4  (id:u16, ?, 1) — id 1..19, 0xFFFF on a placeholder; the third
             byte is 0xFF on 733 rows and 24, 25 or 26 on the other 109
+0x0c  str   the `lockarea` polyline
+0x10  str   the `lock_line` polylines, newline-separated
+0x14  str   empty on 825 of 842
+0x18  str   the `pl_q<quest>` hit area that trips the lock, newline-separated
+0x1c  str   the `emgen` names the lock covers, newline-separated
+0x20  u32   0 on all 842
+0x24  str   a second generator list, on 32 rows
+0x28  str   a third, equal to `+0x1c` on 835 of 842
```

The third byte of `+0x08` is 24, 25 or 26 on 109 rows and 0xFF on the rest, and
it rises with the quest number — 24 on `q001`–`q003`, 25 on `q003`, 26 on
`q004`. It is not a BGM cue: **0 of 109 match a cue the same quest's script
plays**. Unread.

`+0x14` is a string lane the type inference calls `const 0`, because offset 0
is the pool's leading NUL and 825 rows point at it. Seventeen rows do not, and
what they point at has not been looked at. The same trap hides `+0x20`.

## `piecelist.bin`

One string per row: the stages the quest visits. **1,691 of 1,708 name a
`.psq` the same `.pac` ships**, which is what makes the list a table of
contents rather than a coincidence.

## What `xref` checks

```
piecelist -> its own .psq       1691 resolve,   17 do not
enemy.bin slot -> monster       2503 resolve,    0 do not
enemy_gen -> emgen_pos marker   7728 resolve,    7 do not,  289 not testable
enemy_gen -> an enemy slot      7976 resolve,   35 do not
enemy_gen -> kill callback      3067 resolve,    0 do not
enemy_gen -> end callback         56 resolve,    0 do not
piecelock -> lockarea            537 resolve,    3 do not
piecelock -> lock lines         1199 resolve,    0 do not
piecelock -> hit area            552 resolve,    0 do not
piecelock -> its generators     3072 resolve,   42 do not
```

**3,123 script callbacks and not one of them misses.** Every `sfKill_Generator`
and `GenEnd` a generator names is a function the same quest's own `.psq`
defines, which is the same join [`format_psq.md`](format_psq.md) found for
`trigger.trg` and closes the loop from the other side: the trigger starts the
wave, the table says who spawns, and the table names the function that runs
when they are dead.

### And the 320 calls that looked unresolved are explained

[`format_psq.md`](format_psq.md) noted that only **569 of the 889**
`cfStartPieceLock` calls named a string in an `ECH` of their own `.pac` and
left it there. Splitting the rest three ways settles it:

```
cfStartPieceLock   569 in its own quest,  309 in another,   11 nowhere
cfSetEnableEmGen   149 in its own quest,   91 in another,    0 nowhere
cfReviveEmGen        8 in its own quest,    0 in another,    0 nowhere
cfAddEmGenWait      21 in its own quest,    1 in another,    0 nowhere
```

**A stage script ships in every quest that visits the stage** — `900_01_01.psq`
is in 89 quest pacs, `010_01_01.psq` in 48 — so it is written once for the
stage and copied, and it names locks and generators that only some of those
quests declare. The call finds nothing and does nothing. Eleven `pl_` names out of 889
calls are in no quest's table at all, which for a hand-maintained set of 430
quests is what a handful of deleted locks looks like.

## What this says about `ECH` again

[`format_effect.md`](format_effect.md) made the point that a four-byte lane is
often not one field. `enemy.bin` makes a sharper one: **a field can be narrower
than a byte boundary**. `ech.py`'s classifier reads the monster slot as a `u32`
and reports numbers in the tens of millions; the same bytes read as a 12-bit
field are 83 ids that name 83 directories exactly. The count beside them makes
the same point one byte down: `+0x2c` and `+0x30` look like two `u32` lanes and
are eight independent bytes. The tell was free — the low
nibble is zero on all 2,503 — and it is the kind of thing a byte histogram
shows and a type inference does not. Noted in
[`format_ech.md`](format_ech.md).

## Still open

- The counts and timers of a generator: `+0x14`, `+0x18`, `+0x20`, `+0x24`,
  `+0x28` and `+0x30`. Some of them are plainly a period in frames; none is
  named by a consumer, and the disc has no second reader to check them against.
- The third byte of `piecelock`'s `+0x08`, 24 to 26 on 109 rows.
- `piecelock` `+0x14`, and `enemy.bin`'s `+0x37` and `+0x57`.
- `enemy.bin`'s `+0x04` first byte, 1..15.
- The other tables a quest pac ships and this document does not touch:
  `item_reward.bin`, `item_reward_multi.bin`, `item_reward_region.bin`,
  `weapon_decost.bin`, `destructible.bin`, `mapexception.bin`,
  `enemy02..04.bin` (which `changeEnemySet` swaps in), `enemy_ref.bin`, and
  the `q<NNNNN>.bin` that carries the quest's own header.
