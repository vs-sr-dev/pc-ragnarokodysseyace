# `ELBN` — the named-parameter container

**Status: the container is solved, and three of its populations are read.**
707 files, 3,983 entries, **318 distinct parameter names, 13,437 relocations,
0 unreadable**, every check closing on every file. Reader:
[`../tools/elbn.py`](../tools/elbn.py). *The records* describes `objbin.bin` —
the geometry, the monster body regions and the player skill parameters — *The
weapon trail* describes `trace_par.bin`, and *`stobjbin.bin` and the state
table* describes the last per-actor file. What is left is `stageparam.bin`
past its lights and `mot_param.bin` past its motion id.

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
trace_par.bin       207   par_tbl, ref_tbl: the weapon trail
stageparam.bin      154   the stage's own parameters; see format_stage.md
objbin.bin           89   clip_distance, col_hit, jostle_data, se_hitlevel_tbl
stobjbin.bin         89
mot_param.bin        60   motionDataHeader and _dataA, per character class
bowstring.bin        25   one per bow, beside its trace.pac
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
per class. *The records* below reads both it and the monsters' side.

## The vocabulary

318 names. The largest populations, with the file they live in — which is what
says who the parameter belongs to, since the name alone rarely does:

```
par_tbl, ref_tbl                     207   trace_par.bin, per weapon
stage_param, waterparam              155   stageparam.bin, per stage
character_clipping_distance          154   stageparam.bin
shadow_offset, shadow_param          154   stageparam.bin
statusData, statusDataHeader          89   stobjbin.bin, per actor
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

---

# The records

*Session 19.* The container had been solved for a session and not one record
described. This chapter describes the ones in `objbin.bin`, which is the
combat parameter set of a player class and the body of a monster, and it is
the largest of the four `ELBN` populations. Tools:
`elbn.py records`, `elbn.py capsules`, `elbn.py regions`.

The method is the one [`ech.py`](format_ech.md) uses on a column and nothing
cleverer: **look down the same word across every file that carries the
record**. One file cannot tell a constant from a payload or an index from a
measurement; eighty-three can. `elbn.py records <name>` does exactly that, and
everything below came out of reading its output.

## How an array is written, and how to find its stride

The `(count, pointer)` shape is everywhere, and the array it points at carries
no length of its own. The stride is recoverable anyway, because an array is
packed against whatever is allocated after it:

    stride = (the next allocated offset - the pointer) / count

That is exact whenever the array really is the last thing before the next
allocation, and wrong when padding or the payload tail stretches the gap — so
`elbn.py records` takes the **mode** over every file carrying the name rather
than believing any one file's arithmetic. On `se_hitlevel_tbl` the naive
answer is 12 on 59 files, 20 on nine and 16 on five; 12 is right, and the nine
and the five are trailing padding.

**A count word is a maximum as often as a length.** Several records declare
eight and use three, and the eight slots are there whether or not the file has
eight things to put in them. Where that happens it is said so below.

## The geometry: `col_hit`, `jostle_data`, `pgs_data`

Three records, 2,371 of them across 100 files, and all three are the same
thing at three lengths. Each begins with a **bone** and continues with points
in that bone's own space.

```
col_hit        32 bytes   u32 bone; f32 a[3]; f32 b[3]; f32 radius
jostle_data    56 bytes   u32 bone; f32 a[3]; f32 b[3]; f32 r0; f32 r1;
                          then 0, 0, 0, a f32 near 1, and -0.0
pgs_data       28 bytes   u32 bone; f32 centre[3]; f32 radius; u32; u32
```

**`col_hit` is a capsule and it is the actor's body.** A player class carries
exactly two, both on `node_hip`, running to `(0, 0, -0.6)` and `(0, 0, +0.6)`
with a radius of 0.3 — and `node_hip`'s own `z` axis points straight down in
the rest pose of every player model, so the pair stands the body up from
`y = 0.07` to `y = 1.87` on a model whose rest pose runs 0.00 to 1.78. See
[`hitbox.py`](../engine/hitbox.py), which prints both that reading and the one
where the offsets are not turned by the bone — under which the same two
capsules lie flat through the hips, 0.60 m of body. One of those is a person.

**The bone word addresses two spaces, and the value says which**, exactly as
[`.anmcmd`](format_anmcmd.md)'s does: below 1000 it is a node index, at or
above it a [`CMDL`](format_cmdl.md) `S4` locator id. 53 of the 1,161 records
in an `objbin.bin` use the locator route, all of them `1000`, which is
`node_hip`. **Every record whose actor has a model on the disc resolves inside
it — 1,148 of 1,148.** The thirteen that do not belong to `_01`, a directory
that ships an `objbin.bin` and nothing else.

**`jostle_data` is the same capsule with two radii** — a cone rather than a
sleeve — and the word at `+0x34` is `0x80000000`, which is `-0.0f`, on 933 of
its 941 records. That is a sentinel written by a compiler, not a number.

**`pgs_data` is a sphere**: one bone, one centre, one radius. The two words
after it are zero on all 252 monster records and `6` and `15` on the six
player ones.

## The monster's body regions

`region_data`, 336 bytes, **315 records over 83 monsters**, and the first word
is a pointer to a name an artist typed:

```
b18_00   HORN_D HEAD NECK WEAK TOGE CHEST WAIST HIP HAND_L HAND_R LEG_L LEG_R
b17_00   HEAD BODY L_ARM R_ARM LEG L_WING_01 .. L_WING_05 R_WING_01 .. _05
b19_00   LANCE HUMAN_CHEST HUMAN_HIP HUMAN_ARM_L .. HEAD NECK CHEST HIP ..
z04_00   head body tail arm_l arm_r foot_l foot_r
z01_00   all
```

That is the part-breaking, part-targeting layer the genre runs on, and 40 of
the 83 monsters have exactly one region called `all`.

### The record, and the chain that closes on itself

```
+0x000  ptr        the region's name
+0x004  u32   n    then u32[20]: indices into this actor's own `col_hit`
+0x058  u32   4    then u32[4]:  indices into `pgs_data`
+0x06C  u32   8    then u32[8]:  indices into `jostle_data`
+0x090  u32        an index into `s_region_group_data`, or -1
+0x094  u32        0 or 1
+0x098  f32        0 or 30
+0x09C  u32   8    then f32[16], eight used: a flat modifier by `region_lv`
+0x0E0  f32        a scale, near 1
+0x0E4  u32   6    then f32[6]:  six multipliers, near 1
+0x100  u32   8    then u32[16], eight used: hit points by `region_lv`
+0x144  u32        811..817, or -1
+0x148  u32, u32   zero on all 315
```

Unused slots in the index arrays are `0xFFFFFFFF`, and the count word is a
maximum rather than a length: `+0x04` reads 8 on 311 records and 14 on two,
and the two spend all fourteen. **Every index lands inside the array it names
— 274 `pgs_data` indices and 27 `jostle_data` indices, none out of range —
and so does every `col_hit` one.**

**The chain closes on itself, and nothing in the file says it should.** A
region names `col_hit` capsules by index; a capsule names a node index; the
node has a name in the `CMDL`; and **the node's name is the region's own**.
`elbn.py regions` counts it with a synonym table a reader can inspect —
`HEAD` is satisfied by `node_head`, `node_jaw` or `node_neck` — and gets
**259 of the 266 regions the table has a word for**. It prints all seven
misses and all 49 words it has no entry for, so a table that is too generous
shows up as a pass and a table that is too strict shows up as a miss:

```
z04_00   7 regions, 0 breakable, 8 capsules
    head     hit [0]     node_head
    body     hit [1]     node_hip
    tail     hit [2, 3]  node_tail node_tail2
    arm_l    hit [4]     node_l_forearm
    foot_r   hit [7]     node_r_calf
```

The seven that miss are the interesting ones and every one of them is the
reader's fault: `b11_00`'s `HARA` sits on `node_hara`, a bat's `wing` on
`node_l_upperarm`, and `b05_01`'s `L_HAND_B` on `node_l_thigh`, because the
rig calls a quadruped's hind limb a hand — the same convention
[`pose.md`](pose.md) found in the footfall cues.

### The eight slots are `region_lv`

Two of the arrays are eight long — the flat modifier at `+0x9C` and the hit
points at `+0x100` — and the monster's own JSON carries a field called
**`region_lv`** whose value across all 89 files is exactly **0 to 7**. See
[`params.md`](params.md), where it is the field that separates a monster's
difficulty tiers. The name says what it indexes and the range agrees to the
slot.

It is not a perfect join in the other direction: 61 of the 79 monsters fill
only slots their JSON declares, and eighteen fill more than that — a table
filled defensively past the levels the game asks for. Reading `b18_00`'s
`HEAD` across the eight gives 500, 600, 700, 1,000, 1,200, 1,400, 700, 1,400
hit points, which is a difficulty curve and not eight unrelated numbers.

**The flat modifier is very likely a defence.** It is negative on the parts a
designer calls a weak point and positive on the armoured ones: on `b11_00`,
`HARA` — the belly — is −450 while `THORN` and the legs are +500 and the
shoulder +300; on `b18_00` the head, neck and hands are −130 to −200 while the
chest, waist and hip are 0. That is what it looks like; the disc does not name
it, and nothing here proves it is subtracted rather than added to something
else.

**The six multipliers are six of something and the disc has one six.** They
sit near 1 — `b11_00`'s `HEAD` reads 1.10, 1.20, 1.05, 1.20, 1.50, 1.05 — and
the only population of six in this game is the six player classes, which are
also the six directories `job.cpk` ships. That is a guess and it is written
down as one.

### Breaking a part, and the table `params.md` could not index

`region_data_brk`, **752 bytes, 87 records over 23 monsters**, is
`region_data`'s 336 bytes followed by 416 more. The prefix has the same layout
— name, capsule indices, defence, multipliers — and the tail adds:

```
+0x150  u32   8    two more index arrays, the same shape as the first
+0x190  u32   8
+0x1D8  u32   8    then 8 f32: hit points again, 800 to 60,000
+0x21C  u32   8    then 8 u32
+0x260  u32   8    then 8 f32: a second flat modifier, negative throughout
+0x2A4  f32        a scale, then u32 6 and six more multipliers
+0x2C4  u32   4    then u16[4]: ids from a family keyed on the part
+0x2D0  u32   4    then u16[4]: the same family, ten lower
+0x2E0  u32        a node index — the part's own bone
+0x2E8  u32        801..804, or 811..813
```

**Its record count is `it_drop_break`.** The monster JSON carries a list
called `it_drop_break` whose members are drop-table ids — `4150`, `4151`, and
every one of them is a file in
`item.cpk/it_drop.pac/it_drop_table.pac/it_drop_db_<id>.bin`. What the list
had no index for was *which part*. It is this table, positionally, and the
lengths agree on **23 of 23 monsters**: `b18_00` breaks `HORN_U1`, `HORN_U2`,
`TAIL`, `WING_L` and `WING_R` and drops 7950, 7951, 7952, 7953, 7954 in that
order. That names one of the leftovers [`params.md`](params.md) listed.

A quest overrides those drops, and **indexes them the same way**: a
`item_reward_region.bin` block's entries carry a part number whose values are
exactly `0 .. n-1` for this table's own record count, on **298 of 298 blocks**
- a different container, a different reader, and the two lists agree. See
[`format_reward.md`](format_reward.md).

The break hit points are an order of magnitude above the region's — 15,000 for
a horn against 500 for a head — so the two are separate pools, which is what a
game with both a stagger meter and a breakable part needs.

### `region_data_tbl` is how the two tables are reached

Sixteen bytes, one per monster, and it is two `(pointer, count)` pairs in the
order *broken* then *whole*:

```
+0x00  ptr   region_data_brk, or null
+0x04  u32   how many
+0x08  ptr   region_data
+0x0C  u32   how many
```

On all 83 the first pair is null on exactly the 60 monsters that ship no
`region_data_brk` and set on exactly the 23 that do, both pointers land on the
entry they name, and both counts equal that entry's size divided by 752 and
336.

### `s_region_group_data`

48 bytes, 197 records, and **the first eight words are `0xFFFFFFFF` on all
197**. An array of indices that is empty in every file on the disc is not
data; it is a runtime slot the build initialised and left. What the record
actually carries is the three floats at the end — `(-15, 20, -30)`,
`(-20, 35, -45)`, seven, six and five distinct values — and a `region_data`
points into this table by its index at `+0x90`, one entry per region.

## The player's combat parameters

`job.cpk/<class>/objbin.bin`, six files, 78 distinct names, and **the names
are the class's skill list**. Fourteen names are common to all six; the rest
split by class and read as the roster of *Ragnarok Odyssey*:

```
sw   provokeParam hardProvokeParam magnumBreakParam furyStanceParam
     guardStanceParam s_mastersword_par s_just_combo_inf s_combo_motA
as   backStabParam soulBreakerParam stickParam backLoadBulletParam
     s_quick_dash_par soul_breaker_attack_param_tbl
hs   hammerFallParam drillCannonParam drillUpperParam absorbTwisterParam
     loudVoiceParam s_spin_par s_spin_data
ht   arrowStormParam sharpShootingParam trapParam flasherParam
     landMineBuleltParam freezingTrapBuleltParam claymoreTrapBuleltParam
     ht_arrow_tbl ht_atk_revise_tbl ht_react_revise_tbl ht_slow
mg   fireBallParam frostWaveParam crimsonRockParam quagMireParam
     teleportParam safetyCoatParam enhancedAuraParam rapidStrikeParam
     mg_magic_tbl mg_charge_data weapon_effect_offset_data
cl   healParam blessingParam gloriaParam sanctuaryParam kyrieEleisonParam
     coluceoHealParam
```

`Bulelt` is the disc's own spelling. A skill that fires something carries a
second entry, `<skill>BulletParam`, and **its first word is the projectile's
lifetime in frames**: 30 for a fireball, 60 for a frost wave, 180 for a
crimson rock, 300 for a quagmire — one, two, six and ten seconds at the
30 fps [`units.md`](units.md) settles.

Several `*Param` entries are **two bytes long**, which is worth noticing on
its own: `ELBN` sizes a value to the byte and the engine's C++ kept some of
these as a single `u16`. Others pack two `u16` into a word —
`blessingParam`'s first is `0x00140078`, which is 20 and 120, and 120 frames
is four seconds.

### `s_combo_graph` — the player's decision, and it is a table

The monster picks its next action out of `ProbList` with a weighted roll
([`format_ai.md`](format_ai.md) section 11). **The player picks it with a
button, and this is the table that says which one.** Six files, 189 nodes,
266 edges, and it is the last table in the combat loop that had no reader.

`s_combo_graph` is eight bytes — a count and a pointer to that many node
pointers — and each node is sixteen:

```
  +0x00  u16   the node's own index
  +0x02  u16   how many edges leave it
  +0x04  ptr   the edge list, or zero on a finisher
  +0x08  u8    how many motions the node plays
  +0x09  u8    zero on all six classes
  +0x0a  u16   the motion, when it plays exactly one
  +0x0c  ptr   the motion list, when it plays more
```

and each edge is twelve:

```
  +0x00  u32   the button: 0, 1, 2 on the ground and 3, 4, 5 in the air
  +0x04  u16   the node it leads to
  +0x06  u8    the first frame the input is taken
  +0x07  u8    the last
  +0x08  u8    a frame inside that window
  +0x09  u8    the first frame of a second, narrower window
  +0x0a  u8    its last
  +0x0b  u8    zero on all 266 edges
```

**Node 0 is the neutral state, it has exactly six edges on all six classes,
and those six edges name the same six motions on all six**:

```
  button   0      1      2      3            4      5
  motion   311    361    362    391    397 398 399   396
           at_s   at_l   at_l_t (aerial at_s)        (aerial at_l_t)
```

Six is what says the field is a small enum and not a mask, and the split is
the obvious one: 0, 1, 2 on the ground and 3, 4, 5 the same three in the air.
Which of the three each is comes from the animation it starts — `at_s` is the
square chain, `at_l` the triangle, and `at_l_t`'s `_t` is a held press, since
the button-4 entry is the `_st` / loop / `_en` triple of one animation and
button 5 is the separate `_t` list beside it. `python tools/elbn.py combo
extract/tree sw` walks the whole of it:

```
  [ 0] []
       triangle held, air   -> [29] [396]      frames   0..255 at   0
       square, air          -> [19] [391]      frames   0..255 at   0
       triangle, air        -> [24] [397, 398, 399] frames   0..255 at   0
       triangle held        -> [18] [362]      frames   0..255 at   0
       square               -> [ 1] [311]      frames   0..255 at   0
       triangle             -> [17] [361]      frames   0..255 at   0
  [ 1] [311]                  at_s
       square               -> [ 2] [312]      frames   6..18  at  10
       triangle             -> [12] [352]      frames   2..16  at  10
  [ 4] [314]                  at_ssss
       square               -> [ 5] [315]      frames   6..20  at  12
       triangle             -> [ 6] [325]      frames   2..18  at  12  just 8..14
```

#### Two checks, and neither of them is the table checking itself

**The id arithmetic.** The animation list for the combo `ssl` is called
`<class>343at_ssl`, and `343` reads as `3AB` with `A = 6 - the number of
leading squares` and `B = how many buttons have been pressed`. That is a
reading taken off the *names*, and the graph never mentions a name. So the
graph's edges can agree with the arithmetic or fail to, and they agree on
**112 of 116** — every square edge landing on `3·1·(B+1)` and every triangle
edge keeping the branch digit it already had.

The four that do not are all the mage's, and they are named: `314 -> 326`,
`334 -> 336`, `344 -> 346`, `354 -> 356`. The mage's finisher is a **special**
— `mg326`, `mg336`, `mg346`, `mg356` are `sp2` to `sp5` — which occupies a
four-id block where the other classes have one id, so the branch digit is
still right on 116 of 116 and only the depth runs one past.

**The just window.** Some edges carry a second, narrower frame window inside
the first. The disc separately ships `_just` copies of some animation lists —
`sw325at_ssssl_just`, `hs334at_sssl_just` — and neither fact mentions the
other:

```
                _just lists   targets of an edge with a second window   both
  hammersmith             6                                        6      6
  warrior                 8                                        8      8
  the other four          0                                        0      0
```

**14 of 14, in both directions.** The second window is the perfect-timing
input, and the four classes with no `_just` animation have no edge that
carries one.

#### What the graph says that the names cannot

The names give the tree; the graph gives the **transitions**, and they are not
a tree. `at_sl` on button square leads to `at_sss` and not to `at_sls`: the
node's depth is how many hits have landed, so a triangle spent at hit two
puts the next square at hit three. Five of the warrior's nodes lead into
`at_sssss` from five different places, and two separate nodes play `314`
because two paths of length four arrive at it.

A node that names more than one motion is a **hold**: three ids are the
`_st`, the loop and the `_en` of one animation — `sw397a_at_l_st`,
`sw398a_at_l`, `sw399a_at_l_en` — and four ids are a special, where the
trailing value is 2 to 9 and matches the `sp<N>` in the animation's own name.

Still open: the byte at `+0x08` of an edge, which is always inside the window
and reads as the frame the transition is taken on; and the third and fourth
entries of a four-motion node, one of which is the same id on every special
of a class (`373` for the mage).

### The tension tables

Four of them, all `(count, pointer)` with a stride of 8 — a **piecewise curve
of `(threshold, multiplier)` pairs**, looked up by scanning until the
threshold is passed.

**They are not identical across the six classes, and this section used to say
they were.** Session 21 printed all six side by side, which is the only way to
see it: **the threshold column is identical on all six in all four tables, and
the multiplier column is not** in three of them.

```
s_tension_revise_hp_tbl            4 pairs, one profile
  thresholds   0.1    0.25   0.5    0.75
  all six      2      1.5    1.25   1.1

s_tension_revise_damage_tbl        13 pairs, four profiles
  thresholds   6     5     4     3     2     1.5   1.2   1     0.7 .. 0
  as           0.15  0.15  0.15  0.15  0.1   0.08  0.03  0     -0.2 .. -0.9
  hs, ht       0.25  0.25  0.25  0.25  0.15  0.12  0.1   0     -0.2 .. -0.9
  mg           0.3   0.3   0.3   0.3   0.2   0.15  0.1   0     -0.2 .. -0.9
  cl, sw       0.4   0.4   0.4   0.3   0.2   0.15  0.1   0     -0.2 .. -0.9

s_tension_revise_react_damage_tbl  11 pairs, two profiles
  thresholds   1.1   1.3   1.5   1.75  2     3     4     5     6    7    10
  as           0     0.1   0.15  0.2   0.25  0.25  0.3   0.3   0.3  0.3  0.3
  the other 5  0     0.1   0.2   0.3   0.4   0.5   0.6   0.6   0.6  0.6  0.6

s_tension_revise_tension_tbl       8 pairs, two profiles
  thresholds   2     1.5   1     0.5   0.25  0.1   0     -10
  as           1     1     1     1     0.85  0.75  0.5   3
  the other 5  5     4     1     1     0.85  0.75  0.5   3
```

The hp table reads straight off: at a tenth of your health you earn tension
twice as fast, and every class earns it at the same rate. The damage table
runs the other way, from a six-times multiplier down to a tenth, and its rows
descend where the react table's ascend.

**Three of the four cut the assassin, in the same direction, by about half** —
0.15 against the shield classes' 0.4, half the react rate, and none of the
5.0/4.0 bonus above a full meter. It is the class that hits fastest, and the
tension economy is where that is paid for. The *losing* side of the damage
table, from threshold 1.0 down, is identical on all six: what varies is
earning, not spending. See [`combat_loop.md`](combat_loop.md) §7 and
`combat.py tension`.

### `eff_hitlevel_tbl` and `se_hitlevel_tbl`

*Session 21 read both, by joining them to lists that had been printed for two
sessions. See [`combat_loop.md`](combat_loop.md) §6 and `combat.py hitlevel`.*

Both are `(count, pointer)`.

**`se_hitlevel_tbl` is a base cue id, and the block above it is three sizes
and a critical flag.** The record is `(0, base, selector)` at stride 12. The
six player classes carry **fifteen entries between them** and their bases are

```
  1000 1006 1012 1018 1024 1030 1036 1042 1048 1054 1060 1066 1072 1078 1084
```

— fifteen bases six apart, starting at 1000 and ending at 1084, so they **tile
1000..1089 with no gap and no overlap** and 1090 is where the monsters begin.
That is a build-time allocation, and resolving the six against
`sound.cpk/common.acb` says what the six are:

```
  1000  KATAR_DMG_S  KATAR_DMG_M  KATAR_DMG_L  KATAR_DMG_CS  KATAR_DMG_CM  KATAR_DMG_CL
  1012  MACE_DMG     1018 SHIELD_DMG  1024 HOLY_DMG    1030 GODFIST_DMG
  1036  DRILL_DMG    1042 SCREW_DMG   1048 ARROW_DMG   1054 STAFF_DMG
  1060  FIRE_DMG     1066 GRAVITY_DMG 1072 THUNDER_DMG 1078 ICE_DMG
  1084  SWORD_DMG    1006 SOMERSAULT_DMG
```

So `cue = base + size + 3 * critical`, with `size` in `{0, 1, 2}`, and the
fifteen bases are the fifteen weapon kinds the six classes ship. The third
word is 0 on all 59 monster entries and takes 0 to 8 across the fifteen player
ones — a per-class selector, and **not** `it_db_weapon.bin`'s weapon kind,
whose six values are a different space.

The 59 monsters take a base inside the hand-made group above 1090, where the
ladders are `S M L LL` and four wide, so a monster picks a family — blunt,
slash, strike — **and a rung to start from**:

```
  base   n   base+0..3                                     median atk
  1090  15   HIT_DMG_S    _M   _L   _LL                           230
  1091   9   HIT_DMG_M    _L   _LL  _CS                           165
  1092   9   HIT_DMG_L    _LL  _CS  _CM               weight 100  260
  1097   1   SLASH_DMG_S  _M   _L   _LL                            90
  1098  10   SLASH_DMG_M  _L   _LL  STRIKE_S                      192
  1099   5   SLASH_DMG_L  _LL  STRIKE_S  _M                       215
  1101   8   STRIKE_DMG_S _M   _L   _LL                           110
  1102   2   STRIKE_DMG_M _L   _LL  FLAME_M                       188
```

In the two families where the rung moves more than once it moves with the
monster's attack; in `HIT` it moves with weight instead.

**`eff_hitlevel_tbl` carries its key in the open.** Stride 40: four `(2, id)`
pairs, a zero, and one packed word. 48 records over the six classes, and the
four pairs are **identical on all 48** — four slots for an axis this build does
not use. The last word is two `u16`, `(level, kind)`:

```
  0x0000_0001   level 0, kind 1
  0x0001_0001   level 1, kind 1
  0x0002_0001   level 2, kind 1
```

Levels are exactly `{0, 1, 2}` and kinds are `{1,2,3,4,5,7,8,10,13,14,15}`. So
the effect id is only a row in the class's own
[`effect.bin`](format_effect.md) — category 2 is [`.PTP`](format_ptp.md)'s
settled one — and it carries **no arithmetic**; the last word does. Five
classes carry three records, one kind by three levels; the hunter carries 33,
eleven kinds by three, and its eleven kinds are arrow types.

**The two tables agree that the hit level has three values**, S/M/L, at the
effect scales 0.5, 0.8 and 1.0 [`format_effect.md`](format_effect.md) already
measured. What computes the level is not on the disc.

### The hunter's two falloff curves

`ht_atk_revise_tbl` and `ht_react_revise_tbl` sit in the bow's `objbin.bin`
and in nobody else's, and both are the `(threshold, multiplier)` shape the
tension tables use. Their strides are closed by the gap to the next array:

```
  ht_react_revise_tbl   stride 8, 10 pairs
      (0, 1) (60, 0.9) (65, 0.8) (70, 0.7) (75, 0.6)
      (80, 0.5) (85, 0.4) (90, 0.3) (95, 0.2) (100, 0.1)

  ht_atk_revise_tbl     stride 12, 12 triples, third column 1.0 on all twelve
      (0, 1.1) (10, 1.1) (20, 1.1) (30, 1.1) (40, 1.1) (50, 1.0)
      (60, 0.9) (70, 0.8) (80, 0.7) (85, 0.5) (90, 0.3) (100, 0.1)
```

Both hold at or above 1 to half way and then fall to a tenth on an axis that
runs 0 to 100. The bow being the only class with them says what the axis is —
a fraction of the arrow's reach — and the two say the reaction falls off
before the damage does.

### `ht_arrow_tbl` — the arrow's flight

Beside them, and the same `(count, pointer)` shape: **42 records at a stride
of 80**, 15 distinct flights. The first four words are the whole of the
motion —

```
  +0x00  u32   a bit field, eight distinct values over the 42
  +0x04  u32   how many frames it lives
  +0x08  f32   metres per frame
  +0x0c  f32   metres per frame squared, downward
  +0x20  f32   a launch angle in degrees, zero on 30 of the 42
  +0x24  f32   two more angles, on the rows that carry them
  +0x28  f32
```

— and two things outside the table say so. **A speed times a life is a
distance**: 18 of the 42 rows read `13 frames, 1.64 m, -0.06`, which covers
**21.3 m**, and the hunter's own JSON asks for a target inside
`cmb_hmg_search_radius = 20 m`. And **the five rows that do not move** carry a
launch angle of −90 degrees on four of them — straight down, which is a thing
dropped rather than a thing shot, and the hunter is the class whose skill list
holds `landMineBuleltParam`, `claymoreTrapBuleltParam`,
`freezingTrapBuleltParam` and `flasherParam`.

`python engine/player.py arrows extract/tree` prints the table and both
checks. Which of the 42 rows a given arrow list uses is **not** joined yet:
the id is presumably in the `.anmcmd` opcode that spawns it, and thirty of
those opcodes are still unread.

## What the records still do not say

- **The six multipliers.** Six of what. The classes are the only six.
- **The flat modifier's sign convention** — read here as a defence, on the
  strength of which parts are negative, and not proved.
- **`region_data_brk`'s two `u16[4]` arrays.** Their values are drawn from a
  generated family: the *k*-th breakable part of a monster gets `6100 + 100k`
  in one and `6110 + 100k` in the other, running to `6820`. They are not
  effect ids (an `effect.bin` reaches 255), not motion ids, not `se.acb` cues
  (37 in a monster bank), and searching all 4,941 `ECH` tables for a column
  holding the family found nothing. Their coincidence with `it_drop_db_<id>`
  filenames is a coincidence: every `x20` in the range happens to exist and
  almost no `x10` does.
- **`s_region_group_data`'s three angles**, and why its eight index slots are
  empty on every file.
- **`pgs_data`'s trailing `6` and `15`**, on the players only.
- **`chuck_off_param`'s third word**, which is not one field: it reads
  `04 64 00 00`, `03 64 00 00`, `02 1e 00 00` — a small index and a 100 or a
  30, the four-`u8`-in-a-lane trap [`ech.py`](format_ech.md) warns about.
- Everything in the other two populations: `stageparam.bin` past the lights
  and `mot_param.bin` past the motion id, and the mercenary AI's four tables.
  `trace_par.bin` is *The weapon trail* below.

---

# The weapon trail

*Session 20.* `trace_par.bin` is the second-largest `ELBN` population — **207
files** — and its two names, `par_tbl` and `ref_tbl`, had no guess at all
after session 19. Both are 32 bytes to a record, and between them they are the
**swoosh a blade leaves behind**: `par_tbl` is how the ribbon looks and
`ref_tbl` is where it is. Tool: `elbn.py trace`.

The path says it first. Every one of the 207 sits in a directory called
`trace.pac`, and the textures the trail is drawn with sit in it too — `zan`,
in the player-side names, is a cut:

```
character.cpk/weapon.cpk/wp_sw1.pac/trace.pac/
    trace_par.bin
    ef_zan_dain001.CTEX
    ef_zan_sw001.CTEX
monster.cpk/b09_00/trace.pac/
    trace_par.bin
    ef_N_trace_b09_00_tail.CTEX
    ef_N_trace_b09_00_wing.CTEX
```

**154 of the files are weapons** — 26 each for `as`,
`hs`, `mg` and `sw`, 25 each for `cl` and `ht`, which is `weapon.cpk` entire —
and **53 are monsters**, the ones with something worth trailing. That split is
the format's own statement of what it is for.

**Every weapon of a class ships the same table.** 207 files hold 43 distinct
`par_tbl` blobs and 30 distinct `ref_tbl` ones, and on the player side the
grouping is exactly the class: all 25 `wp_cl*` are one blob, all 25 `wp_hs*`
another. So the trail is authored once per class and copied into all
twenty-five weapon packs — which is worth knowing before reading a difference
between two swords as meaningful, because there is none.

## `ref_tbl` — two points on a bone

```
+0x00  f32[3]  one end of the ribbon
+0x0C  f32[3]  the other end
+0x18  u16     the locator the points are measured in
+0x1A  u16     the same locator again, on all 382 records
+0x1C  u32     zero on all 382
```

The `u16` is the dual numbering the rest of the disc uses, and this is the
third format to use it after [`.anmcmd`](format_anmcmd.md) and `col_hit`:
**351 of the 357 non-zero ids are a locator on the actor's own model**. On a
weapon the actor is whoever holds it, so the ids resolve against the player
models, and what they resolve to is the point:

```
4000  node_r_weapon  156, and node_r_sword 3 on a rig that renames it
4100  node_l_weapon   30
1100  node_l_hand     23      1200  node_r_hand     23
1700  node_l_foot      4      1800  node_r_foot      4
10100 .. 10109  eff_10100 ..  95     10200 .. 10205  node_r_eye4 ..  6
0     nothing         25      -- the twenty-five bows
```

`node_r_weapon` and `node_l_weapon` are where a weapon is hung, and the
`eff_*` locators are the ones [`effect.bin`](format_effect.md) already uses,
which is the same table read by a second consumer. The six misses are all
`b18`, which asks for `10100` and `10101` and declares neither — ids that
exist on the humanoid monsters and not on the dragon.

**The two points are the weapon, measured.** The `as` pair reads
`(0, 0, 0) -> (-0.74, 0, 0)` on locator 4000 and again on 4100, which is a
0.74 m blade in each hand: the assassin's two daggers, and the only class with
two `ref_tbl` records for that reason. The rest, one line each:

```
as   4000 + 4100  (0,0,0) -> (-0.74,0,0)          0.74 m   two daggers
cl   4000         (0,0,0) -> (0,1.14,0)           1.14 m
hs   4000         (0.28,0.3,0) -> (0.28,1.05,0)   0.75 m   the shaft
     4000         (0.28,0.67,0.35) -> (0.28,0.67,-0.35)  0.70 m   the head
mg   4000         (0,-1,0) -> (0,0.9,0)           1.90 m   a staff, both ends
sw   4000         (0,0.2,0) -> (0,2,0)            1.80 m   guard to tip
ht   0            (0,1.38,0) -> (0,0,-0.13)       1.39 m
```

The hammersmith's two records **cross**: a 0.75 m segment up the shaft and a
0.70 m one straight across it at right angles, which is a hammer head drawn as
two ribbons. The sword warrior's segment starts at `y = 0.20` and not at zero,
which is where a blade starts and a grip stops.

They are the right size for the models they belong to. Projecting every vertex
of each weapon onto its own class's segment direction: the 26 swords reach
1.88 m on the median against a segment of 1.80, and **25 of 26 land within a
quarter of the segment's length of its far end**; the 25 bows reach 1.51
against 1.39, 23 of 25. The looser classes are the ones whose models are not
one shape — `mg`'s staves and `hs`'s hammers run from 1.14 m to 2.81 m along
the same authored segment, so a long staff trails short of its own tip.

`ht` is the only class whose locator is **0**, and the bow is also the only
weapon carrying a second `ELBN`: `bowstring.pac/bowstring.bin`, 25 files, one
per bow. Its single record is 96 bytes, and the **first 48 are identical on
all 25** while the last 48 are twelve `ARGB` colours in four `(a, b, a)`
triples that differ from bow to bow — an edge, a centre and an edge again, per
band. So the string is drawn per bow and shaped once.

## `par_tbl` — the ribbon

```
+0x00  u32     which texture in this trace.pac, counting from 0
+0x04  f32     1.0 on all 523 records
+0x08  u32     ARGB at one end of the ribbon's life
+0x0C  u32     ARGB at the other
+0x10  f32     a width or a scale, 0 to 2
+0x14  f32     the same, at the other end
+0x18  u8[4]   a selector and two counts, the fourth byte zero on all 523
+0x1C  u32     zero on all 523
```

**The first word indexes the textures beside it.** In the container's own
order — `trace_par.bin` first, then the `.CTEX` — **523 of 523 records name a
texture that is there**, and where a file has two textures the
names line up with where the ribbons are. `b12` ships `ef_N_trace_b12` and
`ef_N_trace_b12_foot`, and its six `ref_tbl` records are two on the body's
`eff_10300` and **four on `node_l_foot` and `node_r_foot`**; `b09` ships a
`_tail` and a `_wing` texture against one 3.10 m segment and four of 0.4 to
0.5 m; `z16` an `_eye` and a `_nail`. What neither table says is which record
is drawn with which texture — the correspondence is in the names and not in a
field. **50 of the 53
monsters carry exactly one record per texture.** Every weapon carries three
for two, and the third is the disabled one described below.

An unpacked directory tree cannot preserve the container's order, so
`elbn.py trace` says which order it is showing; run it against
`extract/PS3_GAME/USRDIR` to get the real one.

**The colours are `ARGB`, not the `RGBA` the rest of this disc packs.** The
tell is the pair a template leaves behind: `ff808080` at `+0x08` and
`00808080` at `+0x0C`, which differ in the first byte only. Read as `ARGB`
that is one grey fading to nothing, which is what a trail does; read as
`RGBA` it is red at half alpha becoming teal at half alpha, which nobody
authors. The population agrees: **496 of 523 records carry `0xff` in the first
byte of the head colour and 449 carry `0x00` in the first byte of the tail**,
and 268 carry the same three low bytes in both. This is the third packed
colour on the disc after [`CMTM`](format_cnom.md)'s and the stage lights'
above, and the third convention — so the byte order is a per-format fact and
nothing declares it.

The three bytes at `+0x18` are **a selector and two counts**, and the selector
is the failure [`.anmcmd`](format_anmcmd.md) keeps producing: byte 0 takes 0
on 244 records, 2 on 254 and **4 on 25**, and on all 25 of the fours the other
two bytes are zero and the colour words are `0` and `1` rather than colours.
That is one record meaning something else, and counting the other columns
across all 523 would have averaged straight through it. The 25 are the sword
warrior's second record, on `wp_sw1` to `wp_sw25`. Bytes 1 and 2 read 6 and 6,
6 and 4, 16 and 1, 40 and 2 — small counts, plausibly a sample count and a
subdivision, and nothing on the disc tests it.

**A weapon's three records are two live ones and a template.** Records 0 and 1
point at the class's own texture, record 2 at `ef_zan_dain001`, the one
texture every class ships; record 2 is grey `ff808080` fading to `00808080`
on all 154, which is the default nobody edited. What picks between record 0
and record 1 is not in this file — the assassin has one per dagger and the
other five classes have two records against a single `ref_tbl` entry, two of
them identical, so it is a state the animation selects and not a place.

The 26th weapon of `as`, `hs`, `mg` and `sw` is the same story from the other
side: all four carry the assassin's table, one trail per hand at 0.74 m, and
all four models are dagger-shaped. A weapon's trail follows the weapon, not
the class that owns the folder.

## What the trail does not say

- **Which `par_tbl` record is used when.** A weapon has three and one
  `ref_tbl` entry to hang them on, so the choice is made outside this file —
  by the animation, most likely, which means an
  [`.anmcmd`](format_anmcmd.md) or [`.mkc`](format_mkc.md) opcode nobody has
  read yet. The same question in the other direction is which of a monster's
  many `ref_tbl` records a given record's texture belongs to.
- **The two counts at `+0x19` and `+0x1a`**, and what the selector at
  `+0x18` selects. Nothing on the disc varies with them.
- **The two floats at `+0x10` and `+0x14`**, read here as a width at each end
  because they sit either side of the two colours and run 0 to 6.
- **`bowstring_data`'s first 48 bytes**, identical on all 25 bows and so
  carrying no evidence at all.

---

# `stobjbin.bin` and the state table

*Session 20.* `statusData` and `statusDataHeader` are 89 files, and the first
thing to fix about them is where they live: **`stobjbin.bin`, not
`objbin.bin`** — 83 monsters and the six player classes, one file each. The
two names sit beside each other in the vocabulary and in the same directory,
which is how the survey came to put them in the wrong one.

The header is the shape *The records* already describes, and it closes:

```
statusDataHeader   12 bytes   (count, pointer, stride)
                              stride 28 on the 83 monsters
                              stride 60 on the six player classes
```

**`count * stride == statusData`'s own size on all 89 files**, so neither the
stride nor the record count had to be guessed — which matters here, because
reading the monsters' 28 into the players' file produces plausible garbage and
nothing complains.

## The record, and what is shared between the two shapes

```
+0x00  u32     an id; see below
+0x04  u32     30 or 60 or 10, and 15 on 22 monsters
+0x08  u32     1, occasionally 2, 5, 100 or 1000
+0x0C  u32     30 or 10 or 5
+0x10  u32     1, occasionally 2, 3 or 5
+0x14  u32     a bit field: 0x2c000000, 0x2d000000, 0x28000000, 0xec200000,
               0xcc8b0000 — and the low sixteen bits are zero on all 3,700
--- the monster's record ends with one more word ---
+0x18  f32     -2.01562, -2, 0, 2 or -0.0
--- the player's continues ---
+0x18  u32     0, or 125 to 750
+0x1C  u32     0, 1, 2, 5
+0x20  u32     0, 1, 8, 10, 15
+0x24  u32     a second bit field of the same kind
+0x28  f32[5]  1, 1, 0.4, 1, 0.4 on 582 of the 630 records
```

The first 24 bytes are the same struct in both, and the two bit fields draw
from the same family — `0x2c000000` and `0x2d000000` appear in monsters and
players alike. So this is one record type that the player build extends,
rather than two records that share a name.

## The id is two levels

3,070 monster records carry **99 distinct ids** and 630 player records carry
**109**, and both sets are the same shape: `16 * group + variant`.

```
monsters   0  16 17  112 113  144  160 161  176..180  192 193  208  224 225
           256  304  1024..1120  4128  8192..8640
players    0  16 17  32..37  48..50  64..75  ...
```

Twenty-three ids are on all 83 monsters, which is the common core, and the
`0x2000` band — 8192 to 8640, stepping by sixteen with up to six variants
apiece — is the part that differs from monster to monster. **A monster carries
24 to 64 records and a class carries 101 to 107.**

That is a state machine's enumeration and not a motion list: the row count
correlates with the number of [`.anmcmd`](format_anmcmd.md) files a monster
ships at 0.71 and **is never equal to it** on any of the 83, so the states are
of the same order as the motions and are not them. Which state each id is
stays open, and the disc offers no second consumer for the numbers — this is
the shape read, not the table named.
