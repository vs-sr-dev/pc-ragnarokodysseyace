# TODO

*Read this first at the start of a session. The frame is in
[`STRATEGY.md`](STRATEGY.md), the disc survey in [`RECON.md`](RECON.md).*

---

# Next session — `CTEX`

11,536 files, the largest population on the disc, and the wall in front of any
rendered frame. **Session 3 already reconnoitred the header**; the write-up is
[`RECON.md` §6.5](RECON.md#65-ctex--reconnoitred-not-yet-solved). Start from
these established facts rather than from the top:

### What is already known

- The file is a **16-byte header** then a payload. `u32` at `0x04` is the
  payload size, and `size + 16 == file length` on **11,536 of 11,536** files.
- `u32` at `0x08` is `0x00010005` on every file; `0x0C` is zero.
- In the payload: **`u16` at `0x12` is the height**, **`u16` at `0x14` is the
  width**, both powers of two (16–1024). **`u16` at `0x16` is the pixel
  format.**
- The pixel formats are identified for the mip-free files, because
  `payload - 80 == width * height * bpp` lands exactly:

  | format | bpp | matches |
  |---|---|---:|
  | `0x109` | 0.5 | 1,809 — DXT1 |
  | `0x10F` | 1.0 | 141 — DXT5 |
  | `0x100` | 4.0 | 400, i.e. **every** file of this format — uncompressed 32-bit |
  | `0x107` | 2.0 | 6 — 16-bit |

- So the payload is **80 bytes of sub-header followed by pixels**, and the 48
  bytes between `0x20` and `0x50` have not been looked at.

### What to do, in order

1. **The mip chain.** 9,180 files do not match the flat formula, and that is
   the whole remaining problem. Concrete case to start from: a 128x32 DXT1 with
   `u32 @0x1C == 0x1050000` occupies 2,560 payload bytes. Base level is 2,048.
   The remainder is 512 — exactly one more level, not the 712 a full chain to
   1x1 would need. So either the chain stops early, or `0x1C` says how many
   levels there are. Test: for every file, try `sum of levels for n in 1..8`
   and see which `n` closes, then correlate `n` against `0x1C`. If that
   correlation is clean the format is done.
2. **Swizzling.** PS3 RSX textures are frequently swizzled (Morton order), and
   DXT blocks may be stored linearly while an uncompressed surface is not. The
   `0x100` files are the ones to test on — 400 files, all with exact sizes, so
   any decode error is visible immediately as a scrambled image rather than as
   a size mismatch.
3. **Write `tools/ctex.py`** with the same shape as the other readers: a
   `check` command that validates the arithmetic over every file and reports
   what did not close, plus `info` and a PNG export for eyeballing. Keep the
   "0 failures out of N" discipline — it is what has caught every wrong
   assumption so far.
4. **Do not skip the eyeball test.** A texture decoder that produces the right
   number of bytes and the wrong picture passes every arithmetic check. Export
   a handful — `misc.cpk/logo.pac/ui_logo_gravity.ctex` is a known logo and
   will be obviously right or obviously wrong.

### After `CTEX`

5. **`CMDL` / `.map` / `CCLS`** — geometry, world layout, collision. 1,127 +
   137 + 155 files. With `CTEX` this is the first frame, and it is what the
   "the numbers are real" milestone is waiting on: the movement parameters are
   known, there is just nowhere to move.

6. **`.psq`** — `FA FA 'SQIR'` then `PART` chunks; the payload names its own
   source as `*.psq.ppcut`. 2,992 files. Big, and probably slow.

7. **`CNOM` motion** (3,043) and **`.anmcmd`** (2,053).

8. **Name the `ECH` columns.** The types are inferred and the tool reports
   them; the *meanings* are the work. `enemy_gen.bin` shows this can often be
   done from the string pool alone, with no EBOOT.

---

## Deferred, with reasons

- **EBOOT decryption** (Phase 3). Load-bearing here in a way it was not on the
  sister project, but everything above is in the clear, and the PC-3Ddot
  experience is that facts get postponed to the disassembler and then found in
  a filename. Nothing on the current list needs it.
- **`ELBN`** (379 blocks) — unidentified, no consumer waiting.
- **Audio and video** — CRI Atom and PAMF are both well-trodden formats.
- **Publishing to GitHub** — the repository is written and the BYOA policy is
  in `.gitignore`, but nothing has been committed; the working directory is not
  a git repository yet.

## Open, unowned

- `CTEX`: the 48 unexamined sub-header bytes; the mip chain; swizzling.
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
- `.PTP` (18), `.trg` (163), `.mkc` (2,690), `.CTXT` (1,151, and they open with
  readable ASCII like `id 8910`).
- What the 14 empty `.cpk.patch` stubs would have overlaid, and whether a
  shipped title update exists that fills them.

---

# Log

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
- `CTEX` reconnaissance (above) and [`RECON.md` §6.5](RECON.md).

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

- `tools/iso.py` — UDF 2.50 reader ported from PC-3Ddot, sets redefined, and a
  **multi-extent index** (the inherited version would have written a silently
  corrupt `sound.cpk`). 109 files, 5.4 GB, manifest computed.
- `tools/cpk.py` — CRI CPK: `@UTF` tables, `TOC`/`ITOC`, CRILAYLA. 20
  containers, 2,450 entries, 0 errors.
- `tools/arc.py` — `ARC`: 1,544 of 1,544 consistent, 13,820 entries, 13,798
  blocks each ending on its declared byte.
- `docs/RECON.md`, `docs/STRATEGY.md`, `README.md`, `.gitignore` (BYOA).
