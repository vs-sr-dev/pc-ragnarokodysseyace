# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — `CMDL`

1,127 files, the geometry, and the last thing between the project and a frame
on screen. The textures now decode ([`format_ctex.md`](format_ctex.md)), so a
mesh with a material reference is a picture.

**Session 4 reconnoitred the container shell.** Start from these facts rather
than from the top; all of them hold on all 1,127 files unless noted.

### What is already known

- **`CMDL` uses the same outer shell as `CTEX`**: `'CMDL'`, `u32` payload size,
  `u32 0x00010005`, `u32` zero. Then `u32 0x10002000` at `0x10`, where `CTEX`
  has `0x1000` and its width. Everything is big-endian.
- **`size + 16` is *not* the file length here** — unlike `CTEX`, where it was on
  every file. The excess is always a multiple of 16 and always at the end
  (`0x40` on 606 files, then `0x70`, `0x80`, `0x50`, …, 36 distinct values).
  File lengths are all 16-aligned. Establish what that tail is before trusting
  any section to end where the directory says: it may be alignment padding, or
  it may be a section the header does not index.
- `0x40` is a **scale vector**: three floats `1.0, 1.0, 1.0` then zero, on all
  1,127.
- `0x50` is a **bounding sphere**: centre `x, y, z` then radius, the radius
  positive on 1,125. One file reads `0, 0, 0, 28.284` — `20 * sqrt(2)`, the
  circumscribed radius of a 40-unit square, which is the kind of number that
  does not arrive by accident.
- `0x60` is **eight `u16` counts**. The first is 7 on every file and the last is
  0 on every file; the middle six vary together and look like per-section
  element counts — `(7, 1, 2, 1, 1, 2, 2, 0)` on 195 files, `(7, 3, 28, 3, 3,
  3, 11, 0)` on 80.
- `0x70` is a float `1.0`, and then at **`0x74` there is an 11-entry `u32`
  section directory**, offsets counted from `0x10` as `CTEX`'s are. The
  eleventh entry equals the payload size on all 1,127 files, so it is the end
  marker and there are ten sections. Entry 0 is `0xb0` on 1,125.
- `0xb0` is a **32-byte NUL-padded name**, printable ASCII on all 1,127 — the
  same field `CTEX` carries at the same offset.
- After the name, 8-byte records of `u16` quads, ascending in their first
  field: `(5,2,3,1) (7,2,5,1) (11,2,9,1) (3,1,1,1) (4,1,2,1) …`.

### What to do, in order

1. **Close the arithmetic first.** Walk the ten sections, check that each ends
   where the next begins, and account for the trailing bytes. Keep the "0
   failures out of 1,127" discipline; it is what has caught every wrong
   assumption so far, including one this session.
2. **Find the vertex buffer by its statistics, not by guessing.** A float
   stream of positions has a signature: values in the range of the bounding
   sphere at `0x50`, a stride that divides the section length exactly, and
   consecutive triples that are close together. Test candidate strides against
   the sphere — a wrong stride puts vertices outside a radius the file itself
   declares.
3. **Then the index buffer**, which is easier: `u16` values all under the vertex
   count, in a section whose length is a multiple of 6 for triangle lists or
   close to `n + 2` for strips.
4. **Then the material link.** The `CTEX` name field at `0x30` is what a
   material would reference, and both formats carry names in the same place.
   `stage.cpk/*/model.pac/ground.pac/` holds a `ground.CMDL` beside the `CTEX`
   files it must be naming; that pairing is the cheapest way in.
5. **Do not skip the eyeball test.** Export an OBJ and look at it. A vertex
   decoder that produces the right count and the wrong stride passes every
   arithmetic check — this session's swapped width and height passed 11,530
   size checks and still drew a comb.

### After `CMDL`

6. **`.map` and `CCLS`** — world layout and collision, 137 + 155 files. With
   `CMDL` and `CTEX` this is the first frame, and it is what the "the numbers
   are real" milestone is waiting on: the movement parameters are known, there
   is just nowhere to move.

7. **`CNOM` motion** (3,043), **`CMTM`** (91) and **`.anmcmd`** (2,053).
   `CNOM` sits beside `CMDL` under `*.mot.pac/`, so the skeleton is probably in
   the model.

8. **`.psq`** — `FA FA 'SQIR'` then `PART` chunks; the payload names its own
   source as `*.psq.ppcut`. 3,011 files. Big, and probably slow.

9. **Name the `ECH` columns.** The types are inferred and the tool reports
   them; the *meanings* are the work. `enemy_gen.bin` shows this can often be
   done from the string pool alone, with no EBOOT.

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
- `CMDL` reconnaissance (above).
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
