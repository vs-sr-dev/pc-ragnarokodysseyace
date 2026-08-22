# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — skinning, then collision

`CNOM` is read ([`format_cnom.md`](format_cnom.md)) and a skeleton poses from
the game's own animations. The one link that makes the *mesh* follow the
skeleton is now reconnoitred too, and it reads cleanly — see below. Putting it
together is the next session's first hour, not its whole day.

### 1. Skinning — reconnoitred, and it reads

Session 6 found the attributes and validated them, so start from these facts
rather than from the top. They hold on **all 931 skinned meshes, 473,193
vertices, with no exception**:

- The skinned vertex types are the ones with bits 8 or 9 set: `0x0313` (794
  meshes, stride 40), `0x0317` (136, strides 32 and 44), `0x0337` (1, stride
  52).
- **The first four bytes of a vertex are four `u8` weights, and they sum to
  exactly 255.** 473,193 of 473,193, and the sum takes no other value anywhere
  on the disc.
- **The last four bytes of the stride are four `u8` bone indices**, and every
  one of them is inside its model's node table.
- So on `mzzh` mesh 4, vertex 0 reads `229 26 0 0` and `0 5 0 0`: 229/255 to
  node 0 and 26/255 to node 5.

The layout bytes at `+0x14` do *not* point at either — byte 3 is the texture
coordinates and byte 2 is the normal, as on the rigid types. The two skin slots
sit at offset 0 and at `stride - 4`, which is what the strides in
[`format_cmdl.md`](format_cmdl.md) leave over once position, normal and
coordinates are placed.

**What is left is only the pose, not the parse:**

1. **Confirm the pairing.** Weight `k` almost certainly goes with index `k`,
   but "almost certainly" has been wrong twice on this disc. Render it and
   look.
2. **The bind-pose inverse.** `CMDL` vertices are in model space, so skinning
   is `world_anim(bone) * inverse(world_bind(bone))` per influence, weighted.
   Both matrices are already available: the bind pose from the `CMDL` node
   transforms, the animated one from `CNOM`'s `pose()`. Nothing else is needed.
3. **Then draw it.** A character mesh posed by a `CNOM`, with its own textures
   on it, is a frame of the actual game — and it is the "the numbers are real"
   milestone this project has been walking towards since session 3.

Guard against the obvious failure: a wrong pairing or a missing inverse does
not crash, it produces a figure that is *almost* right, with limbs stretched
towards the origin. Compare against the model's declared bounding sphere, which
the animated mesh should still roughly fill.

### 2. `CCLS` and `.map` — collision and world layout. 155 + 137 files.

`CCLS` files are named `<stage>.col` and sit in `param.pac` beside `hta.bin`
(`ATIH`, most likely hit areas). **`CCLS` has no `POF0`** — its payload is
followed by sixteen zero bytes and nothing else, on all 155 files — so unlike
`CMDL` and `CNOM` it holds no pointers, and the structure will be flat arrays
rather than a directory to follow. Expect counts and strides, and expect to
have to find them rather than read them.

With ground geometry decoded, collision is what turns a drawn stage into a
stage that can be stood on, and the movement parameters from session 3 then
have somewhere to happen.

### 3. `CMTM` (91 files) and `.anmcmd` (2,053).

`CMTM` sits beside `CNOM` under `*.mot.pac/` and shares the shell. `.anmcmd`
is plainly animation *commands* — the events a motion fires, which is what
turns an attack animation into a hitbox at a frame.

### Then

4. **`.psq`** — `FA FA 'SQIR'` then `PART` chunks, the compiled cutscene
   language, 3,011 files. Big, and probably slow.
5. **Name the `ECH` columns.** The types are inferred and the tool reports
   them; the *meanings* are the work. The AI filenames
   ([`RECON.md` §7b](RECON.md)) give every monster an English name for free,
   which makes a monster table readable without an EBOOT.
6. **Settle the frame rate.** Nothing in `CNOM` says whether a frame is 1/30 or
   1/60 of a second. The actor parameters in [`params.md`](params.md) carry
   durations the animations have to match, so the two together should decide
   it.

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
- `CMDL`: skinning; the four-byte attribute at layout byte 2; the middle byte
  of the mesh descriptor's first word; `S8` and `S9` and the 16-byte digests;
  the eight stage grounds whose texture index runs one past their name list.
  All in [`format_cmdl.md`](format_cmdl.md).
- `CNOM`: the `u8` at `+0x04` of a channel; the constant `1000.0` at `0x4C`;
  the `u16 1` at `0x12`; the frame rate. See
  [`format_cnom.md`](format_cnom.md).
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
- `.PTP` (67), `.trg` (163), `.mkc` (2,690), `.CTXT` (1,151, and they open with
  readable ASCII like `id 8910`).
- What the 14 empty `.cpk.patch` stubs would have overlaid, and whether a
  shipped title update exists that fills them.

---

# Log

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
