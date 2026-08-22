# The monster AI — `ProbList.dat` and the decision scripts

**Status: read.** 84 `ProbList.dat` (**3,269 groups, 19,707 items**), 144
decision scripts (**29,100 instructions, 6,528 rules**), **0 unreadable**,
every file consumed to the byte. Ten of the 77 condition terms are named and
cover two thirds of the instructions. Reader:
[`../tools/ai.py`](../tools/ai.py).

83 monster directories carry an `ai.pac`, and between them the files in it are
the whole of a monster's behaviour:

    <name>.par  _act.par  _cmb.par  _coop.par  _dfa.par  _prowl.par   438
    <name>_SelectScript.dat                                            84
    <name>_ProwlScript.dat                                             60
    <name>_ProbList.dat                                                84
    <name>_EventTable.dat  _MotStream.dat                               8
    <name>.cnut                                                         6

The last line is the reason the rest could be read. **Six monsters ship their
AI twice** — once as these tables and once as compiled Squirrel, which
[`format_psq.md`](format_psq.md) opened. `monster.cpk/b01_00` has both, so
every reading below is checked instruction against decompiled line.

## `ProbList.dat` — the weighted action tables

```
0x00  u32   zero on all 84
0x04  u16   group count, the last group being a terminator
0x06  u16   item count
0x08  u32   zero
0x0C  u32   zero
0x10  (u16 group id, u16 first item) per group
      (u16 action id, u8 weight, u8 zero) per item
```

A group is a list of `(action, weight)`. **The file ends exactly at
`0x10 + 4 * groups + 4 * items` on all 84**, with no padding and no slack — the
arithmetic that turns a plausible reading into a fact. The index is
non-decreasing on all 84, the terminator's offset equals the item count on all
84, and an item's fourth byte is zero on all 19,707.

Group ids ascend on 79 of the 84; the five that do not repeat an id rather than
descend. **2,386 of the 3,269 groups have weights summing to exactly 100**, and
the rest do not — which is allowed, because the selector normalises. The script
proves that: `prt_select` computes `correct = 10000.0 / total` before it picks.

### The oracle

`AI_B01_OrcKing.cnut` defines `prt_0` through `prt_50`, each of them one call:

```
function prt_0()
    local rand = getRand()
    local ret  = prt_select(rand, 1, 8500, 4, 1500)
    return ret
```

and group 0 of `AI_B01_OrcKing_ProbList.dat` is `[(1, 85), (4, 15)]`. **The
script's weights are the table's multiplied by a hundred.**

Of the 31 `prt_N` the script defines, 26 have a group in the table, and **all
26 carry the same action ids in the same order.** 17 of them carry the same
weights as well; the other nine differ, and the five that have no group at all
are three-digit names (`prt_120`, `prt_130`, `prt_140`, `prt_145`, `prt_230`).

Where the weights differ, the disc says why: **`b18_00` and `b18_01` ship the
same `ProbList.dat` byte for byte and different `.cnut`.** The tables are
shared between a monster's difficulty variants; the scripts are not.

### What the selector does

`prt_select(rand, id, weight, …)` is a vararg function — one of the 19 on the
disc — and it is a weighted pick with one twist: an action equal to
`getLastActId()` has its weight passed through `getSelRevise` first, so a
monster is biased away from repeating itself. Weights are per ten thousand
inside the script and per hundred in the table.

## `SelectScript.dat` and `ProwlScript.dat` — the rules

A stream of **six-byte instructions**, `u16 a, u16 b, u16 op`. The word count
divides by three on all 144 files and all 144 end with one all-zero
instruction.

`op`'s low twelve bits are a **term** and its top nibble is flags:

```
0x1000   this instruction begins a rule, and `a` is the action it picks -
         a group id in the monster's own ProbList
0x8000   the negative branch of the term
```

A rule is a run of instructions that must all hold; the first carries the
action. 136 of the 144 files close with a rule whose term is `0x001` and no
operand, which is the unconditional fallback.

### The ten terms that are proven

```
op     term              plain                with 0x8000
0x03   other zako count  > b                  <= b
0x08   probability       rand <= b percent
0x09   AI type           == b                 != b
0x0a   action timer 1    >= b seconds
0x65   HP rate           >= b percent         < b percent
0x66   damage count      >= b                 < b
0x68   angry             is angry             is not angry
0x6e   last action id    == b                 != b
0x6f   action successes  > b                  <= b
0xd3   range to target   <= b/100 metres      > b/100
```

**The range is in hundredths of a unit**, the same convention the stage
`borderline` uses — see [`format_stage.md`](format_stage.md).

Every one of the ten came off the same alignment. The OrcKing's first rule is

```
(8, 0, 0x1009)  (0, 15, 0x000a)  (0, 0, 0x0068)
(0, 75, 0x8065)  (0, 700, 0x00d3)  (0, 20, 0x0008)
```

and the first branch of its `active_script`, decompiled, is

```
if (AIT_TYPE == 0) if (AIT_ANGRY == true) if (AIT_HP_CHK < 75)
if (AIT_RANGE <= 7) if (ACT_TIME1 >= 15) if (getRand() <= 2000)
    return prt_8()
```

— the same terms in the same order, with 75 against 75, 7 against 700, 15
against 15 and 2000 against 20, and the action `8` sitting in `a` of the
instruction that opens the rule. Its second and third rules are the same six
terms with 30 and 50, then 80 and 100, which is the script's next two branches
exactly.

**The OrcKing's first 56 rules pick the same group as the script's rules do, in
the same order.** The first that does not is rule 56, where the table picks
group 14 and the script `prt_140` — one of the five the table does not carry.
The other five monsters with both diverge at the first or third rule, which is
the same story as the weights: shared tables, per-variant scripts.

### What one monster reads like

`python tools/ai.py rules extract/tree AI_Z11_Domovoi_1`:

```
0  -> group 14   act_success > 0,  last_act == 101,  range <= 5.00,  chance rand <= 70%
1  -> group 13   range <= 5.00,  op_067(0, 0)
2  -> group 10   range <= 3.00
3  -> group 12   range > 3.00,  range <= 10.00
4  -> group 11   range > 10.00,  range <= 17.00
5  -> group 0    op_001(0, 0)
```

Rules are tried in order and the first whose terms all hold wins, which is why
the range bands are written as a ladder and why the last rule has no condition
at all.

## What is open

- **67 of the 77 terms.** Ten cover 19,435 of the 29,100 instructions; the
  commonest unnamed ones are `0x07` (795), `0x15` (719), `0xdc` (661), `0x6d`
  (606), `0xd2` (496), `0xd5` (481). The method that named the ten will name
  the rest: align a monster that has both forms, rule by rule. The six `.cnut`
  between them declare `AIT_TYPE`, `AIT_HP_CHK`, `AIT_DAMAGED`, `AIT_DOWNED`,
  `AIT_LAST_ACT`, `AIT_ACT_SUCCESS`, `AIT_RANGE`, `AIT_OTHER_ZAKO`,
  `AIT_OTHER_BOSS`, `AIT_TGT_AT`, `AIT_TGT_DOWN`, `AIT_TGT_JUMP`,
  `AIT_BOSS_TIME`, `AIT_ANGRY` and six `ACT_TIME` slots, so the vocabulary is
  known even where the encoding is not.
- **`0x2000` and `0x4000`**, on 434 instructions between them.
- **The action ids.** A group's items are ids like 1, 4, 100 to 110, 200 to
  205; the script prints `select_actid:` beside them and `chrSetMotion` takes
  something similar, but nothing here ties an action id to a motion.
- **The 438 `.par` files**, which are the other half of `ai.pac` and still
  unread. They carry no magic and their records look 64 bytes wide.
- **`EventTable.dat` and `MotStream.dat`**, eight files between them.
