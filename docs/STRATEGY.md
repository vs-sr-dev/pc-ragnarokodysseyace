# PC-ROA — strategy

*Aligned to the end of session 3 (2026-08-22). Detail and priorities live in
[`TODO.md`](TODO.md); this document is the frame.*

Goal: a **native PC reimplementation** of *Ragnarok Odyssey ACE*, the PS3
edition of the PS Vita game *Ragnarok Odyssey*. Distribution is BYOA — the
player supplies their own disc, the repository ships code and documentation.

Model: Ship of Harkinian, OpenGOAL, devilutionX.

## The shape of the problem, and how it differs from the sister project

On the sister project the decision was easy: 100% of the game logic was
on the disc as readable Lua, so the engine was built to host those scripts
verbatim. **Here there is no Lua.** Everything executable is inside a 19.8 MB
PPC64 SELF, and what the disc hands over instead is *data*:

- **89 JSON files**, 1,069 records, with the movement and combat parameters of
  every player class and every monster, uncompressed and pretty-printed;
- **4,941 `ECH` tables**, 58,534 rows — items, monsters, quests, rewards,
  stages, shop recipes, the endless dungeon — now fully readable;
- **25,288 messages** in 76 `TXT` files, which pair positionally with those
  tables and give every row its name;
- **2,992 `.psq` sequences**, the compiled cutscene language;
- fonts, textures, motion and collision, all in containers we can now open.

So the strategy inverts. On 3D Dot the code was free and the formats had to be
earned; here the formats are cheap and the behaviour has to be recovered. That
makes **Phase 3 (the EBOOT as oracle) load-bearing rather than optional**, and
it makes the data-first phases a way of shrinking what has to be recovered from
it: every rule that turns out to be table-driven is a rule nobody has to read
out of PPC64 assembly.

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
| `CTEX` texture | 11,061 | **highest** | the largest population on the disc; nothing renders without them |
| `CMDL` model | 1,127 | high | geometry |
| `.map` / `CCLS` | 137 / 155 | high | world layout and collision |
| `CNOM` motion | 3,043 | high | |
| `.psq` sequence | 2,992 | high | the cutscene language; `SQIR` + `PART` chunks |
| `.anmcmd` | 2,053 | medium | animation commands |
| `.mkc` | 2,690 | medium | |
| `.CTXT` | 1,151 | medium | opens with readable ASCII |
| `ELBN` | 379 | low | unidentified, no consumer waiting |
| `.PTP` effects | 18 | low | |
| CRI Atom audio | 274 | low | `.acb`/`.awb`, well-documented format |
| PAMF video | 46 | low | ffmpeg territory |
| `.otf` font | 1 | ✅ **free** | ordinary OpenType |

## Phase 3 — The EBOOT as oracle

Decrypt the SELF (`key_revision 0x001C`, public retail keys) to a PPC64
big-endian ELF and open it in Ghidra.

Unlike on the sister project, this is not a deferrable curiosity: with no
scripting layer on the disc, the EBOOT is where the combat loop, the AI
dispatch, the quest state machine and the `.psq` interpreter live.

**But the method note from the sister project still applies, and applies
harder here.**
Repeatedly on that project, things postponed to "the EBOOT phase" turned out to
be written in the clear somewhere on the disc — sometimes in a filename. Before
reaching for the disassembler, ask whether the fact is already declared. On
this disc the `.json` parameters and the `ECH` tables are exactly that kind of
declaration.

## Phase 4 — Host

Nothing built yet. The shape is now clearer than it was: a data-driven engine
whose tables come from `ECH`, whose display text comes from `TXT`, whose actor
parameters come from the JSON, and whose sequences are interpreted from `.psq`.
Three of those four are readable today, and the fourth is the last one left.

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
