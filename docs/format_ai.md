# The monster AI — `ProbList.dat`, the decision scripts and the `.par`

**Status: solved.** 84 `ProbList.dat` (**3,269 groups, 19,707 items**), 144
decision scripts (**29,100 instructions, 6,550 rules**), **438 `.par`**, **0
unreadable**, every file consumed to the byte. **66 of the 76 condition terms
the tables use are named**, off the game's own dispatch, and they cover
**27,862 of the 29,100 instructions**. An action id now names a motion. Reader:
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

**2,386 of the 3,269 groups have weights summing to exactly 100**, and the rest
do not — which is allowed, because the selector normalises. The script proves
that: `prt_select` computes `correct = 10000.0 / total` before it picks, and
an action equal to `getLastActId()` has its weight passed through
`getSelRevise` first, so a monster is biased away from repeating itself.
Since session 21 that function prints as its own source — three `while` loops,
the normalisation, the roll, and a Japanese fallback line that says *it was
not selected* — so this paragraph can be read off it instead of reconstructed.
See [`format_psq.md`](format_psq.md).

## `SelectScript.dat` and `ProwlScript.dat` — the rules

A stream of **six-byte instructions**, `u16 a, u16 b, u16 op`. The word count
divides by three on all 144 files and all 144 end with one all-zero
instruction.

`op`'s low twelve bits are a **term** and its top nibble is flags:

```
0x1000   this instruction begins a rule, and `a` is the action it picks -
         a group id in the monster's own ProbList
0x2000   so does this one, on 22 instructions - see below
0x4000   this term is ORed with its neighbours, on 421 instructions
0x8000   the negative branch of the term
```

A rule is a run of instructions that must all hold; the first carries the
action. 136 of the 144 files close with a rule whose term is `0x001` and no
operand, which is the unconditional fallback. Rules are tried in order and the
first whose terms all hold wins, which is why the range bands are written as a
ladder.

### The term vocabulary

`check_converted_xml_term(term, param, cond)` in the `.cnut` **is the term
table**. It is a switch on exactly these ids, it is byte-identical in all six
`.cnut` (all at `.ppcut` line 1174, so it is a shared include), and its ten
already-proven entries agree with what the previous alignment found. The name
says what it is: the AI was authored as XML, converted to these numeric terms,
and this function is the reference implementation of the converted form.

Every term dispatches to one host call, and `cond` is the `0x8000` flag —
the function ends `ret = (ret == cond)`.

**Since session 21 it prints as its own source.** `psq.py src` rebuilds
control flow, so the function that this table was read out of by correlation
now comes back as the `switch` it was written as, and the table can be checked
against it line by line rather than inferred from call order. It also makes
one row visible as the author wrote it: **terms 10 to 17 share a single case**,
falling through to one body that calls `getTimeFromID(term)` and keys the
timer on the term's own id — which is why the eight of them are one row here
and not eight. See [`format_psq.md`](format_psq.md).

```
      case 10:
        // falls through
      ...
      case 17:
        local time = getTimeFromID(term)
        if ((time == 0) || (time >= param)) {
            ret = true
        }
        break
      case 119:
        local time = getTimeFromID(term)
        if (time >= param) {
            ret = true
        }
        break
```

The `||` in there is a fold the same session added: unfolded, that line
printed as a test of `time >= param` alone, and `time == 0` — the case that
makes an unstarted timer pass — was not in the listing at all.

```
op     id   term            reads                     host call
0x001    1  always          true
0x002    2  total_time      <= b seconds              getTotalTime
0x003    3  other_zako      > 0 and >= b              getOtherZakoCount
0x004    4  other_boss      > 0                       getOtherBossCount
0x007    7  players         >= b                      getPlayerCount
0x008    8  chance          rand < b percent          getRand
0x009    9  ai_type         == b                      getAIType
0x00a-11 10-17 act_time1-8  == 0 or >= b seconds      getTimeFromID
0x012   18  boss_time       <= b seconds              getBossTime
0x013   19  no_zako         no other zako alive       getOtherZakoCount
0x014   20  boss_target     the target is boss b      isBossToTarget
0x015   21  same_kind       >= b of the same kind     getActiveSameKindCount
0x065  101  hp_rate         >= b percent              getHpRate
0x066  102  damaged         >= b                      getDamagedCount
0x067  103  downed          downed, and <= b          isDowned
0x068  104  angry                                     isAngry
0x069  105  poison                                    isPoison
0x06a  106  cure_poison                               isRecoverPoison
0x06b  107  cure_paralysis                            isRecoverParalyz
0x06c  108  cure_faint                                isRecoverFaint
0x06d  109  part_broken     part b is broken off      isDestroyedParts
0x06e  110  last_act        == b                      getLastActId
0x06f  111  act_success     > 0 if b is 0, else >= b  getActSuccessCount
0x070  112  angry_req                                 isAngryReq
0x071  113  stagger         >= b                      getStaggerCount
0x072  114  react                                     isReact
0x073  115  part_damage     part b                    getPartsDamageCount
0x074  116  to_active                                 isToActive
0x075  117  failed_rot                                isFailedRotation
0x076  118  failed_act      >= b                      getFailedActCount
0x077  119  act_time119     >= b seconds              getTimeFromID
0x0c9  201  tgt_hp_rate     >= b percent              getTargetHpRate
0x0ca  202  tgt_job         == b                      getTargetJob
0x0cb  203  tgt_ground                                isTargetGround
0x0cc  204  tgt_attack                                isTargetAttack
0x0cd  205  tgt_guard                                 isTargetGuard
0x0ce  206  tgt_sway                                  isTargetSway
0x0cf  207  tgt_jump                                  isTargetJump
0x0d0  208  range_band      == 0                      checkRangeParam
0x0d1  209  range_band      == 2                      checkRangeParam
0x0d2  210  range_band      == 1                      checkRangeParam
0x0d3  211  range           < b/100                   getTargetRange
0x0d4  212  dmg_from_tgt    >= b                      getDamageFromTarget
0x0d5-6 213-214 angle_to    == the term's own id      getAngleTypeToTarget
0x0d7-a 215-218 angle_at    == the term's own id      getAngleTypeAtTarget
0x0db  219  lock_range      a lock target within b    getLockTargetRange
0x0dc  220  tgt_pos_y       >= b/100                  getTargetPosy
0x0dd  221  tgt_area        == b                      getTargetArea
0x0de  222  tgt_object                                isTargetObject
0x0df  223  tgt_damage                                isTargetDamage
0x0e0  224  tgt_down                                  isTargetDown
0x0e1  225  range           < b/100 times the scale   getTargetRange, getScale
0x3e9-ed 1001-1005                                    checkB15Term
0x3f3  1011                                           checkB09Term
0x3fd-ff 1021-1023                                    checkB11Term
0x41b  1051                                           checkB05Term
0x425  1061                                           checkB01Term
0x426  1062  b18_tire                                 checkB18Term
0x427  1063                                           checkB19Term
0x42a  1066  b19_head                                 checkB19Term
```

Every name in the right-hand column is a host function the engine has to
provide, and [`format_api.md`](format_api.md) lists them beside the rest of the
interface. One of them is worth noting here: the dispatch's fall-through prints
`I don't know the word is ` and then calls `printAitIdName(term)`, so **the
engine holds a name for every term id** — a string table to look for when the
EBOOT opens.

**Every distance is in hundredths of a unit**, the same convention the stage
`borderline` uses — see [`format_stage.md`](format_stage.md).

Two of the entries are subtler than a comparison, and both are read out of the
bytecode rather than the decompiled statement:

- **term 3** is `zako > 0 && zako >= param`, so a zero operand means *any*.
  The OrcKing's script writes `AIT_OTHER_ZAKO < 1` exactly where the table has
  `0` under `0x8000`, which is what confirms it;
- **term 111** is `param == 0 ? success != 0 : success >= param`, and the
  script's first branch writes `AIT_ACT_SUCCESS > 0` against the table's `0`.

### The alignment that checks it

The OrcKing's first rule is

```
(8, 0, 0x1009)  (0, 15, 0x000a)  (0, 0, 0x0068)
(0, 75, 0x8065)  (0, 700, 0x00d3)  (0, 20, 0x0008)
```

and the first branch of its `active_script`, decompiled, is

```
if (AIT_TYPE == 0) if (AIT_ANGRY == true) if (AIT_HP_CHK < 75)
if (AIT_RANGE <= 7) if (ACT_TIME1 >= 15) if (getRand() <= 2000)
    print('ct_actで定義した行動開始から15秒経過\n')
    return prt_8()
```

— the same terms in the same order, with 75 against 75, 7 against 700, 15
against 15 and 2000 against 20, and the action `8` sitting in `a` of the
instruction that opens the rule. Its second and third rules are the same six
terms with 30 and 50, then 80 and 100, which is the script's next two branches
exactly. That debug line also names `ct_act`, which is `_act.par` below.

**The OrcKing's first 56 rules pick the same group as the script's rules do, in
the same order.** `AI_B18_Nidhogg` gives the same check independently: its
table's first two rules are `boss_time <= 2s` and its script's first branch is
`if (BossTime < 2)`.

### `0x2000` — a rule that continues the one before it

22 instructions carry `0x2000`. Of the 22,428 instructions that do *not* carry
`0x1000`, **exactly those 22 have a non-zero `a`, and every one of the 22 is a
valid group id in that monster's own `ProbList`** — so `0x2000` opens a rule
just as `0x1000` does. What is different is where it sits. `AI_Z07_Angel`:

```
31  a=1  range < 4.00     0x10d3
32  a=4  tgt_jump         0x20cf
33  a=3  range < 8.00     0x10d3
34  a=5  tgt_jump         0x20cf
35  a=2  range < 20.00    0x10d3
36  a=6  tgt_jump         0x20cf
```

It reads as *"within 4 metres pick group 1, and if the target is also jumping
pick group 4 instead"* — a rule that inherits the conditions of the rule above
it and adds one. `ai.py rules` marks them with a `+`.

### `0x4000` — an OR group

421 instructions carry `0x4000`, in runs of two (143) and three (45). A run is
a disjunction, and the disc proves it by contradiction: the terms in a run are
mutually exclusive, so under an AND reading every one of those rules would be
dead.

```
AI_B05_Fafnir   angle_at == 217 or angle_at == 218
AI_B12_Fenia    range_band == 0 or range_band == 2
AI_Z01_Orc      ai_type != 2,  ai_type == 1 or ai_type == 0
```

`getAngleTypeAtTarget()` cannot return 217 and 218 at once, and
`checkRangeParam()` cannot be 0 and 2 at once.

### The engine's own name for a term — session 30

The EBOOT is open ([`format_self.md`](format_self.md)), and the first thing it
gave up is the table this document has wanted since session 18: the `AIT_*`
enum `printAitIdName` prints from, **78 names on a 24-byte stride**.

```
$ python tools/self.py names eboot.elf
78 AIT_* condition-term names
  0x001  AIT_ALWAYS
  0x002  AIT_TOTAL_TIME
  ...
  0x005  AIT_WALL_RANGE
  0x006  AIT_FLOOR_ATTR
  ...
  0x0d0  AIT_RANGE_S
  0x0d1  AIT_RANGE_M
  0x0d2  AIT_RANGE_L
  0x0d5  AIT_TGT_FRONT
  0x0d6  AIT_TGT_REAR
  0x0d7  AIT_FRONT_TGT
  0x0d8  AIT_REAR_TGT
  0x0d9  AIT_LEFT_TGT
  0x0da  AIT_RIGHT_TGT
```
(the tool prints all 78; [`ai.py`](../tools/ai.py) holds them as `AIT`)

**The join is the band structure, three times over.** The enum is a flat run
of names; the disc's term ids come in bands — `0x001`–`0x015`, `0x065`–`0x077`,
`0x0c9`–`0x0e1`, then the boss block. Laid end to end the bands are **21, 19
and 25 long and the enum's first three runs are 21, 19 and 25**, and the boss
names that follow are five `B15`, one `B09`, three `B11`, one `B05`, one
`B01`, one `B18` and one `B19` against ids 1001–1005, 1011, 1021–1023, 1051,
1061, 1062 and 1063 — **the same seven functions in the same order**, which
[`ai.py`](../tools/ai.py) had already worked out from the `.cnut` alone.

Three coincidences of that size are not a coincidence. And what falls out is
this document's own homework marked:

- **every one of the 65 named ids agrees with the reading taken off the
  `.cnut`.** `AIT_HP_CHK` is `getHpRate`, `AIT_STAGGER_CHK` is the stagger
  count, `AIT_SCL_RANGE` is the range divided by the scale, `AIT_TGT_SWAY` is
  the target dodging. Nothing had to be revised;
- **`0x0d5`/`0x0d6` are `AIT_TGT_FRONT`/`AIT_TGT_REAR` and `0x0d7`–`0x0da` are
  `AIT_FRONT_TGT`/`REAR_TGT`/`LEFT_TGT`/`RIGHT_TGT`.** That settles the
  reading [`brain.py`](../engine/brain.py) declared as its own and could not
  prove: *to* the target is where the target sits in my frame, *at* the target
  is where I sit in its. Two bands and four, named in the engine's word order;
- **`0x0d0`–`0x0d2` are `AIT_RANGE_S`, `_M` and `_L`** — three ordered bands,
  which is the other reading `brain.py` declared. What the engine's names do
  *not* say is where the far band ends, so the "twice the range" half of that
  reading stands unproved;
- **`0x077` is `AIT_ANGRY_TIME`**, which gives timer id 119 a name it never
  had: it is how long the monster has been angry;
- **two ids get a first name**: `0x005` `AIT_WALL_RANGE` and `0x006`
  `AIT_FLOOR_ATTR`. Neither is used by any of the 144 tables, which is why
  nothing had found them — a distance to a wall and a floor attribute, and
  the second is the only place on this disc that suggests the `CCLS` surface
  codes are read by anything at all.

Thirteen of the 78 names are used by no table, and **eleven of the 76 ids the
tables do use have no name** — which is the next section, and the shape of it
just got sharper.

### The ten terms the dispatch does not carry

`0x0e2`–`0x0e6`, `0x0e9`, `0x0f0`, `0x0fa`–`0x0fc`, 1,094 instructions between
them. **The tables are newer than the `.cnut`**, and `b19_00` proves it: it
ships both, and its `SelectScript.dat` uses term `0x42a` (1066) while its own
dispatch stops at 1063 — yet its `active_script` calls `checkB19Term(1066, 0)`
beside the debug line `atama moge modoi huka`, which is how 1066 gets a name
after all. The ten that remain are characterised only by their operands:

```
0x0e2  226  a distance in hundredths, 0.15 to 4.50   \ always used together,
0x0e3  227  an action id, 100 to 110                  > and usually with 0x0f0
0x0e4  228  a count, 1 to 3                          /
0x0e5  229  a distance in hundredths, 5.00 to 15.00  \ always used together
0x0e6  230  a count, 2 to 6                          /
0x0e9  233  a distance in hundredths                  AI_Z26_DomovoiThief only
0x0f0  240  always 180 - an angle in degrees
0x0fa  250  99 or 50 - a percentage                  \ always used together,
0x0fb  251  always 30                                 > AI_Z21_Nfdeadkafra
0x0fc  252  always 0                                 /
```

The 226/227/228 cluster reads as a query about *other* monsters — a radius, an
action they are performing and a count — but nothing on the disc says so.

**And nothing in the EBOOT says so either**, which is session 30's
contribution to this list and is worth stating as a result rather than as a
disappointment. The `AIT_*` enum stops at `AIT_SCL_RANGE` = `0x0e1`; these ten
are `0x0e2` and up. So the ten terms are missing from the shared `.cnut`
include **and** from the shipped engine's own debug name table, and the
eleventh, `0x42a`, is missing from the enum too while `b19_00`'s script names
it. The tables are newer than both artefacts that could have named them, and
the only thing left that can is the dispatch itself, in code.

### What one monster reads like

`python tools/ai.py rules extract/tree AI_Z11_Domovoi_1`:

```
0  -> group 14   act_success > 0,  last_act == 101,  range < 5.00,
                 chance rand < 70%
1  -> group 13   range < 5.00,  downed <= 0
2  -> group 10   range < 3.00
3  -> group 12   range >= 3.00,  range < 10.00
4  -> group 11   range >= 10.00,  range < 17.00
5  -> group 0    always
```

## An action id names a motion

A group's items are action ids, and the ids fall into three blocks. **A motion
file names itself**: `monster.cpk/pac/z11.pac` holds `z11201wait_1.CNOM`,
`z11501at1.CNOM` and so on, a three-digit id and a name. Add a constant and the
two meet:

```
action    0 - 99    motion = action + 200     wait_1, wait_3, wait_5, down_f
action  100 - 199   motion = action + 401     at1, at2, at3, ...
action  200 - 299   motion = action + 301     the same at1, at2, at3, ...
```

**1,109 of the 1,423 action ids a `ProbList` picks name a motion in the
monster's own pac — 927 of them an `at*`, 168 a `wait*` and 14 a `down*`** —
and the order is exact: 100 is `at1`, 101 is `at2`, 102 is `at3`. Nothing else
lands there; the mapping is not a coincidence of a dense band.

Of the 314 that do not, 57 are action `4`, which no monster ever resolves and
which is therefore a behaviour (approach) rather than a motion; the rest are
actions whose motion lives in a sister pac. Three of the giants share one
motion set — `z18.pac` ships `z19*.CNOM` — so the reader indexes a motion
under both the directory and the filename prefix.

The `2xx` block is the `1xx` block again, one hundred lower: for 287 of 331
uses the monster's own `_act.par` defines `action - 100`, and
`AI_Z27_YamiGiant_1` picks 200, 201, 205, 206, 207, 208, 209, 210 beside 100,
101, 105, 106, 107, 108, 109 — the same attacks under a second id. What the
second id means is not established.

This is the join to the animation layer: an `.anmcmd` is named by the same
three-digit motion id — `b01_00/animcmd.pac/b01_00_501.anmcmd` is the event
list of `at1`. See [`format_anmcmd.md`](format_anmcmd.md).

## Running it, and the three things that came out

**Session 22 executed all of this**: [`../engine/brain.py`](../engine/brain.py)
evaluates the ladder, rolls the group and resolves the action, and
[`../engine/fight.py`](../engine/fight.py) puts the result on a stage. Over
random states, **83 of 83 monsters decide on every one of 40 states**, and
3,320 rolled actions name a motion 2,631 times. Three things fell out that
reading the tables could not produce.

### The dispatch is executable, so it can check the reading

`check_converted_xml_term` is not documentation any more - the Squirrel VM
[`format_psq.md`](format_psq.md) describes runs it. `brain.py terms` puts this
project's own term evaluator beside the disc's own, over **every one of the 458
`(term, operand)` pairs the 144 files actually use**, in 20 random states, both
polarities: **15,040 comparisons and 0 disagreements**.

### Two terms are dead as the include writes them

Squirrel refuses to compare a bool with an integer and its `==` is false
between types, and running the dispatch shows two places where that bites:

- **term 103**, `check_term_param(isDowned(), param)`, *throws* when the
  operand is non-zero, because it compares the flag against the operand. Five
  instructions on the disc pass a non-zero operand there;
- **term 115**, `ret = getPartsDamageCount(param)`, leaves an integer where
  the next line writes `ret == cond` against a boolean, so the term is
  **never true either way**. 47 instructions use it.

Both read cleanly if the engine's own `isDowned` and `getPartsDamageCount`
return numbers rather than flags, which is what the names say and what
[`../engine/brain.py`](../engine/brain.py) assumes.

### The chance term: the include and the hand-written rules disagree

The dispatch writes term 8 as `getRand() * 100 < param`. `getRand()` returns
0 to 10,000 - `prt_select` normalises its weights to 10,000 and rolls against
them - so under that form a 20% chance fires only on a roll of exactly zero.
The OrcKing's own hand-written branch for the same rule reads
`getRand() <= 2000` against a table operand of 20, which is
`rand <= param * 100`.

Running both settles it. Driving the table and the script from the same state
and the same roll, over 300 states, **the OrcKing's table picks the same group
as its script 217 times under the include's form and 293 under the other**.
The include is the converted artefact; the branch is what the author wrote.

The other five `.cnut` do not give the same check, and the disc says why: the
`b18` and `b19` tables are **shared between difficulty variants whose scripts
are not**, so at most one variant can match, and their scripts pick
three-digit `prt_N` that their own `ProbList` has no group for at all - on
`AI_B18_Nidhogg` that is 180 of 300 states.

## The six `.par`

Four of them are arrays of fixed-width records closed by a sentinel word, and
the sentinel is exact on **all 308 of them**; two are single structs.

```
kind      files  record  sentinel     what it is
<name>    82     64      0x7FFFFFFF   the per-action parameter block
_act      82     32      0x00000000   a range and a facing angle per action
_cmb      62     16      0x00000000   chains of up to three actions
_dfa      82      4      0xFFFFFFFF   a list of motion ids
_coop     71     20 or 60  -          one struct: three ids, a range, a time
_prowl    59     16        -          one struct, the same on 57 of the 59
```

### `_act.par` — the per-action gate, and what its range is a range to

**The hit volumes on the same action's motion say.** `_act.par` gives an
action one distance and nothing on the disc says what it measures. The
`.anmcmd` of the motion that action names says how far its hit volumes get
from the body - a different file, read by a different tool, in the same
metres. `fight.py reach` puts them side by side over every action of every
monster:

```
83 monsters, 250 actions with a real range in `_act.par` and a hit record
             on their motion
  the gate runs 1.20 to 99.00 m, median 7.50; the reach 0.71 to 76.71,
             median 4.39
  correlation 0.590 over 250 pairs
  the same pairs reshuffled 200 times: 0.051 on average, 0.231 at the best
```

**0.590 against a shuffled control of 0.051.** So the range is a distance to
the *target*, measured in the same units as the swing that follows, and it is
systematically the longer of the two - shorter than the gate on 171 of the 250
- which is what a gate on *starting* an attack should be: the wind-up has to
be worth it before the blow lands.

### `_act.par` — the per-action gate

```
0x00  u32   action id: 100 to 128, and 5
0x04  f32   a range; 100.0 on an unused slot and 999.0 for "any"
0x08  u16   a facing angle, 0x10000 to the turn - every value on the disc is
            a multiple of 2048, so 33.75, 45, 67.5, 90, 112.5, 135, 180 ...
0x0a  u8    0 or 50
0x0b  u8    30 on 1,004 of the 1,063 records
0x0c  u16   0 on 968 of them
0x0e  u16   0 on 820 of them
0x10        sixteen zero bytes on every record on the disc
```

The OrcKing's own debug print calls this file `ct_act` — 「ct_actで定義した
行動開始から15秒経過」, *"fifteen seconds since the action defined in ct_act
began"* — which is what ties it to the `act_time` terms. The range here and
the three-valued `checkRangeParam` of terms 208/209/210 are the natural pair:
one distance per action, and a term that says whether the target is inside it.

`python tools/ai.py par extract/tree AI_Z11_Domovoi`:

```
act 100  range 3.00     angle 67.50    50  30   0   0   -> at1
act 101  range 18.00    angle 135.00   50  30   0   0   -> at2
act 102  range 0.00     angle 0.00      0  30   0   0   -> at3
act 5    range 10.00    angle 0.00      0  30   0  80   -> wait_5
```

### `<name>.par` — the per-action parameter block

```
0x00  u32   0x2000 + 0x10 * k, and sub-slots 0x2001, 0x2002, ...
0x04  u8    a kind, 0 to 16
0x05  u8    rarely used
0x06  u8    a second selector
0x08  u32   a value
0x0C  u32   0x80000000 on 1,197 of the 1,206 records
0x10        forty-eight zero bytes on every record on the disc
```

**On 74 of the 82 monsters the top-level slots are exactly
`0x2000 + 0x10 * k`, one per 1xx action in the same monster's `_act.par`** —
so slot `k` is action `100 + k`, and `.1`/`.2`/`.3` are extra entries on the
same action. The eight exceptions differ by a slot or two. 74 distinct slot
ids occur across the disc; what a `kind` selects is not established.

### `_cmb.par` — the combo chains

Three action ids and two `u16`; the second and third id may be zero.

```
0x00  u32   the action this row is about
0x04  u32   the action that follows it
0x08  u32   a third, on 185 of the 511 records
0x0C  u16   0 on 502 of the 511
0x0E  u16   0 on 510 of the 511
```

The OrcKing has 17 rows: `104 -> 100`, `107 -> 104 -> 104`, `109 -> 101 ->
103`, and so on.

### `_dfa.par` — a list of motions

`u16 motion id, u8 mode, u8 zero`, closed by `0xFFFFFFFF`. **944 of the 1,007
ids name a motion in the monster's own pac**, 778 of them an `at*` and 126 a
`wait_*`, and the 63 that do not are in the same `5xx` band with their `.CNOM`
in a sister pac. The mode byte is 1 on 889 of the 1,007 records, 3 on 75 and
2 on 28; the fourth byte is zero on all 1,007.

### `_coop.par` and `_prowl.par`

`_coop.par` is one 20-byte struct, padded to 60 on 36 of the 71 files:

```
0x00  u16 x3   ids in the 1000 to 1250 band, in triples - 1040, 1041, 1042
0x06  u8 x6    a pair per id, (1, 1) on most
0x0C  f32      a distance: 5, 10, 15, 20, 24, 40, 50
0x10  u32      a time: 10, 300, 3000, 6000 or 60000
```

`_prowl.par` is 16 bytes and **57 of the 59 files are byte-identical** —
`12 1e 1c 18 00 00 00 00 05 0a 0e 10 12 16 0f 00`, two ascending runs — so it
is a shared default that two monsters override.

## What is open

- **The seven per-boss escape hatches.** `checkB01Term` and its six siblings
  are host functions, not script: nine tables call thirteen term ids on 458
  instructions and **nothing on the disc defines any of them**. Session 30
  located all seven in the EBOOT's own predicate table — B01, B05, B09, B11,
  B15, B18, B19, with a function address each — so what is left is reading
  seven small functions rather than finding them. `b18` and
  `b19` implement theirs for their own variants - `AI_B01_OrcKing_2` uses term
  1061 and ships no `.cnut` of its own - so the implementation is once per
  boss family, inside the binary. Same shape of hole as `prowl_script`;
- **Two terms are dead as the include writes them**, and session 22 found both
  by running it: 103 throws on a non-zero operand and 115 is never true. Both
  read cleanly if the engine's `isDowned` and `getPartsDamageCount` return
  numbers rather than flags, which is what their names say;
- **Ten of the 76 terms**, 1,094 instructions, listed above, plus `0x42a`.
  They are not in the `.cnut` dispatch because the tables are the newer
  artefact, and session 30 showed they are not in the EBOOT's `AIT_*` enum
  either. (`ai.py ops`
  counts 77 codes; the seventy-seventh is the all-zero word that ends a
  file.)
- **What the `2xx` action block means.** The ids resolve to the same `at*`
  motions as the `1xx` block; only `SelectScript.dat` uses them, never
  `ProwlScript.dat`, so it is not the prowl/combat split.
- **The `<name>.par` `kind` byte**, 0 to 16, and what the value at `0x08`
  measures. The slot-to-action pairing is established; the field is not.
- **`_coop.par`'s 1000-band ids** — they are not action ids and not motion
  ids.
- **`EventTable.dat` and `MotStream.dat`**, eight files between them, still
  unread.
- The five `ProbList` files whose group ids repeat rather than ascend.
