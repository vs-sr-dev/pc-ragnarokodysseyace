# PC-ROA

Documentation and tooling towards a native PC reimplementation of
**Ragnarok Odyssey ACE** (PS3, 2013 — the expanded edition of *Ragnarok
Odyssey* for PS Vita).

This repository contains **no game content**. It contains a disc reader, format
documentation, and the tools that produced it. To use any of it you supply your
own copy of the disc.

## Status

Sessions 1-16 (2026-08-23). **Something runs, and now it has feet.** A capsule
with the game's own acceleration, run speed, turn rate and radius crosses the
first field of the game in 405 frames - 13.5 seconds - without leaving the
collision mesh, and walks 135 stages, 127 of them with the body on legal
ground for every frame, at 5.05 m/s against 5.10 flat out. That is [milestone
1](docs/milestone_numbers.md), *"the numbers are real"*, and
[`engine/`](engine) is the first code here that is not a reader.

It was worth doing for its own sake and it also paid: three things fell out
that no further reading would have produced. The spawn marker faces its own
exit, which settles the heading convention the disc never declares. `hta.bin`
and `<stage>.col` agree to a centimetre across 1,432 markers, a join nobody
had reason to make while both were only being read. And a `borderline` is a
closed loop - 105 of 145 stages - which had been an open question since
session 8.

Session 16 gave that capsule a skeleton. An animation played on the walking
body puts its **planted foot three millimetres above the collision mesh**, and
the pose is checked against the disc rather than against itself: `.mkc`'s
footfall opcode fires within a frame of the skeleton landing a foot on **four
firings in five, against one in four** for a frame of the same animation
picked at random. It also paid twice over. The `.mkc` sound record's last
unread field, which says where on a body a sound comes from, turns out to be a
**`CMDL` locator id** — 2,715 of 2,716 resolve, and the numbering then reads
itself: the head carries the voice, the hands carry the cues that end `_L` and
`_R`, and on a quadruped the hands are the front feet. See [the
pose](docs/pose.md).

Underneath that, the container stack is open end to end and the game's
database, text and actor parameters are readable; the textures, geometry,
skinning, motion, stage collision, animation event lists, world layout,
particle banks and **the script layer** all decode. A character can be drawn
with its own textures on it, posed by the game's own animations and with the
mesh following the skeleton; a stage reads as a floor plan with its fences,
its spawn points, its monster generators and the scripts its doorways run. An
attack says which bone it swings from and how hard. The world's two constants
are settled - **one unit is one metre and one frame is 1/30 of a second** - so
the movement numbers are dimensional.

**`.psq` is Squirrel 2.2 bytecode**, debug tables and all, so the cutscenes,
the quest logic and six bosses' AI decompile with the authors' own variable
names and source lines. Those six scripts are the oracle that opened **every
monster's AI**: the weighted action tables, the rules that pick one of them and
the parameters the chosen action runs with. The rules read as conditions on HP,
range, anger, the target's stance and sixty-odd other terms, because one
function in those scripts turned out to be the game's own dispatch for the
whole vocabulary. **And an action id names a motion** - add 401 and it is the
`atN.CNOM` the monster plays - so the AI and the animation layer are joined.
The twelve mercenary classes are the same shape one layer up, and their
command lists turn out to be **button presses** into the combo tree the player
drives.

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
  hit geometry   ->        6 shapes; 2,194 of 2,253 second bones on one chain
  impact sounds  ->       25 of 26 cue ids       named in common.acb
ATIH + fences    ->      163 stages, 5,934 marks tools/stage.py 0 errors
ELBN parameters  ->      707 files, 318 names   tools/elbn.py   0 errors
Squirrel script  ->    3,011 files, 315k insns tools/psq.py    0 errors
  engine API     ->      285 native functions  named and described
  their arguments->   10,787 message ids, 1,220 motion ids, every cue id
                                                 resolving in its own table
monster AI       ->      228 files, 6,550 rules tools/ai.py     0 errors
  action tables  ->    3,269 groups, 19,707 weighted actions
  condition terms->       66 of 76 named, 27,862 of 29,100 instructions
  AI parameters  ->      438 .par, 4 record kinds, every sentinel exact
  action -> motion->   1,109 of 1,423 ids name a motion in their own pac
mercenary AI     ->       12 classes, 48 tables tools/merc.py   0 errors
  probability    ->      454 tables, all summing to exactly 10000
  command lists  ->      350 lists, 1,549 button presses
PTCP effects     ->       67 files, 1,108 blocks tools/ptp.py    0 errors
  resources      ->    2,002 assets, 4,451 references, named in the clear
  addressing     ->      104 of 104 (category, slot) pairs resolving
  category 2     ->       96 of 96 ids, and it is not a bank at all
effect.bin       ->       69 files, 3,918 rows  tools/effect.py 0 errors
  the .PTP slot  ->    2,410 of 2,434 motion rows on a filled block
  the locator    ->      455 of 457 on the actor's own CMDL S4
  a stage marker ->    1,483 of 1,484 ambient rows on a marker of their room
.mkc sound track ->    2,690 files, 19,724 recs tools/mkc.py    0 errors
  sound cues     ->    7,540 of 7,608 references naming a cue in an .acb
  effects        ->    4,187 of 4,190 references, read as a row id
PAMF movies      ->       46 files, 22.7 minutes tools/pam.py    0 errors
  video          ->    720p29.97 MPEG-2, and no audio track on any of them
CRI Atom audio   ->      274 banks, 7,756 waves tools/awb.py    0 errors
  naming         ->    7,756 of 7,756 reached by a cue with a name
  decoding       ->    7,756 of 7,756 to WAV, and not one file encrypted
  a frame -> a wave->    7,592 of 7,608 .mkc references, the rest empty cues

a capsule runs   ->      135 stages walked   engine/run.py  127 clean
  one crossing   ->      405 frames over 010_01_01, 13.5 s at a run
  speed          ->     5.05 m/s achieved against 5.10 flat out
  markers        ->    1,432 obj and appear standing on the mesh to 1 cm
  fences         ->      105 of 145 stages closing into a loop

a body has feet  ->    0.003 m from the planted foot to the mesh, walking
  the footfall   ->    79.5% of 650 .mkc footfalls within a frame of the
                       skeleton landing one, against 25.2% at random
  the gait       ->       23 of 24 player walk and run cycles within 5 mm
                       a frame of walk_sp and run_sp
  sound emitters ->    2,715 of 2,716 resolving to a CMDL locator id,
                       and 508 of 514 front/rear step cues agreeing with it
```

Formats are documented in [`docs/`](docs): [the disc
survey](docs/RECON.md), [`ECH`](docs/format_ech.md),
[`TXT`](docs/format_rmsg.md), [`CTEX`](docs/format_ctex.md),
[`CMDL`](docs/format_cmdl.md), [`CNOM` and `CMTM`](docs/format_cnom.md),
[`CCLS`](docs/format_ccls.md), [the stage layout](docs/format_stage.md),
[the units](docs/units.md),
[`ELBN`](docs/format_elbn.md), [`.anmcmd`](docs/format_anmcmd.md), [the script
layer](docs/format_psq.md), [the engine's script
interface](docs/format_api.md), [the monster AI](docs/format_ai.md), [the
mercenary AI](docs/format_merc.md), [`.PTP`](docs/format_ptp.md),
[`effect.bin`](docs/format_effect.md),
[`.mkc`](docs/format_mkc.md), [the sound banks](docs/format_awb.md),
[the actor parameters](docs/params.md). What running it produced is in
[milestone 1](docs/milestone_numbers.md) and [the pose](docs/pose.md). The
plan is in
[`docs/STRATEGY.md`](docs/STRATEGY.md); what is next is in
[`docs/TODO.md`](docs/TODO.md).

What is still unread: no format at all - the disc's last container was opened
in session 15. What is left is inside them. Ten of the AI's 76 condition
terms, because the shipped tables turned out to be newer than the scripts
that document them; the `ELBN` records, addressable by name but not described
field by field; thirty of the fifty-two `.anmcmd` opcodes, though the two
commonest are read and they are the hitbox; ten of `.mkc`'s twenty-one; and a
dozen of the engine's 285 script functions whose argument roles the disc does
not separate.

Two things listed here for several sessions turned out to be something else,
which is worth keeping visible. `.map` was down as the world layout and is the
minimap - the layout is `hta.bin`, `borderline.bin` and `trigger.trg`. And
`.anmcmd` opcode 10's effect id was called a *global* id because unrelated
monsters share values; they share them because the number is derived from the
animation, and a scan of all 32,600 leaves says no table on the disc maps it
to anything. That one is now the first item on the list that genuinely needs
the EBOOT, and it is cosmetic.

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

Python 3.11+. The readers have **no third-party dependencies**; the only thing
in the repository that has one is `engine/run.py trace`, which draws with
matplotlib and is the one command you can skip.

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
python tools/anmcmd.py shapes <dir>          what `flag` says the three vectors are

python tools/psq.py check|list <dir>          the Squirrel bytecode
python tools/psq.py dump|src <dir> <name>    one file, disassembled or as
                                             reconstructed statements
python tools/psq.py api|calls <dir> [glob]   the 285 host functions, with the
                                             constants each argument is handed
python tools/psq.py sites <dir> <glob>       the call sites themselves
python tools/psq.py xref <dir>               whether a called name resolves

python tools/ai.py check|list <dir>          the monster AI
python tools/ai.py probs|rules <dir> <name>  the action tables, and the rules
python tools/ai.py par <dir> <name>          the six `.par` of one monster
python tools/ai.py acts <dir>                every action id, and its motion
python tools/ai.py terms|ops <dir>           the condition vocabulary

python tools/merc.py check|list <dir>        the mercenary AI
python tools/merc.py dump <dir> <cls>        one class, prt to command step
python tools/merc.py commands|targets <dir>  the command and target tables
python tools/merc.py combos <dir>            the runs, as button presses

python tools/ptp.py check|survey <dir>       the particle effect banks
python tools/ptp.py list <dir> <name>        one bank, slot by slot
python tools/ptp.py slot <dir> <name> <n>    one block, hex and assets
python tools/ptp.py refs <dir>               where the (category, slot) pairs go

python tools/effect.py check|survey <dir>    the effect tables
python tools/effect.py list <dir> <name>     one table, decoded
python tools/effect.py refs <dir>            .mkc, as a row and as an id
python tools/effect.py hitlevel <dir>        category 2, the hit-level scales
python tools/effect.py locators <dir>        +0x04 against the models' S4

python tools/mkc.py check|census <dir>       the presentation track
python tools/mkc.py survey <dir>             every file, one line each
python tools/mkc.py list <dir> <name>        one file, with the cue names
python tools/mkc.py banks|effects <dir>      the sound banks, the effect table
python tools/mkc.py cues <dir> <bank>        one bank's cue list

python tools/pam.py check|list <dir>         the movies
python tools/pam.py mpg <dir> <name> <out>   write the MPEG-2 stream out

python tools/awb.py check|list <dir>         the sound banks
python tools/awb.py cues <dir> <bank>        cue -> waveform, with headers
python tools/awb.py extract|wav <dir> <out>  every waveform, named by its cue

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

## Engine

`engine/` is where the reading stops and the reimplementation starts. Four
files, no renderer, no VM, no combat: a world that answers where the floor is
and where the fence is, an actor that moves under the game's parameter table,
a pose layer that puts a skeleton on the ground, and a driver that reports
what comes out.

```
python engine/run.py numbers <class json>          what the parameters produce
python engine/run.py walk <stage dir> <class json> cross one stage with them
python engine/run.py trace <stage> <json> <png>    draw the crossing
python engine/run.py sweep <stage.cpk dir> <json>  cross every stage
python engine/run.py check <stage.cpk dir>         markers against the mesh,
                                                   and whether fences close
python engine/run.py stride <stage> <json> <tree> <motion>
                                                   walk with the animation on,
                                                   foot against the mesh

python engine/pose.py body <tree> <model>          what touches the ground
python engine/pose.py track <tree> <motion>        where it is, frame by frame
python engine/pose.py footfall <tree>              against .mkc's own footfall
python engine/pose.py emitter <tree>               where a sound comes from
python engine/pose.py locomotion <tree> <json>     against walk_sp and run_sp
```

`numbers` needs no disc geometry at all - it turns the parameter table into
seconds, metres and multiples of Earth gravity, which are quantities a person
can have an opinion about. Most of the rest want a stage.

Every constant the actor uses is the disc's. The four things the disc does not
say - how a body decelerates, how a turn brakes, what the stick does, and what
happens at a wall - are marked as the engine's choices in
[`engine/actor.py`](engine/actor.py) rather than smoothed over, and the four
the pose layer makes in [`engine/pose.py`](engine/pose.py) the same way. The
reasoning, and what came out of running it, is in
[`docs/milestone_numbers.md`](docs/milestone_numbers.md) and
[`docs/pose.md`](docs/pose.md).

## Licence

MIT, see [`LICENSE`](LICENSE). It covers the tools and the documentation in
this repository — which is all this repository contains. It says nothing about
the disc you supply, which is not ours to licence.

## Not affiliated

*Ragnarok Odyssey ACE* is the property of its rights holders (GungHo Online
Entertainment, Game Arts). This project is unaffiliated, non-commercial, and
distributes none of their work.
