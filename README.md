# PC-ROA

Documentation and tooling towards a native PC reimplementation of
**Ragnarok Odyssey ACE** (PS3, 2013 — the expanded edition of *Ragnarok
Odyssey* for PS Vita).

This repository contains **no game content**. It contains a disc reader, format
documentation, and the tools that produced it. To use any of it you supply your
own copy of the disc.

## Status

Sessions 1-10 (2026-08-22): the container stack is open end to end, the game's
database, text and actor parameters are readable, and the textures, geometry,
skinning, motion, stage collision, the animation event lists, the world layout
and **the script layer** decode. A character can be drawn with its own textures
on it, posed by the game's own animations and with the mesh following the
skeleton; a stage reads as a floor plan with its fences, its spawn points, its
monster generators and the scripts its doorways run. An attack says which bone
it swings from and how hard. The world's two constants are settled: **one unit
is one metre and one frame is 1/30 of a second**, so the game's own movement
numbers are dimensional at last.

**`.psq` is Squirrel 2.2 bytecode**, debug tables and all, so the cutscenes,
the quest logic and six bosses' AI decompile with the authors' own variable
names and source lines.

```
ISO (UDF 2.50)   ->      109 files, 5.4 GB      tools/iso.py
  20 x CPK       ->    2,450 entries            tools/cpk.py    0 errors
  1,544 x ARC    ->   13,820 entries            tools/arc.py    0 errors
  + nested CPK, cmp/lzma, cmp/zlib
                 ->   32,727 leaves, 2.0 GB     tools/assets.py

ECH tables       ->    4,941 files, 58,534 rows tools/ech.py    0 errors
TXT messages     ->       76 files, 25,288 msgs tools/rmsg.py   0 errors
JSON parameters  ->       89 files,  1,069 recs tools/params.py
CTEX textures    ->   11,536 files, 5 formats   tools/ctex.py   0 errors
CMDL geometry    ->    1,127 files, 5.6M tris   tools/cmdl.py   0 errors
CNOM motion      ->    3,043 files, 3.0M keys   tools/cnom.py   0 errors
CCLS collision   ->      155 files, 107k tris   tools/ccls.py   0 errors
CMTM material    ->       91 files, 1,388 keys  tools/cmtm.py   0 errors
.anmcmd events   ->    2,053 files, 10,175 cmds tools/anmcmd.py 0 errors
  hit records    ->    6,193 hits, 4,768 bones  all resolving
  impact sounds  ->       25 of 26 cue ids       named in common.acb
ATIH + fences    ->      163 stages, 5,934 marks tools/stage.py 0 errors
ELBN parameters  ->      707 files, 318 names   tools/elbn.py   0 errors
Squirrel script  ->    3,011 files, 315k insns tools/psq.py    0 errors
  engine API     ->      289 native functions  named and counted
```

Formats are documented in [`docs/`](docs): [the disc
survey](docs/RECON.md), [`ECH`](docs/format_ech.md),
[`TXT`](docs/format_rmsg.md), [`CTEX`](docs/format_ctex.md),
[`CMDL`](docs/format_cmdl.md), [`CNOM` and `CMTM`](docs/format_cnom.md),
[`CCLS`](docs/format_ccls.md), [the stage layout](docs/format_stage.md),
[the units](docs/units.md),
[`ELBN`](docs/format_elbn.md), [`.anmcmd`](docs/format_anmcmd.md), [the script
layer](docs/format_psq.md), [the actor
parameters](docs/params.md). The plan is in
[`docs/STRATEGY.md`](docs/STRATEGY.md); what is next is in
[`docs/TODO.md`](docs/TODO.md).

The 438 `.par` AI parameter files are unread, the `ELBN` records are
addressable by name but not described field by field, and thirty of the
fifty-two `.anmcmd` opcodes still have no correlation — though the two
commonest are now read, and they are the hitbox.

`.map`, listed here for six sessions as the world layout, turned out to be the
minimap; the layout is `hta.bin`, `borderline.bin` and `trigger.trg`.

## BYOA

Bring Your Own Assets. Nothing extracted from the disc is redistributed here —
no textures, no models, no text, no audio, no executable. What *is* published:

- the tools, which are original code;
- format documentation, which describes structure rather than content;
- `tools/manifest.tsv`, the fingerprint of the supported disc (path, size,
  sha256), so that a copy can be identified and verified before use. This is
  the same thing devilutionX and Ship of Harkinian publish.

`extract/` and everything derived from the disc stays local. See
[`.gitignore`](.gitignore), which states the policy per file type.

The reference disc is **Ragnarok Odyssey ACE (USA)**, title id `NPWR04119_00`.

## Tools

Python 3.11+, no third-party dependencies.

```
python tools/iso.py index                     read the UDF tree
python tools/iso.py sets                      what a full extract/ means
python tools/iso.py manifest                  compute the disc fingerprint
python tools/iso.py extract [set ...]         extract into extract/
python tools/iso.py verify [set ...] [--deep] check extract/ against it

python tools/cpk.py survey <dir>              census every CPK
python tools/cpk.py list|info|tree|magic <cpk>
python tools/cpk.py unpack <cpk> <dir>

python tools/arc.py check <dir>               verify every ARC in every CPK
python tools/arc.py list|magic <file|dir>
python tools/arc.py unpack <file> <dir>

python tools/assets.py census <dir>           every leaf, grouped by magic
python tools/assets.py find <dir> <glob>      locate a leaf at any depth
python tools/assets.py unpack <dir> <out>     write the whole tree to disk

python tools/ech.py check|survey <dir>        the tables
python tools/ech.py info|dump <dir> <name>    one table, with inferred types
python tools/ech.py grep <dir> <text>         which tables mention a string

python tools/rmsg.py check|attrs <dir>        the text
python tools/rmsg.py list <dir> <name>        the messages of one file
python tools/rmsg.py grep <dir> <text>

python tools/ctex.py check|survey <dir>       the textures
python tools/ctex.py info|find <dir> <name>  one texture, or a search
python tools/ctex.py png <dir> <name> <out>  decode to PNG
python tools/ctex.py unpack <dir> <out>      decode many, mirroring paths

python tools/cmdl.py check|survey <dir>       the geometry
python tools/cmdl.py info|nodes|meshes <dir> <name>
python tools/cmdl.py draws <dir> <name>      the node/material/mesh draw list
python tools/cmdl.py skin <dir> <name>       the bone palettes and the weights
python tools/cmdl.py locators <dir> <name>   the attachment points
python tools/cmdl.py gait <dir> <name> <motion>
                                             the planted foot's speed
python tools/cmdl.py obj <dir> <name> <out> [motion frame]
                                             export Wavefront OBJ, posed

python tools/cnom.py check|survey <dir>       the motion
python tools/cnom.py info <dir> <name>       one animation, per bone
python tools/cnom.py track <dir> <name> <bone>
python tools/cnom.py pose <dir> <name> <frame>

python tools/cmtm.py check|survey <dir>      the material animation
python tools/cmtm.py info <dir> <name>       one file, per material
python tools/cmtm.py track <dir> <name> <material>

python tools/ccls.py check|survey <dir>      the stage collision
python tools/ccls.py info|dump <dir> <name>  one stage
python tools/ccls.py obj <dir> <name> <out>  export the ground as OBJ

python tools/stage.py check|survey <dir>      the world layout
python tools/stage.py info <dir> <stage>     markers, fences and triggers
python tools/stage.py markers|triggers <dir> <stage>
python tools/stage.py grep <dir> <text>      which stages mention a name
python tools/stage.py obj <dir> <stage> <out>  the layout as OBJ

python tools/elbn.py check|survey <dir>      the named parameters
python tools/elbn.py names <dir> <file>      the entries of one file
python tools/elbn.py dump <dir> <file> [entry]
python tools/elbn.py field <dir> <name>      where a parameter occurs

python tools/anmcmd.py check|survey <dir>    the animation commands
python tools/anmcmd.py census <dir>          every opcode, with its size
python tools/anmcmd.py list|dump <dir> <name>  one list, frame by frame
python tools/anmcmd.py hits <dir> <name>     the hit records, with bone names
python tools/anmcmd.py bones <dir>           how many hits name a real bone

python tools/params.py census|tiers <dir>     the actor parameters
python tools/params.py classes <dir>          the six player classes compared
python tools/params.py show|diff <dir> <name> one actor, or one variant
python tools/params.py field <dir> <name>     where a field occurs and its range
```

Point `iso.py` at your image with `--iso`, or drop it in the repository root
under its original name. The readers above take either the directory holding
the `.cpk` files or the tree that `assets.py unpack` writes; the second is much
faster, since decompressing 1.7 GB of CRILAYLA in Python is not.

Each tool's module docstring is the format specification; they are meant to be
read.

## Licence

MIT, see [`LICENSE`](LICENSE). It covers the tools and the documentation in
this repository — which is all this repository contains. It says nothing about
the disc you supply, which is not ours to licence.

## Not affiliated

*Ragnarok Odyssey ACE* is the property of its rights holders (GungHo Online
Entertainment, Game Arts). This project is unaffiliated, non-commercial, and
distributes none of their work.
