# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — the world, then the events

A character now deforms on its own skeleton under its own animation, and a
stage's walkable ground reads as a floor plan. What is missing between them is
where things *are*: the stage is a pile of models with no placement, and the
animations fire no events.

### 1. `.map` — world layout. 137 files.

The obvious next file, and the one `CCLS` points at. A stage directory holds
`ground.CMDL`, `sky.CMDL`, a heap of props, and a `.col` that covers only the
walkable middle of the ground model — so something places the props, sets the
camera, and says where the player enters and the monsters spawn. 137 `.map`
files against 155 stages is close enough to be per-stage.

Start with the shell: if it carries a `POF0` it will fall open the way `CMDL`
and `CNOM` did, and if it does not, expect the flat-array shape `CCLS` turned
out to have — and remember what `CCLS` taught, that a plausible record boundary
can be twelve bytes wrong and still divide the payload exactly. Find an
identity that only the right reading satisfies before believing any of it.

### 2. `.anmcmd` (2,053) and `CMTM` (91).

`.anmcmd` is plainly animation *commands* — the events a motion fires, which is
what turns an attack animation into a hitbox at a frame. It is now much better
placed than it was: the hitboxes it would arm are the `collision_*.CTXT`
capsules found this session, bound to bones through the model's locator table,
and the frames it would fire on are `CNOM` frames. Both ends exist.

`CMTM` sits beside `CNOM` under `*.mot.pac/` and shares the shell, `POF0` and
all, so it should open in an hour.

### 3. The frame rate, and it can be settled now.

Nothing in `CNOM` says whether a frame is 1/30 or 1/60 of a second. The actor
parameters in [`params.md`](params.md) carry durations the animations have to
match — and `.anmcmd`, once read, will carry frame numbers for events whose
timing the parameters also describe. Two independent ways to the same number.

### Then

4. **`.psq`** — `FA FA 'SQIR'` then `PART` chunks, the compiled cutscene
   language, 3,011 files. Big, and probably slow.
5. **Name the `ECH` columns.** The types are inferred and the tool reports
   them; the *meanings* are the work. The AI filenames
   ([`RECON.md` §7b](RECON.md)) give every monster an English name for free,
   which makes a monster table readable without an EBOOT. The `CCLS` surface
   codes are a small, well-posed instance: 1 to 13, and a footstep table would
   key on exactly those.

---

## Deferred, with reasons

- **EBOOT decryption** (Phase 3). Load-bearing here in a way it was not on the
  sister project, but everything above is in the clear, and the experience
  there is that facts get postponed to the disassembler and then found in a
  filename. Nothing on the current list needs it.
- **`ELBN`** (707 blocks) — unidentified, no consumer waiting.
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
- `ELBN`.
- `.PTP` (67), `.trg` (163), `.mkc` (2,690).
- What the 14 empty `.cpk.patch` stubs would have overlaid, and whether a
  shipped title update exists that fills them.

---

# Log

## Session 7 — 2026-08-22

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
