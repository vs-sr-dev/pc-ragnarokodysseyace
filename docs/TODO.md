# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — motion, and the rest of a frame

`CMDL` is read ([`format_cmdl.md`](format_cmdl.md)) and a model draws with its
own textures on it. Three things stand between that and a scene.

### 1. `CNOM` — motion. 3,043 files.

The most valuable, because the actor parameters from session 3 describe
movement that has nowhere to happen. `CNOM` sits beside `CMDL` under
`*.mot.pac/`, so start by checking whether it opens with the same shell:
`'CNOM'`, `u32` payload size, `0x00010005`, zero, and a `POF0` relocation table
at the end. If it does — and `CTEX`, `CMDL` and `CMTM` all do — then the
section directory and the name tables are probably the same shape too, and the
work is naming sections rather than finding them.

**Use `POF0` first.** It says which words are pointers, which is the single
thing that made `CMDL` fall open in an afternoon. Decode it, list the
relocations, look at what they point at, and the structure draws itself.

The bone names are already in hand: `CMDL`'s `S5` names every node, and a
motion track has to key on those.

### 2. Skinning, which finishes `CMDL`.

Bits 8 and 9 of the vertex type mark two four-byte attributes on the character
bodies — bone indices and weights, 931 meshes. Rigid models already draw
correctly, so this only matters once there is motion to drive it, but it is
cheap: four bytes of indices into the node table and four of weights, and the
weights should sum to one, which is a test the file will either pass or fail.

### 3. `CCLS` and `.map` — collision and world layout. 155 + 137 files.

`CCLS` files are named `<stage>.col` and sit in `param.pac` beside `hta.bin`
(`ATIH`, most likely hit areas). With ground geometry decoded, collision is
what turns a drawn stage into a stage that can be stood on.

### Then

4. **`.psq`** — `FA FA 'SQIR'` then `PART` chunks, the compiled cutscene
   language, 3,011 files. Big, and probably slow.
5. **`.anmcmd`** (2,053) and **`.mkc`** (2,690).
6. **Name the `ECH` columns.** The types are inferred and the tool reports
   them; the *meanings* are the work. `enemy_gen.bin` shows this can often be
   done from the string pool alone, with no EBOOT. The AI filenames
   ([`RECON.md` §7b](RECON.md)) give every monster an English name for free,
   which makes a monster table readable without one.

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
