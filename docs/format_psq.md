# The script layer — `.psq` and `.cnut` are Squirrel

**Status: solved.** 3,011 files, **11,232 functions, 314,930 instructions,
55,368 literals, 0 unreadable**, every file consumed to the byte. Reader:
[`../tools/psq.py`](../tools/psq.py).

`.psq` is **Squirrel 2.2 bytecode**, exactly as `sq_writeclosure` emits it on a
big-endian host. There is a scripting layer on this disc after all;
[`STRATEGY.md`](STRATEGY.md) said there was not, and said it twice.

## What ends the question in four words

The file opens `FA FA 'SQIR'`. Both halves are Squirrel constants:

    #define SQ_BYTECODE_STREAM_TAG  0xFAFA
    #define SQ_CLOSURESTREAM_HEAD   'SQIR'
    #define SQ_CLOSURESTREAM_PART   'PART'
    #define SQ_CLOSURESTREAM_TAIL   'TAIL'

and the word that introduces every string in the file, `0x08000010`, is
`OT_STRING` — `_RT_STRING | SQOBJECT_REF_COUNTED`, `0x10 | 0x08000000`. The
`00 00 00 01` after `SQIR` is `sizeof(SQChar)`, so this is an 8-bit build.

Six sessions of `TODO` had `.psq` down as "the compiled cutscene language,
`FA FA 'SQIR'` then `PART` chunks", and the reading that fell out of it was
that `PART` was a chunk with a payload. It is not a chunk at all; it is a
separator between the fields of one serialised record, which is why `PART`
sometimes follows `PART` with nothing in between.

## The container

    fa fa                     SQ_BYTECODE_STREAM_TAG
    'SQIR'  u32               head, then sizeof(SQChar) = 1
    'PART'  function          the root closure
    'TAIL'

A function is `SQFunctionProto::Save` verbatim: two strings, then eight counts,
then eight `PART`-separated tables, then three trailing fields.

```
OT_STRING  source file name        always `<something>.ppcut`
OT_STRING  function name
'PART'
u32 × 8    nliterals, nparameters, noutervalues, nlocalvarinfos,
           nlineinfos, ndefaultparams, ninstructions, nfunctions
'PART'   literals       OT_STRING objects
'PART'   parameters     OT_STRING names
'PART'   outervalues    (type, src, name) triples
'PART'   localvarinfos  (OT_STRING name, u32 register, u32 first pc, u32 last)
'PART'   lineinfos      (u32 source line, u32 pc)
'PART'   defaultparams  u32 each
'PART'   instructions   s32 _arg1, then u8 op, _arg0, _arg2, _arg3
'PART'   functions      each child preceded by its own 'PART'
u32 u8 u8  _stacksize, _bgenerator, _varparams
```

What the corpus says about those tables:

- **every one of the 55,368 literals is a string** — 3,790 distinct. Squirrel
  puts integers in `_OP_LOADINT`'s `_arg1` and floats in `_OP_LOADFLOAT`'s, so
  the pool only ever holds names and text. **1,578 of them are Japanese and
  all 1,578 are valid UTF-8**, which is worth knowing because most Japanese
  text on a PS3 disc of this vintage is Shift-JIS and this is not;
- **parameter 0 is `this` on all 11,232 functions**, which is Squirrel's
  calling convention and a free check that the parameter table is being read
  from the right place;
- **`noutervalues` is 0 on all 11,232.** Nothing on the disc closes over a free
  variable, and `_OP_LOADFREEVAR` never appears — the two agree;
- **`_stacksize` covers every register the code touches on all 11,232**, which
  is what identifies it, since the field carries no name;
- **`_bgenerator` is 0 everywhere and `_varparams` is 1 on exactly the 19
  functions that use `_OP_VARGC`.** That count is what says the last six bytes
  are `u32 + u8 + u8` and not `u32 + u16`: the flag lands in the low byte,
  19 times, against 19 uses of the opcode that reads it.

## The instruction, and which Squirrel this is

`SQInstruction` is eight bytes and the first four are the wide operand:

```c
struct SQInstruction {
    SQInt32       _arg1;
    unsigned char op, _arg0, _arg2, _arg3;
};
```

The header carries no version, so the opcode table has to be established from
the code. Three things do it, independently:

- **the highest opcode on the disc is `0x3C`**, and `_OP_NEWSLOTA` is the last
  entry of Squirrel 2.2's enum. Squirrel 3.x renumbers everything from
  `_OP_ARITH` onwards and inserts `_OP_JCMP`; under a 3.x table the byte that
  ends all 11,232 functions decodes as `_OP_MUL`;
- **`_OP_ARITH`'s `_arg3` is the operator as an ASCII character** — 4,423 `+`,
  674 `*`, 295 `-`, 42 `/`, and nothing else in 5,434 instructions. A wrong
  opcode assignment puts arbitrary bytes in that field;
- **`CLAMP` decodes to its own source.** `misc.cpk/psq_common.pac/common.psq`
  carries a three-line `CLAMP(v, l, h)`. Its twelve instructions read
  `CMP r4 = (v < l)` with `_arg3 = 3 = CMP_L`, then `CMP r5 = (v > h)` with
  `_arg3 = 0 = CMP_G`, then the two moves of a ternary chain. Get the operand
  order backwards — `STK(_arg2)` against `STK(_arg1)` rather than the reverse
  — and the function reads `l > v` and clamps the wrong way round. Squirrel's
  own `CmpOP` enum is `G=0, GE=2, L=3, LE=4, 3W=5`, and the two the file uses
  are the two that discriminate.

41 of the 61 opcodes appear. `_OP_BITW`, `_OP_YIELD`, `_OP_RESUME`,
`_OP_PUSHTRAP`, `_OP_THROW` and the rest of the missing twenty do not, which
is a fair description of what game cutscene script does and does not need.

## The source survives the compile

Squirrel keeps its debug tables and this build shipped them, so a `.psq` is not
an anonymous blob:

- **every function names the file it came from**, and every one of those names
  ends `.ppcut` — a *preprocessed* cut file. The compile ran over macro-expanded
  source;
- **every instruction has a source line.** `lineinfos` maps pc to line, so a
  disassembly can be printed against the author's own line numbering;
- **`localvarinfos` names every local and gives its live range**, which is what
  turns registers back into variables. `psq.py src` uses the range: the write
  one instruction before a local's `first pc` is its declaration, so that
  instruction prints as `local frameA = getDemoFrame()` and every later use of
  the register prints as `frameA`.

The result reads as Squirrel. This is `demo.cpk/010_01_01.pac/010_01_01.psq`,
the opening cutscene, verbatim from `psq.py src`:

```
function main()
    demoPhase <- 0
    demoCount <- 0
    telopLife <- 0
    bgmCueA <- -1
    demoInitBGM <- function demoInitBGM
    demoInit <- function demoInit
    demoUpdate <- function demoUpdate
    bgmCueA = 3
    bgmCueB = 500

function demoInit()
    print('--- demo Init ---\n')
    demoInitActor()
    visibleFieldInfo(0)
    setDemoObiHeight(50, 10)
    initDemoTelop(448, 332)
    cfSetCameraType(4, 0, 0)
    if (!(bgmCueA != -1)) goto L31
    cfSndPlayBGM(0, bgmCueA, 0)
```

Control flow is printed as labels and `goto`, not rebuilt into `if`/`while`.
That is a deliberate limit: the jumps are recovered exactly and the structure
is not guessed at.

The comments are in the clear too. `quest.cpk/q00101.pac/010_01_01.psq` is
three functions long and one of them is

```
function sfQuestInit()
    if (!(cfGetGlobalFlag(1368) == 0)) goto L13
    print('★★ 図鑑用のフラグ立てる ★★ \n')
    cfSetGlobalFlag(1368, 1)
```

— "set the flag for the encyclopedia", with the global flag number beside it.

## Two vocabularies: 296 script names and 291 engine names

`psq.py api` lists every name fetched off the root table and called, with the
arity of each call. **587 names are called; 296 of them are defined by some
`.psq` and 291 are not.** Those 291 are the engine's script interface — the
host functions a reimplementation has to provide — and they are now a closed
list rather than an open question. 120 begin `cf`, 58 `get`, 29 `is`.

**What each of them does is [`format_api.md`](format_api.md)**, which was
written by reading the call sites rather than the executable.

The busiest of them, with call counts:

    6558  print              1730  cfSetQuestFlag     1609  getCharacter
    1476  cfSetGlobalFlag    1460  cfSetEnableHitArea 1227  cfGetGlobalFlag
    1193  chrPlayVoice        908  cfGetQuestFlag      901  chrSetMotion
     892  cfGetCntKillGenPieceLockOnly            889  cfStartPieceLock
     732  cfEndPieceLock      687  cfSetEnableBorderline

### The count was 453 and 289 for six sessions, and it was low twice

Both errors are the same one: `api` looked only for `_OP_PREPCALLK` followed by
`_OP_CALL`.

- **`_OP_TAILCALL` is a call.** `return active_script()` compiles to `0x05`,
  and 132 script names and one native hid behind it;
- **a root call can go through a computed key.** Nearly every quest script
  opens `cntGenKill <- this['cfGetCntKillGenPieceLockOnly']()`, which is
  `_OP_PREPCALL` on a string literal. That name is called **892 times** and was
  on no list.

## The names name things — `psq.py xref`

The vocabulary [`format_stage.md`](format_stage.md) found inside `trigger.trg`
is this vocabulary, and the string arguments resolve against the stage tables
that session read:

    cfSetEnableHitArea      1457 resolve,    2 do not     ATIH marker, own stage
    cfSetEnableBorderline    679 resolve,    7 do not     borderline polyline
    cfMapJump                147 resolve,    0 do not     stage + arrival marker
    cfSetEnableEmGen         203 resolve,   37 do not     emgen_pos marker
    getCharacter            1362 resolve,   45 do not     ATIH marker pos_<name>
    cfGetPosInHta             25 resolve,    1 do not     ATIH marker
    trg callQuestScript      144 resolve,    3 do not     function in that stage

`xref` now also joins the sound, text and motion arguments to their tables;
those lines and what they settle are in [`format_api.md`](format_api.md).

The last line is the one the previous session's `TODO` asked for. `trigger.trg`
runs `callQuestScript("sfEnmGenStart()")` and names a script by string; **144
of the 147 triggers that do so name a function that the same stage's own `.psq`
defines**. The trigger list and the script body are two halves of one thing and
they now join up.

`cfSetEnableEmGen` takes `emgen09` where the marker is `emgen_pos09`, and the
translation is written down on the disc: `enemy_gen.bin` in the quest's `.pac`
is an [`ECH`](format_ech.md) table whose string pool pairs `emgen_pos01` with
`emgen01`, stage by stage, and names `sfKill_Generator` beside them.
`cfStartPieceLock('pl_010_01_02')` names a row of `piecelock.bin` in the same
directory, whose pool carries the stage name, that `pl_` name, the `lockarea`
and `lock_line` polylines and the generator group the lock covers - 569 of the
889 calls name a string in an `ECH` table of their own `.pac`. The other 320 are
explained in [`format_quest.md`](format_quest.md): a stage script ships in
every quest that visits the stage - `900_01_01.psq` is in 89 quest pacs - so it
names locks that only some of them declare. **309 of the 320 are a lock another
quest defines and only 11 are in no table at all.** So the names
that miss `ATIH` are not unresolved; they resolve one table further out, and
which table depends on which quest is running.

## `.cnut` — six bosses and thirteen mercenaries carry their AI as script

19 files on the disc are this format under Squirrel's own extension, and they
were not on any list because nothing was looking for the magic:

    monster.cpk/b01_00/ai.pac/AI_B01_OrcKing.cnut
    monster.cpk/b18_0*/ai.pac/AI_B18_Nidhogg{,_1,_2}.cnut
    monster.cpk/b19_0*/ai.pac/AI_B19_LordOfDeath{,_1}.cnut
    mercenary.cpk/<class>/consider_action.cnut          12 of these
    mercenary.cpk/common.pac/common_script.cnut

`AI_B19_LordOfDeath.cnut` is the largest script on the disc — 123 functions,
7,721 instructions — and it decompiles to a legible decision layer:

```
function active_script()
    local own_hp_rate     = getHpRate()
    local target_distance = getTargetRange()
    local DamagedCount    = getDamagedCount()
    local isAngry         = isAngry()
    local BossTime        = getBossTime()
    local AngryTime       = getTime(0)
    local ACT_TIME1       = getTime(1)
    ...
    local last_act        = getLastActId()
    local AngleTarget     = getAngleTypeAtTarget()
    local SuccessCount    = getActSuccessCount()
```

and under it a bank of `prt_N` tables, each a weighted list of action ids:

```
function prt_5()
    local rand = getRand()
    local ret  = prt_select(rand, 110, 10000)
    return ret

function prt_7()
    local rand = getRand()
    local ret  = prt_select(rand, 1, 5000, 200, 5000)
```

`prt_select(rand, id, weight, id, weight, …)` is a vararg function — one of the
19 — and it is a plain weighted pick with one twist: an action equal to
`getLastActId()` has its weight passed through `getSelRevise` first, so the
boss is biased away from repeating itself. The weights are per ten thousand and
the routine normalises with `correct = 10000.0 / total`.

**78 native functions are called only from the `.cnut` files**, and they are
the AI's sensory interface: `getRange`, `getHeight`, `getPlaneRange`,
`getTargetType`, `getTargetMonsterKind`, `isDestroyedParts`, `isAbnormal`,
`isDowned`, `isTargetJump`, `isTargetGround`, `getNumOfEnemy`, `getNumOfBoss`,
`isAvailableAceSkill`, `getLatestFinishReason`. Every one of them is a question
about the fight, and there is no state in the script at all — the AI reads the
world, picks a number, and returns it.

One function in each file is `check_converted_xml_term`, which says the AI was
authored as XML and converted. That matters for the 438 `.par` files sitting
beside the six `.cnut` in `ai.pac`: 83 monster directories carry AI parameters
and only six carry script, so the `.cnut` are a Rosetta stone for whatever the
`.par` are — `checkRangeParam`, `check_term_param` and `getTime(n)` are named
on one side of that border and unread on the other.

## What is open

- **control flow is not structured.** `src` prints labels and `goto`. Turning
  the jump graph back into `if`/`else`/`while`/`switch` is ordinary work and
  nobody needs it yet;
- **the `.ppcut` preprocessor folded nothing.** `010_01_01.psq` contains
  `if (90 != 1)` as two `_OP_LOADINT` and a compare, and `setDemoID` is called
  with `((3000 + 10) + 0)` computed at runtime. So the constants in the
  disassembly are macro arguments, and the macro names are gone;
- **`_OP_COMPARITH`'s packed `_arg1`** — `(self << 16) | value` — is exercised
  three times on the whole disc and the reading is taken from the interpreter
  rather than confirmed against anything;
- ~~**the 289 native names have arities and nothing else.**~~ **Read in
  session 18** — see [`format_api.md`](format_api.md). `cfSetCameraType`'s five
  camera types are still among the handful that are not.
