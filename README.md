# PC-ROA

Documentation and tooling towards a native PC reimplementation of
**Ragnarok Odyssey ACE** (PS3, 2013 — the expanded edition of *Ragnarok
Odyssey* for PS Vita).

This repository contains **no game content**. It contains a disc reader, format
documentation, and the tools that produced it. To use any of it you supply your
own copy of the disc.

## Status

Sessions 1-24 (2026-08-24). **A quest finishes itself.** A quest's own tables
put monsters on a stage, the player kills them, and the quest's own compiled
script counts the kills and decides the arena is over - then opens the gate it
closed and lets the run walk on to the next room. Nothing in the engine tells a
script how many monsters it put out; the script knows because the tables say
so, in two different files, and **527 of 527 arena locks agree with the
constant compiled into their own kill callback**. That is [milestone
5](docs/milestone_quest.md), *"a quest finishes itself"* -
[`engine/mission.py`](engine/mission.py). Driving all 431 quests, **210 of the
229 arenas the body reached were closed by the script itself**, on 1,534
kills. The ground mesh turned out to be a
navigation mesh already, on two facts
[`docs/format_ccls.md`](docs/format_ccls.md) had established and nothing had
used.

**Before that, a fight in both directions.** A class
presses a button its own combo graph accepts, plays the animation that graph
names, and the hit records on it land on a *named part* of a monster's body -
`Leg_R`, `HEAD`, or one of the parts that break off - while the monster, in
the same loop on the same stage, lands its own records on the player. Six
classes reach 457 of the 492 class-monster pairs, and the warrior duels all 83
monsters with a hit landing both ways in 38 of them. That is [milestone
4](docs/milestone_player.md), *"the player fights back"* -
[`engine/player.py`](engine/player.py). The table behind it,
`s_combo_graph`, had never been opened: 189 nodes and 266 edges over the six
classes, and it agrees with two things written elsewhere on the disc.

**Before that, the monster's half.** An Orc stands on the spawner its stage
declares for it, a body with the player class's own parameters runs at it, and
the Orc reads its own decision tables, rolls an action, closes when that
action's gate says the target is too far, plays the animation the action names
and lands a blow whose volume reaches the player. 83 of 83 monsters decide on
every one of 40 random states. That is [milestone
3](docs/milestone_fight.md), *"a monster fights"* -
[`engine/brain.py`](engine/brain.py) and [`engine/fight.py`](engine/fight.py).

**And the scripts run.** `010_01_01`
initialises itself out of its own compiled Squirrel, a capsule with the game's
own parameters crosses it, the trigger volume at the exit fires the function
`trigger.trg` names, and the `cfMapJump` inside it loads the next stage and
starts that one too. On the same machinery 68 of 68 cutscene scripts drive
themselves to their own end, and a conversation with an NPC comes out as
thirteen lines of English. That is [milestone
2](docs/milestone_stage.md), *"a stage runs"* -
[`engine/squirrel.py`](engine/squirrel.py) is a Squirrel 2.2 virtual machine
and [`engine/host.py`](engine/host.py) binds all 285 functions the scripts
call. Every `.psq` on the disc executes through it with **0 VM faults**.

**And before that it had feet.** A capsule
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

Session 21 also gave the scripts their shape back. `psq.py src` used to print
control flow as labels and `goto`; it now rebuilds `if`, `else`, `switch`,
`while`, `foreach`, `break` and the short-circuit operators, and the number
that says the reading is right is that **nothing is left over**. Squirrel has
no `goto`, so every jump came out of a construct and "most of them" would not
have been a result: **2,753 of 2,753 functions that carry a jump structure
with 0 jumps unplaced and 0 statements stepped over**. What separates a
`switch` from an `else if` turns out to be a jump no `if` ever makes - a case
falls through into the *next case's body*, past its test - and a first
discriminator that counted links instead stranded 100 jumps in 30 two-case
switches. The count is what said so. It also exposed two holes that had been
invisible: `a && b` was printing as a branch on `b` alone, and a liveness rule
that gave up at the first jump was dropping **3,004 statement calls**, most of
them the last action of an `if` arm. Both are fixed, and the AI's term
dispatch and its weighted action selector now read as the source they were
written as. See [the script layer](docs/format_psq.md).

Session 21 wrote the fight down. [The combat
loop](docs/combat_loop.md) traces one hit from the frame it fires to the
number that comes off a health bar, through eight files, and says at each step
which numbers the disc gives and which it does not. It ends in a ledger of
nine: four are ordinary disc work and five want the EBOOT, and each of the
five is one function rather than a subsystem. Laying the chain out end to end
paid the way that exercise usually does here - **the hit level turns out to
be three values and two tables agree about it**, because
`se_hitlevel_tbl`'s fifteen player entries tile the cue ids 1000..1089 exactly
and the six above each base read `S M L` then `CS CM CL`, three sizes and a
critical flag. **A boss takes no hit-stop**, on exactly the 23 `b*` files and
none of the 59 `z*`. **The player's attack is not in its JSON at all** - it is
column 3 of the weapon table, whose kind column partitions 450 rows into six
classes of seventy-five. And the tool written to reproduce one of the
document's own figures refuted it on its first run: the tension curves share
their thresholds across the six classes and **not** their multipliers.

Session 20 gave the blade a swoosh. `trace_par.bin` - 207 files, the second
largest `ELBN` population and one nobody had a guess about - is **the weapon
trail**, and it is two tables: where the ribbon is and how it looks. Where it
is turns out to be two points in the space of a locator on the actor, the
third format on this disc to use that numbering, and the points are the
weapon measured - 0.74 m in each of the assassin's two hands, guard to tip on
a sword, two crossing segments for a hammer's head. How it looks begins with
which texture in the same directory, and **523 of 523 records name one that is
there**. Its colours are `ARGB` where two other formats here pack `RGBA`, and
the only thing that says so is a template that fades `ff808080` to `00808080`.
See [`ELBN`](docs/format_elbn.md).

Session 19 gave it a shape to be hit on. The `ELBN` `objbin.bin` turns out to
carry **the actor's body as capsules on bones** and, for a monster, **its
named body parts** - `HEAD`, `HARA`, `L_WING_03` - each owning the capsules it
is hit through. The chain closes on itself and nothing in the files declares
it: a region names a capsule by index, the capsule names a node, and the
node's name is the region's own on 259 of the 266 regions a reader's synonym
table has a word for. The same table is what `it_drop_break` in the monster's
JSON had always been indexed by, 23 of 23. And placing those capsules settled
a question two sessions old - **a hit offset is written in its bone's own
frame**, which is now measured on an animated frame at fourteen standard
deviations against a chance baseline the other reading sits on exactly. See
[`ELBN`](docs/format_elbn.md) and [the pose](docs/pose.md).

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
  the minimap    ->      135 of 137 .map over their own collision mesh,
                       median IoU 0.805, and 97.5% of the monster
                       generators landing on a drawn pixel
ELBN parameters  ->      707 files, 318 names   tools/elbn.py   0 errors
  body capsules  ->    1,172 col_hit, 1,148 of 1,148 bones resolving
  body regions   ->      315 named parts, 259 of 266 on a bone of that name
  breakable parts->       87 over 23 monsters, indexing it_drop_break 23/23
  the weapon trail->     207 files, 351 of 357 locator ids on the actor,
                       523 of 523 textures named in the pac beside them
  the state table->       89 files, count x stride closing on every one
Squirrel script  ->    3,011 files, 315k insns tools/psq.py    0 errors
  control flow   ->    2,753 of 2,753 functions structured, 0 jumps left over
  engine API     ->      285 native functions  named and described
  their arguments->   10,787 message ids, 1,220 motion ids, every cue id
                                                 resolving in its own table
quest tables     ->      430 quests, 8,024 gens tools/quest.py  0 errors
  the monsters   ->    2,503 slots, 83 ids naming 83 monster directories
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

the combat loop  ->        8 files, 9 gaps     tools/combat.py
  the hit level  ->       15 weapon kinds tiling cue ids 1000..1089 exactly
  the impact cue ->      747 of 754 player records empty, 5,245 of 5,439 not
  hit-stop       ->       23 of 23 bosses take none, 59 of 59 mobs do
  the attack     ->      450 weapons, 6 kinds of 75, and none of it in a JSON
  the stats      ->      162 of 233 abilities named by the cards that move them

a monster fights ->       83 of 83 deciding      engine/brain.py
  the terms      ->   15,040 comparisons against the disc's own dispatch, 0 apart
  the gate       ->    0.590 correlation, `_act.par`'s range against the swing
  the chain      ->    1,419 actions -> 1,109 motions -> 683 event lists

a quest finishes ->      527 of 527 kill counts agreeing  engine/mission.py
  driven         ->      210 of 229 arenas closed by the script itself
  the arena      ->    2,813 of 2,817 spawners inside their own lockarea
  the route      ->      398 of 428 stage lists connected by their jumps
  the ground     ->      a navigation mesh, at no extra cost  engine/world.py

the scripts run  ->    3,011 of 3,011 executing  engine/squirrel.py  0 faults
  the interface  ->      285 bound, 70 doing the work    engine/host.py
  a stage        ->      155 loaded and initialised, 507 of 507 triggers read
  a cutscene     ->       68 of 68 running to their own setDemoEnd
  a conversation ->       13 lines, resumed through the suspend protocol

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
  which foot     ->       28 of 28 player .mkc 0807 firings agreeing with
                       the foot the skeleton has on the ground

a hit has a place->   1,435 hit offsets placed on the frame they fire
  turned by bone ->    13.5% within 26 deg of the bone's own direction
  not turned     ->     5.6%, against a chance baseline of 5.1%
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
[`effect.bin`](docs/format_effect.md), [the quest
tables](docs/format_quest.md),
[`.mkc`](docs/format_mkc.md), [the sound banks](docs/format_awb.md),
[the actor parameters](docs/params.md). How they fit together in a fight is
[the combat loop](docs/combat_loop.md), which traces one hit end to end and
ends in a ledger of what is still missing. What running it produced is in
[milestone 1](docs/milestone_numbers.md), [milestone
2](docs/milestone_stage.md), [milestone 3](docs/milestone_fight.md),
[milestone 4](docs/milestone_player.md), [milestone
5](docs/milestone_quest.md) and [the
pose](docs/pose.md), which
now covers the hit volume as well as the foot. The
plan is in
[`docs/STRATEGY.md`](docs/STRATEGY.md); what is next is in
[`docs/TODO.md`](docs/TODO.md).

What is still unread: no format at all - the disc's last container was opened
in session 15. What is left is inside them. Ten of the AI's 76 condition
terms, because the shipped tables turned out to be newer than the scripts
that document them; two of the four `ELBN` populations, now that `objbin.bin`
and `trace_par.bin` are read and `stobjbin.bin` is read as far as its ids;
thirty of the fifty-two `.anmcmd` opcodes, though the two
commonest are read and they are the hitbox; six of `.mkc`'s twenty-one; and a
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
python tools/elbn.py records <dir> <name>    one name, profiled over the disc
python tools/elbn.py capsules|regions <dir> <actor>  the body and its parts
python tools/elbn.py trace <dir> [actor]     the weapon trail
python tools/elbn.py combo <dir> [class]     the player's combo graph

python tools/anmcmd.py check|survey <dir>    the animation commands
python tools/anmcmd.py census <dir>          every opcode, with its size
python tools/anmcmd.py list|dump <dir> <name>  one list, frame by frame
python tools/anmcmd.py hits <dir> <name>     the hit records, with bone names
python tools/anmcmd.py bones <dir>           how many hits name a real bone
python tools/anmcmd.py shapes <dir>          what `flag` says the three vectors are

python tools/psq.py check|list <dir>          the Squirrel bytecode
python tools/psq.py dump|src <dir> <name>    one file, disassembled or as
                                             reconstructed source
python tools/psq.py struct <dir>             does every jump go back into a
                                             statement? all 20,032 of them do
python tools/psq.py api|calls <dir> [glob]   the 285 host functions, with the
                                             constants each argument is handed
python tools/psq.py sites <dir> <glob>       the call sites themselves
python tools/psq.py xref <dir>               whether a called name resolves

python tools/quest.py check|list <dir>       the four tables of a quest .pac
python tools/quest.py dump <dir> <quest>     its stages, monsters and spawners
python tools/quest.py xref|enemies <dir>     whether the columns name anything

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

`engine/` is where the reading stops and the reimplementation starts. Eleven
files and no renderer: a world that answers where the floor is,
where the fence is and how to get across the room, an actor that moves under
the game's parameter table, a
pose layer that puts a skeleton on the ground, a hitbox layer that puts a
volume on the skeleton, a driver that reports what comes out - and, since
session 22, a Squirrel 2.2 virtual machine, the 285 host functions the
game's own scripts call into, a monster's decision tables and the fight they
turn into, since session 23 the player's own half of that fight, and since
session 24 a quest that runs itself to its own end.

```
python engine/mission.py run <tree> q00102 sw      one quest, end to end
python engine/mission.py runs <tree>               every quest on the disc
python engine/mission.py counts <tree>             the script's kill count
                                                   against the lock's list
python engine/mission.py area <tree>               is the lockarea the arena?
python engine/mission.py route <tree>              is the stage list a route?

python engine/player.py duel <tree> 010_01_01 AI_B01_OrcKing sw
                                                   both halves, one loop
python engine/player.py duels <tree> sw            every monster, both halves
python engine/player.py swings <tree>              six classes, every monster
python engine/player.py combo <tree> sw            the class's action set
python engine/player.py swing <tree> sw ssssl b01_00   one combo, one body
python engine/player.py parts <tree>               the parts, against their
                                                   own names
python engine/player.py reach <tree>               the swing against the weapon
python engine/player.py arrows <tree>              the hunter's flight table

python engine/fight.py fight <tree> 010_01_01 AI_Z01_Orc  a monster fights
python engine/fight.py fights <tree>               every monster, one stage
python engine/fight.py reach <tree>                the gate against the swing
python engine/fight.py chain <tree>                action -> motion -> hit
python engine/brain.py terms <tree>                against the disc's dispatch
python engine/brain.py agree <tree>                the tables against the .cnut
python engine/brain.py decide <tree> <monster>     what it decides to do

python engine/host.py stage <tree> 010_01_01 q00101 job.cpk/sw/sw.json
                                                   a stage, script and all
python engine/host.py demo <tree> [pac]            a cutscene, to its own end
python engine/host.py talk <tree> No13800.psq      a conversation, in English
python engine/host.py stages <tree>                every stage initialised
python engine/host.py api <tree>                   the interface, and how much
                                                   of it is answered
python engine/squirrel.py sweep <tree>             every script on the disc
python engine/squirrel.py run <tree> <psq> [fn]    one script, one function

python engine/run.py numbers <class json>          what the parameters produce
python tools/combat.py hitlevel <dir>          the hit level, cues resolved
python tools/combat.py cues|power <dir>       the hit record, by side
python tools/combat.py weapons <dir>          the attack the JSON has not got
python tools/combat.py abilities <dir>        every stat an item can move
python tools/combat.py stop|tension <dir>     the reaction, and what it earns
python tools/combat.py all <dir>              every join in the combat loop

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
python engine/pose.py foot <tree>                  .mkc 0807 against the foot

python engine/hitbox.py body <tree> job.cpk/as     the body capsules, placed
python engine/hitbox.py show <tree> <anmcmd>       a hit volume, both readings
python engine/hitbox.py turned <tree>              which reading the disc uses
python engine/hitbox.py obj <tree> <anmcmd> <f> <out.obj>
                                                   one frame as Wavefront OBJ
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
[`docs/milestone_numbers.md`](docs/milestone_numbers.md),
[`docs/milestone_stage.md`](docs/milestone_stage.md) and
[`docs/pose.md`](docs/pose.md). The script layer makes its own three, and they
are in the second of those: the root-table fallback, how long the host holds a
talk line, and what a stubbed function returns.

## Licence

MIT, see [`LICENSE`](LICENSE). It covers the tools and the documentation in
this repository — which is all this repository contains. It says nothing about
the disc you supply, which is not ours to licence.

## Not affiliated

*Ragnarok Odyssey ACE* is the property of its rights holders (GungHo Online
Entertainment, Game Arts). This project is unaffiliated, non-commercial, and
distributes none of their work.
