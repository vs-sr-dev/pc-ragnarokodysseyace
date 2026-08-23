# The stage layout — `ATIH`, `borderline` and `trigger.trg`

**Status: solved.** 163 stages, **5,934 markers, 1,455 polylines, 508
triggers, 0 unreadable**, and every arithmetic identity closing on every file.
Reader: [`../tools/stage.py`](../tools/stage.py). The minimap's transform onto
that layout is **measured rather than read**, and how well is below.

This is where things *are*. [`CMDL`](format_cmdl.md) draws a stage and
[`CCLS`](format_ccls.md) says which of it is solid; these three files, all of
them in the same `param.pac`, say where the player enters, where the monsters
come from, where the fence is, and what happens when you walk into it.

## It is not `.map`

The obvious file to open was `.map` — 137 of them, one per stage directory, and
137 against 155 stages is close enough to be per-stage. All 137 begin `CTEX`.

They are 256×256 8-bit paletted images, and decoding one draws the stage's
silhouette. **`.map` is the minimap**, and it belongs to
[`CTEX`](format_ctex.md), which already reads it. `python tools/ctex.py png
extract/tree 010_01_01.map out.png` is the whole of it.

The cost of that wrong guess was about ten minutes, and the thing that ended it
was reading the first four bytes before reading anything else. The layout was
three doors along in the same directory, in files named `hta.bin`,
`borderline.bin` and `trigger.trg`.

Being a picture was where `.map` stopped for eleven sessions. **The minimap**
below finishes it: a picture is not a minimap until something says where on it
the player is standing.

## The minimap, and where it sits over the world

*Session 19.* `.map` was identified in session 8 and then left as a picture.
A picture is not a minimap: a minimap is a picture **plus the transform that
puts the player's position on it**, and the disc does not write that transform
down anywhere. So it has to be measured. `stage.py minimap`, `minimap_png` and
`minimap_check`.

**The population.** 137 files, all `CTEX`, all 256×256, all format `0x107`
(`P8`, 8-bit paletted) and all with an alpha channel. 135 stage directories
carry one beside a `.col`; 155 carry a `.col` at all, so twenty stages —
towns and interiors — have collision and no map. Two directories carry two:
`060_01_01` and `060_01_02` also ship `<stage>_2.map`, **the same silhouette
with part of it hatched off behind a dashed line**, which is the closed half
of a stage that opens later.

Every one names itself in the `CTEX` header, and the name is the stage's.

### What is measured, and against what

The map's **alpha channel is a silhouette** of the walkable ground. The `.col`
beside it is a collision mesh. Project that mesh onto the XZ plane, draw it
under a candidate transform, and score the result against the silhouette by
**intersection over union**. Nothing joins the two files but the transform, so
the score is not fitted to anything: one is a texture an artist painted and
the other is a mesh an exporter wrote.

The transform searched is a scale and an offset, with no rotation and no
shear:

    pixel_x = s * world_x + ox
    pixel_y = s * world_z + oy

**The sign of the `z` term is positive on every stage.** World `+z` runs *down*
the image, which is what a map drawn looking down the `-y` axis does, and
trying the other sign never wins.

### The anchor is the footprint's own centroid, at the centre of the image

Seed the search with the mesh's **area-weighted centroid** on top of the
silhouette's, and it barely moves. Over the 47 stages that fit at IoU 0.85 or
better the centroid lands at

    x = 127.5   sd 4.2 px
    y = 127.5   sd 11.7 px

on a 256×256 image, whose centre is 127.5. That is the rule, and it is exact
to the pixel in the median.

### The scale is one number, and the measurement will not pin it closer than a band

`python tools/stage.py minimap extract/tree/stage.cpk`, 135 stages:

```
  IoU                        median   0.805   p10   0.621   p90   0.924
  px/m                       median   1.360   p10   1.140   p90   1.510
  95 of 135 fit at IoU 0.75 or better, 38 between 0.5 and 0.75, 2 below 0.5
```

The fitted scale spreads from 0.91 to 1.70, which looks like a per-stage
number until you sort by how well the stage fits:

| kept | n | median | mean | sd |
|---|---:|---:|---:|---:|
| everything | 135 | 1.360 | 1.342 | 0.147 |
| IoU ≥ 0.75 | 95 | 1.360 | 1.340 | 0.142 |
| IoU ≥ 0.85 | 47 | 1.350 | 1.323 | **0.098** |
| IoU ≥ 0.90 | 25 | 1.310 | 1.313 | **0.059** |

**The spread collapses as the fit improves**, which is what a constant plus
measurement noise looks like and not what a per-stage parameter looks like.
The best estimate is **1.31 to 1.33 pixels per metre** — 4/3 sits inside one
standard deviation of the 25 best fits — and one caution against calling it
settled: the fitted scale still correlates −0.54 with the log of the stage's
area, and a big stage both fits better and fits lower.

Pinned completely — the centroid on the centre, one scale for all 135, **no
free parameter at all** — the transform still gets a median IoU of 0.65, and
the curve is flat:

```
  s = 1.2500   median IoU 0.642   >= 0.75 on 45 of 135
  s = 1.2800   median IoU 0.649   >= 0.75 on 45
  s = 1.3333   median IoU 0.649   >= 0.75 on 41
  s = 1.4000   median IoU 0.642   >= 0.75 on 38
```

So a renderer that hardcodes `1.32 px/m` about the footprint centroid is right
about two thirds of the picture on every stage in the game, and per-stage
fitting buys the rest. Where the disc declares the per-stage part is **not
found**: `stageparam.bin`, the `ELBN` sitting in the same `param.pac`, carries
only lights, shadows, fog and clipping — see [`format_elbn.md`](format_elbn.md).

### Where the fit loses, it loses for a visible reason

`stage.py minimap_png` draws one: **red is map only, blue is mesh only, white
is both.** Two things show up on every stage and neither is an error in the
transform:

- **a red rim all the way round.** The artist drew an outline stroke outside
  the ground. The mesh has no outline;
- **blue tabs at the exits.** The collision mesh runs on past the doorway into
  the transition volume; the drawing stops at the door.

Both cost a fixed number of *edge* pixels, so they cost a corridor far more
than a field: `010_01_03` is a three-armed passage and scores 0.62 while
`040_01_02`, a blob of the same era, scores 0.92. The two stages below 0.5 are
the narrowest on the disc.

### The markers agree, and they were not part of the fit

`hta.bin` is a third file. It places the monster generators, the props and the
arrival points in world coordinates, and the fit never looked at it. Push them
through the transform — `stage.py minimap_check` — over the 95 stages that fit
at 0.75 or better:

| marker | on a drawn pixel | of |
|---|---:|---:|
| `emgen_pos` — the monster generators | 1,376 | 1,411 (**97.5 %**) |
| `obj` — the placed props | 399 | 421 (**94.8 %**) |
| `appear` — where the player arrives | 167 | 178 (**93.8 %**) |
| `appear01a` / `01b` / `01c` | 197 | 207 (**95.2 %**) |
| `pl_q` | 56 | 60 (93.3 %) |
| `ef_A` | 126 | 136 (92.6 %) |
| `ef` | 113 | 193 (58.5 %) |
| `ef_light` | 35 | 87 (40.2 %) |
| `ef_C` | 1 | 89 (**1.1 %**) |
| `ef_B` | 0 | 43 (**0.0 %**) |

**Every marker kind that has to stand on the ground lands on the ground**, at
93 to 98 %, and the ones that miss are the effect emitters — which hang in the
air, sit on walls and ring the stage from outside it. `ef_B` and `ef_C` are
outside the drawn map on every single instance, which is a fact about those
two kinds and worth carrying to whoever reads the effect layer next.

2,949 of 3,780 markers in all, 78.0 %, with nothing fitted to any of them.

## `hta.bin` — `ATIH`, the marker table

163 files, one per stage, 5,934 markers. A marker is a named point or box in
stage space, and it is the only thing on the disc that places anything.

```
0x00  'ATIH'
0x04  u16   0x0106                  constant
0x06  u16   marker count
0x08  u32   name pool offset        == align16(0x10 + 40 * count)
0x0C  u32   zero
0x10  the markers, 40 bytes each
      the name pool, NUL-terminated, ending at the last byte of the file
```

The name pool arithmetic closes on all 163 files, and the **alignment** is what
makes it close: `0x10 + 40 * count` is 16-aligned when the count is even and
eight bytes short when it is odd. 75 files take the first branch and 88 the
second, and without the round-up the second 88 look like a broken format.

### The marker

```
+0x00  u32       zero                on all 5,934
+0x04  u32       name pointer        a file offset, into the name pool
+0x08  u16       rotation x
+0x0A  u16       rotation y          the one that varies
+0x0C  u16       rotation z
+0x0E  u16       zero                on all 5,934
+0x10  float[3]  position            x y z, stage space, Y up
+0x1C  float[3]  half-extents        x y z
```

**The rotations are 16-bit binary angles, 65536 to the turn.** Of the 3,394
non-zero ones, 3,192 are a whole number of degrees on that scale against 2,271
on a scale of 65536 to the half-turn — and the discriminating cases are the
*odd* degrees, which only the first scale can produce. The values are what a
level editor's angle snap writes: `0x1fff` is 45 degrees, `0x1555` is 30,
`0x71c` is 10. `rotation x` is zero on 5,923 markers and `rotation z` on 5,925,
which is what markers standing on flat ground look like.

**The half-extents say which markers are volumes.** A point marker carries a
uniform 0.25 or 0.5 — an editor gizmo, not an extent — and 5,400 of the 5,934
do. A volume carries three different numbers: a `jump_next` is `(10, 25, 1.5)`,
a doorway 20 units wide, 50 tall and 3 thick; a `lock_start` is
`(7.5, 15, 7.5)`; an `SE_area` is `(3.75, 25, 3.75)`.

The split that test produces is its own confirmation, because **every one of
the 534 volumes is a kind that has to be a region**: 270 `jump_*` doorways, 131
`pl_q` quest areas, 44 `lock_start`, 34 `SE_area`, and 55 more spread over
`itembox`, `savearea`, `recycle_box`, `enemypop`, `camera_*`, `closet` and
`music_player` — and not one `emgen_pos` or `ef_*` among them.

The comparison has to be a loose one: a marker the editor rotated writes
0.4999999 twice and 0.5 once, and an exact test calls it a box.

### What the names say

The engine names its own markers, and the prefix is the kind. No table
anywhere assigns meaning to a marker; the string does.

```
emgen_pos*   2,123   enemy generator positions — where monsters come from
obj*           772   objects
ef*         ~1,200   effects: ef_light, ef_fog, ef_leaf, ef_fire, ef_sm
appear*        289   where the player and the party enter, a b c per point
pl_q*          131   quest volumes, named after a quest id
jump_*         272   map transitions, named after the stage they lead to
lock_start      44   camera lock
SE_area         34   sound areas
```

`appear01`, `appear01a`, `appear01b`, `appear01c` on `010_01_01` are at
`(23, 0, 40)`, `(20, 0, 43)`, `(25, 0, 43)` and `(22, 0, 46)`, all facing 180
degrees: a party of four in a diamond, in formation, at the mouth of the stage.

### The proof is the collision

Drop each `appear*` marker straight down onto the stage's own `.col` and **660
of the 661 land on a triangle**, with a **median height difference of 0.000**
and the tenth to ninetieth percentile inside a fifth of a unit. Spawn points do
not merely lie in the neighbourhood of the walkable ground; they lie on it, to
the last decimal the float carries.

`emgen_pos` markers sit on it too, 2,113 of 2,123, but with a longer tail
upwards — p90 is +3.7 — which is what a flying monster's spawn height looks
like. 27 `appear` markers are a clean ±4.00 above or below their ground, and
those are the ones placed on a platform the collision does not model.

This is what identifies the record. Any wrong reading of a 40-byte record puts
plausible floats in the position slot; only the right one puts them on the
floor of the same stage.

## `borderline.bin` — the fences

146 `borderline.bin`, 137 `borderline.cmr.bin`, 25 `borderline.se.bin`; 1,455
polylines between them. No magic, no version, no length field.

```
0x00  u32   polyline count
then, per polyline:
+0x00  u32   point count
+0x04  u32   name pointer
+0x08  u32   a small number, 0 to 5
+0x0C  the points, 8 bytes each
then the name pool
```

The walk ends **exactly** at the first polyline's name pointer on all 308
files, and that is the only thing in the format that confirms it — nothing
declares a length and nothing declares where the names begin.

### The point, and the scale

```
+0x00  s16   x
+0x02  s16   y
+0x04  s16   z
+0x06  s16   zero
```

**Hundredths of a world unit.** These are integers where everything else on the
disc is a float, and no field says what they are worth.

Divide by a hundred and the median `chara_line` vertex sits **0.75 units** from
the nearest boundary edge of the same stage's collision mesh, with 99.5% of
points inside the ground's bounding box. The alternatives are not close:

| scale | median distance to the collision outline |
|---:|---:|
| 32 | 57.4 |
| 64 | 10.2 |
| **100** | **0.75** |
| 128 | 4.2 |

The identity that finds it is the one [`CCLS`](format_ccls.md) already
established — that the single-use edges of the collision mesh are the outline
of the stage, and that outline is what fences the player in. `borderline.bin`
is that same outline written down again, explicitly, as a polyline.

The names say what each fence is for: `chara_line` (702) is where the player
stops, `lock_line` (304) and `lockarea` (101) are camera, `cam_line`/`cmr_line`
(289, in the `.cmr` file) is where the camera stops, `seLine`/`SE_line` (23, in
the `.se` file) is sound. The `.cmr` points carry `y = 1000` where the others
carry zero, so the camera fence stands ten units above the floor.

One stage spells a polyline `chara_lime`, twice.

## `trigger.trg` — the scripts, in the clear

163 files, 508 triggers. No magic either.

```
0x00  u32   trigger count
0x04  count * 12 bytes:
      +0x00  u32   name pointer
      +0x04  u8    event kind, then three zero bytes
      +0x08  u32   script pointer
then the string pool
```

**The name is an `ATIH` marker, and that is the binding.** 507 of the 508
trigger names are markers in the same stage's `hta.bin`. The one exception is
`jump_010_01_01` in `900_03_02`, a jump to the first field from a menu stage
that has no such marker. So `hta.bin` places a named volume and `trigger.trg`
hangs a script on it; neither file means anything without the other.

**And all 508 of them are a sequence of calls with constant arguments.**
Session 22 had to execute them and so had to parse them; `call_line` in
[`../engine/host.py`](../engine/host.py) reads a name, a bracket and literal
arguments and nothing else, and **507 of the 507 on the 155 stages that have a
collision mesh come back**. 147 are `callQuestScript("<something>()")`, a line
of source inside a string, so the bracket that closes the call has to be found
with the quotes respected - a lazy regular expression stops inside the string
and reads the trigger wrong. See [`milestone_stage.md`](milestone_stage.md).

**The script is source text, not bytecode.**

```
cfMapJump("010_01_02", "appear03");
callQuestScript("sfEnmGenStart()");
sfAreaVolumeCtrl( 1 );
```

The destination stage and the `appear` marker to arrive at are both spelled
out, so a map transition is fully described by two strings. The vocabulary is
small: `cfMapJump` (160), `callQuestScript` (147), `sfAreaVolumeCtrl` (52),
`MapJump` (46), `sfMapJumpA`..`F` (49), `cfSndVolumeCategory` (8),
`sfUpdateCamera` (5), `ClosetCamera`, `RecycleboxCamera`, `questStart`,
`room_select`. `callQuestScript` takes the name of *another* script as a
string, which is where the quest layer starts and where `.psq` presumably ends
up.

The **event kind** is 0 (440), 1 (25), 2 (21) or 4 (22), and
`sfAreaVolumeCtrl` settles two of them: every one of the 21 kind-2 triggers
passes 0, every one of the 21 kind-0 and kind-1 triggers passes 1, and the two
markers that carry both carry kind 1 with `( 1 )` and kind 2 with `( 0 )`. So
**kind 2 fires on leaving the volume and kinds 0 and 1 on entering it.** Kind 4
is the town — `ClosetCamera`, `RecycleboxCamera`, `room_select`, `questStart` —
things you walk up to and press a button on.

## What a stage is, then

`stage.cpk/010_01_01` in full:

```
model.pac/ground.pac/ground.CMDL        the terrain, with 30 textures
model.pac/ground_clip.pac               a low-detail copy for distance
model.pac/sky.pac/sky.CMDL              the sky
param.pac/010_01_01.col                 346 collision triangles
param.pac/010_01_01.map                 the 256x256 minimap
param.pac/hta.bin                       70 markers
param.pac/borderline.bin                4 fences, 52 points
param.pac/borderline.cmr.bin            the camera fence, 34 points
param.pac/borderline.se.bin             a sound line, 14 points
param.pac/trigger.trg                   2 triggers
param.pac/stageparam.bin                ELBN: lights, fog, water, shadows
param.pac/010_01_01.psq                 the cutscene, still unread
sound.pac/                              music and effect banks
```

There are no prop models and no per-prop placement, because there are no props:
a stage is one large `ground.CMDL` with the scenery modelled into it. What
`hta.bin` places is not geometry but *behaviour* — spawns, effects, doorways,
camera and sound.

## Still open

- The polyline's third word, 0 to 5. `chara_line01` on `010_01_01` is 0 and
  `chara_line02` is 1, both parts of the same fence, so it is not a kind.
- ~~Whether a fence is a closed loop or an open chain.~~ **Settled in session
  14**, by making a body live inside one. The last point of `chara_line01` on
  `010_01_01` is the first of `chara_line02` and the last of `chara_line02` is
  the first of `chara_line01` — two polylines, one loop — and disc-wide **105
  of 145 stages have every `chara_line` endpoint shared by exactly two
  polyline ends**. 20 branch, which is a fence with an island in it, and 20
  leave an end loose. `python engine/run.py check extract/tree/stage.cpk`
  prints it; see [`milestone_numbers.md`](milestone_numbers.md).
- What the 45 markers literally named `HTA*` are for.
- The `obj*` markers place objects, but nothing here says *which* object. The
  `objbin.bin` and `stobjbin.bin` [`ELBN`](format_elbn.md) files beside them
  are the obvious place to look; session 19 read the `objbin.bin` records and
  they are a body - capsules, regions, clipping - so they say what an object
  *is*, not which marker gets one. What session 14
  did establish is that they are *placements* and not hints: all 772 of them
  have ground underneath and the median sits **1 cm** above the collision
  mesh.
- `stageparam.bin` is read as a container but its `stage_param` record is not
  named field by field. See [`ELBN`](format_elbn.md). It does **not** carry the
  minimap transform: its five entries are lights, shadows, fog and clipping.
- **`ef_B` and `ef_C` are outside the drawn map on every instance** - 0 of 43
  and 1 of 89 - while every marker kind that stands on the ground is inside it
  at 93 to 98 %. Whatever those two effect kinds are, they ring the stage from
  outside.
- ~~The minimap's transform.~~ **Measured in session 19** - see *The minimap*
  above. What is left of it is **where the disc declares the scale**. The
  orientation and the anchor are settled (no rotation, world `+z` down the
  image, the collision footprint's area centroid at pixel 127.5, 127.5) and
  the scale is 1.31 to 1.33 px/m, but that band is a measurement and not a
  number read off the disc, and per-stage fitting still buys real accuracy -
  median IoU 0.805 fitted against 0.65 pinned. `stageparam.bin` does not carry
  it.
