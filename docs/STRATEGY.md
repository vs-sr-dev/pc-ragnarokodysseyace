# PC-ROA — strategy

*Aligned to the end of session 12 (2026-08-22). Detail and priorities live in
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
are script, and the disc names the 289 host functions they call.

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
but the 289 named native functions the scripts call, plus the parts of the
combat loop no script touches. Every rule that turns out to be table-driven or
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
| `TXT` text | 76 | ✅ **solved** | [`format_rmsg.md`](format_rmsg.md) — 25,288 messages, pairs positionally with the tables |
| `.json` params | 89 | ✅ **read** | [`params.md`](params.md) — 1,069 records; the stagger model, the difficulty tiers, and one movement model shared by all six classes |
| `CTEX` texture | 11,536 | ✅ **solved** | [`format_ctex.md`](format_ctex.md) — five pixel formats, mip chains, Morton swizzle |
| `CMDL` model | 1,127 | ✅ **solved** | [`format_cmdl.md`](format_cmdl.md) — geometry, materials, the draw list and the skinning |
| `CCLS` collision | 155 | ✅ **solved** | [`format_ccls.md`](format_ccls.md) — the walkable ground, one welded triangle mesh per stage |
| `.map` | 137 | ✅ **solved** | not the world layout at all: a 256x256 minimap, and a [`CTEX`](format_ctex.md) |
| stage layout | 163 | ✅ **solved** | [`format_stage.md`](format_stage.md) — `ATIH` markers, the fences and the trigger scripts |
| `ELBN` params | 707 | ✅ **solved** | [`format_elbn.md`](format_elbn.md) — the named-parameter container, 318 names |
| `CNOM` motion | 3,043 | ✅ **solved** | [`format_cnom.md`](format_cnom.md) — 3.0M keys, quaternion rotations, bound to skeletons by name |
| `CMTM` material | 91 | ✅ **solved** | [`format_cnom.md`](format_cnom.md) — `CNOM` with scalars; animates material colour |
| `.psq` / `.cnut` | 3,011 | ✅ **solved** | [`format_psq.md`](format_psq.md) — **Squirrel 2.2 bytecode**; 11,232 functions decompile with their own names |
| `.anmcmd` | 2,053 | ✅ **read** | [`format_anmcmd.md`](format_anmcmd.md) — the event lists; the hit record read and bound to the skeleton, 22 of 52 opcodes correlated |
| `.mkc` | 2,690 | medium | |
| `.CTXT` | 1,151 | ✅ **solved** | plain text: hit capsules and springs, bound to a bone through the model's locator table; see [`format_cmdl.md`](format_cmdl.md) |
| `.PTP` effects | 70 | medium | `PTCP` + `PTB`; the `.anmcmd` effect ids point somewhere here |
| AI tables | 228 | ✅ **solved** | [`format_ai.md`](format_ai.md) — `ProbList.dat` and the decision scripts; 66 of 77 terms named off the game's own dispatch |
| `.par` AI | 438 | ✅ **solved** | [`format_ai.md`](format_ai.md) — four record kinds and two structs, every sentinel exact |
| mercenary AI | 48 | ✅ **solved** | [`format_merc.md`](format_merc.md) — four `ELBN` per class and the script that indexes them; the command runs are button presses |
| CRI Atom audio | 274 | ✅ **read** | `@UTF` tables; `cpk.py` opens them, and `common.acb` names the hit record's sound |
| PAMF video | 46 | low | ffmpeg territory |
| `.otf` font | 1 | ✅ **free** | ordinary OpenType |

## Phase 3 — The EBOOT as oracle

Decrypt the SELF (`key_revision 0x001C`, public retail keys) to a PPC64
big-endian ELF and open it in Ghidra.

Unlike on the sister project, this is not a deferrable curiosity: the EBOOT is
where the combat loop lives, and it is where the **289 native functions**
[`format_psq.md`](format_psq.md) enumerated are implemented. It is no longer
where the quest state machine or the boss AI live — those are script, and they
are readable now.

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

Nothing built yet, but the shape is now settled: a data-driven engine whose
tables come from `ECH`, whose display text comes from `TXT`, whose actor
parameters come from the JSON, and which **hosts a Squirrel VM** and exposes
289 named functions to it. All four are readable today. Squirrel is small,
permissively licensed and still maintained, so the fourth is a dependency
rather than a project — and the sister project's decision, "build the engine to
host the game's own scripts verbatim", applies here after all.

## Phase 5 — Bring-up by area

Not reached.

---

## Milestones

None reached yet, but the first one — **"the numbers are real"** — now has its
numbers. Moving a capsule with the game's own acceleration, run speed and turn
rate needs `acc = 0.035`, `run_sp = 0.17`, `rot_y_acc = 8`, `rot_y_spd = 32`,
and those are the same for every class; the stagger and hit-stop models are
readable too. What is still missing is a stage to move around in, which is why
`CMDL`, `.map` and `CCLS` moved up the list.

That milestone needs no rendering of the game's art and no EBOOT, and it is the
first honest test of whether the reimplementation thesis holds here the way it
held on the sister project.

**As of session 8 it has its stage too.** `010_01_01` reads end to end: a
ground mesh, 346 collision triangles, a fence to stop at, four spawn points in
formation at one end and a doorway at the other, and twenty-odd places
monsters come from in between. Everything the milestone needs is now readable
except the loop that runs it.

**As of session 10 it has the stage's script.** The same stage's `.psq`
decompiles, its triggers name functions that are in it, and the calls those
functions make name the markers the stage already declared. The second
milestone — *"a stage runs"* — needs a Squirrel VM, the 289 native functions
stubbed, and nothing else that is not already read.

**As of session 12 it has a monster that can act.** The AI's condition
vocabulary, its action tables and its parameters are read, and an action id
resolves to a named motion, so the loop *decide → pick → play* is describable
end to end from the disc. The third milestone — *"a monster fights"* — now
needs the 40-odd host predicates the terms call (`getHpRate`, `getTargetRange`,
`isTargetJump` and the rest), which are small functions over state the engine
would have anyway, plus the motion playback that `CNOM` and `.anmcmd` already
describe.
