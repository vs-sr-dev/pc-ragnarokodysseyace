# PC-ROA — strategy

*Aligned to the end of session 22 (2026-08-23). Detail and priorities live in
[`TODO.md`](TODO.md); this document is the frame.*

Goal: a **native PC reimplementation** of *Ragnarok Odyssey ACE*, the PS3
edition of the PS Vita game *Ragnarok Odyssey*. Distribution is BYOA — the
player supplies their own disc, the repository ships code and documentation.

Model: Ship of Harkinian, OpenGOAL, devilutionX.

## The shape of the problem, and how it differs from the sister project

On the sister project the decision was easy: 100% of the game logic was
on the disc as readable Lua, so the engine was built to host those scripts
verbatim. This document said for nine sessions that there was no equivalent
here — that everything executable was inside a 19.8 MB PPC64 SELF and the disc
handed over only data. **Session 10 overturned that.** `.psq` is Squirrel 2.2
bytecode: 3,011 files, 11,232 functions, with the compiler's debug tables
intact. The cutscenes, the quest logic, the stage scripts and six bosses' AI
are script, and the disc names the 285 host functions they call.

So the shape is between the two: a large data layer *and* a scripting layer,
with the engine underneath both. What the disc hands over is:

- **89 JSON files**, 1,069 records, with the movement and combat parameters of
  every player class and every monster, uncompressed and pretty-printed;
- **4,941 `ECH` tables**, 58,534 rows — items, monsters, quests, rewards,
  stages, shop recipes, the endless dungeon — now fully readable;
- **25,288 messages** in 76 `TXT` files, which pair positionally with those
  tables and give every row its name;
- **3,011 Squirrel closures**, 11,232 functions — the cutscenes, the quest
  logic, the stage scripts and the boss AI, decompiling with their authors'
  own variable names and source lines;
- fonts, textures, motion and collision, all in containers we can now open.

The strategy still inverts, but less than it looked. On 3D Dot the code was
free and the formats had to be earned; here the formats were cheap and the
behaviour had to be recovered — and a good deal of that behaviour turns out to
be script after all. **Phase 3 (the EBOOT as oracle) stays load-bearing**, but
what it is now needed for is narrower and better defined: not "the game logic"
but the parts of the combat loop no script touches — session 18 read the 285
native functions off their own call sites, so they are no longer waiting on it
either. See [`format_api.md`](format_api.md). Every rule that turns out to be table-driven or
script-driven is a rule nobody has to read out of PPC64 assembly.

**Why not static recompilation.** Same answer as the sister project: the RSX
would need substantial HLE, and the result would be an opaque, unmoddable
binary. Here there is a second reason — a Vita-era engine with its parameters in
JSON is a good candidate for honest reimplementation, and a bad one for
translation.

---

## Phase 1 — Getting at the bytes

- **1a. Official extractor.** ✅ **done** — `tools/iso.py`, own UDF 2.50 reader
  (PS3 Blu-rays use a metadata partition that `pycdlib` will not follow), with
  declared sets, an sha256 manifest and verification. Corrected for
  multi-extent files, which this disc has and the sister disc did not.
- **1b. CPK containers.** ✅ **done** — `tools/cpk.py`, `@UTF` tables and
  CRILAYLA. 20 containers, 2,450 entries, 0 errors.
- **1c. ARC containers.** ✅ **done** — `tools/arc.py`. **1,544 of 1,544**
  files consistent, 13,820 entries, 13,798 blocks each ending on its declared
  byte.
- **1d/1e. A single addressable asset tree.** ✅ **done** (session 2) —
  `tools/assets.py`, one path per leaf across every layer: nested CPKs, ARCs
  inside ARCs, and the `cmp` wrapper in both its codecs. **32,727 leaves,
  2.0 GB**, depth up to six. Phase 1 is closed.

## Phase 2 — Asset formats

Priority set by what the first frame needs, and by what removes work from
Phase 3.

| Format | N | Priority | Notes |
|---|---:|---|---|
| `ECH` tables | 4,941 | ✅ **solved** | [`format_ech.md`](format_ech.md) — 58,534 rows, string pools, inferred column types |
| quest tables | 1,719 | ✅ **read** | [`format_quest.md`](format_quest.md) — the four tables of a quest `.pac`, and which monster comes out of which spawner |
| `TXT` text | 76 | ✅ **solved** | [`format_rmsg.md`](format_rmsg.md) — 25,288 messages, pairs positionally with the tables |
| `.json` params | 89 | ✅ **read** | [`params.md`](params.md) — 1,069 records; the stagger model, the difficulty tiers, and one movement model shared by all six classes |
| `CTEX` texture | 11,536 | ✅ **solved** | [`format_ctex.md`](format_ctex.md) — five pixel formats, mip chains, Morton swizzle |
| `CMDL` model | 1,127 | ✅ **solved** | [`format_cmdl.md`](format_cmdl.md) — geometry, materials, the draw list and the skinning |
| `CCLS` collision | 155 | ✅ **solved** | [`format_ccls.md`](format_ccls.md) — the walkable ground, one welded triangle mesh per stage |
| `.map` | 137 | ✅ **solved** | not the world layout at all: a 256x256 minimap, and a [`CTEX`](format_ctex.md) |
| stage layout | 163 | ✅ **solved** | [`format_stage.md`](format_stage.md) — `ATIH` markers, the fences and the trigger scripts |
| `ELBN` params | 707 | ✅ **solved** | [`format_elbn.md`](format_elbn.md) — the named-parameter container, 318 names; `objbin.bin` and `trace_par.bin` read |
| `CNOM` motion | 3,043 | ✅ **solved** | [`format_cnom.md`](format_cnom.md) — 3.0M keys, quaternion rotations, bound to skeletons by name |
| `CMTM` material | 91 | ✅ **solved** | [`format_cnom.md`](format_cnom.md) — `CNOM` with scalars; animates material colour |
| `.psq` / `.cnut` | 3,011 | ✅ **solved** | [`format_psq.md`](format_psq.md) — **Squirrel 2.2 bytecode**; 11,232 functions decompile with their own names, and all 20,032 jumps back into `if`/`switch`/`while` |
| `.anmcmd` | 2,053 | ✅ **read** | [`format_anmcmd.md`](format_anmcmd.md) — the event lists; the hit record read and bound to the skeleton, 22 of 52 opcodes correlated |
| `.mkc` | 2,690 | ✅ **solved** | [`format_mkc.md`](format_mkc.md) — the presentation track: 19,724 records, every sound reference naming a cue, and its emitter a place on the body |
| `.CTXT` | 1,151 | ✅ **solved** | plain text: hit capsules and springs, bound to a bone through the model's locator table — which `.mkc` addresses too; see [`format_cmdl.md`](format_cmdl.md) |
| `.PTP` effects | 70 | ✅ **solved** | [`format_ptp.md`](format_ptp.md) — the container, and the `(category, slot)` pair three consumers address an effect with |
| AI tables | 228 | ✅ **solved** | [`format_ai.md`](format_ai.md) — `ProbList.dat` and the decision scripts; 66 of 77 terms named off the game's own dispatch |
| `.par` AI | 438 | ✅ **solved** | [`format_ai.md`](format_ai.md) — four record kinds and two structs, every sentinel exact |
| mercenary AI | 48 | ✅ **solved** | [`format_merc.md`](format_merc.md) — four `ELBN` per class and the script that indexes them; the command runs are button presses |
| CRI Atom audio | 274 | ✅ **read** | `@UTF` tables; `cpk.py` opens them, and [`.mkc`](format_mkc.md) addresses them by bank and cue id. Only the `.awb` waveforms are left |
| PAMF video | 46 | ✅ **solved** | [`pam.py`](../tools/pam.py) — a 2 KB Sony header over a plain MPEG-2 program stream; 22.7 minutes of 720p29.97, and no audio track on any of the 46 |
| `.otf` font | 1 | ✅ **free** | ordinary OpenType |

**Phase 2 has no open rows.** Every format the disc ships is read, and what is
left inside them is columns and opcodes rather than containers: the `ELBN`
records field by field, the `ECH` column names, thirty `.anmcmd` opcodes and
six of `.mkc`'s. From here the work is building rather than reading — and
[`combat_loop.md`](combat_loop.md) is the first document here written from the
building side, which is why it is a chain and a ledger rather than a format.

## Phase 3 — The EBOOT as oracle

Decrypt the SELF (`key_revision 0x001C`, public retail keys) to a PPC64
big-endian ELF and open it in Ghidra.

Unlike on the sister project, this is not a deferrable curiosity: the EBOOT is
where the combat loop lives, and it is where the **285 native functions**
[`format_psq.md`](format_psq.md) enumerated are implemented. It is no longer
where the quest state machine or the boss AI live — those are script — nor,
since session 18, where *what those functions do* has to be read:
[`format_api.md`](format_api.md) has them off the call sites. What is left
inside it is the implementation and the combat loop.

**Session 22 added two items of the same size and the same shape**, both
from the monster AI: the **seven per-boss escape hatches** (`checkB01Term` and
its siblings), which nine tables call on 458 instructions and nothing on the
disc defines, and the **ten unnamed condition terms**, 1,094 instructions,
which are not in the `.cnut` dispatch because the tables are the newer
artefact. Both are small functions, both are needed to run a boss exactly, and
neither is anywhere but inside the binary. See
[`format_ai.md`](format_ai.md).

**And since session 21 that is a list rather than a category.**
[`combat_loop.md`](combat_loop.md) traces one hit through the eight files that
touch it and ends in a ledger of nine gaps. Four are ordinary disc work. The
other five are what the EBOOT is actually needed for, and each is one function
rather than a subsystem: **the damage expression**, **what the hit record's
`+0x35` is a strength of**, **what computes the hit level**, **the sign of a
region's flat modifier**, and **what `react_p` is a pool of**. That is a
smaller and much better specified reason to decrypt the binary than "the
combat loop" was, and it is the fourth time on this project that writing
something down has shrunk the phase it was supposed to justify.

**But the method note from the sister project still applies, and applies
harder here**, and session 10 is the sharpest instance yet. `.psq` sat on the
list for nine sessions as "the compiled cutscene language, `SQIR` + `PART`
chunks", and the six bytes that identify it were being read the whole time:
`0xFAFA` and `SQIR` are two `#define`s in a widely used open-source VM. Session
8 had the same shape — `ELBN`, deferred five times over as "unidentified, no
consumer waiting", turned out to ship the engine's own parameter names, and the
stage triggers turned out to be **script source text in the clear**. None of
the three needed a disassembler; all three needed somebody to open the file and
take the magic seriously.
Repeatedly on that project, things postponed to "the EBOOT phase" turned out to
be written in the clear somewhere on the disc — sometimes in a filename. Before
reaching for the disassembler, ask whether the fact is already declared. On
this disc the `.json` parameters and the `ECH` tables are exactly that kind of
declaration.

## Phase 4 — Host

**Begun in session 14.** [`engine/`](../engine) is the first code here that is
not a reader: a world that answers *where is the floor* and *where is the
fence*, and an actor that moves under the parameter table. It is three files
and it has no renderer, no VM and no combat — but it runs, and reaching
milestone 1 with it is written up in
[`milestone_numbers.md`](milestone_numbers.md).

**Session 16 added the fourth file.** [`pose.py`](../engine/pose.py) plays a
`CNOM` on a `CMDL` skeleton and finds the node that touches the ground, so the
body has a shape as well as a position: on `010_01_01` the walking capsule's
planted foot sits three millimetres above the collision mesh. It is checked
against the disc rather than against itself — `.mkc`'s `7ffa` fires within a
frame of the skeleton landing a foot on four firings in five, against one in
four for a frame picked at random. It also closed the `.mkc` sound record: its
last unread field is a `CMDL` locator id, and 2,715 of 2,716 resolve. See
[`pose.md`](pose.md).

**Session 22 added the fifth and sixth, and they are the VM.**
[`squirrel.py`](../engine/squirrel.py) executes Squirrel 2.2 bytecode - 48
opcodes, and every script on the disc runs through it with **0 VM faults** -
and [`host.py`](../engine/host.py) is the other side of
[`format_api.md`](format_api.md): all 285 functions bound, 66 of them to real
state, the `suspend` vocabulary turned into a scheduler, and the trigger
volumes wired to the marker table. It was written rather than linked because
the disc's reader is already in Python and complete, so the interpreter is the
second half of a file that exists; a C Squirrel would need a build, a binding
and a byte-swap to read a big-endian stream.

**And session 22 added the seventh and eighth.**
[`brain.py`](../engine/brain.py) runs a monster's decision - the rule ladder,
the weighted table and the action it rolls - and
[`fight.py`](../engine/fight.py) turns that action into a motion, an event
list and a hit volume placed against a body on the collision mesh. Together
with `host.py` that is **115 of the 285 host functions doing the work rather
than recording the call**, and 18,435 of the 25,699 calls the disc makes.

The shape of the rest is settled: a data-driven engine whose
tables come from `ECH`, whose display text comes from `TXT`, whose actor
parameters come from the JSON, and which hosts that VM. All four sources are
readable today, and the sister project's decision, "build the engine to host
the game's own scripts verbatim", applies here after all.

## Phase 5 — Bring-up by area

Not reached.

---

## Milestones

### 1. "The numbers are real" — ✅ **reached, session 14**

A capsule with the game's own `acc = 0.035`, `run_sp = 0.17`, `rot_y_acc = 8`,
`rot_y_spd = 32` and `col_r = 0.5` crosses `010_01_01` from the player spawn to
the exit in **405 frames — 13.5 seconds — with 0 frames off the collision
mesh**, sliding along the fence for half of them. The same capsule then walks
**135 stages**, 127 of them with the body on legal ground for every frame, at
**5.05 m/s against 5.10 flat out**. The full report is
[`milestone_numbers.md`](milestone_numbers.md); the code is
[`engine/`](../engine).

It took six sessions to attempt because everything it needed had been ready
since session 8 and nothing forced the issue. Three things came out of it that
no amount of further reading would have produced:

- the spawn marker faces its own exit, which **settles the heading
  convention** the disc never declares;
- `hta.bin` and `<stage>.col` agree: `obj` and `appear` markers stand on the
  collision mesh to **a centimetre**, over 1,432 markers and 155 stages, and
  exactly one of them has no ground under it;
- **a `borderline` is a closed loop** — 105 of 145 stages have every fence
  endpoint shared by exactly two polyline ends — which had been an open
  question since session 8;
- **`fall_spd_max` is a speed after all**, and it is the terminal velocity of
  something that has fallen out of the level. [`units.md`](units.md) could not
  tell whether the clamp ever fires; letting a body walk off the mesh made it
  fire, at 8.000 m in a frame, exactly.

The stage this ran on has been readable since session 8: a ground mesh, 346
collision triangles, a fence, four spawn points in formation at one end and a
doorway at the other, and twenty-odd places monsters come from in between.

### 2. "A stage runs" — ✅ **reached, session 22**

`010_01_01`'s own script initialises it, milestone 1's capsule crosses it in
**460 frames with 0 frames off the collision mesh**, the trigger volume at the
exit fires the function `trigger.trg` names, and the `cfMapJump` inside it
loads `010_01_02` and starts that stage's script and its quest script. On the
same machinery **68 of 68 cutscene scripts run to their own `setDemoEnd`**,
driven by a length read off their camera track, and a conversation with Norn
comes out as 13 lines of English through the `suspend` protocol. Over the
whole disc, **155 stages load and initialise and all 507 trigger lines
parse**. The report is [`milestone_stage.md`](milestone_stage.md).

Three things came out of it that reading could not produce: a vararg function
keeps all its declared parameters, which 447 boss-AI failures said and the
weight tables summing to 10,000 confirmed; a cutscene's length is the `u16` at
`0x10` of its `.CSCM`; and the root table is one table shared by the resident
library and the loaded stage, which three name collisions in 155 stages and
147 in one town's conversations settle from both sides.

### 3. "A monster fights" — ✅ **reached, session 22**

An Orc stands on the spawner `010_01_01` declares for it, a body with the
player class's own parameters runs at it, and the Orc reads its own decision
tables, rolls an action out of the group they name, closes when that action's
own `_act.par` gate says the target is too far, plays the animation the action
names and **fires the hit records on it into a volume that reaches the
player**. Over the whole disc, 83 of 83 monsters decide on every one of 40
random states. The report is [`milestone_fight.md`](milestone_fight.md).

Three things came out of running it that reading could not produce:

- **the disc's own term dispatch is executable**, now that there is a VM, so
  it can check this project's evaluator rather than only document it: 458
  `(term, operand)` pairs, 15,040 comparisons, 0 disagreements. Two of the 76
  terms turn out to be dead as the shared include writes them;
- **the chance term's two readings are separable by running both sides.** The
  OrcKing's table picks the same group as its own script 217 times in 300
  under the include's form and 293 under the hand-written one;
- **`_act.par`'s range is a distance to the target**, and the hit volumes on
  the same action's motion say so: correlation **0.590** over 250 actions
  against a shuffled control of 0.051, with the gate systematically the longer
  of the two.

What it does not do is damage: [`combat_loop.md`](combat_loop.md)'s ledger
still owns the expression, so a hit is reported as a connection and not as a
number, and the player does not fight back.
