# The mercenary AI — the four `ELBN` and the script that indexes them

**Status: solved.** 12 classes, 4 tables each, **0 unreadable**: 454
probability tables, 350 command lists, 1,549 command steps and 166 target
records, every one consumed to the byte. Reader:
[`../tools/merc.py`](../tools/merc.py).

The mercenaries are the party members the player fights beside, and they are
**the six player classes over again**. `mercenary.cpk` holds one `.pac` per
class per sex and the six prefixes are `job.cpk`'s own — `as`, `cl`, `hs`,
`ht`, `mg`, `sw` — with each naming itself through a skill motion its own
`animcmd.pac` ships:

```
cl  Cleric          cl10357magnus_exorcismus
hs  Hammersmith     hs444act_6_drill_cannon
ht  Hunter          ht20600_arrow_storm, ht20700_sharp_shooting
sw  Sword Warrior   sw10001_mastersword, and a shield
as  Assassin        the evade profile in params.md already named it
mg  Mage            mg10411a_sp2_at1_bullet, _aura, _ball, _coat
```

`cl` and `sw` are also the two classes that carry `guard_*` and `jg_*` in
their JSON and nobody else does — see [`params.md`](params.md), which settled
that before this file existed.

This is a **second AI system**, independent of the monsters' — see
[`format_ai.md`](format_ai.md) — and it is built the other way round. The
monsters keep their rules in a table and a script mirrors them; the
mercenaries keep their rules in a **script** and their parameters in a
**table**.

## The five files of a class

```
consider_action.cnut     the rules - Squirrel, three functions
select_action.bin        ELBN: prt00 .. prtNN  +  select_prt
select_target.bin        ELBN: prt00 .. prtNN  +  select_prt
command_data.bin         ELBN: act_cmd_00 .. act_cmd_NN  +  act_cmd_data
target_data.bin          ELBN: target_00 .. target_NN    +  target_data
```

All four are `ELBN`, which [`format_elbn.md`](format_elbn.md) already opened,
and `ELBN` names its own entries — so the structure of this AI was declared on
the disc all along. `select_prt`, `act_cmd_data` and `target_data` are arrays
of pointers, one per numbered entry, and **all 970 of those pointers are in
their own file's `POF0` relocation list.**

## How a mercenary decides

`consider_action.cnut` defines three functions, each suffixed with its class:

```
check_active_<cls>()     -1 or 1, whether to engage
select_target_<cls>()    an index into select_target.bin
select_action_<cls>()    an index into select_action.bin
```

**The index is the proof.** On all 12 classes and both functions — 24
comparisons — the set of values the script returns lies inside the set of
`prt` indices its table defines, and **`max(return)` equals the last table
index exactly**: no overrun, and no unused tail.

A `prtNN` is a weighted list of `(u32 id, u32 weight)` closed by
`(0xFFFFFFFF, 0)`. **All 454 are closed that way and all 454 sum to exactly
10000** — the same per-ten-thousand convention the monsters' `prt_select`
computes, reached here without a normaliser because the tables are exact.

So the loop is

```
check_active  ->  select_target  ->  prtNN  ->  target_NN
              ->  select_action  ->  prtNN  ->  act_cmd_NN  ->  the steps
```

and `merc.py dump` prints it end to end:

```
select_action -> act_cmd
  prt01  act_cmd_02 @20%, act_cmd_04 @10%, act_cmd_05 @20%,
         act_cmd_06 @10%, act_cmd_07 @40%
  prt02  act_cmd_00 @100%
```

## `act_cmd_NN` — a scripted input sequence

A list of **20-byte steps** closed by a step whose first word is
`0xFFFFFFFF`; all 350 are exactly that.

```
0x00  u32   a command id: 0, 3, 5, 8, 9, 12, 14, 15, 16, 19, 20, 21, 22
0x04  u32   a duration in milliseconds
0x08  u32   flags, 12 distinct values, near-determined by the command
0x0C  u32   zero on 1,457 of the 1,549 steps
0x10  f32   a distance
```

Thirteen command ids occur, and their operands separate them cleanly:

```
id   uses  where            duration        distance
 0    345  333 of them last      10 ms      0
 3    106  first or mid      40 - 660 ms    0.5 - 3.0
 5     86  almost always first  150 ms      15 - 33
 8    102  always first        3000 ms      3.5
12    174  first or mid   3000, 90, 180 ms  3.5
14    444  always mid           600 ms      7.0
15    248  always mid           600 ms      7.0
 9, 16, 19, 20, 21, 22 - between 2 and 18 uses each
```

Only `mg` uses 16, only `cl` and `mg` use 21 and 22, and only `as` uses 9. The
flag word is near-determined by the command: 297 of the 299 uses of
`0x10000000` are on command 0, and every one of the 694 uses of `0x4082000` is
on 14, 15 or 16.

A typical list reads as an opener, a combo and a close:

```
act_cmd_03    cmd 8   3000 ms  0x00104000  3.50
              cmd 14   600 ms  0x04082000  7.00
              cmd 15   600 ms  0x04082000  7.00   x4
              cmd 0     10 ms  0x10000000  0.00
```

## 14 and 15 are the two attack buttons

`job.cpk` names a player's combo motions **by the string of presses that
reaches them**: `sw311at_s`, `sw312at_ss`, `sw343at_ssl`, `sw325at_ssssl`,
`sw355at_sllll`, `sw361at_l`. There are two attack buttons, `s` and `l`, and a
combo is a word over those two letters.

Write command 14 as `s` and command 15 as `l`, and a run of them is that word:

```
(14, 14, 14, 14, 15)  ->  ssssl  ->  sw325at_ssssl
(14, 14, 15, 15, 15)  ->  sslll  ->  sw345at_sslll
(14, 15, 15, 15, 15)  ->  sllll  ->  sw355at_sllll
(15,)                 ->  l      ->  sw361at_l
```

**168 of the 188 runs on the disc name a combo motion the same class ships**,
and **no run anywhere exceeds five presses**, which is the depth of the combo
tree. The 20 that do not are the Mage and the Hammersmith, whose trees are
shallower than the tables written for them — `mg` stops at `at_sssl` and has
no `at_ssssl`, `hs` has no `at_sssll`. `merc.py combos` prints the check
class by class.

That settles what an `act_cmd` is: not a list of animations but a list of
**inputs**, with a per-press timeout and a range, which the combat loop feeds
to the same combo tree the player drives.

## `target_NN` — who to attack

28 bytes, seven `u32`, and the last three are zero on all 166.

```
+0x00   5 distinct values: 8 (80), 7 (62), 2 (12), 4 (10), 5 (2)  - a
        target type: `getTargetType()` is compared against 2, 4, 6, 7 and 8
        in the scripts, and four of those five are exactly this set
+0x04   8 distinct: 18, 2, 4, 0, 32, 30, 10, 20
+0x08   zero on 157; where not, a f32 - 15.0, 19.25, 25.0
+0x0C   zero on 93; else 2, 18, 6, 32, 4, 3
+0x10   zero on all 166
```

## What the host has to provide

`psq.py api` over `mercenary.cpk` gives the whole interface: **19 predicates
and `print`**, and every one of the 19 is inside the disc-wide list
[`format_psq.md`](format_psq.md) enumerated and
[`format_api.md`](format_api.md) reads.

```
getPlaneRange(n)        getNearestBossKind()     getRange(n)
getNearestBossAction()  getTargetActId()         getRand()
getTargetType()         getNumOfEnemy(a, b)      getHpRate(n)
getTargetMonsterKind()  getNumOfBoss(a, b)       getHeight(n)
getActionLastFrame(n)   isAbnormal(a, b)         isActive()
isAvailableAceSkill(n)  getLatestFinishReason()
getPartyMemberHpRate(n) getNumOfUnderHpRate(a, b)
```

`getHpRate` is the one name the two AI systems share, and the arity differs:
the monsters call it with no argument and the mercenaries with one — twelve
calls against a hundred and ten.

**The `n` is an actor slot: 0 is the mercenary, 1 the player it follows, 2 its
current target.** `check_active_*` reads `getRange(1) < 35 && isAbnormal(1, 3)`
and prints `plyer freeze` on the next line, which names the slot and the status
at once; `getHpRate(0) < 85` guards the mercenary's own ace skills; and the
phases split, with `check_active` and `select_target` asking about slot 1 and
`select_action` — which runs after a target exists — asking about slot 2. In
`getNumOfEnemy(centre, radius)` and `getNumOfBoss` the same 0/1 is the centre
of the count and a radius of 0 means no limit: the scripts write
`getNumOfEnemy(0, 5) - getNumOfBoss(0, 0)` and the same pair with `1` on
consecutive lines, which is *non-boss enemies near me*, then *near my master*.
See [`format_api.md`](format_api.md).

**`getNearestBossAction()` and `getTargetActId()` return the monster's own
action id**, and the disc says so: across all twelve scripts those two are
compared against **21 distinct values and every one is between 102 and 125**,
squarely inside the 100-to-128 block [`format_ai.md`](format_ai.md) reads as
the monster's attacks. So the two AI systems meet there. `check_active_swm`
reads

```
if (getNearestBossKind() == 28)
if (getNearestBossAction() == 108)
if (getRange(1) > 5)
    return -1
```

— *"monster kind 28 has started action 108 and I am more than five metres
away: hold off"* — and action 108 is motion 509 in that monster's own pac.

## What the tables share

Within a job the male and the female share their tables, and in five jobs of
six their script as well: `swm` and `sww` decompile to the same statements and
differ by one source line number. The Cleric is the exception, and its two
scripts genuinely differ. That is the arrangement the monster AI uses too —
shared tables, per-variant scripts — arrived at independently.

```
select_action  6 distinct: one per job
select_target  5 distinct: cl and mg share one
command_data   7 distinct: mgm and mgw differ from each other
target_data    6 distinct: htm and htw differ; hs and mg share one
```

57 of the 227 `prt` tables a job defines are never named by either of its own
scripts, and the pattern is regular: **`prt00` and `prt04` of `select_action`
are unreachable in all six jobs**, as are `prt01`, `prt09` and `prt10` of
`select_target` in five of the six. No script ever returns 0, so `prt00` reads
as the engine's own default rather than a dead table.

## The roster

`common.pac` carries three `ECH` tables, which [`format_ech.md`](format_ech.md)
opens, and one script:

- `mercenary_universal_db` — 13 rows x 8: an id, four message ids and an RGBA
  colour. Twelve mercenaries and a null row;
- `mercenary_special_db` — 169 rows x 28: four floats between 0.1 and 0.6 and
  eight message ids per row;
- `mercenary_common_db` — one row of 18 constants: twelve `1.0`, then 700,
  1.1, 1000, 15, 25, 30;
- `common_script.cnut` — one function, `print_root_table`.

## What is open

- **The command ids** other than 14, 15 and 0. Their operands are described
  above and they separate cleanly, but nothing on the disc names them. 8, 12,
  5 and 3 are openers with a range and a long timeout; 19 to 22 are rare.
- **The flag word at `+0x08`.** Twelve values, near-determined by the command,
  so it is likely a per-command parameter mask rather than free flags.
- **The seven words of `target_NN`.** Four of them vary and three are always
  zero.
- **Command 16**, two uses, both in the Mage's tables, both mid-run — a third
  press the disc does not name.
- **The message ids** in the two roster tables: they are in the 11000, 20000,
  30000, 80000, 120000-140000 and 170000 bands and no `TXT` pairing has been
  tried for them yet.
