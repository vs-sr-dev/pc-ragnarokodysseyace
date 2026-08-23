# `.PTP` — the particle effect banks

**Status: container solved; the addressing solved, proven three ways, and
all three categories now named; the interior of a block open.** 70 files,
three of them zero bytes; **67 read,
1,108 `PTB` blocks, 2,002 resources, 4,451 resource references, 0 unreadable**,
with sixteen arithmetic identities closing on every file. Reader:
[`../tools/ptp.py`](../tools/ptp.py).

This is where an effect comes from. A [`.anmcmd`](format_anmcmd.md) opcode 10
spawns one on a frame of an animation, an [`ELBN`](format_elbn.md) parameter
block lists which ones an actor has, and a stage's [`.psq`](format_psq.md)
starts them by hand — and **all three address an effect the same way: as a
pair, a category and a slot.**

The disc says that in its own words. `stage.cpk/050_02_03/param.pac` declares
the record and then uses it:

    class EffData { _hta_name; _eff_cate; _eff_id; _rnd_radius; _y_offset;
                    _sec_fix; _sec_rnd; _cue_id; _work }

    handle = effStart(data._eff_cate, data._eff_id)
    effSetPos(handle, x, y, z)
    effSetRot(handle, 0, cfGetRandI(65536), 0)
    cfSndPlayStgSE3D(-1, data._cue_id, 0, x, y, z)

    EffData('ef_fire01', 1, 8, 0, -8.5, 5, 5, 3, 190)
    EffData('ef_fire03', 1, 9, 2, -8.5, 5, 5, 2, 188)

Category 1, slots 8 and 9 — and slots 8 and 9 of
`stage.cpk/050/effect.pac/effect.PTP` are the only two blocks in that file that
name `anm_ef_M_vlcn001.txx`, a volcano. The markers they are placed on are
called `ef_fire01` to `ef_fire06` and the rest of the file is `ef_M_hinoko001`
— embers. Script, marker name, slot number and asset name all say the same
thing, which is the whole check.

## The container

Five tables and then the payload. The header gives four of the five offsets and
the two counts; the fifth is the first table, always at `0x40`.

```
0x00  u32   A   the block directory        always 0x40
0x04  u32   B   the resource directory
0x08  u32   E   the reference list
0x0C  u16   nA  entries in A
0x0E  u16   nB  entries in B
0x10  'PTCP'
0x14  u32   1   version
0x18  u32   C   one u32 per A entry
0x1C  u32   D   one u32 per B entry
0x20  32 zero bytes
```

Each table ends exactly where the next begins, and that is what says the five
are five and not four or six:

```
A + 8 * nA == B      B + 8 * nB == C
C + 4 * nA == D      D + 4 * nB == E
```

An entry of `A` or `B` is

```
+0x00  u32   offset of the block, or zero for an empty slot
+0x04  u16   first, where this block's run in E begins
+0x06  u16   zero          on all 3,616 entries
```

and the matching word of `C` or `D` is that block's **size in bytes,
little-endian** — the one field on this big-endian disc that is not, and the
reason the sizes read as nonsense until you turn them round. An empty slot is
zero in both tables at once, on all 67 files.

`A` is **sparse and the sparseness is the point.** `misc.PTP` declares 161
slots and fills 137; `job.cpk/sw/effect.PTP` declares 76 and fills 24, in three
runs at 1..16, 31..32 and 60..71. Nothing is compacted, because **the slot
number is the effect's name** and the gaps are effects that were cut.

`E` is a `u16` array. A block's run starts at its `first` and ends where the
next used block's run starts; the values index `B`. The list is padded to the
next sixteen bytes and the last block's run is not declared anywhere — which
matters less than it sounds, because of the identity below.

## The identity that binds the two directories

A `PTB` names the files it uses in the clear — `ef_I_circle002.ctex`,
`anm_ef_I_smoke001_roop.txx`, `ef_h_z21_19_cirl000.rnx` — and the container
indexes the same files through `E`.

**Every non-final `PTB` names exactly as many distinct files as it has distinct
references: 1,041 of 1,041.**

That is what makes this a reading rather than a plausible story. The strings
are written by the effect authoring tool and the index by the packer, they
never disagree, and between them they say the run lengths are right. It also
gives the last block its length for free, since its run is what its own strings
say it is.

## What a resource is

| | |
|---|---:|
| `CTEX` textures | 790 |
| `ARC` archives | 736 |
| no magic — the first word reads as a float | 476 |

The nameless ones are raw curve data; the blocks that use them name them
`.rnx`. Nothing needs a name table: the consumer carries its own name.

## The addressing, and where it is proven

**Category 0 is `misc.cpk/misc.PTP`, the common bank. Category 1 is the
actor's or the stage's own file.**

The proof is `eff_vari_tbl`, an `ELBN` entry in eighteen monsters'
`objbin.bin`. It is a list of `(category, slot)` pairs — a monster's effect
variations, one row per variation. **All 104 pairs in all 18 files land on a
slot that exists** under that reading: `z18` and `z20` reach only into the
common bank, `z11` and `z14` only into their own, `z27` alternates between the
two in the same row. `ptp.py refs` prints it.

Three consumers, three files, one addressing:

| where | how it is written | category |
|---|---|---|
| `050_02_03.psq` | `effStart(_eff_cate, _eff_id)` | 1, its own stage bank |
| `<monster>/objbin.bin` | `eff_vari_tbl`, pairs | 0 and 1 |
| `job.cpk/<class>/objbin.bin` | `eff_hitlevel_tbl`, pairs | 2 — see below |

## Category 2 is not a bank

*Session 17.* `eff_hitlevel_tbl` in each of the six classes' `objbin.bin` is
three or thirty-three rows of *four* `(2, id)` pairs followed by
`(0, level << 16 | 1)`. The sword's ids are 101, 102, 103 and the bow's are
110, 111, 112, 120, 121, 122, … 250, 251, 252. Those numbers reach 252, no
`PTCP` on the disc has that many slots, and a search of all 32,600 leaves for
the magic finds `PTCP` in 67 `.PTP` and nowhere else — because **category 2 is
the class's own [`effect.bin`](format_effect.md), addressed by row id**, and
that is a different kind of table entirely. **96 of 96 pairs resolve**;
`python effect.py hitlevel extract/tree` prints it.

The reading of the ids survives intact and is now confirmed from the other
side: `fht`'s eleven triples are eleven weapon kinds by three hit levels, each
triple is *one* slot of `job.cpk/ht/effect.PTP`, and the three rows differ
only in their scale — 0.5, 0.8 and 1.0. **The hit level is the scale**, and
the same three numbers come out of all twelve player tables.

So the addressing is three banks and a table, not four banks:

| category | what it names |
|---|---|
| 0 | `misc.cpk/misc.PTP`, the common bank |
| 1 | the actor's or the stage's own `effect.PTP` |
| 2 | the actor's own `effect.bin`, by row id — which then names a `(0, slot)` or `(1, slot)` of its own |

## Still open

- **The inside of a `PTB`.** The header is read far enough to walk it —
  `'PTB\0'`, `u16 2`, `u16 11`, an emitter count, a header size of `0x40`, then
  five `(count, offset)` pairs — but not one field of an emitter is described.
  Nobody needs it until something renders.
- **`.anmcmd` opcode 10's number does not resolve here**, and the reason is in
  [`format_anmcmd.md`](format_anmcmd.md): it is not a slot and not a global
  registry, and no table on the disc contains it.
- **Three `.PTP` are zero bytes** — `stage.cpk/{060,090,900}/effect.pac` — the
  same kind of empty stub as the fourteen empty `.cpk.patch`.
