# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — the opcodes, the frame rate, and the cutscenes

The world layout is done, and it came with two formats nobody had asked for:
`ELBN`, which turns out to carry the engine's own parameter vocabulary, and
`trigger.trg`, which turns out to be script source. What is left between the
data and a running loop is behaviour.

### 1. Name the `.anmcmd` opcodes. Carried over, and now better armed.

Still the same 52 unnamed opcodes over 10,175 commands, and still the same
starting point: opcode 0, the commonest at 2,508 uses, the only
variable-length one, `12 + 116 * n`, which is the shape a hitbox set has.

What is new since the item was written is the other end of the correlation.
`ELBN` now hands over `se_hitlevel_tbl` and `eff_hitlevel_tbl` (76 files each),
`s_combo_finish_inf` and `s_combo_graph` per player class, and
`enemy_state_sound_param`; the `.CTXT` capsules were already bound to bones
through the model's locator table. An opcode that arms a hit has all three of
those waiting for it, and an opcode whose 116-byte record holds a locator id
names a bone outright.

### 2. The frame rate. Still two independent routes, and a third now.

Nothing in `CNOM` says whether a frame is 1/30 or 1/60 of a second, and a
search of `game_common_param.bin` and `latency.bin` this session found no
declaration anywhere. The routes:

- the actor parameters in [`params.md`](params.md) carry durations the
  animations have to match;
- `.anmcmd` carries event frames for moves those parameters describe;
- and `mot_param.bin` now gives, per class, one 16-byte row per motion — 87
  rows for `fas`, 115 for `fmg` — whose `u16` of flags is a small number
  (0, 3, 6, 8) that a loop bit and a blend length would both live in.

### 3. `.psq` — the cutscene language. 3,011 files.

`FA FA 'SQIR'` then `PART` chunks. It is now clear what calls it:
`trigger.trg` runs `callQuestScript("sfEnmGenStart()")`, naming another script
by string, and every stage carries its own `<stage>.psq` beside the trigger
list. So `.psq` is where a named script's body is, and the trigger vocabulary
— 20-odd function names — is the entry point list to check any decoding
against.

### Then

4. **The `ELBN` records, field by field.** The container is solved and 318
   names are addressable; not one record is described. `job.cpk/<class>/
   objbin.bin` is the best target, because it is the same territory as the
   JSON in [`params.md`](params.md) and the two can be compared against each
   other rather than guessed at.
5. **Name the `ECH` columns.** Unchanged. The `CCLS` surface codes 1 to 13 are
   still the small well-posed instance, and the `ATIH` marker names now give a
   second vocabulary to correlate against — 272 `jump_*` markers name the
   stage they lead to, which is a stage graph that the stage table in `ECH`
   must also encode.
6. **The minimap transform.** 137 `.map` images, each visibly the silhouette
   of its own stage's collision. Fitting the transform is a small job and
   gives the UI layer a working map for free.

---
## Deferred, with reasons

- **EBOOT decryption** (Phase 3). Load-bearing here in a way it was not on the
  sister project, but everything above is in the clear, and the experience
  there is that facts get postponed to the disassembler and then found in a
  filename. Nothing on the current list needs it.
- **Audio and video** — CRI Atom and PAMF are both well-trodden formats.

## Open, unowned

- `CTEX`: the `0x28` stamp and bit 0 of `0x1D`. Both are described in
  [`format_ctex.md`](format_ctex.md); neither affects the decode.
- `CMDL`: the four-byte attribute at layout byte 2; the middle byte of the
  mesh descriptor's first word; `S8` and the 16-byte digests at the head of
  `S9`; the eight stage grounds whose texture index runs one past their name
  list; and the 25 models whose node table disagrees with their own inverse
  bind matrices. All in [`format_cmdl.md`](format_cmdl.md).
- `CNOM`: the `u8` at `+0x04` of a channel; the constant `1000.0` at `0x4C`;
  the `u16 1` at `0x12`. See [`format_cnom.md`](format_cnom.md). The frame rate
  is now item 3 above rather than an open question.
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
- `.anmcmd`: all 52 opcodes; why 554 of the 2,053 name no motion. See
  [`format_anmcmd.md`](format_anmcmd.md).
- `.PTP` (67) and `.mkc` (2,690) — the second of these sit beside the `CNOM`
  files and may be what the unmatched `.anmcmd` lists key through. (`.trg` is
  now [`format_stage.md`](format_stage.md).)
- The stage layout's own leftovers: the polyline's third word, 0 to 5; whether
  a fence is a closed loop; the 45 markers named `HTA*`; and what places the
  object a `obj*` marker marks.
- What the 14 empty `.cpk.patch` stubs would have overlaid, and whether a
  shipped title update exists that fills them.

---

# Log

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
- Looked for the frame rate in `game_common_param.bin` and `latency.bin` and
  found neither — `latency.bin` is network ping thresholds. It stays item 2.

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
