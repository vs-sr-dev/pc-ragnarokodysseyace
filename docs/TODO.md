# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — a quest that pays

Session 24 reached **milestone 5**: a quest finishes itself. The report is
[`milestone_quest.md`](milestone_quest.md), beside
[`milestone_player.md`](milestone_player.md),
[`milestone_stage.md`](milestone_stage.md) and
[`milestone_fight.md`](milestone_fight.md). What to carry:

- **210 of the 229 arenas the body reached closed on the script's own count**,
  over all 431 quests, on 1,534 kills. A trigger volume calls
  `sfEnmGenStart`, `cfStartPieceLock` raises the fences and spawns the lock's
  generators, each kill calls back the function `enemy_gen.bin` names, and the
  quest's own `sfKill_Generator` counts to a constant compiled into its own
  bytecode and calls `cfEndPieceLock`. Nothing in the engine tells it how many
  to expect;
- **the count is written twice and the two agree — 527 of 527.** The
  threshold is a Squirrel integer; the generator list is a newline-separated
  string in `piecelock.bin` `+0x1c`. Different files, different readers, no
  way to arrange it. `python engine/mission.py counts extract/tree`;
- **the callback counts generators, not corpses** — the script prints
  `--- generator [emgen01] End ---`, and on 36 of the 527 the population byte
  is twice the threshold;
- **`lockarea` is the room and `lock_line` are the doors** — 2,813 of 2,817
  spawners and 572 of 575 triggers inside the polygon;
- **the stage list is a graph, not a path** — 767 of 1,280 consecutive pairs
  carry a jump, but 398 of 428 lists are connected end to end;
- **the ground mesh is a navigation mesh**, on two facts
  [`format_ccls.md`](format_ccls.md) had already established and nothing had
  used: it is welded, and the edge of the walkable region is the fence;
- **the walk is the weak half.** 252 of the 431 quests walked their whole
  stage list and 125 runs end with *the body stopped walking*. That is this
  repository's steering and not a reading, and it is what stands between 210
  arenas closed and the 25 of 131 arena-bearing quests that finish end to end.

### 1. What a finished quest pays.

The quest completes and hands back nothing, which is the obvious next hole and
it is all tables. A quest `.pac` ships `item_reward.bin`,
`item_reward_multi.bin`, `item_reward_region.bin`, `weapon_decost.bin`,
`destructible.bin`, `mapexception.bin`, `enemy_ref.bin`, `enemy02..04.bin` and
the `q<NNNNN>.bin` that carries the quest's own header — nine tables, none of
them described, and every one of them an [`ECH`](format_ech.md) whose container
has been readable since session 6. Two of them have obvious second consumers:
the header should name the quest, which joins to the 25,288 messages, and
`item_reward*` should index `it_db_*`, which session 21c read. See
[`format_quest.md`](format_quest.md).

### 2. The three entries beside `s_combo_graph`.

Unchanged from last session and still the cheapest well-posed item.
`s_combo_finish_inf` (132 bytes on the warrior), `s_just_combo_inf` (8) and
`s_combo_motA` (64) sit in the same `objbin.bin` and none of them is read.
They are the rest of the combo machinery, they are small, and the graph now
gives them a frame to be read against: a finisher is a node with no outgoing
edge, and a just window is a byte pair on an edge.

### 3. A generator's counts and timers, now that one runs.

`enemy_gen.bin` `+0x14`, `+0x18`, `+0x20`, `+0x24`, `+0x28` and `+0x30` were
deferred because *"the disc has no second reader to check them against"*.
It has one now: a running arena. `+0x28`'s `k` is 0, 5, 10, 15, 30, 60 or 90 —
halves and multiples of a second at 30 fps — and a respawn delay is testable
the moment a monster can die, because a wave that respawns and a wave that
does not reach the script's threshold at different times or not at all.
Beside it, the 91 rows where the population is double the generator count:
a generator that ships two monsters still fires one callback, so what the
second monster is and when it appears is now a question with a shape.

### 4. The `.anmcmd` opcodes, with two questions that name their own answer.

Thirty of fifty-two are unread, and two consumers want particular ones:

- **which opcode spawns a projectile and which `ht_arrow_tbl` row it names.**
  42 rows, 15 distinct flights, and no join from a list to a row;
- **what turns a weapon trail on.** A weapon carries three `par_tbl` records
  and one `ref_tbl` entry to hang them on, so something outside the file picks
  between them. See [`format_mkc.md`](format_mkc.md) for the six `.mkc`
  opcodes still open, each with a file set that says something.

Session 17's lesson still applies: a selector byte inside a payload changes
what the rest of it means, and counting occurrences never sees that.

### 5. The player's *base* defence and hit points.

[`combat_loop.md`](combat_loop.md) ledger item 2, unchanged and still the one
gap in the loop that may not need the binary. The modifier side is read and
named — `DEF` is ability 1 of `it_db_ability.bin` and `MAX HP` is ability 3 —
and `it_db_equip.bin` is costumes, not armour. The level-up tables
(`it_db_myorder*.bin`) are the next place to look.

### 6. Draw it.

`hitbox.py obj` writes a frame as Wavefront OBJ — bones, body capsules and hit
volumes together. Nobody has looked at one yet, and there is now an *arena* to
take the picture of: eight bodies, a fence that went up around them, and the
navigation mesh under all of it.

### Then

7. **`se_hitlevel_tbl`'s third word**, 0 to 8 across the fifteen player
   entries and per class rather than global — what a weapon or a skill
   declares to pick its cue block, and *not* `it_db_weapon.bin` column 5.
   `it_db_skill.bin` is the obvious other side.
8. **The last two `ELBN` populations.** `stageparam.bin` is 154 files and only
   its lights are read; `mot_param.bin` is 60 and only its motion id is.
9. **Where the minimap's scale is declared.** Session 19 measured the
   transform — see [`format_stage.md`](format_stage.md) — and it is not in
   `stageparam.bin`. The scale is a band, 1.31 to 1.33 px/m.
10. **The three unread bytes of an `effect.bin` motion row**, `+0x08` to
    `+0x0a`. Bit fields; the obvious reading is a space or follow mode.
11. **The `CCLS` surface codes 1 to 13**, and the pose layer says where a foot
    is, so the triangle under it is a lookup away. The navigation mesh now
    walks a body over hundreds of them in a row, which is a second way in.

---

## Deferred, with reasons

- **EBOOT decryption** (Phase 3). Narrower again: the quest state machine and
  the boss AI are script, and since session 18 the 285 native functions are
  described rather than merely named, so what is left inside it is **the combat
  loop and the implementations**. **Session 14 produced the first item that
  genuinely needs it** — the table that maps `.anmcmd` opcode 10's effect id to
  a `PTB` slot is not on the disc, and 32,600 leaves were searched for it. It
  is a cosmetic lookup, so it still does not justify the phase on its own.
  Session 18 added a second, of the same size: the engine holds a **name for
  every AI term id**, because the term dispatch's fall-through calls
  `printAitIdName`, and that string table would finish
  [`format_ai.md`](format_ai.md)'s last ten.
- **Audio and video** — no longer deferred at all. The 46 movies are read by
  [`pam.py`](../tools/pam.py) and the 274 sound banks by
  [`awb.py`](../tools/awb.py): 7,756 waveforms, 12 h 18 m, every one reached
  by a named cue, and not one of them encrypted. See
  [`format_awb.md`](format_awb.md).

## Open, unowned

- `CTEX`: the `0x28` stamp and bit 0 of `0x1D`. Both are described in
  [`format_ctex.md`](format_ctex.md); neither affects the decode.
- `CMDL`: the four-byte attribute at layout byte 2; the middle byte of the
  mesh descriptor's first word; `S8` and the 16-byte digests at the head of
  `S9`; the eight stage grounds whose texture index runs one past their name
  list; and the 25 models whose node table disagrees with their own inverse
  bind matrices. All in [`format_cmdl.md`](format_cmdl.md).
- `CNOM`: the `u8` at `+0x04` of a channel; the constant `1000.0` at `0x4C`;
  the `u16 1` at `0x12`; and **which rig the 72 `fgn`/`mgn` animations were
  exported from**, since they key `node_hip` absolutely and carry no `xrot`
  track, and no model on the disc matches. See
  [`format_cnom.md`](format_cnom.md). The frame rate is settled in
  [`units.md`](units.md).
- `CCLS`: what the fifteen-word bit says about the nine early stages; what the
  surface codes 1 to 13 name; the eleven stages with an edge used by three or
  four triangles. See [`format_ccls.md`](format_ccls.md).
- `ECH`: what the header word at `0x08` is for (zero on all 4,941 files, so the
  disc offers no evidence either way); the one-byte row width; column
  semantics everywhere except the 69 `effect.bin` and the quest `.pac`'s four,
  which are named end to end by their consumers rather than by the type
  inference. See [`format_effect.md`](format_effect.md) and
  [`format_quest.md`](format_quest.md) — the second of which shows a field can
  be **narrower than a byte**, which nothing in `ech.py` can see.
- The quest tables' leftovers: the counts and timers of a generator (`+0x14`,
  `+0x18`, `+0x20`, `+0x24`, `+0x28`, `+0x30` of `enemy_gen.bin`) — which now
  have a second reader, since an arena runs; the third
  byte of `piecelock`'s `+0x08`, 24 to 26 on 109 rows; `enemy.bin`'s `+0x37`
  and `+0x57`; and the reward tables a quest pac also ships —
  `item_reward{,_multi,_region}.bin`, `weapon_decost.bin`, `destructible.bin`,
  `mapexception.bin`, `enemy_ref.bin` and the `q<NNNNN>.bin` header, which is
  next session's item 1. **`lockarea` and `lock_line` are settled** — the
  first is the room and the second are the doors — and so is what closes an
  arena. See [`format_quest.md`](format_quest.md) and
  [`milestone_quest.md`](milestone_quest.md).
- `TXT`: what word 2 of a record selects; why attribute id 0 carries both RGBA
  colours and scale factors.
- `params`: what records 1 and 2 of a player class are — record 1 is plainly an
  **empowered** state, and session 21 narrowed it: it zeroes `stiff`,
  `stiff_dmg` and `stiff_act` as well as `stun_f`, so it takes no hit-stun at
  all, and the only mechanic a class file has other machinery for is the one
  its four `s_tension_*` tables fill the meter of. Record 2 changes four
  locomotion fields and **the same four with the same values on all six**, so
  it is a global movement state and not a class ability. The disc names
  neither, and a search of all 25,288 messages for "Fever" found nothing. The
  **player's base `def` and `hp` are not located**: `atk` is
  `it_db_weapon.bin` column 3, and `def` and `hp` are abilities 1 and 3 of
  `it_db_ability.bin` — which is the *modifier* side, with its bounds, and not
  a starting value. See [`combat_loop.md`](combat_loop.md) ledger item 2. Also the four unexplained
  elements of the `ab_*` status vectors — **their order is settled**, since `isAbnormal(1, 3)` is the
  player frozen and index 3 is `ab_frz`: [`format_api.md`](format_api.md).
  **`it_drop_break` is settled**: it is indexed by `region_data_brk`, the
  monster's breakable parts in order, and `region_lv` indexes the eight-slot
  arrays in `region_data`. Both in [`format_elbn.md`](format_elbn.md).
- `.anmcmd`: thirty of the fifty-two opcodes; the unit of `+0x35`, which
  [`combat_loop.md`](combat_loop.md) §5 narrows to two readings and gives the
  measurement that separates them; and opcode 10's effect id, which session 14
  showed resolves nowhere on the disc. **Part of "why 554 of the 2,053 name no
  motion" is answered**: 115 of them are the hunter's projectiles, which have
  no motion because they are not on a body - see the naming rules in
  [`format_anmcmd.md`](format_anmcmd.md).
  **`+0x48` is settled and it is a monster's field** — 747 of the player's 754
  records carry the sentinel and the player's impact sound is computed from
  `se_hitlevel_tbl` instead. **The hit record's geometry is settled** —
  `flag` at `+0x01` is a shape, it says which vector is which, and session 19
  showed the offsets are turned by their bone. What is left of it is **what
  flag 4's three points bound**. See [`format_anmcmd.md`](format_anmcmd.md)
  and [`hitbox.py`](../engine/hitbox.py).
- `.psq`: `_OP_COMPARITH`'s packed `_arg1`, which the disc emits three times
  and session 22's VM *executes* once without faulting - which is not the same
  as confirming the operand order, since a wrong one computes a wrong number
  rather than raising; and the `.ppcut` macro names, which the preprocessor
  consumed. **Control flow is no longer among them** - 2,753 of 2,753
  functions structure with nothing left over - and neither is the language:
  every script on the disc runs, with 0 VM faults. See
  [`format_psq.md`](format_psq.md) and
  [`milestone_stage.md`](milestone_stage.md).
- The script interface: **six names that are not functions** -
  `MONS_KIND_ORGA` and `DEMO_S174_A`..`DEMO_S178_A`, read off the root table,
  called by nobody and defined by no `.psq`, so the engine holds them as
  constants; **how long the host holds a blocked script**, since the thirteen
  `suspend` numbers are the disc's but the delays in `host.py`'s `RESUME` are
  this repository's policy; and about a dozen of the 285 whose argument roles
  the disc does not separate — `cfSetCameraType`'s five camera types, the second
  argument of the `cfSetCmr*` family, `cfDialogParamAll`'s seven numbers,
  `cfCmrQuake`'s four, `cfTutorialLineup`'s nine, `setDemoID`'s second, and
  whether `msg_emotion.bin` is `cfAnimeIcon`'s table. Also **`prowl_script`**,
  which all six bosses tail-call and nothing on the disc defines. See
  [`format_api.md`](format_api.md).
- `.PTP`: the inside of a `PTB`, which nothing needs until something renders.
  See [`format_ptp.md`](format_ptp.md). **Category 2 is settled**: it is the
  actor's own [`effect.bin`](format_effect.md) addressed by row id, 96 of 96,
  and not a bank at all.
- `.acb`: the waveform `ExtensionData`, empty on all 7,756; the command
  streams past opcode 2000 (volume, pitch, panning, AISAC); which member of a
  variation set the game picks and with what weights; and the `.acf`'s 16
  mixer categories and 40 buses. See [`format_awb.md`](format_awb.md).
- `.mkc`: **six** of the twenty-one opcodes — `0805`, `0806`, `080c`, `080d`,
  `080f`, `0406` — the argument roles of `0800` and of the camera shake, which
  has a sibling in the script layer in `cfCmrQuake` that agrees on its first
  argument and disagrees on its fourth; `7ffb`, which the footfall measurement
  does not touch; and whether `7ff9` and `7ffd` differ at all. See
  [`format_mkc.md`](format_mkc.md). Session 19 read `0400`, `0803`, `0804` and
  `0807`, and `0807` says **which foot**, which is what `7ffa` never did:
  [`pose.md`](pose.md). `7ffa`, the emitter and the effect index are all
  settled, leaving `z07` as the only pac that asks for something its table has
  not got: [`format_effect.md`](format_effect.md).
- The AI's own leftovers: **the seven per-boss escape hatches** -
  `checkB01Term` and its siblings - which nine tables call on 458 instructions
  and which nothing on the disc defines, the same shape of hole as
  `prowl_script`; **two terms that are dead as the shared include writes
  them**, 103 (which throws on a non-zero operand) and 115 (which is never
  true), both of which read cleanly if the engine's own predicate returns a
  number rather than a flag; and ten of the 76 condition terms, which the six
  `.cnut` predate and so cannot name; what the `2xx` action block means, given
  that its ids resolve to the same motions as the `1xx`; the `kind` byte of
  `<name>.par` and the 1000-band ids in `_coop.par`; the five `ProbList` files
  whose group ids repeat rather than ascend; and the eight `EventTable.dat`
  and `MotStream.dat`. See [`format_ai.md`](format_ai.md).
- The stage layout's own leftovers: the polyline's third word, 0 to 5; the 45
  markers named `HTA*`; and what places the object a `obj*` marker marks — the
  last of which is now half answered, since `obj` markers turn out to sit on
  the collision mesh to a centimetre. **Whether a fence is a closed loop is
  settled**: 105 of 145 stages close, 20 branch, see
  [`milestone_numbers.md`](milestone_numbers.md).
- The mercenary AI's leftovers, one fewer since the predicates' argument turns
  out to be an actor slot: the command ids other than 0, 14 and 15; the
  flag word at `+0x08`; the seven words of a `target_NN`; command 16, used
  twice; and the message ids in the two roster tables. See
  [`format_merc.md`](format_merc.md).
- `effect.bin`: the three bit-field bytes at `+0x08`..`+0x0a` of a motion row,
  which correlate with whether the row carries a locator and whether it
  carries an offset without matching either; the two at `+0x08`..`+0x09` of a
  stage row; the `kind` byte, 0 on 102 rows of 2,434 with nothing else
  splitting with it; and the near/far pair of distances a stage row carries.
  See [`format_effect.md`](format_effect.md).
- `ELBN`: the six multipliers in a `region_data`, which are six of something
  and the classes are the only six; the sign convention of its flat modifier,
  read as a defence and not proved; `region_data_brk`'s two `u16[4]` arrays,
  whose ids come from a family keyed on the part and resolve against nothing
  on the disc; `s_region_group_data`'s three angles and its eight empty index
  slots; and `stageparam.bin` past the lights and `mot_param.bin` past the
  motion id. `trace_par.bin` is read, and what it leaves is **which of a
  weapon's three `par_tbl` records is used when**, the two counts at `+0x19`
  and `+0x1a`, and `bowstring_data`'s first 48 bytes, identical on all 25 bows
  and so carrying no evidence. `statusData` is read as records and **its ids
  are not named** — 99 of them, `16 * group + variant`, with no second
  consumer on the disc. **Both hit-level tables are read** and what they leave
  is `se_hitlevel_tbl`'s **third word**, 0 to 8 across the fifteen player
  entries, per class rather than global, and not `it_db_weapon.bin`'s weapon
  kind; plus `eff_hitlevel_tbl`'s four identical `(2, id)` pairs, an axis this
  build does not use. **`ht_arrow_tbl` is read** — a lifetime, a speed and a
  gravity, 21.3 m against a search radius of 20 — and what is left of it is
  which of its 42 rows a given arrow list uses. See
  [`format_elbn.md`](format_elbn.md) and
  [`combat_loop.md`](combat_loop.md) §6.
- What the 14 empty `.cpk.patch` stubs would have overlaid, and whether a
  shipped title update exists that fills them.

---

# Log

## Session 24 - 2026-08-24

Milestone 5, written up in [`milestone_quest.md`](milestone_quest.md).
Sessions 22 and 23 are in [`milestone_stage.md`](milestone_stage.md),
[`milestone_fight.md`](milestone_fight.md) and
[`milestone_player.md`](milestone_player.md); what is here is what did not fit
in a milestone report.

- **`enemy_gen.bin`'s kill callback fires once per generator, not once per
  corpse.** The line the script prints is `--- generator [emgen01] End ---`,
  and on 36 of the 527 locks whose threshold matches, `enemy.bin`'s population
  byte for the slots those generators use is exactly twice the threshold. That
  is the 91 doubled rows [`format_quest.md`](format_quest.md) already found,
  seen from the consumer's side: a generator that ships two monsters still
  reports once, when it is exhausted.
- **A `piecelock` row's two polyline lanes are a room and its doors**, and
  point-in-polygon says which is which without running anything: 2,813 of
  2,817 spawners and 572 of 575 triggers inside the `lockarea`. The
  `lock_line`s are two-point segments across corridors, mostly outside it.
- **`piecelist.bin` is a graph, not a path.** Only 767 of 1,280 consecutive
  pairs carry a `jump_<next>` marker, but 398 of 428 lists are connected end
  to end under those markers. The thirty that are not are almost all `170_*`,
  where the exit marker is named **`jump_next`** and the stage's own
  `MapJump()` branches on `getQuestName()` - interchangeable floors, so the
  door does not name where it goes.
- **The ground mesh is a navigation mesh and it took no new data.**
  [`format_ccls.md`](format_ccls.md) had established that the mesh is welded
  and that the edge of the walkable region is the fence; those two facts are
  the whole of a navmesh. `world.py` gains `graph`, `path` and
  `nearest_triangle`, built out of `ccls.py`'s triangles and `stage.py`'s
  polylines and nothing else.
- **Four more host functions answer with a number**:
  `cfGetCntKillGenPieceLockOnly`, `getLatestKilled`, `getNumOfEnemy` and
  `getNumOfBoss`, which takes `host.py api` to 70 of the 285 and 70% of the
  interface's traffic. And `brain.py`'s `State` finally has a crowd to count:
  `other_zako`, `other_boss` and `same_kind` were marked *world* and had been
  zero in every fight so far, because every fight had one monster in it.

## Session 21c — 2026-08-23

- **`it_db_equip.bin` is not armour, it is costumes.** 146 rows against 146
  names, and the names are `Assassin`, `Bishop`, `Track Suit`, `Ryu Hayabusa`,
  `Lloyd Irving`, `Kasumi`. Column 1 is a **sex** — 0 or 1, seventy-three
  each, and row *n* and row *n + 73* carry the same name — and column 2 is the
  class in the same space `it_db_weapon.bin` column 5 uses, with **8 on the
  110 costumes any class can wear**. No stat anywhere in it.
- **`it_db_ability.bin` is one row per stat the game lets an item move**, and
  the row is `(index, floor, ceiling, kind)` with the index equal to the row
  on all 233. It carries no name — but `it_db_skill.bin`'s 1,091 card skills
  index it and pair positionally with 1,091 names and 1,091 descriptions, so
  the join gives **all 162 used abilities the game's own English**.
- **`DEF` is ability 1 and `MAX HP` is ability 3**, which is where the
  player's two missing numbers enter the loop. The card system reaches every
  quantity [`combat_loop.md`](combat_loop.md) describes: ability 9 is the
  critical rate, 10 its bonus, 8 the knockback and stun resistance, 5 the base
  tension level, 34 the defence while guarding. The **base** values are still
  not located, so ledger item 2 narrows rather than closes.
- **968 of the 993 magnitudes lie inside their ability's range**, which is
  what says the skill's column 6 is the magnitude and the ability's two floats
  are its bounds. **Eighteen of the 25 that do not are one ability**: 175's
  values are `170001` to `170040`, ids in the skill band and not magnitudes,
  and its range `(0, 41)` bounds the low part of them. The selector trap
  again, in a table that had looked uniform.
- `combat.py abilities` is the join.

## Session 21b — 2026-08-23

- **The `.psq` control flow is structured, and all of it.** `psq.py src` no
  longer prints labels and `goto`: it rebuilds `if`, `else`, `switch`,
  `while`, `do..while`, `foreach`, `break` and the short-circuit operators.
  `psq.py struct` measures it over the disc — **2,753 of 2,753 functions that
  carry a jump, 0 jumps not placed, 0 statements stepped over.** Squirrel has
  no `goto`, so every jump came out of a construct and *most of them* would
  not have been a result; the shortfall is the whole instrument.
- **What the 20,032 jumps turned into**: 5,068 `if`, 3,483 `if/else`, 1,761
  `break`, 248 `switch` with 203 fall-throughs, 34 `while`, 11 `foreach`, 4
  `do..while`, plus the 2,635 `&&` and `||` folded a level down as
  expression. **Only 49 jumps on the whole disc go backwards** — the cutscenes
  are linear and the AI is table-driven.
- **A `switch` is told from an `else if` by a jump no `if` ever makes.** Both
  compile to a chain of tests of one register against constants; a `switch`
  case falls through by jumping into the **next case's body**, past that
  case's own test, and Squirrel emits that jump even after a `break` — so a
  `switch` shows two consecutive `_OP_JMP` where an `else if` shows one. The
  first rule written was "three links or more"; it left 100 jumps stranded in
  30 two-case switches, and the residual count is what said so.
- **Two holes were invisible until the arms became blocks.** `_OP_AND` and
  `_OP_OR` printed as control flow, so `a && b` read as a branch on `b` alone
  and **the left operand was silently gone from the listing**, on 2,635 sites.
  And the liveness rule gave up at the first jump it met, which made a call at
  the end of a block always look live and dropped **3,004 statement calls** —
  most of them the last action of an `if` arm. `print_root_table`'s `foreach`
  came out with an empty body, which was the tell.
- **The fix for the second is what the first made possible**: real backward
  dataflow to a fixed point over the jump graph, which the same jump fields
  already describe. `writes()` is the mirror of `reads()` and `liveness()` is
  twelve lines. Also fixed on the way: `_OP_COMPARITHL` was declaring one
  read where it makes two, so a call on the right of `+=` printed twice.
- **The AI now reads as its author wrote it.** `check_converted_xml_term` is
  the `switch` [`format_ai.md`](format_ai.md) reconstructed by correlation,
  and `prt_select` is the weighted action selector with its three loops, its
  10000 normalisation and a Japanese fallback line. Terms 10 to 17 are one
  case falling through to `getTimeFromID(term)` — one row, not eight — and the
  `||` fold restores the `time == 0` that made an unstarted timer pass.

## Session 21a — 2026-08-23

- **[`combat_loop.md`](combat_loop.md) exists**, which was item 1 for three
  sessions. One hit, from the frame it fires to the number that comes off a
  health bar, through eight files, saying at each step which numbers the disc
  gives and which it does not. It ends in a **ledger of nine**: four items are
  ordinary disc work and five want the EBOOT, and each of the five is one
  function rather than a subsystem. [`combat.py`](../tools/combat.py) is the
  six joins behind it.
- **The hit level is three values and two tables agree about it.**
  `se_hitlevel_tbl`'s fifteen player entries are six apart and run 1000 to
  1084, so they **tile the cue range 1000..1089 exactly** and 1090 is where
  the monsters start; resolving the six against `common.acb` gives `S M L`
  then `CS CM CL`, so `cue = base + size + 3 * critical`. The fifteen bases
  are the fifteen weapon kinds — katar, somersault, mace, shield, holy,
  godfist, drill, screw, arrow, staff, fire, gravity, thunder, ice, sword.
- **`eff_hitlevel_tbl` carries its key in the open**, two `u16` `(level,
  kind)` in the last word, levels `{0,1,2}` over all 48 records. That corrects
  the *"weapon kind × 10 + hit level"* reading of its ids, which fits the
  hunter and is contradicted by the other five classes.
- **The player's impact sound is computed and the monster's is written down.**
  747 of the player's 754 hit records carry the sentinel, 5,245 of the
  monsters' 5,439 carry a cue, and **not one record on either side reaches
  into 1000..1089**. A monster's claw always sounds the same and a player's
  weapon does not. `format_anmcmd.md` had read `+0x48` as *the* impact sound;
  it is a monster's field.
- **`atk`, `def` and `hp` occur in 82 actors and all 82 are monsters.** The
  player's attack is `it_db_weapon.bin` **column 3** and its weapon kind is
  **column 5**, whose six values take **seventy-five rows each** — 450 rows,
  an exact partition, pairing positionally with 450 names. The defence and the
  hit points are still not located.
- **A boss takes no hit-stop.** `dmg_stop_mul` is zero on exactly the 23 `b*`
  and non-zero on exactly the 59 `z*`, 82 of 82. And the two families split as
  giver and taker: `stop_mul` is a thousandth so its operand is damage, while
  `dmg_stop_mul` is 1 so its operand is already frames.
- **The tension curves are per class, and the tool caught the document.**
  All four share their threshold column across the six and three of the four
  do not share their multipliers; three cut the assassin in the same direction
  by about half — 0.15 against the shield classes' 0.4, half the react rate,
  and none of the 5.0/4.0 bonus above a full meter. `format_elbn.md` said
  "identical across all six classes"; `combat.py tension` was written to
  reproduce that line and refuted it on its first run.
- **`cri` and `dmg_critical_factor` run opposite, rank for rank** — the
  assassin crits most often and gains least, the warrior least often and gains
  most, and the product varies by 1.8x where the rate varies by 3.3x.
- **Record 1 of a player class zeroes `stiff`, `stiff_dmg` and `stiff_act`**
  as well as `stun_f`, so it takes no hit-stun at all; record 2 changes four
  locomotion fields and **the same four with the same values on all six**, so
  it is a global movement state and not a class ability.
- **The bow carries two falloff curves nobody else does**,
  `ht_atk_revise_tbl` (stride 12) and `ht_react_revise_tbl` (stride 8), both
  closed by the gap to the next array, both holding at or above 1 to half way
  and then falling to a tenth on a 0..100 axis. The reaction falls off before
  the damage does.

## Session 20 — 2026-08-23

- **`trace_par.bin` is the weapon trail**, and both its names are read. 207
  files — 154 weapons, which is `weapon.cpk` entire, and 53 monsters — and
  every one of them sits in a directory called `trace.pac` with the textures
  it is drawn with. [`format_elbn.md`](format_elbn.md) gains a chapter and
  [`elbn.py`](../tools/elbn.py) gains `trace`.
- **`ref_tbl` is two points in the space of a locator**, the third format to
  use the dual numbering after `.anmcmd` and `col_hit`: **351 of the 357
  non-zero ids are a locator on the actor's own model**, 156 of them
  `node_r_weapon` and 30 `node_l_weapon`, the rest hands, feet, eyes and the
  `eff_*` locators [`effect.bin`](format_effect.md) already uses. The six
  misses are all `b18`, which asks for two ids it does not declare.
- **The points are the weapon, measured.** The assassin's pair reads
  `(0,0,0) -> (-0.74,0,0)` on each hand, which is two daggers; the sword
  warrior's runs `y = 0.20` to `y = 2.00`, guard to tip, and 25 of its 26
  models reach within a quarter of that; the hammersmith's two records cross
  at right angles, which is a hammer head drawn as two ribbons.
- **A weapon's trail is authored once per class.** 207 files hold 43 distinct
  `par_tbl` blobs, and on the player side the grouping is exactly the class —
  so a difference between two swords would have been read as meaning, and
  there is none.
- **`par_tbl`'s first word indexes the textures beside it**, 523 of 523, in
  the container's own order; `b12` ships a body texture and a `_foot` one and
  hangs four of its six ribbons off `node_l_foot` and `node_r_foot`.
- **Packed colour, third format, third convention.** These are `ARGB` where
  [`CMTM`](format_cnom.md)'s and the stage lights' are `RGBA`. The tell is the
  template pair, `ff808080` fading to `00808080`, which differs in one byte;
  496 of 523 head colours open at `0xff` and 449 tails close at `0x00`.
- The selector trap again, in a new place: `+0x18`'s first byte is 0 on 244
  records, 2 on 254 and **4 on 25**, and on those 25 the colour words are `0`
  and `1` rather than colours. Averaging the columns across all 523 would have
  gone straight through it.
- **`statusData` lives in `stobjbin.bin`, not `objbin.bin`.** Its header is
  `(count, pointer, stride)` and `count * stride` closes on all 89 files; the
  stride is **28 for a monster and 60 for a class**, the first 24 bytes are the
  same struct in both, and the id is `16 * group + variant` — 99 distinct ids
  over 3,070 monster records and 109 over 630 player ones. The row count
  correlates with a monster's `.anmcmd` files at 0.71 and equals it on none of
  the 83, so it is a state list of the same order as the motion list and is
  not the motion list. What the states are stays open.

## Session 19 — 2026-08-23

- **The `ELBN` records are read, for the population that matters most.**
  [`format_elbn.md`](format_elbn.md) gains a chapter and
  [`elbn.py`](../tools/elbn.py) gains `records`, `capsules` and `regions`.
  `objbin.bin` is the actor's body and the player class's skill list, and the
  method was the one `ech.py` uses on a column: look down the same word across
  every file that carries the record.
- **`col_hit` is a capsule per bone and it is the body.** 1,172 records over
  100 files: a bone, two endpoints in that bone's own space, a radius. Every
  one whose actor has a model resolves inside it, **1,148 of 1,148**, through
  the same dual numbering `.anmcmd` uses — a node index below 1000, a `CMDL`
  locator id above. `jostle_data` is the same with two radii, `pgs_data` is a
  sphere.
- **A monster has named body parts, and three files agree about them without
  saying so.** `region_data`, 315 records over 83 monsters, first word a
  pointer to `HEAD`, `HARA`, `L_WING_03`. A region names `col_hit` capsules by
  index, a capsule names a node, and **the node's name is the region's own**
  on 259 of the 266 a reader's synonym table has a word for. All seven misses
  are the table's fault and every one is printed: `HARA` is on `node_hara`, a
  bat's `wing` on `node_l_upperarm`.
- **`region_data_brk` is the index `it_drop_break` never had.** 87 records
  over 23 monsters, and its record count equals the length of the JSON's
  `it_drop_break` list on **23 of 23**. `b18_00` breaks `HORN_U1`, `HORN_U2`,
  `TAIL`, `WING_L`, `WING_R` and drops 7950 to 7954 in that order.
- **The eight-slot arrays are `region_lv`**, a field the monster JSON already
  carried and whose range across all 89 files is exactly 0 to 7. Hit points
  and a flat modifier, per difficulty tier.
- **An offset is turned by its bone — settled, on an animated frame.**
  [`hitbox.py`](../engine/hitbox.py) is new: `pose.py` gained a `matrix()` so
  a bone arrives with its orientation, and every hit record on the disc is
  placed twice on the frame it fires. Against the direction from the bone to
  its child, the turned reading lands within 26° on **13.5 %** of 1,435
  placements — **chance is 5.1 %** — and the carried reading lands on 5.6 %,
  which is chance. Fourteen standard deviations against one.
  `col_hit` says the same thing in the rest pose without a measurement: turned
  by `node_hip`, whose own `z` points down, the player's two capsules stand a
  body up from 0.07 to 1.87 m; not turned, they lie flat over 0.60 m.
  **Two measurements that did not work are written down** — the capsule axis
  against the limb, where both readings share the limb term and score the
  same, and a floor test, where a monster in the air has no floor to be under.
- **Four more `.mkc` opcodes.** `0400` carries a state and a **locator id**,
  and grouped by (file, locator) the state alternates on **722 of 722**
  groups, which is a switch and not a parameter — the hunter's string attacks
  show something on `node_r_weapon` at frame 2 and hide it at frame 6, and
  frame 7 plays `ARROW_DUMMY_S`. `0803` fires on the same frames with the
  opposite value. `0804` is not an event at all: 24 records, all at frame 0,
  on exactly the twelve player bodies' `213run` and `215run_dash`.
- **`0807`'s argument is which foot**, and that is the thing `7ffa` never
  said. `pose.py foot` puts the skeleton under all 66 firings: **28 of 28 on
  the players**, 0 the right and 1 the left, 47 of 55 over every actor, and
  the eight that miss are two scuffing damage reactions, a cutscene where
  neither foot is near the floor, and one monster that also uses 2 and 3.


- **The minimap is a minimap and not just a picture.** `stage.py` gains
  `minimap`, `minimap_png` and `minimap_check`, and
  [`format_stage.md`](format_stage.md) gains the transform. The method is
  intersection over union between a texture's alpha channel and a collision
  mesh drawn under a candidate transform — two files that share nothing else.
  135 stages, **median IoU 0.805**, 95 at 0.75 or better, 2 below 0.5.
- **The anchor is exact and the scale is a band.** Over the 47 best fits the
  footprint's area centroid lands on pixel **127.5, 127.5** — the centre of a
  256×256 image — with a standard deviation of 4 px in x. The scale's spread
  collapses as the fit improves (sd 0.147 over all 135, 0.098 over the best
  47, **0.059 over the best 25**), which is a constant plus noise; the best
  estimate is 1.31 to 1.33 px/m and the disc does not declare it anywhere
  found. Pinned with no free parameter at all the median IoU is still 0.65.
- **The markers confirm it and were not part of the fit.** `hta.bin` places
  the monster generators, props and arrival points in world coordinates.
  Pushed through the transform, **1,376 of 1,411 `emgen_pos` (97.5 %)**, 399
  of 421 `obj` and 167 of 178 `appear` land on a drawn pixel. The kinds that
  miss are the effect emitters, and **`ef_B` and `ef_C` are outside the drawn
  map on every one of their 43 and 89 instances**.
- Two stages ship a second map: `060_01_01_2.map` and `060_01_02_2.map` are
  the same silhouette **with half of it hatched off behind a dashed line**.

## Session 18 — 2026-08-23

- **The engine's script interface is read: 285 functions, what each is handed
  and what it does.** See [`format_api.md`](format_api.md) and
  [`tools/psq.py`](../tools/psq.py), which gains `calls` and `sites`. No
  disassembler was involved. The sources, in order of how much they settle:
  the 65-function wrapper library in `common.psq` names the arguments; the
  compiler's `localvarinfos` name the results; the constants join tables that
  are already read; and this build shipped its `print` calls.
- **The count was 453 names and 289 natives, and it was low twice** — the same
  mistake in two forms. `psq.py api` looked only for `_OP_PREPCALLK` then
  `_OP_CALL`, so it missed **tail calls** (`return active_script()` is `0x05`;
  132 script names and one native hid there) and **root calls through a
  computed key** (`this['cfGetCntKillGenPieceLockOnly']()`, which nearly every
  quest script opens with — **892 calls to a native nobody had listed**). The
  numbers are now 587, 296 and 291, and of the 291 five are Squirrel's own
  standard library and one is missing.
- **One name resolves to nothing, and it is a hole in the game.** All six boss
  `.cnut` end `if (isActive()) return active_script(); return prowl_script()`
  and **no file on the disc defines `prowl_script`**. The AI was converted from
  XML with two behaviours and only the active half was exported.
- **`suspend` is the protocol, not a function.** `_bgenerator` is 0 on all
  11,232 functions, so this is `sq_suspendvm`: the script hands the host a
  number and stops. Thirteen numbers cover every blocking thing in the game —
  100 and 101 a talk window, 110 a choice returning its index, 120 any
  full-screen mode, 300 to 302 a dialog, 400 the quest-start prompt, 1000 a
  plain wait. A reimplementation owes the interface a resume as well as 285
  functions.
- **Five arguments were checked against tables rather than argued about**, and
  `psq.py xref` now runs all of them.
  - **`talk(speaker, message)` joins both ways.** Every one of **10,787**
    message ids is inside `menu.cpk/msg_field.en.pac/msg_npc_talk.bin`, whose
    6,139 messages the script reaches to 6,138 — the table is exactly as large
    as it needs to be, and not one call falls outside. The speaker is a row of
    the 55-name `msg_npc.bin`, 54 is `Norn`, and she is the busiest at 2,759
    lines. And the town scripts are named after who speaks in them: **10,058 of
    10,333 lines under a two-letter-prefixed script use that prefix's own
    character**, over 30 prefixes, `No` → Norn 2,756 of 2,756;
  - **a motion id is the number inside its own `.CNOM` filename**, and it is a
    vocabulary the whole cast shares — 11 `wait_1`, 12 `wait_2`, 15 `talk`, 16
    `greeting`, 22 `sit`, 25 `sit_talk`, 41 `toast`, 901 `demo_01`. **1,220 of
    1,331** `chrSetMotion` and `chrSetMotionNPC` calls name a motion the
    addressed character has, and **every one of the 111 that do not asks for
    201**, which no `.CNOM` on the disc carries — a sentinel, and it turns up
    in the same place in `chrSetMotionNPC`'s *connect* slot 90 times;
  - **a voice line names the speaker.** `chrPlayVoice` addresses the 58-cue
    `sound.cpk/en/vnpc.acb`, and **1,120 of 1,144 calls pass a cue whose name
    carries the name of the character handed to it**. The 24 that do not are a
    complete list: a war cry, a toast, and four cases of one character speaking
    another's lines;
  - **every BGM, common-SE and NPC-voice cue id resolves** — 292 of 292;
  - **`getCharacter(name)` names an `hta.bin` marker**, `pos_<name>`, on 1,362
    of 1,407. The 45 misses are `player0`, the `DEMO_*` cutscene actors that
    `setDemoPos` places instead, and two spellings. The record behind it is
    `<stage>/param.pac/npc.bin`: `(kind, name, model pac, marker, index,
    const, radius)`.
- **The mercenary AI's argument is an actor slot** — 0 the mercenary, 1 the
  player it follows, 2 its target. [`format_merc.md`](format_merc.md) listed
  the 19 predicates with `n` unread. `check_active_*` reads
  `getRange(1) < 35 && isAbnormal(1, 3)` and then **prints `plyer freeze`**,
  which names the slot and the status in one line, and the phases split cleanly
  either side of the target being chosen.
- **And that names the status ids.** Dropping the scalar that heads them, the
  `ab_*` vectors appear in the player JSON in a fixed order — `pss psl prl frz
  brn nrv ten tir atd dfd` — and index 3 is `ab_frz`. So the abnormal-status
  kind is a **zero-based index into that block in its own declared order**,
  which was one of four things [`params.md`](params.md) had open about it.
- **A stage script converts seconds to frames, and the constant is 30.**
  `050_02_03.psq`'s `genCycle(fix, random)` is `fix * 30 + random * 30 *
  rand()`, and `fix` and `random` are the `_sec_fix` and `_sec_rnd` session 17
  matched field for field against `effect.bin`. [`units.md`](units.md) had a
  declared frame rate down as the EBOOT's business; this is not a declaration,
  and it assumes the update runs once a frame, but it is the first
  seconds-to-frames constant found outside the executable and it agrees with
  the gait.
- **The same fourteen lines are the whole effect API**, and they close
  `EffData._work`: it is not a field of the record, it is the **slot number** in
  the host's `setInt`/`getInt` integer store where that effect's countdown
  lives, which is why `effect.bin` has no lane for it. `getHTAPos` returns
  `[x, y, z]`, `effStart(cate, id)` returns a handle, and `effSetRot` is given
  `cfGetRandI(65536)` for its yaw.
- **The angle unit is the script layer's too.** 65536 to the turn, the same as
  the marker table: the cameras are swung `32768 ± 8192` for ±45°,
  `setDemoRotY(index, 21845)` is 120° to the last unit, and the NPC turn speeds
  are multiples of 256 of it. The engine offers `cfSetCmrAngY` and
  `cfSetCmrAngYDeg` for the same setting, and the artists used the second.
- **`chrSetAttachArticle`'s middle argument is a `CMDL` locator** — 4000 and
  4100 are `node_r_weapon` and `node_l_weapon`, and twelve NPCs are handed beer
  mugs, eight right-handed and four left. That is the **fourth consumer** of
  one numbering, after `.CTXT`, `.mkc`'s emitter and `effect.bin`'s socket.
- **Still open here**: `cfSetCameraType`'s five camera types, the second
  argument of the `cfSetCmr*` family, `cfDialogParamAll`'s seven numbers,
  `cfCmrQuake`'s four and whether it is `.mkc`'s `0802`, `cfTutorialLineup`'s
  nine, `setDemoID`'s second argument, and whether `msg_emotion.bin` is
  `cfAnimeIcon`'s table.
- **A quest is a spawn system in four tables, and they are read.** See
  [`format_quest.md`](format_quest.md) and
  [`tools/quest.py`](../tools/quest.py). 430 quests, 1,708 stage entries,
  2,503 monster slots, 8,024 generators, 567 arena locks. `piecelist.bin` is
  the stages the quest visits, `enemy.bin` gives each stage eight monster
  slots, `enemy_gen.bin` is one row per spawner, and `piecelock.bin` is one
  row per arena lock.
- **The monster id is twelve bits, and it names a directory.** A filled
  `enemy.bin` slot reads `01 hh h0 00`, and **the low nibble of the third byte
  is zero on all 2,503 filled slots** — which is the whole tell. Read as a
  12-bit field the ids are `1000 + 10*NN + MM` for `monster.cpk/zNN_MM` and
  `2000 + …` for `bNN_MM`, and **2,503 of 2,503 slots name a directory that
  exists: 83 ids against 83 directories, nothing left over either way.**
  - and it is the AI's numbering. A cutscene writes
    `getLatestKilled() == 2000 + 10*(37 - (28 - 1))`, which is 2100, which is
    `b10_00`, so **`getNearestBossKind()`'s kind *k* is `b(k - 27)`** — 28 is
    the Orc King, whose `.cnut` is the one everybody quotes. The quest tables,
    the AI and the model directories are one namespace.
- **The chain from a quest to a monster on the ground is complete**, and every
  link is counted: a generator names an `emgen_pos` marker of its stage (7,728
  of 7,735), a lane of that stage's `enemy.bin` row (7,976 of 8,011), and up to
  two script callbacks — **3,123 of them, and not one misses** a function the
  same quest's own `.psq` defines. A lock names its `lockarea` and `lock_line`
  fences (1,736 of 1,739), its `pl_q` hit area (552 of 552) and the generators
  it covers (3,072 of 3,114).
- **The 320 `cfStartPieceLock` calls that looked unresolved are explained.**
  [`format_psq.md`](format_psq.md) had 569 of 889 naming a string in their own
  `.pac` and left it. **309 of the other 320 name a lock a *different* quest
  declares and only 11 name nothing at all**, because a stage script ships in
  every quest that visits the stage — `900_01_01.psq` is in 89 quest pacs — so
  it is written once and copied, and it asks for locks only some of them have.
  Same for `cfSetEnableEmGen`: 149 own, 91 another quest's, 0 nowhere.
- **Two lanes of `enemy.bin` are eight bytes.** `+0x2c` holds one byte per
  monster slot, 99 where the slot is empty — it agrees with the slots on
  **11,040 of 11,088** pairs — and where the slot is filled the byte is the
  **count of that monster in that room**: equal to the number of generators
  aimed at the slot on 2,275 of 2,503, exactly double on 91, ragged on 137.
- **What this says about `ECH` for the second session running.** Session 17
  showed a four-byte lane is often not one field. This one shows a field can be
  **narrower than a byte**, and that the tell is free: a nibble that is zero
  everywhere. Both are in [`format_ech.md`](format_ech.md), because it is the
  method that transfers.
- **Still open here**: the counts and timers of a generator (`+0x14`, `+0x18`,
  `+0x20`, `+0x24`, `+0x28`, `+0x30`), the third byte of `piecelock`'s `+0x08`
  which is 24 to 26 on 109 rows and rises with the quest number but is **not**
  a BGM cue (0 of 109 match one the quest plays), and the reward tables a quest
  pac also ships.

## Session 17 — 2026-08-23

- **`effect.bin` is read, both schemas, and it is the file that says where an
  effect goes.** See [`format_effect.md`](format_effect.md) and
  [`tools/effect.py`](../tools/effect.py). 69 files, 3,918 rows, 0 failures.
  A `.PTP` block is a particle system with no placement in it; this is what
  supplies the placement. The 69 turn out to be **two unrelated structs that
  share a name, a width and a container**: 54 motion tables with no string
  pool, and 15 stage tables with one.
- **`.mkc`'s `0801` addresses a row's own id byte, not its position.** Every
  row opens `(kind, id, category, slot)`; the id is unique inside all 54
  tables and skips wherever an effect was cut. **4,187 of 4,190 references
  resolve as an id against 4,125 as a position**, and thirteen of the fourteen
  pacs listed in [`format_mkc.md`](format_mkc.md) as *indexing past the end of
  their own table* stop doing so — `b15`'s 67 against 48 rows is an id that is
  simply there. `z07` is the one left, asking for 4, 5 and 6 out of a table
  holding 1, 2, 3, 7 and 8.
  - the reason the position reading looked right is the ceiling: on 29 of the
    54 pacs the largest argument is exactly the row count, which a dense table
    satisfies under either reading. The sparse tables are what tell them apart.
- **The `u32` at `+0x04` is a `CMDL` locator id** — the same `S4` namespace
  session 16 named for `7ff9`'s emitter. **455 of the 457 non-zero values
  resolve** on the actor's own rig, and the vocabulary reads itself again:
  `node_r_weapon` on 66 rows, which is the weapon trail; `node_hip`, the
  hands, the head, `node_jaw`, the toes; `big_gun`, which is the shield
  stage's own turret; and the `eff_*` sockets. The other 1,977 rows leave it
  at 0 and hang the effect off the actor's origin. One table, two consumers,
  one answer: a sound and an effect come out of the same socket.
- **`.PTP` category 2 is this file, and not a fourth bank.**
  `eff_hitlevel_tbl` reaches id 252, no `PTCP` on the disc has 252 slots, and
  the reason is that category 2 addresses **the class's own `effect.bin` by
  row id — 96 of 96 pairs resolve**. That closes the last unplaced piece of
  the effect addressing; see [`format_ptp.md`](format_ptp.md).
  - and the table then explains the numbers. `fht`'s ids are 110, 111, 112,
    120, 121, 122 … 250, 251, 252, and each triple is **one `.PTP` slot at
    scale 0.5, 0.8 and 1.0**. Eleven weapon kinds by three hit levels, and
    **the hit level is the scale** — the same three numbers out of all twelve
    player tables.
- **The rest of the motion row reads as placement.** A scale, an `(x, y, z)`
  offset in metres, and up to two rotations written as `(axis 1..3, degrees)`
  — 168 of the 181 angles are a whole multiple of five and **no row ever names
  the same axis twice**, which is what an artist typing Euler angles leaves
  behind. `z01`'s rows 16 to 24 are one smoke puff at half size scattered a
  metre either way with `y` left at zero: nine dust clouds on the ground.
- **The stage table is a placement list, and a script names its columns.**
  A row is one effect standing on one named marker in one room. All 1,484 rows
  land on a filled block of **the stage's own `effect.PTP`** — there is no
  category lane because there is no choice, and 24 of them are on a slot
  `misc.PTP` has not got, which is what rules the common bank out.
  - `stage.cpk/050_02_03/param.pac` declares `class EffData { _hta_name;
    _eff_cate; _eff_id; _rnd_radius; _y_offset; _sec_fix; _sec_rnd; _cue_id;
    _work }` and lists **the same six markers the binary lists for the same
    room**. The two agree field for field: slots 8, 8, 9, 8, 9, 8; `y` −8.5 on
    all six; a period of 5 s + 5 s on all six. The script carries one field the
    table does not, `_rnd_radius`;
  - **a row names a cue exactly when it carries a period**: 44 do both, 1,440
    do neither, 0 disagree. A fire that restarts every five seconds makes a
    noise when it does; embers and smoke run continuously and are silent;
  - **a row stands on a marker its room declares**: 1,483 of 1,484 `(room,
    marker)` pairs are in that room's `hta.bin`, so the table joins straight
    through to a world position. The one that is not is `080_01_02`'s
    `ef_uplight001`, in a room that declares `ef_uplight002` and no `001`.
- **What this says about the `ECH` type inference.** `effect.bin` is the first
  `ECH` whose columns are named end to end, and neither the EBOOT nor
  `ech.py`'s classifier did it — the *consumers* did, four of them, each with
  its own reason to reject a wrong reading. `ech.py` reads the first four
  bytes of a motion row as one `u32`; they are four one-byte fields, two of
  which are an address. Noted in [`format_ech.md`](format_ech.md), because it
  is the method that transfers, not the table.
- **The hit record's three vectors are named, and the answer is that there is
  no single answer.** See [`format_anmcmd.md`](format_anmcmd.md). The question
  had been open since session 9 and was being asked the wrong way round:
  **`flag` at `+0x01` is a shape**, and the shape says what the vectors are.
  `python anmcmd.py shapes extract/tree`.
  - **a flag never half-uses a vector.** Flags 0, 1 and 2 leave the third at
    zero on all 5,616 of their records and flag 0 leaves the second at zero on
    all 3,258. That is a field under a selector, not a field that happens to
    be empty;
  - **on flags 3 and 5 the second vector is a direction and the third is a
    bare number.** All 131 second vectors have length exactly 1, 98 of them on
    the `y` axis alone, and all 129 third vectors carry a value in `x` and
    nothing in `y` or `z`. The tilted axes settle it beyond argument: 24
    records carry `(-0.5144957304000854, 0.8574929237365723, 0)`, which is
    `(-0.6, 1, 0)` normalised to the last bit of a float. Nobody types that.
    So the shape is a cylinder — a centre, an axis and a radius — and the
    files agree: `freezing_trap_bullet_active` is a disc of radius 4.5 m
    standing on the ground, `quag_mire_bullet` the same with 3.0;
  - **the second bone appears only where the second vector is a point.**
    Flags 1, 2 and 4 name one on 2,253 records; flags 0, 3 and 5 name one on
    none of their 3,390. A sphere needs one anchor, a disc needs one anchor,
    a capsule needs two;
  - **flags 2, 4 and 5 are monsters only** — one player record in 538. A
    player gets a sphere or a capsule; the complicated shapes are the bosses'.
- **`+0x04` is the anchor of the second vector, and it is a bone of the same
  limb.** Over the 2,253 records that name one, **2,194 sit on one chain with
  the first**: the same node 1,467 times, its parent 256, its child 201,
  further up the chain 270, elsewhere 59. The pairs read as limb segments —
  `node_r_forearm → node_r_hand`, `node_head → node_neck`,
  `node_neck → node_neck2`, `node_hara → node_spine1`.
  - **and the vectors are far too short to span the limb themselves.** Over
    the 786 records naming two *different* nodes the joint separation is
    6.41 m at the median while `|v1 - v0|` is 1.00 m — 16 % of it — under half
    of it on 614 of 786 and within 30 % of it on 35. The limb supplies the
    length. Read that way the capsule comes out 7.79 m long against a 6.41 m
    limb, which is a hitbox a little longer than the arm it wraps.
- **The offsets are lengths in the actor's own metres, and one of the two
  "sizes" is not a length at all.** Median `|v0|` per actor rises with the
  actor's standing height over 80 actors (r = 0.61), and so does `+0x2C`
  (r = 0.75 over 88). **`+0x30` does not** — r = −0.04, a median of 1.00 from
  the 1.9 m `z05` to the 35 m `b11`, and 5,160 of 6,193 values inside
  [0.5, 2.0]. It is a ratio, and calling both fields "a size" was hiding that.
- **What the rest pose could not settle, said plainly.** Whether an offset is
  turned by its bone or only carried with it is still open, and two
  measurements that looked decisive are not: the mirror test splits 141
  `x`-negated against 102 identical *with the same bone giving both answers in
  different files*, and the capsule-length test gives 1.25 limb-lengths turned
  against 1.10 untuned, within a factor of two on 79 % either way — these
  rigs' bind rotations sit too close to identity for a rest pose to separate
  the readings. Both are written into the doc so the next reader does not
  spend the afternoon on them again. The weapon case and a weak child-
  direction measurement (29.3 % within 26° against 15.2 %) lean toward the
  bone's own frame; an animated frame with a bent elbow would decide it.
- **Still open here**: the three bit-field bytes at `+0x08`..`+0x0a` of a
  motion row, the two at `+0x08`..`+0x09` of a stage row, the `kind` byte that
  is 0 on 102 rows and 1 on 2,332 with nothing else splitting with it, and the
  near/far pair of distances a stage row carries.

## Session 16 — 2026-08-23

- **The capsule gets a skeleton, and it is checked rather than looked at.**
  See [`pose.md`](pose.md) and [`engine/pose.py`](../engine/pose.py). The
  layer is 630 lines: a contact node, the height it stands at, forward
  kinematics along its chain, and four commands.
  - **the contact node is the toe when there is one and the ankle when there
    is not.** The players stop at `node_l_foot`; every monster with legs has a
    `node_l_toe` under it, and on `b01_00` the ankle is at 1.02 m while the
    toe is at 0.42 — for a digitigrade leg the ankle is a hock;
  - **the height that counts as down is read off the rest pose**, because the
    rest pose is a standing one: the lowest node in it is at exactly `y = 0`
    on every player model and the ankle is at 0.1421, against the 0.138 the
    same skeleton reaches at its lowest in `fas213run`. Nothing is fitted;
  - **`7ffa` is a landing, and the disc proves it.** Over 650 firings on the
    259 animations whose feet leave the floor, **79.5 % fire within one frame
    of the skeleton putting a foot down** and 47.1 % on the frame exactly,
    against 25.2 % and 8.8 % for a frame of the same animation picked at
    random. The median offset is zero. Shown at three tolerances so the
    tolerance can be seen not to be carrying it;
  - **and a tolerance-free version says the same**: the lower foot has fallen
    21.8 mm over the three frames into a firing, against 0.5 mm at an ordinary
    frame. A foot merely being *on the floor* proves nothing, because in most
    animations one of the two always is — that column is printed and marked as
    saying nothing, because it looked like a result;
  - **`7ffa`'s fourth cue is not a footstep.** Split by kind, the fall into
    the event is 6.9 mm for `WALK`, 138 mm for `RUN` and 353 mm for
    `LANDING` — the three order themselves exactly as their names do — while
    `DRESS` comes in at **−0.2 mm**, which is no arrival at all. Set it aside
    and the remaining 601 firings agree 81.9 % of the time. `DRESS` is cloth,
    and the skeleton is what says so;
  - **on the stage, the planted foot sits 3 mm above the collision mesh.**
    `run.py stride` walks the body over `010_01_01` with the animation
    running: median +0.0028 m over 76 planted frames of a walk, −0.0048 m at a
    run, −0.0032 m on `030_01_01`. The foot slides 6 mm a frame over the
    ground, of which 4 are the cycle being authored for 0.0459 while `walk_sp`
    says 0.05. Three things — a parameter table, a skeleton and a collision
    mesh — meeting to a few millimetres, with nothing arranging it;
  - **the gait comes back from a different definition.**
    [`units.md`](units.md) measured the planted slide against each animation's
    own lowest ankle; `pose.py` measures it against the model's rest standing
    height, which is a property of the skeleton and works on an animation with
    no cycle in it. Medians 0.0484, 0.1696 and 0.2769 against the old 0.0492,
    0.1699 and 0.2790, and **12 of 12 walks and 11 of 12 runs within 5 mm a
    frame of `walk_sp` and `run_sp`**. The four cycles belonging to sets with
    no `job.cpk` directory — no class, so no table to obey — are 0 for 8,
    which is the control arriving for free.
- **Two motion sets are keyed for a rig this disc does not ship.** `fgn` and
  `mgn`, 72 animations, carry **no `xrot` track at all** and key `node_hip` at
  `y = 0.899`, where every other player set keys the hip at 0.07 under an
  `xrot` the model puts at 0.9. Played on the shipped skeleton the body floats
  a metre and no foot ever touches. Drop the 0.9 and the walk's planted foot
  sits at −0.0014 m over 29 frames of contact, which identifies the fault
  exactly. No model on the disc supplies the rig either: of the 180 with an
  `xrot` node, the only three that put it at the origin are `b18_00`,
  `b18_01` and `b18_02`. See [`format_cnom.md`](format_cnom.md).
- **Where the residual is.** 109 firings of 601 are more than a frame out at
  1 cm, and they are not spread evenly: 54 are on attack motions, 20 on
  damage reactions, 14 on emotes, and the locomotion cycles contribute 17
  between them. Attacks and staggers are where a foot pivots and scuffs rather
  than lands. On `fht303landing` the cue fires two frames before the foot
  settles, and a sound starting slightly ahead of contact is what an audio
  department does on purpose — nothing here separates *fires early* from *is
  wrong*.
- **The emitter is a `CMDL` locator id, and that was the whole answer.**
  `7ff9`'s third argument says where on the body a sound comes from, in 23
  values nothing on the disc was known to define. `CMDL` section `S4` is a
  list of `(id, node)` pairs — the numeric attachment points the 1,151
  `.CTXT` collision and spring files are named after — and **2,715 of the
  2,716 references resolve** against the locator table of the actor's own
  model. `python engine/pose.py emitter extract/tree`.
  - the vocabulary then reads itself: 1300 is the head and carries the voice
    and the sounds a beak makes, 1100 and 1200 are the hands, 1700 and 1800
    are the feet — the left and right one whether the model calls it a toe, a
    foot or a claw — 10600 is the tail, 4000 is a weapon and 6200 is `b19`'s
    shield. The `10xxx` band binds to nodes named `eff_*`, which are effect
    sockets with no anatomy to give away;
  - **on a quadruped the hands are the front feet**, and the cue names say so
    without being asked. `b18` has `FRONT_STEP` and `REAR_STEP`, `b10` has
    `GRENDEL_STEP_F_S` and `_B_S`, `b19` has `HORSE_STEP_F` and `_B`, and over
    the **514 references that carry one the locator is the matching pair 508
    times**, with the six exceptions all one way;
  - **the `31xxx` band is not `1xxx` plus 30000 on a second body.** `b19` is a
    rider on a horse and declares both in one table: 1100/1200/1300 are the
    rider's — `node_human_l_hand`, `node_human_head` — and 31100, 31200, 31700
    and 31800 are the horse's;
  - the one reference that resolves to nothing is `b19501at1` frame 42,
    `HORSE_STEP_F` from 31300 on an actor that declares 31100, 31200, 31700
    and 31800 and no 31300;
  - and the pose agrees a third time: over the 1,737 references whose emitter
    names a node with a mirror twin, **the named limb fell 0.34 m (feet) or
    0.50 m (hands) over the three frames into the event and its twin fell
    0.0002 m**.
- **That check was a null result first, and the reference was what was
  wrong.** Measured as *height above where the node stands in the rest pose* —
  the definition `footfall` uses, which works on every player model — it came
  back at exactly 50.0%. A monster's rest pose is not a standing one: `b19`'s
  horse hangs two metres over its own, so height above standing is a height
  above nothing. Measuring a descent instead cancels the offset and the same
  data goes to 80.8%. `Body.floor` now says so in as many words.
- **`S4` is therefore not a sidecar index but the model's public numbering of
  places on itself**, with two consumers that never meet. Also visible only
  from that use: an id may bind to more than one node — `b09_00` declares
  `6100` for its head mesh and again for the damaged one — and the ids belong
  to the actor rather than the model file, since armour variants share a rig.
  See [`format_cmdl.md`](format_cmdl.md).

## Session 15 — 2026-08-23

- **`.mkc` opens, and it turns out to be the sound.** See
  [`format_mkc.md`](format_mkc.md) and `mkc.py`. **2,690 files, 19,724
  records, 0 unreadable**, every one landing exactly on its `0xffff`.
  - **the grammar is three words and a count**: `(frame, opcode, argc,
    args[argc])`, terminated by `0xffff`. The count is explicit, which is why
    the records are not a fixed width — the thing session 14 noticed and could
    not explain. Walking by that count closes on all 2,690;
  - **the frame is absolute and the disc settles it.** Of the 2,085 non-empty
    files paired with a `CNOM`, the absolute reading stays inside the
    animation's declared length on 2,077 and the delta reading overruns on
    1,471. Frames never step backwards on any file;
  - **a bank id is an `.acb` and the id is arithmetic**: 100 is
    `common.acb`, `200 + 10k` is `job.cpk/<class>/se.acb` over the eight
    classes alphabetically, `3000 + 10n` and `4000 + 10n` are the monsters.
    The two unused class slots, 230 and 270, are `cm` and `nn` — the two
    classes with no directory in `job.cpk`, which is what confirms the rule;
  - **the cue is a `CueId`, not a row number**, and that is the whole
    difference between nonsense and prose: 225 of `common.acb`'s 529 rows
    carry an id that is not their index. Read properly, **6,881 of 6,949
    sound references and 659 of 659 voice references name a cue**;
  - and then the game reads back in words. `mht361at_l` draws the bow on
    frame 4 (`DRAW_L`), releases on 18 with an `ATK_L` grunt, and fires
    `ARROW_DUMMY_L` on 20. `mht301jump` plays `JUMP`, `mht220escape_f_st`
    plays `AVOID`, `mht204wait_4` — the low-health idle — plays `DYING_1`
    then `DYING_2`, and `com060emo_10` claps four times;
  - **the first semantic test failed and that was the useful part.** Opcode
    `0801`'s argument looked like a cue index because it ascends through a
    monster's motions in the same order the cue list does. Probing it against
    the names — does a `*die*` motion reference a `*DEAD*` cue — said no. The
    same probe against `7ff9`'s *second* argument said yes at 100% on turns,
    84% on runs and 71% on damage, with every apparent miss being a better
    name than the regex asked for: `WOLF_L_V_DEATH_1`, `GRENDEL_V_TETTAI`,
    `LEG_DRAG_L` and `SUPER_RUMBLE` for a giant crawling;
  - **`effect.bin` acquires a consumer.** `0801` is a 1-based index into the
    `ECH` table sitting beside the `.mkc.pac` — 69 of them, never opened
    before. On 29 of the 54 pacs that use it the largest index is *exactly*
    the row count, and it is never 0 on any file;
  - **`7ffc` is the player's voice**, and it resolves against the 57-cue
    `v{m,f}NN.acb`: 23 `ATK_S` 114 times, 25 `ATK_L` 86, 24 `ATK_M` 69, 22
    `JUMP`, 15 `DASH`, 17 `DMG_S`. Players and the emote set use it and
    nothing else does;
  - **`7ffa`/`7ffb` are the foot**, and the argument picks one of the four
    cues in the character model's own `.acb` — `WALK`, `RUN`, `LANDING`,
    `DRESS`. Over the whole disc `kind = 0` is what walks fire, 1 what runs
    fire, 2 never appears in a walk or a run, and 3 in no walk, run, dash or
    landing at all;
  - **`0802` is the camera shaking.** 1,207 of its 1,275 records are on the
    big monsters, where it fires on the footsteps — and all 64 player uses
    are the impact frame of a big skill: `back_stab`, `hammer_fall`,
    `drill_cannon`, `sharp_shooting`, `fire_ball`, `frost_wave`, and nothing
    else in the move list;
  - **the emitter is a place on the body.** Non-zero only on the sixteen big
    monsters, and Hraesvelgr names it for us: `BLAST_L` and `SWOOPED_L` take
    1100, `_R` takes 1200, sixteen of the seventeen voice cues take 1300, the
    steps take 1700 and 1800, and the three tail sounds take 10100;
  - **a motion set can be shared.** `z18`, `z19`, `z20` and `z27` ship the
    *same* `z19.mkc.pac` and all four fire bank 4190 — one animation set and
    one sound bank across four palette swaps;
  - and one negative worth writing down: the emitter vocabulary is **not** the
    `.anmcmd` effect catalogue. Two of its 23 values also occur there and the
    other 21 do not.

- **The movies, and they are simpler than the row implied.** See `pam.py`.
  **46 files, 3.4 GB extracted, 22.7 minutes, 0 unreadable.** A `.pam` is a
  2 KB-aligned Sony header over a plain **MPEG-2 program stream** — not AVC,
  which is what the row had guessed — and `file length == 0x800 * header
  sectors + 2048 * packs` on all 46. Every one is 1280x720 at 29.97 fps,
  BT.709, one elementary stream at `0xE0`. **There is no audio**: all
  1,778,690 PES packets on the disc are video, system header, private stream 2
  or padding, and no audio stream id appears anywhere, so the cutscene
  soundtrack is played by the game beside the film rather than inside it.
  ffmpeg reads them once told twice — `-f mpeg` because the extension collides
  with Netpbm's, and `-skip_initial_bytes 2048`.

- **The sound banks open, and every sample on the disc has a name.** See
  [`format_awb.md`](format_awb.md) and `awb.py`. **274 banks, 7,756 waveforms,
  12 hours 18 minutes, 0 unreadable.**
  - **the archive was hiding in a column.** `cpk.py` has opened `.acb` since
    session 9; what nobody had opened is `AwbFile`, which is not a pointer but
    a whole `AFS2` archive carried inside the `@UTF` row;
  - **the offset width is declared and both widths occur** — `fas1.acb` uses
    two bytes and `b09/se.acb` four. Assuming either produces empty entries
    for half the disc and no error, which is how the first pass lost 1,302
    waveforms. The identity that catches it is that the last offset is the
    length of the archive;
  - **`header size + frames * frame size == the entry length` on all 7,659
    HCA**, and **`ciph` is 0 on every one of them.** Encryption was the one
    thing that could have made this unreachable, and it is not used;
  - **every waveform is reached by a cue.** A cue names a synth or a sequence,
    a synth names waveforms and other synths, a sequence names tracks whose
    command stream carries the same reference under **opcode 2000**. Recursing
    through both, 7,756 of 7,756 waveforms get a name, and 20,955 of the
    20,964 reference items land inside the table they name;
  - **the chain closes end to end.** `mht361at_l` frame 4 says `7ff9(250, 14)`,
    bank 250 is `job.cpk/ht/se.acb`, cue 14 is `DRAW_L`, and `DRAW_L` is
    waveform 16, 19 frames of 24 kHz mono. Disc-wide **7,524 of the 7,608
    sound references in the `.mkc` files reach a waveform that exists**;
  - **7,755 of 7,756 decode through ffmpeg**, which reads HCA and ADX. The
    7,756th is a lone Sony `VAGp` named `dummy_Enc_24000_`, and `vag_pcm()`
    decodes it here in forty lines because ffmpeg will not demux a bare one;
  - three shapes rather than one: 273 banks carry `AFS2`, `bgm.acb` streams
    its 439 tracks from the 1.2 GB `bgm.awb` beside it, and `en/vprev.acb`
    carries a `CPK ` with an `ITOC` — which `cpk.py` reads unchanged.

- **The last two unresolved banks turn out to be stages**, and with them the
  cue side of [`.mkc`](format_mkc.md) closes completely. 1140 and 1170 fit no
  rule the other banks follow; what places them is **where their motion sets
  live** — `treasure_big` under `stage.cpk/170_12_01/`, `bird_a` and
  `recycle_box` under `stage.cpk/140_*`. The rule is `1000 + the stage group`,
  and read that way `treasure_big` fires `BIG_TREASURE`, `bird_a` fires
  `BIRD_FLUP_1` and `BIRD_SINGING`, `recycle_box` fires
  `BILLIONAIRE_POT_MOVE`, and the five NPCs that share bank 1140 fire cues
  named after themselves — `MINA_STEP_1`, `IRIEY_STEP`, `FORTE_LANDING`,
  `UNDEADKAFLA_DANCE`, and `n03`'s single unique motion playing `HAIRCUT_M`
  ten times, `HAIRCUT_L` once and `HAIRCUT_S` three times, which is a haircut.
  The NPCs have no bank of their own because they only ever stand in the town,
  and the town is stage 140.

  **All 7,608 sound references in the 2,690 `.mkc` now name a cue that
  exists, and 7,592 of them reach a waveform.** The 16 that do not are
  complete as an account rather than a gap: they name twelve cues — `LOKI_DIE`,
  `HRSV_V_WAIT`, `DOMOVOI_AT4` among them — whose synth carries no items at
  all. The bank declares the name and puts nothing behind it.

- **Phase 2 is closed.** Every container the disc ships is read. What is left
  is columns and opcodes: the `ELBN` records, the `ECH` column names, thirty
  `.anmcmd` opcodes and ten of `.mkc`'s.

## Session 14 (part two) — 2026-08-23

- **Milestone 1 reached: "the numbers are real".** See
  [`milestone_numbers.md`](milestone_numbers.md) and the new
  [`engine/`](../engine) — `world.py`, `actor.py`, `run.py`, the first code in
  this repository that is not a reader. A capsule with `acc = 0.035`,
  `run_sp = 0.17`, `rot_y_acc = 8`, `rot_y_spd = 32` and `col_r = 0.5` crosses
  `010_01_01` from `appear01` to `jump_010_01_02` in **405 frames — 13.5
  seconds — with 0 of 405 frames off the collision mesh.** Findings worth
  carrying:
  - **the heading convention is settled by the level, not by a field.** The
    spawn marker's Y rotation points at the stage's only exit to within 12.8
    degrees, so a heading of zero faces `+Z`. Under the other convention the
    player spawns facing the wall behind them. Nothing on the disc declares
    this and no amount of further reading would have;
  - **`hta.bin` and `<stage>.col` agree to a centimetre**, and nobody had put
    them in the same coordinate frame because until something has to stand up
    there is no reason to. Over 155 stages: `obj` markers 772, median 1.0 cm,
    none off the mesh; `appear` 660, median 1.8 cm, one off the mesh.
    `emgen_pos` is the loose one at 57 cm, which is a fact about what a
    generator is rather than a failure;
  - **a `borderline` is a closed loop**, open since session 8. On `010_01_01`
    `chara_line01` ends where `chara_line02` begins and vice versa — two
    polylines, one loop. Disc-wide, **105 of 145 stages have every fence
    endpoint shared by exactly two polyline ends**; 20 branch, which is a
    fence with an island in it;
  - **`rot_y_acc` rescues a number `units.md` had worried about.** That
    document estimated a 180-degree turn at 0.19 s from `rot_y_spd` alone and
    said it was below the threshold at which a turn reads as a turn. Integrate
    the acceleration properly and it is 0.32 s. A table cannot show that; a
    loop can;
  - **`col_r = 0.5` is what makes the corridor passable.** The first attempt
    stopped the body dead at the fence and it stuck in the first concave
    corner. Pushing the capsule centre out to exactly `col_r` from the fence
    yields sliding for free, and the same body then runs the whole 65 metres
    of wall without catching once. The parameter earned its place by being
    needed;
  - **and then every other stage.** `run.py sweep` spawns the same capsule on
    every stage that has a spawn, an exit and a fence: **135 stages walked,
    127 of them with the body on legal ground for every frame**, 126 reaching
    the exit while steering straight at it. Of the 62 that are a real crossing
    the median takes **18.8 seconds** and the body averages **5.05 m/s against
    5.10 flat out** — which says the fence contact and the acceleration ramp
    cost almost nothing, and that a field in this game is about twenty seconds
    wide. The eight that leave the mesh walk into a hole in it, because a
    straight line at the exit does not know the world has pits;
  - **the check caught the engine lying, which is the point of having one.**
    The first version reported 135 of 135 clean — because when there was no
    ground within reach it snapped to whatever ground it could find. Printing
    *the largest vertical move in any single frame* exposed a 4-metre teleport
    immediately. Made to fall properly instead, the honest figure is 127, and
    the largest vertical move became **8.000 m on `150_04_02` — which is
    `fall_spd_max` exactly**;
  - **`fall_spd_max` is settled, and it took falling out of the world.**
    [`units.md`](units.md) had it open as "a clamp that never fires or it is
    not a speed". It is a speed: a body that walks off the mesh accelerates at
    `fall_gravity_y` for `8 / 0.035 = 229` frames and then stops. Seven and a
    half seconds of unobstructed fall — unreachable in play, which is what a
    guard is;
  - the seam between read and chosen is marked in the code rather than
    smoothed over: deceleration, turn braking, the stick and the response to a
    wall are the engine's four choices, and every value they use is the
    disc's.

## Session 14 (part one) — 2026-08-23

- **`.PTP` opens, and the effect turns out to have a two-part address.** See
  [`format_ptp.md`](format_ptp.md) and `ptp.py`. **70 files, three of them zero
  bytes; 67 read, 1,108 `PTB` blocks, 2,002 resources, 4,451 resource
  references, 0 unreadable**, sixteen identities closing on every file.
  Findings worth carrying:
  - **the header holds five tables, not one.** Six sessions of notes had this
    down as "a 16-byte header and an 84-entry sparse index at `0x40`". It is a
    block directory, a resource directory, a size array for each, and a `u16`
    reference list, and each ends exactly where the next begins — four
    equations that fix all five and leave nothing unaccounted for;
  - **the sizes are little-endian** in an otherwise big-endian file, which is
    why they read as nonsense for as long as they were read the other way. The
    check that says the reading is right is that a size of zero and an offset
    of zero always occur together, and that the blocks tile the file;
  - **the container and the block agree on the count.** A `PTB` names its
    textures in the clear and the container indexes the same textures through
    the reference list, and **1,041 of 1,041 non-final blocks name exactly as
    many distinct files as they reference.** Two tools, the effect authoring
    tool and the packer, never disagreeing;
  - **the disc declares the addressing in a class definition.** A stage script
    carries `class EffData { _hta_name; _eff_cate; _eff_id; ... }` and calls
    `effStart(_eff_cate, _eff_id)`. So an effect is a **pair**, and `_eff_id`
    is the slot number. `EffData('ef_fire01', 1, 8, ...)` on stage `050`
    resolves to slot 8 of that stage's own bank, which is one of the only two
    blocks in it naming `anm_ef_M_vlcn001.txx` — a volcano, at a marker called
    `ef_fire01`. **Fourth instance of the same lesson**, after `ELBN`'s
    parameter names, `.psq`'s stream tag and the AI's term dispatch: the
    answer was written out, in a file already being read;
  - **category 0 is `misc.PTP` and category 1 is the actor's own file**, and
    the proof is arithmetic rather than plausible: `eff_vari_tbl` in eighteen
    monsters' `objbin.bin` is a list of these pairs, and **all 104 pairs in all
    18 files land on a slot that exists** under that reading. `ptp.py refs`
    prints it. Category 2, which only the six classes' `eff_hitlevel_tbl` uses,
    reaches ids of 252 and stays open;
  - **an inference from session 9 was wrong, and the data said so all along.**
    Opcode 10's effect id was called *global* because unrelated monsters share
    values. They share them because **the number is derived from the motion**:
    of 385 distinct (animation, effect id) pairs, 66 are exactly `10000 + the
    motion id` and 67 more are `(1000 + the motion id) * 10 + a variant`.
    Monsters share motion numbering, so they collide without sharing an effect.
    The correction is in [`format_anmcmd.md`](format_anmcmd.md);
  - **and that number resolves nowhere on the disc.** All 32,600 leaves were
    scanned for the 187 ids in use, as aligned big-endian `u32` and `u16`;
    nothing but float noise. It is not in the `.PTP` in any width or byte
    order either. So the bridge is a static table in the SELF — the first thing
    on the list that actually needs Phase 3, and a cosmetic one.
- Scouted the two formats that are left, so that neither starts cold next
  time. **`.mkc`**: 2,690 files, all of even length, all ending on `0xffff`,
  256 of them nothing but that; **2,304 of the 2,690 share a stem with a
  `CNOM`** and sit in the same `.pac`, while only 3 share one with an
  `.anmcmd`, so it is a second per-motion sidecar rather than a variant of the
  first. Above `0x0800` only eleven distinct values occur in the whole corpus,
  `0x7ff9` leading at 6,251 uses, and file lengths spread over all four even
  residues mod 8 — so the records are variable-length and the `.anmcmd` method
  applies. **The movies**: 46 `.pam`, and they are not in `extract/` at all —
  `iso.py sets` declares `movie` as its own 3.4 GB set and it has never been
  pulled, which is the real cost of that item.

## Session 13 — 2026-08-22

- **The mercenary AI opens, and it names the attack buttons.** See
  [`format_merc.md`](format_merc.md) and `merc.py`. **12 classes, 454
  probability tables, 350 command lists, 1,549 command steps, 166 target
  records, 0 unreadable.** Findings worth carrying:
  - **the container had already declared the structure.** All four `.bin` in a
    mercenary `.pac` are `ELBN`, which session 8 opened, and `ELBN` names its
    own entries: `prt00..prtNN` beside `select_prt`, `act_cmd_00..NN` beside
    `act_cmd_data`. Two sessions of TODO listed these as unread files; the
    names were in them the whole time. Third instance of the same lesson in
    four sessions;
  - **the script indexes the table and the arithmetic proves it.** On all 12
    classes and both selector functions - 24 comparisons - the values
    `consider_action.cnut` returns lie inside the table's `prt` indices and
    `max(return)` equals the last index exactly. All 454 `prt` are closed by
    `(0xffffffff, 0)` and **all 454 sum to exactly 10000**;
  - **command 14 is the weak attack button and 15 the strong one.**
    `job.cpk` names a combo motion by the press string that reaches it -
    `sw325at_ssssl`, `sw355at_sllll`, `sw361at_l` - and a run of 14s and 15s
    in an `act_cmd` is that string. **168 of the 188 runs name a motion the
    same class ships**, and no run exceeds five presses, the depth of the
    combo tree. The 20 that miss are the Mage and the Hammersmith, whose trees
    are shallower than the tables written for them. So an `act_cmd` is a list
    of *inputs*, not of animations;
  - **the two AI systems meet at the action id.** `getNearestBossAction()` and
    `getTargetActId()` are compared against 21 distinct values across the
    twelve scripts and every one is between 102 and 125, inside the block
    session 12 resolved to the monster's `at*` motions. A mercenary holds off
    because the boss has started action 108;
  - **the same shared-table arrangement, reached independently**: within a job
    the male and female share their tables, and in five jobs of six their
    script too - `swm` and `sww` decompile identically but for one source line
    number. The Cleric is the exception;
  - the whole host interface is **19 predicates and `print`**, all already
    inside the disc-wide 289, and `getHpRate` is the one name both AI systems
    call - with no argument from the monsters and one from the mercenaries.

## Session 12 — 2026-08-22

- **`ai.pac` closes.** See [`format_ai.md`](format_ai.md) and `ai.py`. The
  vocabulary, the flags, the six `.par` and the join to the animation layer.
  **66 of the 76 condition terms named, 27,862 of the 29,100 instructions;
  438 `.par` read, 0 unreadable, every sentinel exact; 1,109 of 1,423 action
  ids resolving to a named motion.** Findings worth carrying:
  - **the term table was a function in the file, not a puzzle.**
    `check_converted_xml_term(term, param, cond)` in the six `.cnut` is a
    switch on exactly the ids the binary tables use, and it names the host
    call for every one. It sits at `.ppcut` line 1174 in all six, so it is a
    shared include. Its name says what it is: the AI was authored as XML,
    converted to numeric terms, and this is the reference implementation of
    the converted form. That is the third time this project has found the
    answer written out in the clear — after `ELBN`'s parameter names and
    `.psq`'s `SQ_BYTECODE_STREAM_TAG` — and the shape is identical: read the
    file rather than reason about it;
  - **the shipped tables are newer than the scripts that document them.**
    `b19_00` carries both, and its `SelectScript.dat` uses term 1066 while its
    own dispatch stops at 1063 — but its `active_script` calls
    `checkB19Term(1066, 0)` beside a debug line, so even the term the dispatch
    forgot has a name. That asymmetry is the honest explanation for the ten
    that stay open, and it is worth remembering the next time an oracle and its
    data disagree: the oracle can be the older artefact;
  - **two flags read off the data alone.** `0x2000` opens a rule: of the
    22,428 instructions without `0x1000`, exactly the 22 that carry `0x2000`
    have a non-zero `a`, and all 22 are valid group ids. `0x4000` is an OR, and
    the proof is by contradiction — the terms in a run are mutually exclusive
    (`angle_at == 217 or == 218`, `range_band == 0 or == 2`), so an AND reading
    would make 421 instructions dead;
  - **an action id names a motion, and the constant is 401.** A `.CNOM` names
    itself — `z11.pac/z11501at1.CNOM` — and action 100 is motion 501 `at1`,
    101 is 502 `at2`, in exact order. The `0xx` block is `+200` and lands on
    `wait_*`, the `2xx` block is `+301` and lands on the same `at*`. This is
    the last gap the previous TODO named, and it closes the loop *decide →
    pick → play*;
  - **the `.par` are six kinds, four of them arrays with an exact sentinel**
    — `0x7FFFFFFF`, `0x00000000`, `0x00000000`, `0xFFFFFFFF` on 308 files with
    no exceptions. `_act.par` gives every action a range and a facing angle,
    and the OrcKing's own debug print calls it `ct_act`, which is what ties it
    to the `act_time` terms. `<name>.par` is addressed `0x2000 + 0x10*k`, and
    on 74 of the 82 monsters the slots are one per 1xx action in the same
    monster's `_act.par`;
  - **the giants share a motion set**: `z18.pac` ships `z19*.CNOM`, so a
    motion has to be indexed under the directory as well as the filename, or
    three monsters look motionless.

## Session 11 — 2026-08-22

- **The monster AI opens.** See [`format_ai.md`](format_ai.md) and `ai.py`.
  **84 `ProbList.dat` (3,269 groups, 19,707 items), 144 decision scripts
  (29,100 instructions, 6,528 rules), 0 unreadable**, every file consumed to
  the byte. Findings worth carrying:
  - **the six `.cnut` are the oracle and they work.** `monster.cpk/b01_00`
    ships its AI twice - as `ProbList.dat` + `SelectScript.dat` and as
    `AI_B01_OrcKing.cnut` - so every reading here is checked instruction
    against decompiled line rather than against plausibility;
  - **`ProbList.dat` is a weighted action table**: a `(group id, first item)`
    index and `(action id, weight, 0)` items. The file ends exactly at
    `0x10 + 4*groups + 4*items` on all 84, and **the script's weights are the
    table's multiplied by a hundred** - `prt_select(rand, 1, 8500, 4, 1500)`
    against `[(1, 85), (4, 15)]`. Of the OrcKing's 31 `prt_N`, 26 have a group
    and **all 26 carry the same action ids in the same order**;
  - **the decision scripts are six-byte instructions**, `u16 a, u16 b, u16 op`,
    where `op`'s low twelve bits are a condition term, `0x1000` starts a rule
    and puts its action in `a`, and `0x8000` takes the term's negative branch.
    All 144 divide by three and all 144 end with one all-zero instruction;
  - **ten terms are proven** - HP rate, range, angry, last action, damage
    count, other-zako count, action successes, AI type, an action timer and a
    probability - and they cover 19,435 of the 29,100 instructions. The range
    is in hundredths of a unit, the same convention the stage `borderline`
    uses;
  - **the OrcKing's first 56 rules pick the same group as its script's, in the
    same order.** The first that does not is rule 56, where the script picks
    `prt_140`, one of five three-digit groups the table does not carry;
  - **the tables are shared between difficulty variants and the scripts are
    not**: `b18_00` and `b18_01` ship byte-identical `ProbList.dat` and
    different `.cnut`. That is why the other five monsters with both diverge
    early, and it is a fact about how the game was built rather than a failure
    of the reading;
  - a monster now reads as what it is - `AI_Z11_Domovoi_1` tries fourteen rules
    in order, laddering on range, and falls through to an unconditional group.

## Session 10 — 2026-08-22

- **`.psq` is Squirrel 2.2 bytecode.** See [`format_psq.md`](format_psq.md) and
  `psq.py`. **3,011 files, 11,232 functions, 314,930 instructions, 55,368
  literals, 0 unreadable**, every file consumed to the byte. Findings worth
  carrying:
  - **the six bytes that identify it were on the first line all along.**
    `0xFAFA` is `SQ_BYTECODE_STREAM_TAG` and `SQIR`, `PART`, `TAIL` are
    `SQ_CLOSURESTREAM_HEAD`, `_PART` and `_TAIL`. Nine sessions of TODO had
    `PART` down as a chunk with a payload; it is a separator between the fields
    of one record, which is why `PART` sometimes follows `PART` with nothing in
    between. The word `0x08000010` that introduces every string is `OT_STRING`;
  - **the debug tables shipped.** Every function names its `.ppcut` source
    file, every instruction has a source line, and `localvarinfos` gives every
    local a name and a live range — so a `.psq` decompiles with the authors'
    own variable names. `psq.py src` prints statements; control flow stays as
    labels and `goto` rather than being guessed at;
  - **the version is settled by the code, not the header, three ways**: the
    highest opcode on the disc is `0x3C`, which is the last entry of Squirrel
    2.2's enum; `_OP_ARITH`'s `_arg3` is the operator as ASCII — 4,423 `+`,
    674 `*`, 295 `-`, 42 `/` and nothing else; and `CLAMP(v, l, h)` in
    `common.psq` decodes to its own three-line source, with `CMP_L` and `CMP_G`
    the right way round. Under a Squirrel 3.x table the byte that ends all
    11,232 functions reads as `_OP_MUL`;
  - **`_varparams` is 1 on exactly the 19 functions that use `_OP_VARGC`**,
    which is what says the trailer is `u32 + u8 + u8` and not `u32 + u16`;
  - **all 55,368 literals are strings** — Squirrel puts numbers in the
    instruction — and **1,578 are Japanese, all valid UTF-8**, not Shift-JIS.
    The developer comments are in the clear: `★★ 図鑑用のフラグ立てる ★★`
    sits next to `cfSetGlobalFlag(1368, 1)`.
- **The engine's script interface is a closed list.** `psq.py api`: 453 names
  are called on the root table, 164 are defined by a `.psq`, and **289 are
  not**. Those 289 — 119 of them beginning `cf` — are the host functions a
  reimplementation has to provide, with a call count and an arity histogram
  each.
- **The names name things.** `psq.py xref` joins the script layer to the stage
  layer [session 8](format_stage.md) read:
  - `cfSetEnableHitArea` — **1,457 of 1,459** name an `ATIH` marker of their own
    stage;
  - `cfMapJump` — **147 of 147** name a stage that exists and an arrival marker
    inside it;
  - `cfSetEnableBorderline` — **679 of 686** name a `borderline` polyline;
  - **`trigger.trg`'s `callQuestScript("sfEnmGenStart()")` resolves 144 times
    of 147** against a function the same stage's own `.psq` defines. That is
    the question last session's TODO asked, closed;
  - the ones that miss resolve one table further out: `enemy_gen.bin` in the
    quest's `.pac` pairs `emgen_pos01` with the `emgen01` the script says, and
    `piecelock.bin` names the `pl_*` the script locks with.
- **19 `.cnut` files are the same format under Squirrel's own extension**, and
  nothing was looking for them because nothing was matching on the magic:
  **six bosses and twelve mercenary classes carry their AI as script.**
  `AI_B19_LordOfDeath.cnut` is the largest script on the disc — 123 functions,
  7,721 instructions — and `active_script()` reads HP rate, target range,
  damage count, anger, six timers, last action and target angle, then picks
  from `prt_N` weighted tables through a vararg `prt_select(rand, id, weight,
  …)` that biases away from repeating the last action. **78 native functions
  are called only from the `.cnut`** and every one is a question about the
  fight. The AI holds no state at all.
- **The hit record's `+0x48` is a CRI Atom cue id**, and `common.acb` names it.
  See [`format_anmcmd.md`](format_anmcmd.md); `anmcmd.py hits` prints the cue.
  An `.acb` is an `@UTF` table, so [`cpk.py`](../tools/cpk.py) already read it
  and no new format was needed. Findings worth carrying:
  - **26 distinct cue ids are used across the 6,193 hit records and 25 of them
    name a cue** in `sound.cpk/common.acb`. The exception is 347, four times,
    in one monster's `z24_01_511`. 941 records carry zero, and **zero is a
    sentinel rather than cue 0**, because cue 0 is `SYSTEM_CURSOR`, a menu blip
    no sword swing would play;
  - **the names are the damage model**: `HIT_DMG`, `SLASH_DMG`, `STRIKE_DMG`,
    `FLAME_DMG`, `STORM_DMG`, each with an `S`/`M`/`L`/`LL` size. So a hit
    declares its family and its size in one field, and the sound is not a
    separate decision from the damage;
  - **that corroborates `+0x35` from a second direction.** Session 9 read the
    byte as the strength of the hit from two small series inside single files.
    Group all 5,252 records by their cue's size suffix instead and the median
    rises with the suffix in **all five families** — `STRIKE` runs 4, 55, 100,
    100. A sound designer and an animator agreeing about which hits are big;
  - session 9 called the space "1091 to 1106". It is 26 values over 260 to
    1108, and the low band is `FIRE_EXPLOSION_S/L`, `BURNING_ATTACK`,
    `SAND_GET` — a handful of uses each.
- Opened `.PTP` far enough to see it is `PTCP`, an index of `PTB` blocks naming
  their own textures, and far enough to know the effect id is not its index.
  That is now TODO item 2.

- Rewrote [`STRATEGY.md`](STRATEGY.md), which had said for nine sessions that
  this disc had no scripting layer.

## Session 9 — 2026-08-22

- **The `.anmcmd` hit record.** See [`format_anmcmd.md`](format_anmcmd.md) and
  `anmcmd.py hits` / `bones`. Findings worth carrying:
  - **opcode 27's payload is 116 bytes, which is one of opcode 0's records.**
    The two are a single and a list of the same thing, 6,193 of them, and that
    is the observation the rest hangs off. Opcode 0's head declares the count
    and it equals `(size - 12) / 116` on all 2,508 — two fields written by
    different parts of an exporter, never disagreeing;
  - **opcode 0 declares the set, opcode 27 updates one slot of it**: on all 185
    files carrying both, the first 0 precedes the first 27;
  - **the record names a bone and all 4,768 references resolve.** The field
    addresses two spaces at once and the value says which, because **locator
    ids start at 1000 and no model has more than 149 nodes** — so there is no
    ambiguous case. Players use locator ids (433 of 436), monsters node indices
    (3,983 of 4,332);
  - **the names settle what the record is**: `node_head` 429, `node_r_weapon`
    266, `node_r_hand` 236, `node_jaw` 201, `node_r_toe` 76, `b19_00_shield`
    72. A monster's hitboxes are on its jaw, its head, its hands and its
    weapon. `b01_00_507` puts one on the left hand at frame 46 and one on the
    right at 54 — a one-two — and the sword's charged swing hangs its hit on
    `locator 4000`, `node_r_weapon`;
  - **the byte at `+0x35` scales with the strength of the hit**, twice over: it
    decays 95 → 45 → 15 across the three frames of `sw383cge_l3` as the capsule
    shrinks 2.70 → 1.50, and it rises 50 → 70 → 95 across the sword's three
    charge levels as the capsule grows 1.12 → 2.70;
  - **the same locator table serves hit and hurt.** `S4` is what the
    `collision_*.CTXT` capsules bind through, and it is what this binds
    through. One door.
- **Twenty-two opcodes correlated by position**, which is the only method
  available without an oracle:
  - **13 opens a window and 5 closes it** — both payloadless, both once per
    file, 13 before 5 on 356 of 366;
  - **24, 50, 41, 52 and 39 are exclusive terminators**, each once per file at
    the last frame as the last command, and a file carrying one carries no
    other;
  - **10 emits and never appears in what it emits**: not one of the 229
    `*bullet*` files carries it, while 197 of those carry a hit record instead.
    The bow carries it most, and the fully charged shot issues it ten times;
  - 17 is a boolean; 8, 9, 11, 14 are the same field almost always set; 1, 2
    and 35 carry a small index; 22 carries a scale and three angles in degrees;
    40 and 53 are frame-0 setup, 53 on all 231 of its uses.
- Searched all 4,941 `ECH` tables for the two id spaces the record points at —
  1091..1106 and 10200..12130 — and **none of them occurs anywhere**, so they
  belong to the sound banks or the effects. That is now TODO item 2.

## Session 8 — 2026-08-22

- **`.map` is the minimap, not the world layout.** All 137 begin `CTEX` —
  256x256, 8-bit paletted, one level — and decoding one draws the silhouette of
  its stage. Six sessions of TODO had it down as "the obvious next file, and
  the one `CCLS` points at", on the reasoning that 137 against 155 stages is
  close enough to be per-stage. The count was right and the conclusion was
  wrong, and reading the first four bytes ended it in ten minutes. Documented
  in [`format_ctex.md`](format_ctex.md), which already read them.
- `tools/stage.py` — the actual world layout, three files along in the same
  directory. **163 stages, 5,934 markers, 1,455 polylines, 508 triggers, 0
  unreadable**, every identity closing. See
  [`format_stage.md`](format_stage.md). Findings worth carrying:
  - **`hta.bin` is `ATIH`, a table of named markers**, 40 bytes each: name
    pointer, three 16-bit Euler angles, a position and three half-extents. The
    name pool sits at `align16(0x10 + 40 * count)` and that round-up is the
    whole arithmetic — 88 of the 163 have an odd count and are eight bytes
    short without it;
  - **the collision proves the record.** Drop every `appear*` marker onto its
    own stage's `.col` and 660 of 661 land on a triangle with a **median height
    difference of 0.000**, p10 to p90 inside a fifth of a unit. Any wrong
    reading of a 40-byte record puts plausible floats in the position slot;
    only the right one puts them on the floor;
  - **the half-extents separate points from volumes**, and the split is
    self-checking: all 534 volumes are `pl_q`, `jump_*`, `lock_start` or
    `SE_area`, and not one is an `emgen_pos` or an `ef_*`. The test has to be a
    loose one — a rotated marker writes 0.4999999 twice and 0.5 once;
  - **rotations are 16-bit binary angles, 65536 to the turn.** 3,192 of the
    3,394 non-zero ones are whole degrees on that scale against 2,271 on the
    half-turn scale, and the odd degrees are what discriminate;
  - **`borderline` coordinates are hundredths of a unit**, and nothing says so.
    At /100 the median `chara_line` vertex is **0.75 units** from the nearest
    boundary edge of the stage's collision mesh; at /128 it is 4.2, at /64
    10.2, at /32 57. The identity is the one `CCLS` already established — that
    the single-use edges are the outline — so the fence and the outline are the
    same thing written twice;
  - **`trigger.trg` is script source in the clear**, and its name field is an
    `ATIH` marker: 507 of 508 resolve. `cfMapJump("010_01_02", "appear03");`
    spells out the destination stage and the arrival marker, so a map
    transition is fully described by two strings. `sfAreaVolumeCtrl` settles
    the event kinds — all 21 kind-2 triggers pass 0 and all 21 kind-0/1 pass 1
    — so kind 2 is leave and 0/1 are enter.
- Proved by drawing `010_01_01` and `030_03_01` as floor plans: the collision
  ground, the `chara_line` fence tracing its boundary, four `appear` markers in
  diamond formation at the mouth, a `jump_` doorway at the far end, and twenty
  `emgen_pos` between them. The silhouette is the same shape as the `.map`
  minimap, which confirms both findings at once.
- `tools/elbn.py` — `ELBN`, off the deferred list. **707 files, 3,983 entries,
  318 distinct parameter names, 13,437 relocations, 0 unreadable**, every check
  closing on the first reading. See [`format_elbn.md`](format_elbn.md).
  Findings worth carrying:
  - **it is the format that names its own contents** — a sorted table of
    `(name, offset, size)`, so every value arrives with the identifier the
    engine's C++ used. It had been deferred five times as "unidentified, no
    consumer waiting", and it is the single largest declaration of engine
    vocabulary on the disc;
  - **the same shell and a `POF0` tail**, the fifth format in that family, so
    the relocation trick from `CMDL` said which words are pointers and nothing
    had to be guessed;
  - **`mot_param.bin` is the motion table.** `motionDataHeader` is
    `(count, ptr, stride)` and `_dataA` is `count * stride` bytes, on all 19;
    every motion id in a player class's table is a `CNOM` in the same `.pac`,
    87 of 87 for `fas`, 115 of 115 for `fmg`, with nothing left over on either
    side. `fas` row 211 is `fas211walk`;
  - **packed RGBA is the trap again.** A stage's lights carry colour as a word,
    and `0x46d7b4ff` reads as a perfectly plausible 27610.5. `CMTM` produced
    the same error last session at -4e37, where it was obvious. `dump` now
    prints the RGBA reading of any word ending in `ff` beside whatever it
    inferred;
  - **a name is not a meaning**: `region_data` lives in
    `monster.cpk/<monster>/objbin.bin`, one per monster, so it is not a stage
    spawn region however much it sounds like one.
- **The frame rate, and the metre.** See [`units.md`](units.md) and
  `cmdl.py gait`. Findings worth carrying:
  - **the twelve player models are 1.55 to 1.88 units tall with the sole of
    the foot at `z = 0.000`**, and their arm span is 1.512, so a unit is a
    metre and the characters are 1:1 humans;
  - **the planted foot of a locomotion cycle slides backwards at exactly the
    parameter's speed.** Walk 0.0492 against `walk_sp` 0.05, run **0.1699
    against `run_sp` 0.17**, dash 0.2790 against `fast_sp` 0.28, on all twelve
    player models, with nothing fitted. So `_sp` is metres per animation frame
    and the animations are authored against the JSON;
  - **that closes the loophole that mattered.** Had the art been on thirties
    and the tick on sixties, the foot would slide by a factor of two. The
    animation frame and the simulation frame are the same frame;
  - **a frame is 1/30 s.** The run cycle is 21 frames: at 30 fps that is
    5.09 m/s at 171 steps a minute with a 1.78 m step, which is a real
    runner's gait in all three numbers at once; at 60 fps it is 10.19 m/s at
    **343 steps a minute**, a cadence no human has ever run. `fall_gravity_y`
    agrees independently — 3.2 times Earth at 30 fps, 12.8 at 60;
  - what this does *not* say is that the game renders at 30. Nothing on the
    disc speaks about the display, and a 60 Hz presentation over a 30 Hz tick
    is exactly what a Vita game's port would look like.
- Looked for a declared frame rate in `game_common_param.bin` and `latency.bin`
  and found none — `latency.bin` is network ping thresholds in milliseconds.

## Session 7 — 2026-08-22

- `tools/cmtm.py` — material animation. **91 files, 231 tracks, 254 channels,
  1,388 keys, 0 unreadable.** It is `CNOM` with one magic word changed: same
  shell, same header, same track, channel and key layout, so `Cmtm` subclasses
  `Cnom` and overrides only the magic and how a value is read. What differs
  follows from what it animates — **a track names a material, not a bone** (227
  of 231 are `S6` names), a track carries one to three channels rather than
  always three, and every key is four bytes. Two of the five channel kinds are
  **packed RGBA, not floats**; read as floats they come out around -4e37, which
  is how you notice.
- `tools/anmcmd.py` — the animation event lists. **2,053 files, 6,802 blocks,
  10,175 commands, 0 unreadable**, every check closing. See
  [`format_anmcmd.md`](format_anmcmd.md). Findings worth carrying:
  - **three nested tables and nothing else** — no magic, no version, no `POF0`.
    A block table keyed by frame, a command count, and commands that declare
    their own size;
  - **the commands fill their block exactly**, 6,802 of 6,802, which is the
    only thing in the file that confirms the reading — nothing else declares a
    length;
  - **51 of the 52 opcodes have one fixed size**. The exception is opcode 0,
    the commonest, always `12 + 116 * n`, so it is a list of records;
  - **the name is the link to the motion**: class prefix plus a three-digit
    motion id. 1,499 of 2,053 resolve to a `CNOM`, and 1,473 of those have
    every command frame inside the motion's length — which is what proves
    these numbers are `CNOM` frames;
  - opcodes 1000, 1002, 1004 and 10000 look like locator ids and are not: 1002
    and 1004 are locator ids on no model on the disc. A minute of checking
    against a plausible wrong answer.
- **Skinning.** The mesh follows the skeleton. See [the skinning section of
  `format_cmdl.md`](format_cmdl.md). Findings worth carrying:
  - **the four `u8` at the tail of a vertex are not node indices.** They index
    a per-mesh **bone palette** that `+0x30` of the mesh descriptor points at,
    80 bytes an entry. Read as node indices they are every one in range and
    every one wrong, which is this disc's favourite shape of error;
  - **the bone is a name**, in a table at the tail of `S9`, so a model binds to
    its own skeleton the way `CNOM` already bound to it;
  - **the matrix is the inverse bind pose, transposed**, and it satisfies
    `matrix * Rx(90) * bind(node) == identity` on 872 of the 931 skinned
    meshes. That `Rx(90)` is the up-axis question answered — character vertex
    buffers are Z-up, the skeleton is Y-up, and no field anywhere says so;
  - **the bind that closes it leaves the node scale out.** Keeping the scale
    closes only 800 of 931. So a node scale is a runtime one, over the top of
    the skinning: `z20_01` carries 1.5 on `top` and 2/3 on each weapon node to
    undo it, which is a base monster wearing a size;
  - a **rigid mesh is a one-bone skin** on the node its draw call names, so
    both kinds land in the same space and draw together.
- Proved on `fas2` under `fas211walk`: a textured walk cycle in profile,
  creasing at hip, knee and elbow, and a clean T-pose at rest — the guard
  against the failure that does not crash.
- **`S4` is the locator table**, `(id, node)` pairs, and it identifies
  **`.CTXT`**: 1,151 plain-text files named after a locator id and opening by
  repeating it, on all 1,151. 961 are `collision_*` hit capsules, 190 are
  spring parameters for hair and cloth. **Character collision was never in
  `CCLS`** — it is here, in the clear, and needs no reader.
- `tools/ccls.py` — the stage collision. **155 files, 107,343 triangles, 0
  unreadable**, every check closing. See [`format_ccls.md`](format_ccls.md).
  Findings worth carrying:
  - **the array starts at `0x24`, not `0x30`** — twelve bytes inside what looks
    like the header. Both readings divide the payload exactly and both make the
    normal perpendicular to `v1 - v0` on every record, because a plane normal
    is perpendicular to *any* edge in its plane. Only the cross product tells
    them apart, and it does so 107,338 times out of 107,343;
  - **it is a ground mesh, not a hull.** 98.4% of triangles face up; 814 in the
    whole game stand vertical;
  - **and it is welded** — 150,236 edges used by two triangles, 21,448 by one,
    31 by more, matching vertices bit for bit with no T-junctions. The
    single-use edges are the outline of every stage, and that outline is what
    fences the player in;
  - **the fifteen trailing words are one bit about the stage**, not a
    per-triangle attribute: 146 stages are entirely 1, 9 are entirely -1, no
    stage mixes them, and the nine are all in the game's first two areas.


## Session 6 — 2026-08-22

- `tools/cnom.py` — the motion format. **3,043 animations, 77,331 tracks,
  231,993 channels, 3,020,726 keys, 0 unreadable**, every check closing on
  every file. See [`format_cnom.md`](format_cnom.md). Findings worth carrying:
  - **the same shell again**, and reading `POF0` first is what made it take an
    hour. Five formats carry a `POF0` tail — `CMDL`, `CNOM`, `CMTM`, `CSCN`,
    `CSCM` — while `CTEX` and `CCLS` have none, which says in one pass which of
    the remaining formats will open the easy way;
  - **every track has exactly three channels** — translation, rotation, scale —
    and value blocks tile 16-aligned while key-time blocks tile 4-aligned, with
    no gap and no overlap on any file;
  - **the sixteen-byte channel is a quaternion and the disc proves it**: all
    77,331 rotation channels have every key unit-length to within a thousandth.
    Four floats could be anything; that test costs a square root and settles
    it;
  - **motions bind to skeletons by name**, not by index. 3,019 of 3,043
    animations have every track name present as a `CMDL` node name; the 61 that
    are not are `*_PIVOT` helpers and scene props;
  - **70% of channels carry one key.** A bone that does not move still gets a
    channel holding a constant, which is why a 24-bone 41-frame walk is 11 kB.
- Proved by posing `fas2.CMDL` with `fas211walk.CNOM`: a walk cycle in profile,
  legs scissoring through contact and passing, arms counter-swinging, and the
  bind pose standing in a T.
- **Skinning reconnaissance** (above): four `u8` weights summing to 255 at the
  head of every skinned vertex, four `u8` bone indices at the tail, on all 931
  meshes and 473,193 vertices with no exception.

## Session 5 — 2026-08-22

- `tools/cmdl.py` — the geometry format. **1,127 models, 15,833 meshes,
  6,127,335 vertices, 5,591,558 triangles, 0 unreadable**, every arithmetic
  check closing on every file. See [`format_cmdl.md`](format_cmdl.md).
  Findings worth carrying:
  - **the tail after the payload is a `POF0` relocation table**, and it lists
    every word in the file that holds a pointer. That is what made the format
    fall open: *these* words are offsets and no others, so nothing had to be
    guessed. 76,423 relocations, all valid. `CTEX`, `CMTM` and probably `CNOM`
    share the shell, so the same trick should work again;
  - its 22-bit delta is **three bytes, not four** — the four-byte reading
    decodes 751 of 1,127 files and walks off the end of the rest;
  - **`S0` is the draw list**: `(node, material, mesh)` triples, every index in
    range on the whole disc. `S7` names the textures and they are `CTEX` names
    sitting in the same `.pac`, so model → material → texture resolves by name
    inside one container;
  - **vertices are already in model space** — the node hierarchy is a skeleton,
    not a placement scheme;
  - every vertex type appears at two strides twelve apart, the wider one being
    the same layout with a normal inserted. That is what identifies the normal
    without guessing, and the position offset is confirmed on all 15,833 meshes
    against each mesh's own declared bounding sphere.
- **A textured render of `monster.cpk/b17_00`** from the draw list, its own
  seven `CTEX` textures sampled through the decoded UVs. First frame.
- The disc names its own monsters: `ai.pac/AI_B17_Loki.par`. See
  [`RECON.md` §7b](RECON.md).

## Session 4 — 2026-08-22

- `tools/ctex.py` — the texture format, solved. **11,536 files, 11,530 closing
  exactly, 0 unreadable, five pixel formats decoded and eyeballed.** See
  [`format_ctex.md`](format_ctex.md). Findings worth carrying:
  - **byte `0x19` is mip levels minus one**, and the chain is stored back to
    back with no padding, no alignment and no pitch — that was the open
    question and it closes the arithmetic;
  - **`0x107` is 8-bit indices with the palette *after* them**, not a 16-bit
    format. Read as 16-bit its size closes for six files out of 832, which is
    exactly the kind of partial agreement that reads as confirmation;
  - **A8R8G8B8 is Morton-swizzled and nothing else is**, and no header field
    says so — the pixel format does. Scoring every non-DXT file for horizontal
    roughness both ways separates 400 from 751 with no ambiguous case;
  - **width comes before height**, which reverses what session 3 recorded.
    Nothing in the size arithmetic notices, because every formula is symmetric
    in the two. 11,530 files passed `check` with the axes swapped.
- `CMDL` reconnaissance, which session 5 built on.
- Removed the relative links to the sister project's tree from the docs; the
  repository is public and that one is not.

## Session 3 — 2026-08-22

- `tools/params.py` — the 89 JSON actor files. **1,069 records, 1,056 distinct
  fields.** See [`params.md`](params.md). Findings worth carrying:
  - the stagger model closes — `stg_p` is strictly ascending in **all 1,068**
    records that carry it, always four thresholds, with three independent
    reaction weights per stage;
  - monster difficulty tiers pair as `(n, n+1)`: +3 `region_lv` in 123 of 168
    pairs, and `hp` **exactly ×1.5** in 138 of them;
  - **173 of 225 fields are identical across all six player classes** — one
    movement model, not six. `guard_*` and `jg_*` exist for exactly `cl` and
    `sw`, the two shield classes;
  - a 66-field shared actor struct plus 609 per-move fields named after the
    monster or the move.
- `tools/ech.py` — a constant column wide enough to be a float now reports what
  it reads as (`0x42700000` is 60.0, the fever duration).
- `CTEX` reconnaissance and [`RECON.md` §6.5](RECON.md).

## Session 2 — 2026-08-22

- `tools/assets.py` — one addressable path per leaf across all container
  layers. **32,727 leaves, 2.0 GB.** Found a fifth layer on the way: `cmp/zlib`
  (3,077 blocks, 282 MB) alongside the `cmp/lzma` already known, both under
  CRILAYLA.
- `tools/ech.py` — the table format. **4,941 tables, 58,534 rows, 0 failures.**
  String pools, default rows, and a type inference pass that reads byte columns
  as well as word columns. See [`format_ech.md`](format_ech.md).
- `tools/rmsg.py` — the text format. **76 files, 25,288 messages, 7,125
  attributes, 0 failures.** Variable-length records; the attributes are RGBA
  colours and scale factors. See [`format_rmsg.md`](format_rmsg.md).
- Verified that `ECH` tables and `TXT` files pair **positionally**, on seven
  independent pairs. The item database reads with names.

## Session 1 — 2026-08-22

- `tools/iso.py` — UDF 2.50 reader ported from the sister project, sets
  redefined, and a **multi-extent index** (the inherited version would have
  written a silently corrupt `sound.cpk`). 109 files, 5.4 GB, manifest
  computed.
- `tools/cpk.py` — CRI CPK: `@UTF` tables, `TOC`/`ITOC`, CRILAYLA. 20
  containers, 2,450 entries, 0 errors.
- `tools/arc.py` — `ARC`: 1,544 of 1,544 consistent, 13,820 entries, 13,798
  blocks each ending on its declared byte.
- `docs/RECON.md`, `docs/STRATEGY.md`, `README.md`, `.gitignore` (BYOA).


