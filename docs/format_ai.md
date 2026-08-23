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

```
op     id   term            reads                     host call
0x001    1  always          true
0x002    2  total_time      <= b seconds              getTotalTime
0x003    3  other_zako      > 0 and >= b              getOtherZakoCount
0x004    4  other_boss      > 0                       getOtherBossCount
0x007    7  players         >= b                      getPlayerCount
0x008    8  chance          rand < b percent          getRand
0x009    9  ai_type         == b                      getAIType
0x00a-11 10-17 act_time1-8  >= b seconds              getTimeFromID
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

- **Ten of the 76 terms**, 1,094 instructions, listed above. They are not in
  the `.cnut` dispatch because the tables are the newer artefact. (`ai.py ops`
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
