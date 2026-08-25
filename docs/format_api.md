# The script interface — the functions the engine has to provide

**Status: read, and since session 22 implemented.** All 285 are bound in
[`../engine/host.py`](../engine/host.py), 66 of them to something that
does the work rather than records the call - which is 17,635 of the 25,699
calls the disc makes. See [`milestone_stage.md`](milestone_stage.md).

587 names are called on the root table; 296 of them are
defined by a `.psq` and **291 are not**. Five of the 291 are Squirrel's own
standard library and one is a script that was never exported, so the engine's
own interface is **285 functions**. This document says what they do. Tool:
[`../tools/psq.py`](../tools/psq.py), commands `api`, `calls`, `sites`, `xref`.

    python tools/psq.py calls extract/tree 'cf*'
    python tools/psq.py sites extract/tree getCharacter
    python tools/psq.py xref  extract/tree

[`format_psq.md`](format_psq.md) reads the bytecode; this reads the vocabulary.
Nothing here comes from a disassembler. It comes from what the call sites hand
each function, from the names the authors gave the results, and — for the
claims that carry a count — from joining an argument to a table that is already
read.

## The count, and why it moved

[`format_psq.md`](format_psq.md) said 453 names and 289 natives. Both numbers
were low, for two reasons that are the same mistake twice: the enumeration
looked only for `_OP_PREPCALLK` followed by `_OP_CALL`.

- **`_OP_TAILCALL` is a call.** `return active_script()` compiles to `0x05`,
  not `0x06`, and 132 script names and one native were invisible because of it;
- **a root call can go through a computed key.** Nearly every quest script
  opens `cntGenKill <- this['cfGetCntKillGenPieceLockOnly']()`, which is
  `_OP_PREPCALL` on a literal rather than `_OP_PREPCALLK`. That is **892 calls
  to a native nobody had listed** — the second-busiest name on the quest side.

The five that are Squirrel and not this game are `print`, `suspend`, `array`,
`getroottable` and `getconsttable`, all in `sqbaselib.cpp`. The sixth is
`prowl_script`, and it is a hole: all six boss `.cnut` end

```
function select_action()
    if (isActive() != false)
        return active_script()
    return prowl_script()
```

and **no file on the disc defines `prowl_script`**. The AI was converted from
XML with two behaviours, active and prowl, and only the active half was
exported. Either the engine supplies a default under that name or the bosses'
idle branch is dead code.

## How a function was read

Four sources, in descending order of how much they settle.

1. **The wrappers name the arguments.** `misc.cpk/psq_common.pac/common.psq` is
   a 65-function library over the interface, and its parameter lists are the
   engine's own vocabulary: `animeIcon(name, kind)` is
   `cfAnimeIcon(getCharacter(name), kind, 0, 1)`, `animeIconLoop` is the same
   with `1`, `animeIconSilent` the same with the last argument `0`. So
   `cfAnimeIcon(chr, kind, loop, sound)`, with no guessing.
2. **The author names the result.** `localvarinfos` survived the compile, so
   `psq.py calls` can print what a return value was called:
   `getHpRate → own_hp_rate`, `getDemoFrame → frameA`,
   `getTargetRange → target_distance`, `cfGetPosInHta → result001X`.
3. **The constants join a table.** A cue id resolves in an `.acb`, a message id
   in a `TXT`, a marker name in `hta.bin`, a motion id in a `.CNOM` filename.
   That is what the counts below are.
4. **The `print` calls.** This build shipped its debug output.
   `check_active_swm` prints `plyer freeze` on the line after
   `isAbnormal(1, 3)`, which names both the argument and the status.

## The conventions the whole interface shares

- **An actor is a handle**, and `getCharacter(name)` is the only thing that
  makes one. Every `chr*` function takes it first.
- **An angle is a 16-bit binary angle, 65536 to the turn** — the same unit
  [`format_stage.md`](format_stage.md) found in the marker table. The script
  layer confirms it three separate ways: `cfSetCmrAngY` is written
  `32768 - 8192 * t` and `32768 + 8192 * t` to swing a camera ±45° about
  straight-behind; `setDemoRotY(index, 21845)` is 120° to the last unit; and
  `effSetRot(handle, 0, cfGetRandI(65536), 0)` picks a random yaw over exactly
  one turn. `cfSetCmrAngXDeg` and `cfSetCmrAngYDeg` are the same two settings
  in degrees — the engine offers both, and the `Deg` pair is what the artists
  used (`85.83`, `200.07`) while the raw pair is what computed code writes.
  The values are **not wrapped**: `cfSetCmrAngY(98263, ...)` is a turn and a
  half, so the host reduces.
- **A length is a metre and a time is a frame**, as in
  [`units.md`](units.md) — `setBlackFade(5, 0)` is a sixth of a second,
  `cfSndStopBGM(0, 60)` a two-second fade, `wait(150)` five seconds.
- **A flag argument is 0 or 1** and reads *enable*: `cfSetEnableHitArea(name,
  1)` turns the area on.
- **A string argument is a row of a table the same `.pac` ships.** This is the
  rule the previous session found for `cfSetEnableHitArea` and it holds across
  the interface.

### One script converts seconds to frames, and the constant is 30

`stage.cpk/050_02_03/param.pac/050_02_03.psq` is a self-contained worked
example of the effect API, and it contains

```
function genCycle(fix, random)
    local cycle = ((fix * 30) + ((random * 30) * cfGetRandF(1)).tointeger())
```

where `fix` and `random` are the `_sec_fix` and `_sec_rnd` of the same
`EffData` record [`format_effect.md`](format_effect.md) matched field for field
against `effect.bin`. The result is a countdown decremented once per update and
compared against zero. So the game's own authors wrote **30 as the number of
ticks in a second**, in the clear, on the disc. [`units.md`](units.md) lists a
declared frame rate as still open and says the EBOOT is the only place left to
look; this is not a declaration, and it assumes the update runs once a frame,
but it is the first seconds-to-frames constant anybody has found outside the
executable, and it agrees with the gait.

## `suspend` is the protocol between the script and the host

`_bgenerator` is 0 on all 11,232 functions, so nothing here is a coroutine.
`suspend` is Squirrel's own `sq_suspendvm`: the script hands the host a number
and stops, and the host resumes it — with a value, where the script uses one.
Every blocking thing in the game is written that way, and the numbers are a
small closed vocabulary:

```
 100  a talk window opened          cfTalkOpen
 101  a talk line is on screen      cfTalk, cfTalkClose
 110  a choice is up                cfChoice, cfChoiceFreedom → the index
 120  a full-screen mode is open    every shop, the closet, the save area
 140  the room selector             openRoomSelect → 0 or 1
 150  the shop pipe menu            cfShopPipe → a selection, ≥65535 is cancel
 200  a tutorial image              openTutorial
 201  the tutorial line-up          cfTutorialLineup → a global flag id
 300  a dialog opened               cfDialogStart
 301  a dialog closed               cfDialogEnd
 302  a dialog message is up        cfDialogMessage
 400  the quest-start dialog        cfCheckQuestStart → 1 to start
1000  a plain wait                  setWaitCount(n) first
1100  the recycle box
```

So the host's side of the interface is not only 285 functions but also a
resume, and the number says which UI it is waiting on. `wait(n)` is
`setWaitCount(n); suspend(1000)` — the frame counter lives in the host.

## What the names name

`psq.py xref` joins every string and id argument it can to the table that must
hold it. Nothing here is asserted without a count.

```
cfSetEnableHitArea        1457 resolve,    2 do not      ATIH marker, own stage
cfGetPosInHta               25 resolve,    1 do not      ATIH marker
getCharacter              1362 resolve,   45 do not      ATIH marker `pos_<name>`
cfSetEnableEmGen           203 resolve,   37 do not      emgen_pos marker
cfSetEnableBorderline      679 resolve,    7 do not      borderline polyline
cfMapJump                  147 resolve,    0 do not      stage + arrival marker
trg callQuestScript        144 resolve,    3 do not      function in that stage
cfSndPlayBGM                 5 resolve,    0 do not      sound.cpk/bgm.acb
cfSndPlayStgBGMOW          197 resolve,    0 do not      sound.cpk/bgm.acb
cfSndPlayCmnSE              21 resolve,    0 do not      sound.cpk/common.acb
cfSndPlayVoiceNPC           69 resolve,    0 do not      sound.cpk/en/vnpc.acb
chrPlayVoice              1120 name the speaker, 24 do not
talk arg1                10787 name a message,   0 do not  msg_npc_talk.bin
talk arg0                10840 name a speaker,   0 do not  msg_npc.bin
chrSetMotion[NPC]         1220 name a motion of that character, 111 do not
```

Five of those lines are new this session and each says something the interface
would otherwise leave open.

### `getCharacter` looks up a marker, and `npc.bin` is the cast list

`getCharacter('NPC_Norn')` names the `hta.bin` marker `pos_NPC_Norn` on 1,362
of 1,407 testable calls. The 45 that miss are three clean classes and no
others: `player0`, the `DEMO_*` and `HIRO_*` cutscene actors that
`setDemoPos` places rather than a marker, and two spellings (`NPC_Ottar` where
the marker says `Ottal`).

The record behind the name is `<stage>/param.pac/npc.bin`, an
[`ECH`](format_ech.md) of 21 rows by 7 words:

```
   0             0   'NPC_Silon'  'npc_16.pac' 'pos_NPC_Silon'   14   1045220557   2.5
   1             0   'NPC_Binit'  'npc_17.pac' 'pos_NPC_Binit'   15   1045220557     3
```

— a kind, the name the script asks for, the model pac, the marker it stands
on, an index, a constant, and a radius. So a character handle is a row of that
table, and everything the `chr*` calls need hangs off it.

### A motion id is the number in its own `.CNOM` filename

`npc.cpk/npc_16.pac` holds `n16011wait_1.CNOM`, `n16015talk.CNOM` and
`n16016greeting.CNOM`. The three digits after the model number are the id the
script passes: **1,220 of 1,331 `chrSetMotion` and `chrSetMotionNPC` calls name
a motion the addressed character actually has**, and every one of the 111 that
do not asks for **201**, which no `.CNOM` on the disc carries. 201 is a
sentinel — no motion, or back to the default — and it appears in the same place
in `chrSetMotionNPC`'s *connect* slot, 90 times.

**And the id is a vocabulary the whole cast shares.** Every NPC pac names its
animations from the same list:

```
 11 wait_1     15 talk        22 sit        41 toast       901 demo_01
 12 wait_2     16 greeting    25 sit_talk   42 toast_wait
                17..20 greeting_2..5 / talk_2..3          45..48 uni_1..4
```

so the call sites read as themselves. `chrSetMotion(eid, 16, 0)` — 591 of 901
calls — is an NPC greeting the player; `chrSetMotionNPC(Ead, 15, 12, 0)` is
*talk, then back to wait_2*; `chrChangeMotion(chr, 1, m)` and `(chr, 2, m)`
replace the idle and the talk, which is why slots 1 and 2 are the only ones
used. The one cutscene that hands out beer mugs plays 41, `toast`, and
`setDemoMotion(0, 901)` in the opening cutscene is `demo_01`.

### `talk` is a speaker table and a message table, and both are exact

`talk(speaker, message)` is `cfTalk(speaker, message); suspend(101)`.

- **every one of 10,787 message ids is inside
  `menu.cpk/msg_field.en.pac/msg_npc_talk.bin`**, which holds 6,139 messages;
  the largest ids used are 6,133 and 6,138, so the table is exactly as large as
  the script needs and not one call falls outside it;
- **the speaker is a row of `menu.cpk/msg_common.en.pac/msg_npc.bin`**, 55
  names. 54 is `Norn` and she is the busiest at 2,759 lines, which is right for
  the hub's shopkeeper; 15 is `Eadgils`, 21 `Hilda`, 5 `Brokkr`.

And the two join up against the file names. The town scripts are named after
whoever speaks in them, and **10,058 of 10,333 lines under a two-letter-prefixed
script use that prefix's own character**: `No` → Norn 2,756 of 2,756, `Hi` →
Hilda 1,061 of 1,061, `Ea` → Eadgils, `Ru` → Rune, `Lv` → Lif, `Hr` → Harald,
`Pb` → Brokkr, over 30 prefixes. The `msg_npc.bin` list carries the cast twice,
ids 3–27 and 28–49, which is why a second smaller id shows up beside each.

Norn's affection is the tidiest instance. `cfGetNornFeeling()` returns 0 to 5,
and the script picks a line, a voice, a motion and an icon off it:

| rank | message | text |
|---:|---:|---|
| 0 | 5964 | *Thank you.* |
| 1 | 5965 | *Thanks for coming!* |
| 2 | 5966 | *I had lots of fun talking with you!* |
| 3 | 5967 | *I wish time would stop so we could keep talking...* |
| 4 | 5968 | *YOU'RE MY FAVORITE!!* |
| 5 | 5969 | *I LOVE YOU!!* |

### A voice line names the character speaking it

`chrPlayVoice(chr, id)` and `cfSndPlayVoiceNPC(id, 0)` address
`sound.cpk/en/vnpc.acb`, the 58-cue NPC voice bank, by cue id. All 69
`cfSndPlayVoiceNPC` calls resolve, and for `chrPlayVoice` the check is
sharper, because the script also says *who* is speaking: **1,120 of 1,144 calls
pass a cue whose name carries the name of the character handed to it** —
`chrPlayVoice(getCharacter('NPC_Eadgils'), 6)` is `VC_EADGILS`,
`chrPlayVoice(Bro, 0)` is `VC_BROKKR_1`.

The 24 that do not are a complete list: 18 are `VC_OTAKEBI_S`/`_L`, a war cry,
and one is `VC_KANPAI`, a toast — cues that belong to nobody — and four are a
character speaking another's lines. The public-address scripts check out too:
`Pb11000` plays `VC_BROKKR_TUBE_1`, `Pl11000` `VC_LINDE_TUBE_1`, `Pr11000`
`VC_RUNE_TUBE_1`, and the file prefixes are the speakers' initials.

### `chrSetAttachArticle`'s middle argument is a `CMDL` locator

Twelve calls, all in one cutscene, all of the form
`chrSetAttachArticle(Ead, 4000, 'beer01')`. **4000 and 4100 are `node_r_weapon`
and `node_l_weapon`** in the locator table
[`format_cmdl.md`](format_cmdl.md) describes — the same `S4` namespace
[`format_mkc.md`](format_mkc.md) uses for a sound's emitter and
[`format_effect.md`](format_effect.md) for an effect's socket. Twelve NPCs are
handed beer mugs, eight into the right hand and four into the left. That is the
**third consumer** of one namespace, and it says a prop, a sound and an effect
all hang off the same sockets.

### `setInt`/`getInt` is the host's integer store, and `EffData._work` indexes it

`setInt(0, slot, value)` and `getInt(0, slot)` are a bank and a slot. Session 17
found that the `EffData` class the stage script declares carries a field
`_work` that `effect.bin` has no lane for; `effect_update` uses it as
`getInt(0, val._work)`. So `_work` is **the slot where that effect's countdown
lives**, and the six fires of `050_02_03` are given `190 - 0` … `190 - 5` with
the phase at 191.

## The families

Counts are call counts over the whole disc. A `?` marks an argument whose role
is not settled.

### Flags, progress and the save

```
cfGetGlobalFlag(id)                1227  the persistent flag bank; ids 10..1588
cfSetGlobalFlag(id, v)             1476  v is 0..5, and 1 on three quarters
cfGetQuestFlag(id)                  908  reset per quest; ids 1..768
cfSetQuestFlag(id, v)              1730
getDemoGlobalFlag(id)                 1
cfGetMainCounter()                  181  the scenario counter, 11000..23900
cfSetMainCounter(n)                  26  ... and the story advances by writing it
setInt(bank, slot, v) / getInt        12  a host integer store, bank 0 only
cfIsQuestClear(name)                  3  'q00408' — a quest by name
cfIsQuestClearByIDFlag(id)           10
cfSetQuestUnselect() cfStartQuest()  18
cfIsQuestSelect()                   117  is a quest chosen at the counter
cfIsBarQuestSelected()               50
getQuestName()                       72  → 'q01105'; the scripts branch on it
getLatestKilled()                    23  the monster id last killed, 2000+10k
setSuccessiveBattle(n)               20  this quest is a consecutive-battle one
cfIsMulti() cfIsMultiStart() cfIsMultiError()   45
cfGetJob() cfSetJobItem()            18
cfGetFreeCardSlot()                  10   cfCheckEqCard(id)  cfCheckEqAceSkill(id)
cfAddItem(id, n)                     10   ids like 80787, one at a time
cfRefineEqWeapon() cfExtendEqCloth()  2
cfCheckShopOpenItemFlag(n)            8   n is 1..8, one per shop
cfCheckShopOpenNewItem() cfResetShopOpenItemFlag()   4
cfCheckDictionaryReward() cfCheckMyOrderClear()      2
cfGetBillingStatus()                  1   0..4; 0 and 1 are "running"
isVITA() isPS3() isEnableCrossSave()  3   getHardwareType() wraps the first two
getCrossSaveExplainTime()             1   seconds, against a threshold of 86400
clearCrossSaveExplainTime()           1
```

The Yggdrasill (endless dungeon) group is four of its own:
`getCurrentYggdrasillFloorNo(-1)`, `getYggdrasillPieceType(-1)`,
`isYggdrasillClimbing()` — the scripts call the result `updown` — and
`continueYggdrasillQuest()`. The `-1` is constant on all nine calls and reads
as *the local player*.

### The stage

```
cfStartPieceLock(name)              889  a row of piecelock.bin; the arena closes
cfEndPieceLock()                    732
cfGetCntKillGenPieceLockOnly()      892  generators killed inside the lock
cfSetEnableEmGen(name, on)          240  a spawner, by its emgen_pos marker
cfAddEmGenWait(name, -1800)          22  delay it; only under cfIsMultiStart
cfReviveEmGen(name)                   8
cfSetEnemyMax(n)                      6  1 or 2 — how many at once
cfSetEnemyAttendType('RATCHET',1,n,0) 6  a named kind, and two numbers
changeEnemySet('enemy02.bin', 'EnemyPopA()')   23   swap the spawn table, then
                                                    call a script by name
cfSetEnableHitArea(name, on)       1460  an ATIH volume: a jump, a lock, a trap
cfSetEnableBorderline(name, on)     687  a fence polyline
setHTAFlag(piece, hta_name, type, param)  153   the author's own parameter names
cfGetPosInHta(marker, axis)          40  axis 0/1/2 = x/y/z; one float
getHTAPos(marker)                     1  the same as an [x, y, z] array
cfMapJump(stage, marker)            176  cfMapJumpForce is the same without a
cfMapJumpForce(stage, marker)        17  confirmation; cfQuitBarJump(force) 21
npcRelocation(stage)                 32  put that stage's NPCs back
visibleMiniMapCamera(on)              8
effSetPauseMapEff('ef_01', on)        4  the stage effects named in hta.bin
callQuestScriptPC('sfQuestBGMInit();')  34   run a string in the quest script
delayScriptCall(1, 'Tutorial_IMG( 1524, 27)')  1   ... after a delay
```

### Characters

```
getCharacter(name)                 1609  → a handle; see above
chrSetPos(chr, x, y, z)              85  metres
chrSetRot(chr, angle)                84  binary angle; the constants are
chrSetDir(chr, angle, speed)        109  multiples of 256, i.e. 1/256 of a turn.
                                          speed 2048 is 11.25° a frame
chrGetRot(chr)                        1  chrChangeDir wraps set-after-get
chrSetFromHta(chr, 'appear01')        8  stand it on a marker
chrRotOpponent(chr)                   8  turn it to face the player
chrSetMotion(chr, motion, force)    901  see above; 201 is "none"
chrSetMotionNPC(chr, mot, connect, force)  502
chrChangeMotion(chr, slot, motion)  348  slot 1 is the idle, slot 2 the talk
chrPlayVoice(chr, cue)             1193  vnpc.acb
chrSetAlpha(chr, a, frames)          26  fade a character in or out
chrVisible(chr, on) chrFreeze(chr, on)   2
chrSetAttachArticle(chr, locator, name)  12   a prop on a CMDL locator
chrSignalIcon(chr, kind)             64  kind 0, 1, 2 — the quest marker overhead
npcSignalIcon()                      19
cfAnimeIcon(chr, kind, loop, sound)   3  the emote balloon; kind runs 1..21
getCountAnimeIcon(kind)               2  how many are still playing
cfEmo(chr, kind)                      1
setShieldEnable(on) setShieldMotion(mot)   6   the shield-stage turret
```

`cfAnimeIcon`'s `kind` is 1..21 and the histogram reads as conversation — the
four commonest are 4, 5, 3 and 11. `menu.cpk/msg_field.en.pac/msg_emotion.bin`
lists 25 named emotes in exactly that range, and 3, 4, 5 and 11 there are *Nod*,
*Shake Head*, *Celebrate* and *Sit*. It is the obvious table and nothing on the
disc joins the two, so it stays a proposal.

### Talk, dialogs and the shops

```
talk_begin()                       1072  the only native of the talk group;
                                          talk/talk_open/talk_close/talk_end
                                          are script over cfTalk*
cfTalk(speaker, message)              2  → suspend(101)
cfTalkOpen(speaker, message)          1  → suspend(100)
cfTalkClose() cfTalk_end()            2
cfChoice(sel) cfChoiceFreedom(sel)    2  → suspend(110) returns the index
cfDialogStart() cfDialogEnd()         2
cfDialogMessage(type, id)             1  type 0 is a signal, 2 a tutorial page
cfDialogParamAll(a,b,c,d,e,f,g)      35  seven numbers; the two shapes used are
                                          (2,0,90,900,120,0,1) for a one-line
                                          signal and (3,1,0,900,450,2,1) for a
                                          tutorial page. Roles unread
cfDialogParam(4, 0, 0)                1  set one of them
cfDialogButton(3, 1)                  1  put a button on the last page
cfSetShopDialogFlg(on)               28  suppress talk while a shop is open
cfCheckQuestStart()                   1  → suspend(400)
openTutorial(n [, delay])             3  → suspend(200)
cfTutorialLineup(70,8,80,32,48,32,8,38,10)  2   nine numbers, a layout
cfTutorialLineupMode(on)              2
cfSetBarQuestAccess() cfLowBarQuestAccess()      147
cfSetBarShopAccess() cfLowBarShopAccess()        140
cfSetBarClosetAccess() cfLowBarClosetAccess()      2
cfIsBarMenuAccess()                  12
cfShopSmith cfShopSewing cfShopGoods cfShopBarber cfShopCannon
cfShopCard cfShopBottle cfShopPipe cfShopQuest cfShopQuestCancel   10
openCloset openSaveArea openMusicPlayer openSpectroLight openRoomSelect
openShopBilling openRecycleBox openRecycleModeCon openRecycleModeOttal
openPipeModeSmith openPipeModeSewing openPipeModeGoods              19
moveRecycleBox() notifyRecycleModeEnd() notifyPipeModeEnd()        180
cfRecvDlc() cfRecvNear() cfRecvNearMyGift() cfRename()               4
cfGetNornFeeling() cfSubNornFeeling() cfUpdateNornAccess()         159
cfInfoChapterClear()                  1
cfPadStartFocus() cfPadEndFocus() cfPadFocusReset()                535
visibleFieldInfo(on)                176  the field HUD
setWaitCount(n)                       1  → suspend(1000)
```

The ten `cfShop*` are called exactly once each, all from `common.psq`, and
every one is followed by `suspend(120)`. With the `open*` group that is one
mechanism with twenty-two entry points.

### Camera

```
cfSetCameraType(type, ?, ?)         330  type 0, 1, 3, 4, 6; the cutscenes save
                                          the old type and put it back at the end
cfSetCmrPos(x, y, z, flag)           83  metres
cfSetCmrPosIndividual(v, axis, 1)    83  axis 0/1/2 = x/y/z, one component
cfSetCmrAngX(a, flag) cfSetCmrAngY   95  binary angle
cfSetCmrAngXDeg(d, flag)            129  ... and the same in degrees
cfSetCmrAngYDeg(d, flag)
cfSetCmrFov(deg)                     59  24, 25, 30, 35, 40, 45
cfResetCmrFov() cfResetCmrReserve()  19
cfSetCmrFortressTalkMode(on)        127  the town's over-the-shoulder framing
cfEnableCmrHoming(on)                 4
cfInheritCameraSettingOnce(1)         2  the script's comment is カメラ引継ぎ
cfCmrQuake(kind, 0, n, m)            57  kind 2, 5, 6; n 5 or 10; m 0, 15, 20
cfSetClearColor(0, 0, 0, 255)         6
```

`cfCmrQuake` and [`.mkc`](format_mkc.md)'s opcode `0802` are both a camera
shake with four arguments, and `0802`'s first is a kind 1..12 which contains
the script's 2, 5 and 6. But `0802`'s fourth argument is 0..4 and the script's
is 0, 15 or 20, so the two signatures do not line up and the correspondence is
not established.

### Sound

Every cue id in this group resolves; see the xref table above.

```
cfSndPlayBGM(slot, cue, fade)        22  slot 0, 1, 2; cue in sound.cpk/bgm.acb
cfSndPlayStgBGMOW(0, cue, 0)        197  the stage's BGM, overwriting
cfSndPlayStgBGM(0, 0)                16
cfSndStopBGM(slot, fade)            184  fade in frames: 0, 10, 15, 30, 55, 60
cfSndVolumeBGM(0, v, frames)          3
cfSndVolumeCategory(cat, v, frames)  59  cat 7 and 9, two of the .acf's sixteen
cfSndPlayCmnSE(0, cue, 0)            21  common.acb: SYSTEM_UNLOCK, RUMBLE_HIT
cfSndPlayCmnSE_useStgPlayer(cue, 0)   2
cfSndPlaySE(0, 3, cue, 1)            21  forcePlayStageSE(cue) is this
cfSndPlayStgSE(-1, n, 0)             39
cfSndPlayStgSE3D(-1, cue, 0, x,y,z)   2  positioned, in metres
cfSndPlayVoiceNPC(cue, 0)            69  vnpc.acb
isPlayPhonographPlay()                1
SoundManager_getInstance()            3  three calls, all in dead test code
```

### The cutscene layer

A `demo` is a numbered cutscene with its own `.psq` under `demo.cpk`. The host
drives it: it calls `demoInit`, then `demoUpdate` every frame, then `demoEnd`.

```
setDemoID(id, kind)                 290  which cutscene; ids like 5000+n, 10520
setDemoMode(on) isDemoMode()         30
inquireDemoTriggerType()              1  == 2 means "a monster died"
setDemoHook(id)                       2  arm one on a monster id
getDemoFrame()                       68  an array: [0] is now, [1] the end
setDemoPause(on)                     52
setDemoEnd()                         88
setDemoBGM(cue)                       68  cue 500 is DEMO_STG_010, in the 010
                                          cutscene — the bank names it
setDemoMotion(index, mot)             68  an actor slot, not a character handle
setDemoPos(index, x, y, z)            68
setDemoRotY(index, angle)             68  binary angle
setDemoVisible(index, on)             55
setBlackFade(frames, to)            247  to = 1 fades to black, 0 back out
setWhiteFade(frames, to)             27
setDemoObiHeight(px, frames)        136  the letterbox bars: 50 at the start,
                                          0 at the end, over 10 frames
initDemoTelop(x, y)                  43  the subtitle, at 448,332 or 1500,374
startDemoTelop(x, y, on, frames)     60
endDemoTelop()                       26
cfIsEmptyInClosetWeapon()             3
```

### Effects

Four functions, and one stage script uses all of them together:

```
effStart(category, id)                1  → a handle. The (category, slot) pair
                                          of format_ptp.md
effSetPos(handle, x, y, z)            1  metres
effSetRot(handle, x, y, z)            1  binary angle; the disc's only call
                                          passes cfGetRandI(65536) as the yaw
effSetPauseMapEff(name, on)           4
```

### The monster AI

51 names, and [`format_ai.md`](format_ai.md) already puts every predicate
among them against the term id it implements, with its units. Nothing to add
here except which of them are the engine's:

`getAIType getTotalTime getBossTime getTime getTimeFromID getRand getScale
getPlayerCount getOtherZakoCount getOtherBossCount getActiveSameKindCount
getHpRate getDamagedCount getStaggerCount getLastActId getActSuccessCount
getFailedActCount isDowned isAngry isAngryReq isPoison
isRecoverPoison isRecoverParalyz isRecoverFaint isReact isToActive
isFailedRotation isActive isDestroyedParts getPartsDamageCount
getTargetHpRate getTargetJob getTargetRange getTargetPosy getTargetArea
getAngleTypeToTarget getAngleTypeAtTarget getLockTargetRange
getDamageFromTarget checkRangeParam isTargetGround isTargetAttack
isTargetGuard isTargetSway isTargetJump isTargetDown isTargetObject
isTargetDamage isBossToTarget getSelRevise printAitIdName`
plus `checkB01Term`, `checkB05Term`, `checkB09Term`, `checkB11Term`,
`checkB15Term`, `checkB18Term` and `checkB19Term`, one per boss, which are the
per-monster escape hatch for a term the shared table has no id for.

`printAitIdName(term)` is a debugging aid — the fall-through of the term
dispatch prints `I don't know the word is <name>.` — and it means **the engine
holds a name for every AI term**. That is a string table worth looking for when
the EBOOT opens.

### The mercenary AI, and what its argument selects

19 predicates, listed in [`format_merc.md`](format_merc.md) with `n` unread.
**`n` is an actor slot: 0 is the mercenary itself, 1 is the player it follows,
2 is its current target.** Four things say so and they agree:

- `check_active_*` reads `getRange(1) < 35 && isAbnormal(1, 3)` and then prints
  **`plyer freeze`** — the argument is the player, and status 3 is freeze;
- the phases split cleanly. `check_active` and `select_target` — run before a
  target exists — use `getRange(1)`, `getHpRate(1)`, `getNumOfEnemy(1, r)`;
  `select_action`, run after, uses `getPlaneRange(2)` and `getHeight(2)`;
- `getHpRate(0) < 85` guards the mercenary's own ace skills;
- `getNumOfEnemy(0, 5) - getNumOfBoss(0, 0)` and the same pair with `1` are
  written side by side: non-boss enemies near me, then near my master. A
  radius of 0 means no limit.

```
getRange(n)                         216  distance; always the player
getPlaneRange(n)                    304  the same, ignoring height
getHeight(n)                         52  height difference
getHpRate(n)                        110  0..100
getNumOfEnemy(centre, radius)       110  radius 0 is unlimited
getNumOfBoss(centre, radius)         88
getNumOfUnderHpRate(40, 80)           2  two calls, both in the cleric; the
                                          radius/threshold order is unread
getPartyMemberHpRate(i)               6  i is 0, 1, 2
isAbnormal(slot, kind)               36  all 36 calls are (1, 3)
isAvailableAceSkill(1|2)             28  and the two return as actions 11 and 12
getActionLastFrame(actId)            68  frames since that action last ran;
                                          compared against 40, 60, 550, 750,
                                          1901 — cooldowns
getNearestBossKind()                252  a monster kind, 28..46
getNearestBossAction()              180  an action id, 102..125
getTargetMonsterKind()              108
getTargetActId()                    180
getTargetType()                     140  2, 4, 6, 7, 8 — the same set target_NN
                                          carries at +0x00
getLatestFinishReason()              12  8 is a wall hit; the script says so
isActive()                           18
getRand()                          1010  0..10000
```

### The status kinds, which the mercenary check names

`isAbnormal(1, 3)` is the player frozen. The `ab_*` vectors in the player JSON
[`params.md`](params.md) appear in the file in a fixed order, and dropping the
scalar `ab_ef_s` that heads them leaves ten five-element vectors:

```
0 ab_pss   1 ab_psl   2 ab_prl   3 ab_frz   4 ab_brn
5 ab_nrv   6 ab_ten   7 ab_tir   8 ab_atd   9 ab_dfd
```

Index 3 is `ab_frz`, and ten of the twelve mercenary scripts print `freeze` on
the line after the call. So **the status kind is a zero-based index into that
block in its own declared order**, which is one of the four things
[`params.md`](params.md) lists as unexplained about those vectors.

### Squirrel's own

`print`, `suspend`, `array(n, fill)`, `getroottable()`, `getconsttable()`. A
reimplementation gets these from the VM.

`EffData` and `Vec3` are neither: they are Squirrel *classes* the stage script
declares itself, and the enumeration counts a constructor call as a root-table
call. `cfTestVec3`, `getSampleFloatArray3`, `getSampleFloatArray4`,
`getSampleIntArray2` and `SoundManager_getInstance` are test scaffolding, one
call each, in a `misc.cpk` script that nothing runs.

## Six names that are not functions

Running the scripts turned up a second hole of `prowl_script`'s shape. Six
names are *read* off the root table, never called, and defined by no `.psq`:

```
DEMO_S174_A  DEMO_S175_A  DEMO_S176_A  DEMO_S177_A  DEMO_S178_A
MONS_KIND_ORGA
```

`setDemoID(DEMO_S177_A, 0)` is `quest.cpk/q07607.pac/010_01_01.psq`, where
every other quest script writes the number; `MONS_KIND_ORGA` is a monster kind
in a mercenary debug function. This document read that as **the root table
carrying named constants as well as functions**, and these six being the only
ones the scripts still reach for. They are the whole of it: 25 names are read
off `this` and the other 19 are the reading script's own globals.

### The EBOOT says the reading was wrong, and they are dead

Session 30 opened the binary ([`format_self.md`](format_self.md)) and it binds
its interface by name, in the clear. **274 of the 285 native names in this
document are NUL-terminated strings inside it** — which is the check that says
the list is the engine's list and not an artefact of how the scripts were
read. None of the six is:

```
prowl_script     absent      MONS_KIND_ORGA   absent
DEMO_S174_A      absent      DEMO_S175_A      absent
DEMO_S176_A      absent      DEMO_S177_A      absent
DEMO_S178_A      absent
```

So the engine does not hold them as constants. `setDemoID(DEMO_S177_A, 0)`
reads a slot nothing ever filled and passes null, and `prowl_script()` is a
tail call into nothing — **dead references in the shipped game**, not a hole
in this repository's reading. The six `.cnut` were converted from a
`prowl_script` the conversion did not carry, and one quest script was written
against a constant somebody removed.

### The eleven that are absent, and why each is

The absences are informative rather than worrying, and they fall into four
groups:

- **`isRecoverPoison`, `isRecoverParalyz`, `isRecoverFaint`** — the engine
  spells them `recoverPoison`, `recoverParalyz`, `recoverFaint`, in its own
  AI predicate table. The `is` is the `.cnut`'s, not the engine's;
- **`Vec3` and `EffData`** are classes rather than functions, and
  `050_02_03` defines its own `Vec3` — which is the one name this document
  already knew is defined twice;
- **`SoundManager_getInstance`, `getSampleFloatArray3`, `getSampleFloatArray4`,
  `getSampleIntArray2`, `cfTestVec3`** are a method on a receiver and four
  helpers, registered under a name this flat list cannot see;
- **`cfShopCannon`** is simply not there. One call site, and nothing in the
  binary answers it.

## The library the interface sits under

`misc.cpk/psq_common.pac` is not one file but five - `common`, `class`,
`stage`, `quest` and `test` - and together they define **85 functions and no
name twice**, which is what says they are all resident. The wrappers named
throughout this document (`wait`, `talk`, `animeIcon`, the ten `shop_*`) are
theirs.

Two counts say the root table really is one table shared by the library and
whatever stage is loaded:

- `room_select`, in `common.psq`, calls **`mapjump_140_02_01`**, which only
  `stage.cpk/140_01_01/param.pac/140_01_01.psq` defines;
- over all 155 stages, loading the library and then that stage's own scripts
  defines exactly **three** names twice - `Vec3` in `050_02_03` and
  `checkQuestClearByIDFlag` in the two town stages.

The town's *conversations* are the exception that proves it: the 460 scripts
under `stage.cpk/140_02_01` collide on **147** names - seventeen of them
define `talkNornThanks` - so one is loaded when a conversation starts and
dropped when it ends.

## Still open

- **`cfSetCameraType`'s five types**, and the second and third arguments of the
  `cfSetCmr*` family, which are 0 or 1 and are not a fade — the cutscenes pass
  both in the same shot.
- **`cfDialogParamAll`'s seven numbers.** Only two combinations are ever used,
  so the disc will not separate them.
- **`cfCmrQuake`'s four**, and whether it is `.mkc`'s `0802`.
- **`cfSetEnemyAttendType('RATCHET', 1, 4|6, 0)`** — six calls, one quest, and
  `RATCHET` is a monster kind name that appears nowhere else in the scripts.
- **`cfTutorialLineup`'s nine numbers**, two calls.
- **`cfAnimeIcon`'s `kind`**, if `msg_emotion.bin` is the table.
- **`setDemoID`'s second argument**, 0, 1 or 2.
- **`prowl_script`**, which nothing defines.
- **`chrSetDir`'s speed against `rot_y_spd`.** The NPC turn speeds are
  multiples of 256 of a 65536-unit turn — 2048, 4096, 8192 — which in
  1/256-turn units are 8, 16 and 32, and `rot_y_spd = 32` in the player JSON is
  in that set. [`units.md`](units.md) reads that 32 as degrees per frame. The
  two subsystems are separate and nothing joins them, but the coincidence is
  worth a measurement.
