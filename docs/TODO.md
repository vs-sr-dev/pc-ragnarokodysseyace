# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — name the rest of the AI terms, then `.par`

The AI tables are open: `ProbList.dat` and the two decision scripts read, 0
unreadable, checked against the six monsters that also ship their AI as
Squirrel. See [`format_ai.md`](format_ai.md). What is left in `ai.pac` is the
`.par` half and two thirds of the condition vocabulary.

### 1. The 67 unnamed condition terms.

Ten of the 77 are proven and cover 19,435 of the 29,100 instructions. The
commonest unnamed ones are `0x07` (795 uses), `0x15` (719), `0xdc` (661),
`0x6d` (606), `0xd2` (496), `0xd5` (481), `0x12` (479).

**The method is the one that named the ten**: take a monster with both a
`.cnut` and a `SelectScript.dat`, decompile with `psq.py src`, and align rule
by rule — `AI_B01_OrcKing`'s first 56 rules already line up with the table's.
The vocabulary is known from the scripts' own local names (`AIT_TGT_DOWN`,
`AIT_BOSS_TIME`, `AIT_OTHER_BOSS`, six `ACT_TIME` slots and the rest), so this
is matching a known list against a known list, not guessing.

Also open: the `0x2000` and `0x4000` instruction flags, 434 uses between them.

### 2. `.par` — the other half of `ai.pac`. 438 files.

Five or six per monster: `<name>.par`, `_act`, `_cmb`, `_coop`, `_dfa`,
`_prowl`. No magic, records that look 64 bytes wide. `check_term_param` and
`checkRangeParam` are named in the `.cnut` and unread on this side, and the
`_act`/`_cmb`/`_dfa` split matches the modes the decision scripts switch
between.

### 3. Tie an action id to a motion.

A `ProbList` group's items are ids like 1, 4, 100 to 110, 200 to 205, and the
script prints `select_actid:` beside them. `.anmcmd` names a motion by a
three-digit id in its filename and `CNOM` by name, so if an action id resolves
to one of those the AI joins the animation layer, and the last gap between
"the monster decides" and "the monster moves" closes.

### 4. `.PTP` — the effect ids.

Opcode 10's `+0x02` in `.anmcmd` runs 10001 to 39547 and the same values are
used by unrelated monsters, so it is a **global** effect id, not an index into
the per-class file. `.PTP` is `PTCP`: a 16-byte header, an 84-entry sparse
index of `(u32 offset, u16, u16)` at `0x40`, then `PTB` blocks naming their own
assets in the clear — `ef_I_as_hit_zan001.ctex`, `anm_ef_I_fire_tubu001.txx`.
70 files. Nothing in the first 64 bytes of a `PTB` looks like the id, so what
is wanted is a field further in or a separate table; `eff_hitlevel_tbl` in
`ELBN` is the place to look first.

### 5. The 289 native script functions.

`psq.py api` gives each one a name and an arity histogram, and the call sites
give the argument values. That is enough to write down what most of them do
without a disassembler. The ones a stage needs to run first:
`cfSetEnableEmGen`, `cfSetEnableHitArea`, `cfSetEnableBorderline`, `cfMapJump`,
`cfStartPieceLock`, `cfGetGlobalFlag`, `cfSetGlobalFlag`, `chrSetMotion`.

### Then

6. **The rest of the `.anmcmd` opcodes.** Thirty of the fifty-two have no
   correlation. The positional method is close to exhausted; what would move
   it further is the geometry — pose the skeleton, draw the hit capsule — which
   is also item 7.
7. **Which vector is which** in the hit record. Three signed vec3s; the natural
   readings are an offset, an end point and a direction. `cmdl.py gait` already
   does the forward kinematics that needs.
8. **The `ELBN` records, field by field.** The container is solved and 318
   names are addressable; not one record is described. `job.cpk/<class>/
   objbin.bin` is the best target, because it is the same territory as the
   JSON in [`params.md`](params.md).
9. **Name the `ECH` columns.** `piecelock.bin` and `enemy_gen.bin` are now
   small, well-posed instances with known consumers: the `.psq` calls name
   their rows, so the columns can be read against the script that uses them.
   The `CCLS` surface codes 1 to 13 are the other one.
10. **The minimap transform.** 137 `.map` images, each visibly the silhouette
    of its own stage's collision. A small job that gives the UI layer a map.
11. **Structure the `.psq` control flow.** `psq.py src` prints labels and
    `goto`. Rebuilding `if`/`while`/`switch` is ordinary work and nobody needs
    it yet.

---
## Deferred, with reasons

- **EBOOT decryption** (Phase 3). Narrower than it was: the quest state machine
  and the boss AI are script, so what is left inside it is the combat loop and
  the 289 native functions. Still nothing on the current list needs it.
- **Audio and video** — the `.acb` half is no longer deferred: an `.acb` is an
  `@UTF` table and `cpk.py` opens it, which is how the hit record's sound got
  named. What is still deferred is decoding the waveforms in the `.awb`, and
  PAMF video, both well-trodden.

## Open, unowned

- `CTEX`: the `0x28` stamp and bit 0 of `0x1D`. Both are described in
  [`format_ctex.md`](format_ctex.md); neither affects the decode.
- `CMDL`: the four-byte attribute at layout byte 2; the middle byte of the
  mesh descriptor's first word; `S8` and the 16-byte digests at the head of
  `S9`; the eight stage grounds whose texture index runs one past their name
  list; and the 25 models whose node table disagrees with their own inverse
  bind matrices. All in [`format_cmdl.md`](format_cmdl.md).
- `CNOM`: the `u8` at `+0x04` of a channel; the constant `1000.0` at `0x4C`;
  the `u16 1` at `0x12`. See [`format_cnom.md`](format_cnom.md). The frame
  rate is settled in [`units.md`](units.md).
- `CCLS`: what the fifteen-word bit says about the nine early stages; what the
  surface codes 1 to 13 name; the eleven stages with an edge used by three or
  four triangles. See [`format_ccls.md`](format_ccls.md).
- `ECH`: what the header word at `0x08` is for (zero on all 4,941 files, so the
  disc offers no evidence either way); the one-byte row width; column
  semantics.
- `TXT`: what word 2 of a record selects; why attribute id 0 carries both RGBA
  colours and scale factors.
- `params`: what records 1 and 2 of a player class are — record 1 is plainly a
  buffed state but the disc never names it, and a search of all 25,288 messages
  for "Fever" found nothing. Also the four unexplained elements of the `ab_*`
  status vectors.
- `.anmcmd`: thirty of the fifty-two opcodes; which of the hit record's three
  vectors is which; the unit of `+0x35`; why 554 of the 2,053 name no motion.
  See [`format_anmcmd.md`](format_anmcmd.md).
- `.psq`: `_OP_COMPARITH`'s packed `_arg1`, exercised three times on the whole
  disc and read out of the interpreter rather than confirmed; and the `.ppcut`
  macro names, which the preprocessor consumed. See
  [`format_psq.md`](format_psq.md).
- `.PTP` (70) and `.mkc` (2,690) — the second of these sit beside the `CNOM`
  files and may be what the unmatched `.anmcmd` lists key through.
- The AI's own leftovers: 67 of the 77 condition terms; the `0x2000` and
  `0x4000` instruction flags; what an action id names; the five `ProbList`
  files whose group ids repeat rather than ascend; and the eight
  `EventTable.dat` and `MotStream.dat`. See [`format_ai.md`](format_ai.md).
- The stage layout's own leftovers: the polyline's third word, 0 to 5; whether
  a fence is a closed loop; the 45 markers named `HTA*`; and what places the
  object a `obj*` marker marks.
- What the 14 empty `.cpk.patch` stubs would have overlaid, and whether a
  shipped title update exists that fills them.

---

# Log

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
