# `ELBN` — the named-parameter container

**Status: solved as a container.** 707 files, 3,983 entries, **318 distinct
parameter names, 13,437 relocations, 0 unreadable**, every check closing on
every file. Reader: [`../tools/elbn.py`](../tools/elbn.py).

`ELBN` sat on the deferred list for six sessions as *"unidentified, no consumer
waiting"*. It is the format on this disc that **names its own contents**: the
top level of every file is a sorted table of `(name, offset, size)`, so every
value arrives carrying the identifier the engine's own C++ used for it.

That makes it the binary counterpart of the `.json` actor parameters in
[`params.md`](params.md) — the same job, for everything the JSON does not
cover. Thirteen of the files are called `objbin.cpp`, which is a build step
that forgot to rename its output, and is as good as a comment.

## The shell, again

The same 16-byte shell as [`CMDL`](format_cmdl.md), [`CNOM`](format_cnom.md),
`CMTM` and [`CTEX`](format_ctex.md) — and, like the first three and unlike
`CTEX`, a **`POF0` relocation table** after the payload. That is the fifth
member of the family, and the trick from `CMDL` works unchanged: *these* words
hold pointers and no others, so nothing about the structure has to be guessed.

```
file length == 16 + payload + 16 + POF0 payload + 16

0x00  'ELBN'
0x04  u32   payload size
0x08  u32   0x00010000          not the 0x00010005 the others carry
0x0C  u32   zero
--- the payload begins here; every offset below is relative to it ---
0x00  u32   entry count
0x04  count * 12 bytes:
      +0x00  u32   name offset
      +0x04  u32   data offset
      +0x08  u32   data size
then the names and the data, and then POF0
```

Every one of the 707 files passes all of it on the first reading: the count is
sane, every name offset lands on a NUL-terminated ASCII string, every data
region lies inside the payload, **no two data regions overlap**, and every
relocation names a word inside the payload holding an offset that is also
inside the payload.

**The entries are sorted by name on all 707 files.** That is what a table meant
to be looked up by name looks like, rather than one written in whatever order
somebody declared things — and it is a free check that the table has been read
correctly, since a wrong stride would scramble the order.

## The values, and what can be known about them

`ELBN` says how big a value is and what it is called. It does **not** say what
type it is, and there is no type field anywhere in the format. So a reader can
only do what [`ech.py`](format_ech.md) does with its columns, which is infer.
Three things are knowable without guessing:

- **which words are pointers**, because `POF0` says so;
- **which words are plausible floats**, on the usual exponent test;
- **what a pointer points at**, by following it.

That is enough to render a value as structure, and `elbn.py dump` does. It is
not enough to name the fields inside a record, and that stays open.

### The shapes that recur

**A count and a pointer, sometimes with a stride.** `mot_param.bin` holds
exactly two entries: `motionDataHeader`, twelve bytes reading `(87, ptr, 16)`,
and `_dataA`, whose size is `87 * 16` to the byte. `count * stride == size` on
all 19 of them.

That one is **the motion table**, and the disc proves it. Each 16-byte row
begins with a motion id, and for the twelve player classes every id in the
table is a `CNOM` animation sitting in the same `.pac` — 87 of 87 for `fas`,
91 of 91 for `fcl`, 115 of 115 for `fmg` — with no id left over on either side.
`fas` row 211 is `fas211walk`, the walk cycle sessions 6 and 7 posed a
character with. The rest of the row is a `u16` of flags, four zero bytes, and
five bytes that are all 100.

**A pointer to a name.** `stage_param` is how a stage reaches its lights.
`010_01_01`'s copy is 48 bytes of counts and pointers leading to one fog
record, four ambient lights and six directional ones, each ending in a pointer
to a string an artist chose: `st_fog_0`, `ch_amb_1`, `mc_dir_2`, `bm_dir_1`.
A directional light is 28 bytes — name, flags, colour, intensity, and a
three-float direction.

**Four bytes that are four bytes.** `shadow_param` is `0a 14 28 c8`; read as a
float that is 1.4e-32.

### Packed RGBA is the trap here that it was in `CMTM`

A stage's directional lights carry their colour as a word — `0xfaebc8ff` is a
warm sun, `0x82d7afff` a green bounce. Most such words fall outside the float
range, so the inference calls them integers and the eye catches them. One does
not: `ch_dir_2` on `010_01_01` is `0x46d7b4ff`, which is a perfectly plausible
27610.5 and is in fact `(70, 215, 180, 255)`.

`dump` therefore prints the RGBA reading of **any** word ending in `ff`
alongside whatever it inferred, and leaves the choice to the reader. This is
the same failure `CMTM` produced in session 7, where the wrong reading came out
at -4e37 and was obvious; here it comes out at 27610.5 and is not.

## Where it is used

```
trace_par.bin       207   ref_tbl, par_tbl
stageparam.bin      154   the stage's own parameters; see format_stage.md
objbin.bin           89   clip_distance, col_hit, jostle_data, se_hitlevel_tbl
stobjbin.bin         89
mot_param.bin        60   motionDataHeader and _dataA, per character class
bowstring.bin        25
objbin.cpp           13
command_data.bin     12   with select_action, select_target, target_data
select_action.bin    12
select_target.bin    12
target_data.bin      12
                          and 13 more files, one or two of each
```

`command_data.bin`, `select_action.bin`, `select_target.bin` and
`target_data.bin` sit in `ai.pac` beside the `AI_B17_Loki.par` files that
[`RECON.md` §7b](RECON.md) already used to name the monsters. That is where the
AI's own tables are, and their names — *select action*, *select target* — say
what an AI tick does.

And `job.cpk/<class>/objbin.bin` is the **combat parameter set of a player
class**, with the names spelled out: `backStabParam`, `soulBreakerParam`,
`soulBreakerBulletParam`, `s_combo_finish_inf`, `s_combo_graph`,
`s_quick_dash_par`, `s_tension_revise_hp_tbl` and three more `s_tension_*`
tables, `s_breathing_prob`, `eff_hitlevel_tbl`, `se_hitlevel_tbl`. That is the
same territory the JSON in [`params.md`](params.md) covers, in a second file
per class, and the two have not been compared.

## The vocabulary

318 names. The largest populations, with the file they live in — which is what
says who the parameter belongs to, since the name alone rarely does:

```
par_tbl, ref_tbl                     207   trace_par.bin
stage_param, waterparam              155   stageparam.bin, per stage
character_clipping_distance          154   stageparam.bin
shadow_offset, shadow_param          154   stageparam.bin
statusData, statusDataHeader          89   monster.cpk/*/objbin.bin
pgs_data                              88   monster.cpk/*/objbin.bin
region_data, region_data_tbl          83   monster.cpk/*/objbin.bin
s_region_group_data, ..._tbls         82   monster.cpk/*/objbin.bin
se_hitlevel_tbl                       76   both objbin kinds
_dataA, motionDataHeader              61   mot_param.bin, per class
jostle_data                           43   objbin.bin
chuck_off_param                       41   objbin.bin
ceiling_data                          36   objbin.bin
field_camera_data, manual_camera_data 24   monster.cpk/*/objbin.bin
bowstring_data                        25   bowstring.bin
act_cmd_00 .. act_cmd_15              12   ai.pac/command_data.bin
lockon_camera_data                    12
s_abnormal_ef_inf                     17
```

**A name is not a meaning.** `region_data` sits in `monster.cpk/<monster>/
objbin.bin`, one per monster, so it is not a spawn region on a stage — it is
whatever a monster has regions of. The camera entries are per-monster too. The
temptation to read the vocabulary as a specification is the same trap the
opcode names in [`.anmcmd`](format_anmcmd.md) present, and the method that
works on it is the same one `params.md` used: correlate against something else.

`elbn.py survey` prints all 318 with the sizes each takes; `elbn.py field
<name>` prints every file that carries one.

## Still open

- **Every field inside every value.** The container is solved; the records are
  not. `stage_param`'s light and fog records are the only ones read far enough
  to name anything.
- Whether `objbin.bin` is what the stage's `obj*` markers place. It carries
  `clip_distance`, `col_hit` and `jostle_data`, which is what a pushable crate
  needs, and the three `objbin.cpp` files sit in `kibako.pac` (crate),
  `kibako_bomb.pac` and `taru.pac` (barrel).
- What the five 100s at the tail of a motion row are a percentage of.
- `trace_par.bin`'s `par_tbl` and `ref_tbl` — 207 files, the largest
  population, and no guess.
- **The payload tail.** Past the last byte any entry, name or pointer target
  reaches, 447 files hold nothing but zeros and 260 hold data — the
  continuation of arrays whose length is declared by the count beside their
  pointer rather than by any extent in the file. A reader that follows counts
  gets there; one that only measures does not. `dc_demo_data.bin`'s tail is the
  string `app0:movie/dictionary/stg_173.mp4`, which is a PS3 filesystem path
  and the only one seen so far in an `ELBN`.
- `col_hit`, 1,172 records of 32 bytes across 100 files. Its leading word is a
  small integer on most records and the locator id `1000` — the hip, per
  [`CMDL`](format_cmdl.md) — on 53, so it is not one thing, and the mixture
  is not explained.
