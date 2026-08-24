# Lighting — where the light comes from, and it is the disc

*Session 27. Companion to [`format_cmdl.md`](format_cmdl.md),
[`format_elbn.md`](format_elbn.md) and
[`milestone_draw.md`](milestone_draw.md).*

Session 26 drew a frame. Its shading was `draw.py`'s own — a face normal, one
directional light, an ambient of 0.55, flat — and the document said so in a
section called *Three conventions this file picks, and says so*. This one
takes all three off the disc.

The answer turns out to be in three places that were already read, and it is
one model rather than three settings:

```
stageparam.bin   the stage's own lights, named          ELBN, 154 files
CMDL vertex      a baked colour on 13,168 meshes        layout byte 2
CMDL material    a diffuse, an ambient, a specular      +0x08, +0x0c, +0x10
                 and a blend mode                       +0x04 byte 0
```

---

## The stage declares its own lights, and names them

`stageparam.bin` is the `ELBN` in every stage's `param.pac`. Its `stage_param`
entry is 48 bytes and six of its twelve words are a pointer and a count:

```
+0x00  ptr -> f32[2]      the clip range, 1 to 500 on a field stage
+0x04  ptr -> u32         0x01010100
+0x08  ptr, +0x0c u32     the directional lights, and how many
+0x10  ptr, +0x14 u32     the ambient lights, and how many
+0x18  ptr, +0x1c u32     the fog, and how many
+0x20  ptr -> f32[4]      +0x24  ptr -> f32[3]
+0x28  f32                +0x2c  ptr -> waterparam
```

A light is 28 bytes and every field of it is legible:

```
+0x00  ptr     its own name
+0x04  u32     a category byte, then three flag bytes
+0x08  rgba    colour
+0x0c  f32     intensity
+0x10  f32[3]  direction, unnormalised; zero on an ambient
```

`010_01_01`, the first field in the game, reads:

```
dir  ch_dir_1   ch 010101  rgb 250 235 200  x0.75  dir  -16.00    5.00   -8.00
dir  ch_dir_2   ch 000100  rgb  70 215 180  x0.55  dir    4.00   -8.00   12.00
dir  mc_dir_1   mc 010101  rgb 250 235 200  x0.75  dir  -16.00    6.00   -8.00
dir  mc_dir_2   mc 000100  rgb 130 215 175  x0.55  dir    4.00   -9.00   12.00
dir  bm_dir_1   bm 010101  rgb 250 235 200  x1.00  dir  -16.00    6.00   -8.00
dir  bm_dir_2   bm 000100  rgb 130 215 175  x0.75  dir    4.00   -9.00   12.00
amb  ch_amb_1   ch 000000  rgb  85  95 110  x0.80
amb  mc_amb_1   mc 000000  rgb  80  90 105  x0.80
amb  bm_amb_1   bm 000000  rgb  70  80  95  x0.80
amb  st_amb_1   st 000000  rgb 255 255 255  x0.90
fog  st_fog_0      mode 0  rgb  50 140 245  density 0.02087  7 to 230  x0.80
```

A warm key at three quarters and a cool fill at a half, per category, over a
blue-grey ambient. That is a lighting artist's two-light rig, written down.

### The name and the number say the same thing

The prefix of the name and the top byte of the flags are the same fact
recorded twice, by the artist and by the exporter, and over 154 stages they
agree on **1,491 of 1,497 lights**:

```
0x00  st    the stage            0x0a  mc  the main character
0x08  ch    a character          0x0b  pv
0x09  np    an NPC               0x0c  bm  a background model
```

The six that disagree explain themselves. Five are a *second* ambient whose
name is a variant of its category's — `ms_amb_1` carrying the `mc` byte on
four stages, `bs_amb_1` carrying `bm` on one. The sixth is `120_02_01`, where
`mc_amb_1` carries the `bm` byte, and that one is a slip.

### Which way the vectors point, and the disc says which

The direction is never a unit vector — the lengths run 4.4 to 29.2 with a
median of 13.4 — so it is a direction to normalise, and its sign has to come
from somewhere. It comes from the names: **the light named `_1` points above
the horizon on 422 of 450 and the one named `_2` below it on 426 of 450.** A
key light comes from above and a bounce from below, so the vector points
*towards* the light. Nothing else about the rig would have settled that.

### The rig is normalised to one unit, and that is what fixes `0x80`

Ambient plus key, in the brightest channel, per category per stage:

```
                       n    min   median    max   within 15 % of 1.0
bm                   123   0.88     1.14   1.37   63
ch                   154   0.72     0.99   1.35   116
mc                   150   0.88     1.09   1.31   95
np                     5   1.02     1.08   1.13   5
pv                     5   1.13     1.13   1.13   5
st (ambient alone)   154   0.80     0.90   1.00   153
```

**A surface turned to the key receives about one unit of light.** Everything
else in the chain multiplies that: the material's diffuse, `0x808080` on
4,696 of 5,425 materials, and the vertex colour, whose histogram over 473,677
stage-ground vertices has its single tallest spike at **128–135, at 16 % of
all vertices**, with mass running both above and below it.

Read those lanes as `c / 255` and a fully lit neutral surface renders at
`0.5 x 1.0 = 0.5`, and a stage — which multiplies both — at `0.25`. Read them
as `c / 128` and both come out at unity. **`0x80` is one and `0xff` is two.**

That is three independent things pointing the same way: the commonest value
of a colour lane is its neutral and it is `0x80`; the light rig sums to one;
and the bake's tallest histogram bin is `0x80`.

---

## The stage has no directional light, and that is the model

Over all 154 stages there is **no `st_dir` anywhere.** The stage gets
`st_amb_1` — white, at 0.9 — and nothing else, while `ch`, `mc`, `bm` and `np`
each get a key and a fill.

That absence is not a gap; it is the whole lighting model, and the geometry
says the same thing from the other side. Every mesh outside `stage.cpk`
carries a normal lane and almost none of `stage.cpk` does, while 94 % of
`stage.cpk` carries a baked vertex colour and almost none of the rest does.

```
container         meshes   with a normal   with a colour
stage.cpk          13,672           0.093           0.940
character.cpk       1,083           1.000           0.029
monster.cpk           562           1.000           0.365
npc.cpk               154           1.000           0.000
```

**A stage is lit once, into its vertices; an actor is lit as it moves.** Two
files written by different tools, agreeing on a division of labour neither of
them states in words.

So the renderer never has to decide. It asks the rig for the category's
directional lights, and for a stage the answer is an empty list.

## What the bake is, and the control that says so

The colour lane is declared by bit 2 of the vertex type and placed by byte 2
of the layout, and those two agree on 15,833 of 15,833 meshes. Its fourth
byte is `0xff` on 5,076,882 of 5,412,488 vertices. See
[`format_cmdl.md`](format_cmdl.md).

That it is a *bake* and not a tint is a measurement with a control: **a bake
is smooth in space.** The mean luminance step across a triangle edge is
**20.61**, and between two vertices of the same mesh drawn at random **38.88**
— a ratio of 0.530, with the edge the smaller of the two on **228 of the 232
models** whose lane varies at all.

## The blend mode, and the thing it made visible

Byte 0 of the material's `+0x04` is `0x01` opaque on 4,077 materials, `0x00`
alpha on 773 and `0x02` additive on 571. The material *names* agree where they
say anything — `_non_` is `0x01` on 1,114 of 1,120, `_alp_` is `0x00` on 15 of
15, `_add_` is `0x02` on 7 of 7 — and the textures agree from a third side:
under `0x02`, **38 % of the texels are black and fully opaque**, against 6 %
and 8 % under the other two, which is what an additive sprite looks like.

[`TODO.md`](TODO.md) carried an item since session 26: *`010_01_01` still has
a heap of tree trunks near the origin.* It is not tree trunks and it is not
near the origin. It is `renz_frea_01`, `_02` and `_03` — **the stage's own
lens flare**, three cards of twelve to sixteen vertices, drawn as opaque black
discs because the renderer had one blend mode. Their textures are near-black
with a bright core and an alpha of 255 everywhere, so neither an alpha test
nor an alpha blend would have saved them; only the additive mode the material
declares. Drawn that way, the black disc becomes a sun.

`renz` is レンズ and `frea` is フレア.

---

## What the renderer does now

```
pixel = texel
      x material diffuse / 128
      x vertex colour    / 128   where the mesh carries one
      x ( ambient + sum over the category's directionals
                    of colour x max(0, N.L) )
```

with `N` the mesh's own normal lane, skinned by the **inverse transpose** of
the same matrices the positions take — the one piece of matrix work `cmdl.py`
did not do before this session — and interpolated across the face, so the
shading is per vertex rather than per triangle.

That the inverse transpose is the right carrier is measured rather than
assumed, against the posed geometry and with the obvious mistake as the
control. Put twelve skinned models in a pose their own `CNOM` names and ask
how far a triangle's three vertex normals sit from the way that triangle now
faces:

```
skinned by the inverse transpose   median 14.89 deg, within 30 deg on 0.809
left in the rest pose              median 71.73 deg, within 30 deg on 0.085
```

`python tools/cmdl.py shading extract/tree`. Where a mesh has no normal
lane and its category has no directional, the whole bracket is the ambient and
the geometry needs no normal at all.

Three of `draw.py`'s policies survive, and they are still policies:

- **triangles are drawn two-sided**, with the normal turned towards the eye,
  because the disc's winding is consistent within a mesh but nothing declares
  which way is out;
- **the draw order is per call, not per triangle** — opaque first in file
  order under the z-buffer, then everything that blends, furthest first, by
  its draw call's own bounding-sphere centre;
- **an opaque material whose texture has holes in it takes an alpha test.**
  The material says opaque and the texture says otherwise; the texture wins,
  because a cut-out card with no test is a black rectangle. This replaces the
  old rule, which read `_alp_` out of the material name and therefore covered
  15 of 5,425 materials.

Two things it still does not do: **vertex alpha**, which `mizuumi_kiwa` on
`010_01_01` uses on 127 of its 237 vertices, and **fog**, which every stage
declares.

## Running it

```
python tools/elbn.py lights extract/tree            every stage's rig
python tools/elbn.py lights extract/tree 010_01_01  one stage's rig
python tools/cmdl.py lanes  extract/tree            the normal and the bake
python engine/draw.py light extract/tree            the lanes, the blend
                                                    modes, and the frame twice
```

`draw.py light` renders every stage under this file's old light and under the
stage's own rig and reports both. Over all 135 stages with a ground model,
mean pixel luminance goes from **30.8 to 50.0** and **0.590 of the lit pixels
move**.

## What the numbers say is still missing

`st_amb_1` is white at 0.9 on **all 154 stages**, so every bit of the
difference between one stage's brightness and another's is in the bake, and
some bakes are very dark: `170_01_01` averages 33.8 against `010_01_01`'s
77.2. Rendered, **29 of 124 stages come out below a mean luminance of 15**,
which is nearly black.

Something is carrying part of those pictures that this renderer does not
draw, and the obvious candidate is the one thing in `stage_param` still
unused: **the fog**. `170_01_01` declares two of them, both a warm brown at
full strength, which in a dark cave is not haze but light. Drawing it is the
next thing this file needs.
