# `CMDL` — the geometry format

**Status: geometry solved.** 1,127 models, 15,833 meshes, 6,127,335 vertices,
5,591,558 triangles, 0 unreadable, and every arithmetic check closing on every
file. Reader: [`../tools/cmdl.py`](../tools/cmdl.py).

With [`CTEX`](format_ctex.md) decoded, this is the first frame: geometry,
texture coordinates, and the model → material → texture chain that says which
picture goes on which triangle.

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
| S3 | mesh descriptors, then the vertex and index buffers | |
| S4 | absent on 705 files | |
| S5 | node names | one per node, on all 1,127 |
| S6 | material names | one per material, on all 1,127 |
| S7 | texture names — these are `CTEX` names | |
| S8 | pointers into a block of short `u16` records, one per texture | |
| S9 | 16-byte digests, then a further pointer table | |

A name table is `u32 count`, then that many pointers, then the strings.

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

The three words at `+0x08` are RGBA colours; `808080ff` and `000000ff` are the
common pair.

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
a skinned mesh needs — weights at offset 0 and bone indices at `stride - 4` —
which is why the `0x03__` types are the character bodies and the `0x00__` types
the rigid attachments. Byte 2 is the offset of a
four-byte attribute sitting between the coordinates and the normal.

**Vertices are already in model space**, not in node space. No transform has to
be composed to draw a model; the node hierarchy is read for the skeleton, not
for placement.

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

## Still open

- **Skinning — the attributes read, the pose does not yet.** On all 931 skinned
  meshes and 473,193 vertices, the first four bytes of a vertex are four `u8`
  weights summing to exactly 255, and the last four bytes of the stride are
  four `u8` bone indices, every one inside the model's node table. No
  exceptions. What is not yet done is applying them: the weight-to-index
  pairing is unconfirmed and the bind-pose inverse is not written. See
  [`TODO.md`](TODO.md).
- The four-byte attribute at layout byte 2 — colour is the obvious guess and
  the obvious guess has been wrong twice on this disc.
- The middle byte of the mesh descriptor's first word, and `+0x04`, constant at
  `0x0e250200` everywhere.
- `S8` and `S9`, and the 16-byte digests in `S9`.
- What the eight stage grounds mean by a texture index one past the end of
  their name list.
