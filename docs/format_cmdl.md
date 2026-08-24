# `CMDL` — the geometry format

**Status: solved, skinning included.** 1,127 models, 15,833 meshes, 6,127,335
vertices, 5,591,558 triangles, 0 unreadable, and every arithmetic check closing
on every file. Reader: [`../tools/cmdl.py`](../tools/cmdl.py).

With [`CTEX`](format_ctex.md) decoded, this is the first frame: geometry,
texture coordinates, and the model → material → texture chain that says which
picture goes on which triangle. With [`CNOM`](format_cnom.md) decoded and the
skinning below read, it is a frame of the game: a character mesh deforming on
its own skeleton, driven by its own animation.

## Three chunks, and an identity

```
file length == 16 + payload + 16 + POF0 payload + 16      on all 1,127
```

```
0x00  'CMDL'
0x04  u32   payload size
0x08  u32   0x00010005          the same version word CTEX carries
0x0C  u32   zero
0x10  u32   0x10002000
0x40  float[3] + pad            scale, 1 1 1 on every file
0x50  float[4]                  bounding sphere: centre x y z, radius
0x60  u16[8]                    element counts
0x70  float 1.0
0x74  u32[11]                   the section directory
0xb0  char[32]                  the model's name
0xd0  the sections
```

Big-endian. **Every offset in the file is relative to `0x10`**, so a file
offset is `0x10 + value`.

## `POF0` is why the payload does not reach the end of the file

The tail after the payload is a `POF0` chunk with the same 16-byte shell, then
sixteen zero bytes. It is a **relocation table**: it lists every word in the
payload that holds a pointer, so the loader can turn stored offsets into
addresses.

That is worth more than it first looks. A format with a relocation table is
self-describing about its own pointers — *these* words and no others — which
turns "is this word an offset or a float?" from a guess into a lookup. 76,423
of them across the disc, and every one lands inside its payload and holds a
valid offset.

The encoding is a stream of deltas in units of four bytes, the top two bits of
the first byte giving the width:

```
01xxxxxx                     6-bit delta
10xxxxxx yyyyyyyy            14-bit
11xxxxxx yyyyyyyy zzzzzzzz   22-bit
00                           end
```

**The 22-bit case is three bytes, not four.** Reading it as four decodes 751 of
1,127 files cleanly and then walks off the end of the other 376 — which reads
as a corrupt file rather than as a wrong assumption, and is the second time
this project has been caught by a decode that is right most of the time. The
tell was that the three-byte reading lands the last relocation exactly on the
final word of the payload.

## The section directory

Eleven `u32` at `0x74`, the first ten pointing at sections in ascending order,
the eleventh equal to the payload size. That last one is the end marker, which
is why it is the one entry `POF0` does not relocate — a nice cross-check that
costs nothing.

| | | |
|---|---|---|
| S0 | the draw list | `counts[1]` × 12 bytes, padded to a multiple of 16 |
| S1 | the node table | `counts[2]` × 96, exactly, on all 1,127 |
| S2 | the material table | `counts[3]` × 48, exactly, on all 1,127 |
| S3 | mesh descriptors, then the vertex, index and bone-palette blocks | |
| S4 | the locator table | absent on 705 files |
| S5 | node names | one per node, on all 1,127 |
| S6 | material names | one per material, on all 1,127 |
| S7 | texture names — these are `CTEX` names | |
| S8 | pointers into a block of short `u16` records, one per texture | |
| S9 | 16-byte digests, then the skinning bone names | |

A name table is `u32 count`, then that many pointers, then the strings.

## The locator table, and what `.CTXT` is

`S4` is `u32 count`, then that many `(u16 id, u16 node)` pairs — numeric
attachment points on the skeleton. `fas2` declares forty of them: `1000` at the
hip, five apiece at each hand, `8199` at a swinging bone, `10000` at the node
actually named `eff_10000`.

Those ids are the other half of a format the survey had left unidentified. The
1,151 **`.CTXT`** files are plain ASCII key/value, they sit in the same `.pac`
as the model, and they are named after a locator id and open by repeating it —
on all 1,151, with no exception:

```
collision_8910.CTXT          blast_8199.CTXT
  id 8910                      id 8199
  shape 3                      mass 0.6
  offset 0 0.03 0              damping_linear 0.99
  size 0.16 0.45 0.18          stiffness_spring 120 140 160
  rol 0 0 90                   linear_limitter_min -0.5 -0.2 -0.1
```

There are three kinds — `collision` (961 files: `shape`, `offset`, `size`,
`rol`), `blast` (75: masses, dampings, spring stiffnesses, linear limits) and
`hair` (115: `spring_x/y/z`, `radius`, `init_angle`, angle limits). So
`collision_*` is a hit volume bound to a bone and the other two are the springs
that make hair and cloth trail: `8199` on `fas2` resolves through `S4` to
`node_secondly01`, which is what that node is for. 1,119 of the 1,151 ids are
declared by a model sitting in the same directory; the 32 that are not are
`hair_800x` on detachable hair, which presumably resolve against the head that
wears them.

**Session 16 found the table a second consumer, and it is not a file.**
[`.mkc`](format_mkc.md)'s sound record carries a third argument that says
where on the body the sound comes from, in a numbering nothing on the disc was
known to define. It is these ids: **2,715 of the 2,716 references resolve
against the locator table of the actor's own model**, and once joined the
vocabulary reads itself — 1300 is the head and carries the voice, 1100 and
1200 are the hands, 1700 and 1800 are the feet, 10600 is the tail. So `S4` is
not a sidecar index, it is **the model's public numbering of places on
itself**, and `.CTXT` and `.mkc` are two different things looking it up. See
[`format_mkc.md`](format_mkc.md#it-is-a-cmdl-locator-id).

**Sessions 17 and 18 found the third and fourth.** `effect.bin`'s `+0x04` is a
locator id — see [`format_effect.md`](format_effect.md) — so an effect hangs
off the same socket a sound comes out of; and the script layer's
`chrSetAttachArticle(chr, 4000, 'beer01')` puts a prop on one, 4000 and 4100
being `node_r_weapon` and `node_l_weapon`. Four consumers, one numbering:
[`format_api.md`](format_api.md).

Two details of the table that only that use made visible: **an id may bind to
more than one node** — `b09_00` declares `6100` twice, once for its head mesh
and once for the damaged one — and the ids are **per actor, not per model
file**, since a monster's armour variants share a rig and an emitter may name
a node only one of them carries.

**Character collision is therefore not in `CCLS`.** It is here, in the clear,
one small text file per capsule, and it needs no reader at all.

## The draw list is what ties the model together

```
+0x00  u32   zero
+0x04  u16   node index
+0x06  u16   material index
+0x08  u16   mesh index
+0x0A  u16   1
```

`counts[1]` records. Every index on the disc is in range. On
`monster.cpk/b17_00` the list reads straight out as English:

```
  0  node 14  b17_white_eye_l3   mat 0  monster_a_ex1_s  tex 0  b17_00_a   mesh 0
  1  node 20  b17_white_eye_l2   mat 0  monster_a_ex1_s  tex 0  b17_00_a   mesh 3
  ...
  6  node 102 b17_body           mat 0  monster_a_ex1_s  tex 0  b17_00_a   mesh 16
  7  node 112 b17_l_crash_c      mat 6  monster_a_ex2_s  tex 4  b17_00_d_spe mesh 42
```

## The material

48 bytes. **`u16` at `+0x02` is the index of its texture** in the `S7` name
list, and those names are `CTEX` names — the `CTEX` files of exactly those
names sit in the same `.pac` as the model. Model → material → texture resolves
by name inside one container, with nothing else to consult.

### Its four colours, and where unity is

The three words at `+0x08` are RGBA colours, and a fourth sits at `+0x28`:

```
+0x08  rgba  diffuse    808080ff on 4,696 of 5,425, then 959595ff and 000000ff
+0x0c  rgba  ambient    808080ff on 4,929, and the same second and third
+0x10  rgba  specular   000000ff on 5,391 — six distinct values in all
+0x28  rgba             808080ff on 5,424 of 5,425, so it says nothing
```

`+0x10` is named specular by the company it keeps. Thirty-four materials over
the whole disc are not black there, and they are `wp_as10`, `wp_ht7`,
`wp_mg6`, `wp_mg14`, `wp_cl10_shield`, a suit of armour, a monster's plates
and four birds — the metal and the feathers, which is where a highlight goes.

**`0x80` is unity in these lanes and `0xff` is twice it.** Two things say so
and neither is a convention taken from another console:

- the commonest value of a colour lane is its neutral, and here that value is
  `0x80` on 4,696 and 4,929 of 5,425 rather than `0xff`;
- the stage's own lighting rig is normalised to one unit of light —
  `stageparam.bin`'s ambient plus key sums to a median of 1.06 in its
  brightest channel over 442 (category, stage) pairs, and the stage's own
  ambient to 0.90. Read `0x80` as `0.5` and every surface in the game renders
  at half, and a stage — which multiplies a material colour by a vertex
  colour — at a quarter. See [`lighting.md`](lighting.md).

### Byte 0 of `+0x04` is the blend mode

```
0x01   opaque      4,077 materials
0x00   alpha       773
0x02   additive    571
0x03                 4
```

The materials name it too, on the ones whose names say anything: **`_non_` is
`0x01` on 1,114 of 1,120, `_alp_` is `0x00` on 15 of 15, and `_add_` is `0x02`
on 7 of 7** — a string and a number written by different halves of a toolchain
agreeing. The textures agree from a third side. Grouped by the byte, the mean
texture under it is

```
byte   fully transparent   partly transparent   black and opaque
0x01               0.008                0.036              0.056
0x00               0.172                0.206              0.078
0x02               0.084                0.129              0.383
```

`0x00` is where the transparency is, and `0x02` is where **38 % of the texels
are black and fully opaque** against 6 % and 8 % — which is what an additive
sprite looks like, because black adds nothing. Its materials are named
`eff_light01`, `mt02_fire02`, `moon_cloud`, `window_a` and `renz_frea_03`:
lights, fire, the moon, lit windows and a lens flare.

The name test is nearly useless on its own, which is worth saying because
`draw.py` used to rely on it: **4,178 of the 5,425 materials carry no blend
token in their name at all**, and only 15 carry `_alp_`.

The index is in range on 1,119 files. The eight that are not are stage grounds
where one material of forty-odd points one slot past the end of `S7`; on those
files `S8` declares one entry more than `S7` does, so the index space is
probably `S8`'s and `S7` runs one name short. `check` reports them rather than
clamping them.

## The node table

96 bytes, and the hierarchy is a depth-first walk with the depth written in the
file, so the parent of a node is the nearest earlier node one level shallower.

```
+0x00  u32   flags
+0x04  u8    depth, 1 at the root, then 0x000001
+0x08  u32   0x08000000 when the node carries geometry
+0x10  float[3] + pad   translation
+0x20  float[3] + pad   rotation, radians
+0x30  float[3] + pad   scale
+0x40  i16, u16, u32
+0x50  float[4]         bounding sphere, zero unless the node has geometry
```

The names are legible skeletons: `TopN`, `top`, `trans`, `xrot`, `node_hip`,
`node_l_thigh`, `node_l_calf`, `node_l_foot`, `mzzh_r_hand`.

Which of `+0x10` and `+0x20` is translation and which is rotation is settled by
the file, not by taste: compose the hierarchy both ways and only one puts the
assembled bounds centre on the model's declared sphere centre. It does so to
three decimal places.

## The mesh descriptor

80 bytes, `counts[4]` of them, at the head of S3.

```
+0x00  u32   0x010f__07, the middle byte varying
+0x04  u32   0x0e250200
+0x08  u16   index count      +0x0A  u16  primitive type
+0x0C  u32   index buffer
+0x10  u16   vertex count     +0x12  u16  vertex type
+0x14  u8[4] attribute offsets
+0x18  u8 0, u8 stride, u8 stride again, u8 0
+0x1C  u32   vertex buffer
+0x30  u32   bone palette, on skinned meshes only
+0x40  float[4]  bounding sphere
```

Indices are `u16` triangle lists. **The vertex block ends exactly where the
index block begins** — `vertex pointer + count * stride == index pointer` on
all 15,833 meshes, with no padding and no alignment between them.

### The vertex layout

`+0x14` byte 0 is the **position** offset, three floats. The file proves it
rather than the reader assuming it: the mesh's own bounding sphere centre
equals the centre of the decoded vertex bounds, on all 15,833 meshes.

Byte 1 is the **normal**, and it is present exactly when `byte0 - byte1 == 12`.
That rule is readable off the census rather than guessed, because every vertex
type on the disc appears at two strides twelve apart, the wider being the same
layout with a normal inserted in front of the position:

| type | strides | position | count |
|---|---|---|---:|
| `0x0003` | 12, 24 | 0 / 12 | 138 |
| `0x0011` `0x0013` | 20, 32 | 8 / 20 | 1,696 |
| `0x0015` `0x0017` | 24, 36 | 12 / 24 | 11,819 |
| `0x0031`…`0x0037` | 28, 40 / 32, 44 | 16 / 28, 20 / 32 | 1,216 |
| `0x0073` | 36, 48 | 24 / 36 | 12 |
| `0x0313` `0x0317` `0x0337` | 40 / 32, 44 / 52 | 24 / 16, 28 / 36 | 931 |

Byte 3 is the offset of the **texture coordinates**, two floats, present when
bit 4 of the vertex type is set. Bits 5 and 6 add a second and third set, eight
bytes each, stacked in front of the first; bits 8 and 9 add the four-byte pair
a skinned mesh needs — weights at offset 0 and palette slots at `stride - 4` —
which is why the `0x03__` types are the character bodies and the `0x00__` types
the rigid attachments.

### Byte 2 is a baked vertex colour

**Bit 2 of the vertex type declares a four-byte attribute and byte 2 of the
layout is where it is** — 15,833 of 15,833 meshes agree with that rule read
both ways, the bit and the offset, with the offset differing from both the
position and the normal exactly when the bit is set.

It is RGBA, and the light the artist baked there:

- **the fourth byte is `0xff` on 5,076,882 of 5,412,488 vertices** while the
  first three range over the whole byte and cluster on greys — `ffffffff`,
  `808080ff`, `7f7f7fff`, `595959ff` — which is an alpha and three channels
  and not four of anything else;
- **it is smooth in space**, which a bake is and a tint or an index is not.
  The mean luminance step across a triangle edge is **20.61** against **38.88**
  between two vertices of the same mesh drawn at random, a ratio of 0.530, and
  the edge is the smaller of the two on **228 of the 232 models** that vary at
  all;
- 11,745 of the 13,168 meshes that carry it vary within themselves, with a
  median luminance spread of 126 out of 255.

The census that makes it a lighting model rather than a curiosity is the split
by container:

| container | meshes | with a normal | with a colour |
|---|---:|---:|---:|
| `stage.cpk` | 13,672 | 0.093 | 0.940 |
| `character.cpk` | 1,083 | 1.000 | 0.029 |
| `monster.cpk` | 562 | 1.000 | 0.365 |
| `npc.cpk` | 154 | 1.000 | 0.000 |
| `menu.cpk` `misc.cpk` `item.cpk` `demo.cpk` | 362 | 1.000 | — |

**Every mesh outside `stage.cpk` carries a normal; almost none of `stage.cpk`
does, and 94 % of it carries a colour instead.** A stage is lit once, at build
time, into its vertices; an actor is lit as it moves. The stage's own
`stageparam.bin` says the same thing from the other side by declaring an
ambient for the stage and no directional at all — see
[`lighting.md`](lighting.md).

`python tools/cmdl.py lanes extract/tree` runs every measurement above, and
`python tools/cmdl.py shading extract/tree` checks the other half of reading
a normal — that it is carried by the **inverse transpose** of the matrices
the positions take. Posed by their own `CNOM`, a triangle's three vertex
normals sit a median of **14.89°** from the way the posed triangle faces
against **71.73°** left in the rest pose.

**Vertices are already in model space**, not in node space. No transform has to
be composed to draw a model; the node hierarchy is read for the skeleton, not
for placement.

## Skinning

931 of the 15,833 meshes are skinned — the vertex types with bit 8 or 9 set,
`0x0313`, `0x0317`, `0x0337`. Three pieces put a mesh on a skeleton, and the
file states each of them rather than leaving it to be inferred.

**The vertex carries four weights and four slots.** The first four bytes are
`u8` weights and **they sum to exactly 255**, on all 473,193 skinned vertices
with no exception; the last four bytes of the stride are `u8` slot numbers, and
weight *k* goes with slot *k*. The layout bytes at `+0x14` describe neither —
they place the position, the normal and the coordinates, and the two skin
fields take the four bytes left over at each end of the stride.

**The palette is the mesh's own bone list.** `+0x30` of the mesh descriptor
points at a block of 80-byte entries, and the slot numbers index *that*, not
the node table — which is why reading them as node indices produces a figure
whose bones are plausible and whose limbs are wrong. A mesh has a palette
exactly when it is skinned: 15,833 of 15,833. The blocks tile the tail of `S3`
after the vertex and index buffers, so a palette runs to the next block or to
the end of the section.

```
+0x00  u16   bone            then fourteen zero bytes
+0x10  float[16]             the inverse bind pose, transposed
```

**The bone is a name.** The `u16` indexes the name table at the tail of `S9`,
past the count and the 16-byte digests, and those names are node names — which
is how [`CNOM`](format_cnom.md) binds too. A palette holds only the bones its
mesh uses, 14 of `fas2`'s 21 on the first mesh, in node order; the bone ids
number the model's bones in the order the meshes first ask for them.

**The matrix is transposed** — the translation is the fourth *row*, so the file
is written for row vectors. Rebuilt for column vectors it satisfies

```
matrix * Rx(90) * bind(node) == identity          872 of 931, to a thousandth
```

and that `Rx(90)` answers the up-axis question the whole format had been
quiet about: **the vertex buffers are Z-up and the skeleton is Y-up**, and the
conversion is baked into these matrices rather than stored anywhere as a field.
Skinning a vertex is then

```
v' = Σ weight[k]/255 · world(bone[slot[k]]) · inverse_bind[k] · v
```

which lands in the skeleton's Y-up space. `world()` is the node hierarchy posed
by a `CNOM`, or the rest pose where the motion does not name a node.

`bind()` is the node hierarchy **with the node scale left out**, and that is
what closes the identity — keeping the scale closes only 800 of the 931. So a
scale on a node is a runtime one, multiplying the skinned result instead of
being baked into it, and `z20_01` says as much in the file: `top` carries 1.5
and both weapon nodes carry 2/3 to undo it, so the monster is a base model
wearing a size.

A rigid mesh is the same expression with one bone, the node its draw call
names. At rest that reduces to `Rx(-90)`, so rigid and skinned meshes come out
in the same space and can be drawn together.

The 59 meshes still left over, across 25 models, have a node table whose rest
transform sits a few degrees from the one their matrices were baked against —
shoulders and arms, mostly — plus one stage prop, `crystal`, whose nodes place
twelve instances up to 78 units from where the mesh was modelled. **The matrix
is what to trust** for the bind. Nothing on the animated path goes through the
node table's Euler angles at all, since `CNOM` keys quaternions.

## What it looks like

`tools/cmdl.py obj` writes Wavefront OBJ with texture coordinates, one object
per draw call, each carrying the name of its node and of its texture. The
render that proved the format was `monster.cpk/b17_00`, decoded straight from
the draw list with its own seven `CTEX` textures sampled through the decoded
UVs: a symmetric winged boss with six eyes down the wings, gold and teal
plumage, and the `b17_white_eye_*` nodes exactly where the eyes are.

That model is Loki, and the disc says so without a disassembler:
`monster.cpk/b17_00/ai.pac/AI_B17_Loki.par`. **The AI filenames name the
monsters** — `AI_Z27_YamiGiant`, `AI_Z24_Gagapu`, `AI_Z21_Nfdeadkafra` — which
gives every model an English name for free.

`cmdl.py obj <dir> <model> <out> <motion> <frame>` writes the same thing posed,
skinning included. The frame that proved the skinning was the player body
`character.cpk/model.cpk/fas2` under `fas211walk`: a walk cycle in profile, the
mesh creasing at the hip, knee and elbow, with its own textures on it — and the
same model at rest standing in a clean T-pose, which is the guard against the
failure that does not crash, a wrong pairing dragging limbs towards the origin.

## And the engine draws it now

[`engine/draw.py`](../engine/draw.py) is a software rasteriser over this
format: **1,127 of 1,127 models render**, only `aaa1` and `dummy` coming out
blank, and **9,095 of 9,304 draw calls find the `CTEX` their material names
sitting in the same `.pac`**. See [`milestone_draw.md`](milestone_draw.md).

Drawing corrected one thing this document had wrong. **A rigid mesh's
vertices are in its node's own space**, so the matrix is that node's world
matrix; `skin_matrices` used to multiply them by the `Rx(90)` that belongs to
the *inverse bind* pose above, and no picture had ever been taken of that
branch because both models that proved the format are skinned. Measured
against two files a model does not touch, a rigid mesh's centroid lands
**0.055 m** from the node its own draw call names against 2.2 m either other
way, and a stage's visible ground agrees with its collision mesh to
**0.034 m** against 0.345 m. `python engine/draw.py convention extract/tree`.

The eight stage grounds below account for **120 of the 209 draw calls that
find no texture**; the other 89 are `menu.cpk` and `misc.cpk` interface
models, which are the one place a texture does not sit beside its model.

## Still open

- ~~The four-byte attribute at layout byte 2.~~ **A baked RGBA vertex
  colour** — see *Byte 2 is a baked vertex colour* above. The obvious guess
  was right this time, and it took a control to say so.
- What byte 1 of `+0x04` is: `0x80` on all but 17 materials, and the 15 that
  carry `_alp_` in their name are 15 of the 17.
- The rest of the material record: `+0x14`, `+0x18` (whose byte 0 tracks the
  blend mode loosely and is not it), `+0x1c` — `0x0a`, `0x05` and `0x00` in
  the top byte, which would fit a specular power — and `+0x2c`.
- The middle byte of the mesh descriptor's first word, and `+0x04`, constant at
  `0x0e250200` everywhere.
- `S8`, and the 16-byte digests at the head of `S9` — one per texture, so a
  content hash is the obvious reading.
- What the eight stage grounds mean by a texture index one past the end of
  their name list.
- Why 25 models disagree with their own inverse bind matrices, and whether the
  engine reads a rest pose from somewhere other than the node table.
