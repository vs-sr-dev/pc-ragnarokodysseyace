# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — the capsule gets a skeleton

Session 15 read `.mkc`, the movies and the sound banks, and **Phase 2 now has
no open rows**: every container the disc ships is read, and the chain from a
frame of an animation to a PCM sample closes on 7,524 of 7,608 references.
What is left inside the formats is columns and opcodes, not containers. From
here the work is building.

### 1. Pose the body.

`engine/` has a capsule that runs, turns, slides along a fence and falls, and
no pose at all. Everything it needs is read and none of it has ever been put
in the same place at the same time:

- [`CNOM`](format_cnom.md) has 3.0M keys and binds to a skeleton by name;
- `cmdl.py gait` already does the forward kinematics, and `cmdl.py obj` already
  writes a posed model out;
- [`.anmcmd`](format_anmcmd.md) says what happens on which frame, and its hit
  record names the bone it hangs off;
- and [`.mkc`](format_mkc.md) now says which frame the foot lands on. That is
  the one that makes a pose checkable rather than merely visible: **`7ffa`
  fires on the frame the foot plants**, so the animation's own footfall can be
  measured against the root motion `cmdl.py gait` derives, over 3,043
  animations, and the two either agree or the pose is wrong. The same frame
  now also reaches a WAV, through [`awb.py`](../tools/awb.py), so the first
  thing that runs and makes a noise is closer than the first thing that runs
  and has a face.

The first deliverable is small: play one `CNOM` on the walking capsule and
print, per frame, the height of the planted foot above the collision mesh.

### 2. `effect.bin` — 69 tables that just acquired a consumer.

[`.mkc`](format_mkc.md) opcode `0801` indexes them, 1-based, 3,926 times. They
are `ECH` tables of 60-byte rows of which the last 44 are usually zero, and
nobody has named a column. The head reads as two `u16` ids, a `u32` that is 0
or 10000, a `0x40`/`0xff` pair and a float at `+0x0C` that is 1.0, 0.8 or 0.7.
The obvious question is whether one of the two ids is a `(category, slot)`
half of the [`.PTP`](format_ptp.md) address, which would join the effect layer
end to end — and 14 pacs index past the end of their own table, which is the
other half of the same question.

### 3. The 289 native script functions.

`psq.py api` gives each one a name and an arity histogram, and the call sites
give the argument values. That is enough to write down what most of them do
without a disassembler. Session 12 added a second, sharper source: the AI's
term dispatch names **forty-odd predicates over monster state** —
`getHpRate`, `getTargetRange`, `getAngleTypeAtTarget`, `isTargetJump`,
`getActiveSameKindCount`, `checkRangeParam` and the rest — and every one of
them is a small function over state the engine has to keep anyway. Writing
those down is the shortest route to *"a monster fights"*. The mercenary AI
adds 19 more of the same shape — `getRange`, `getNumOfEnemy`, `getTargetType`,
`isAvailableAceSkill` — and its whole interface is only those 19 plus `print`.
The ones a **stage** needs first are still `cfSetEnableEmGen`,
`cfSetEnableHitArea`, `cfSetEnableBorderline`, `cfMapJump`, `cfStartPieceLock`,
`cfGetGlobalFlag`, `cfSetGlobalFlag`, `chrSetMotion`.

### 4. The opcodes that are left, in both event formats.

Thirty of `.anmcmd`'s fifty-two and ten of `.mkc`'s twenty-one. The positional
method is close to exhausted on `.anmcmd`; what would move it further is the
geometry, which is item 1. `.mkc`'s ten are easier and worth doing in the same
pass, because six of them are players-only or monsters-only and that is where
a correlation starts: `0803`, `0804`, `0805`, `080d` are the players'
(624 records), `080f` is the monsters' (193), and `0802`'s four arguments are
a camera shake whose roles are unread.

### Then

5. **Which vector is which** in the hit record. Three signed vec3s; the natural
   readings are an offset, an end point and a direction. `cmdl.py gait` already
   does the forward kinematics that needs.
6. **The `ELBN` records, field by field.** The container is solved and 318
   names are addressable; not one record is described. `job.cpk/<class>/
   objbin.bin` is the best target, because it is the same territory as the
   JSON in [`params.md`](params.md).
7. **Name the `ECH` columns.** `piecelock.bin` and `enemy_gen.bin` are now
   small, well-posed instances with known consumers: the `.psq` calls name
   their rows, so the columns can be read against the script that uses them.
   The `CCLS` surface codes 1 to 13 are the other one — and `.mkc` gives them
   a second consumer, since `7ffa`/`7ffb` fire a footstep and the ground is
   what has to choose its sound.
8. **The minimap transform.** 137 `.map` images, each visibly the silhouette
   of its own stage's collision. A small job that gives the UI layer a map.
9. **Structure the `.psq` control flow.** `psq.py src` prints labels and
   `goto`. Rebuilding `if`/`while`/`switch` is ordinary work and nobody needs
   it yet.

---
## Deferred, with reasons

- **EBOOT decryption** (Phase 3). Narrower than it was: the quest state machine
  and the boss AI are script, so what is left inside it is the combat loop and
  the 289 native functions. **Session 14 produced the first item that genuinely
  needs it** — the table that maps `.anmcmd` opcode 10's effect id to a `PTB`
  slot is not on the disc, and 32,600 leaves were searched for it. It is a
  cosmetic lookup, so it still does not justify the phase on its own.
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
  vectors is which; the unit of `+0x35`; why 554 of the 2,053 name no motion;
  and opcode 10's effect id, which session 14 showed resolves nowhere on the
  disc. See [`format_anmcmd.md`](format_anmcmd.md).
- `.psq`: `_OP_COMPARITH`'s packed `_arg1`, exercised three times on the whole
  disc and read out of the interpreter rather than confirmed; and the `.ppcut`
  macro names, which the preprocessor consumed. See
  [`format_psq.md`](format_psq.md).
- `.PTP`: what category 2 addresses — `eff_hitlevel_tbl` reaches ids up to 252
  and no `PTCP` on the disc has that many slots — and the inside of a `PTB`,
  which nothing needs until something renders. See
  [`format_ptp.md`](format_ptp.md).
- `.acb`: the waveform `ExtensionData`, empty on all 7,756; the command
  streams past opcode 2000 (volume, pitch, panning, AISAC); which member of a
  variation set the game picks and with what weights; and the `.acf`'s 16
  mixer categories and 40 buses. See [`format_awb.md`](format_awb.md).
- `.mkc`: ten of the twenty-one opcodes, the argument roles of the camera
  shake, the emitter namespace, the fourteen
  pacs that index past the end of their own `effect.bin`, and whether `7ff9`
  and `7ffd` differ at all. See [`format_mkc.md`](format_mkc.md).
- The AI's own leftovers: ten of the 76 condition terms, which the six
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
- The mercenary AI's leftovers: the command ids other than 0, 14 and 15; the
  flag word at `+0x08`; the seven words of a `target_NN`; command 16, used
  twice; and the message ids in the two roster tables. See
  [`format_merc.md`](format_merc.md).
- What the 14 empty `.cpk.patch` stubs would have overlaid, and whether a
  shipped title update exists that fills them.

---

# Log

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
