# `CCLS` — the stage collision format

**Status: solved.** 155 files, one per stage, **107,343 triangles, 0
unreadable**, and every arithmetic check closing on every file. Reader:
[`../tools/ccls.py`](../tools/ccls.py).

The files are named `<stage>.col` and sit in `param.pac` beside the stage's
models. With [`CMDL`](format_cmdl.md) drawing a stage and this saying which of
it is solid, a stage stops being scenery.

## The plain one of the family

`CCLS` carries the same 16-byte shell as `CMDL`, `CNOM` and `CTEX` — magic,
payload size, `0x00010005`, zero — but **no `POF0`**. No relocation table means
no pointers, which means no directory to follow: a header, then one flat array.

```
file length == 16 + payload + 16                      on all 155
0x24 + 112 * count + 12 == 0x10 + payload size        on all 155
```

```
0x00  'CCLS'
0x04  u32   payload size
0x08  u32   0x00010005
0x0C  u32   zero
0x10  u32   1
0x14  u32   zero
0x18  u32   triangle count
0x1C  u32   zero
0x20  u32   0x7fffffff
0x24  the triangles, 112 bytes each
      then twelve zero bytes, then sixteen more
```

## The triangle

```
+0x00  float[3]  v0
+0x0C  float[3]  v1
+0x18  float[3]  v2
+0x24  float[3]  the face normal
+0x30  u32       surface code, 1 to 13
+0x34  s32[15]   all 1, or all -1
```

**The normal is the normalised cross product of `v1 - v0` and `v2 - v0` on
107,338 of the 107,343**, with the same winding every time. The five that are
not are degenerate triangles, one each in five stages, with no normal to
compute.

That identity is the whole proof, and it is worth saying how easily it is
missed. A header of `0x20` bytes is the obvious guess, so the array looks like
it starts at `0x30` — and read that way every field lands twelve bytes late.
The count still divides the payload exactly. The vertices still look like
vertices, because they are, just the wrong two of them. The normal is still
perpendicular to `v1 - v0` on **every** record, which reads as confirmation and
is worth nothing: a plane normal is perpendicular to any edge in its plane, so
that test passes under both readings. Only the cross product tells them apart,
and it says the array starts at `0x24` — twelve bytes inside what looks like
the header.

## It is a ground mesh, not a collision hull

98.4% of the triangles face up within 45 degrees, and only 814 of the 107,343
stand vertical. Nothing here traces a closed volume. What the file describes is
the walkable surface and where it ends — which is the shape an action game
needs, and it is why the stages draw as clean floor plans: a corridor narrowing
in, an arena opening out, a second corridor leaving.

**And it is welded.** Match triangles by exact vertex equality and 150,236 of
the disc's edges are used by exactly two triangles, 21,448 by one, and 31 by
more; 144 of the 155 stages are clean on their own. So this is a surface with a
boundary rather than a soup, and the vertices meet to the last bit — no
T-junctions anywhere on the disc.

That boundary answers where the walls are. 814 vertical triangles is nowhere
near enough to fence 155 levels, and it does not need to be: **the edge of the
walkable region is the fence.** Those 21,448 single-use edges are the outline
of every stage in the game.

**The coordinates are the stage's own model space, with nothing in between.**
On 124 of the 155 stages every collision vertex lies inside the bounding box of
that stage's `ground.CMDL` — which draws a good deal further out than the
collision does, the backdrop terrain being geometry nobody walks on. Note that
this is Y-up — the thinnest axis of a stage ground is `y` on 119 of 155 —
whereas a character's vertex buffer is Z-up. Stage geometry needs no `Rx(90)`;
skinned geometry has one baked into its inverse bind matrices.

## The surface code

1 to 13, with 8 the commonest at half the disc. A stage uses two or three:
`100_03_01` uses 8 and 13, `110_01_02` uses 3 and 7, `060_01_01` uses only 3.

Drawn as a plan they are broad contiguous patches rather than scatter, which is
what a terrain type looks like — footstep sound and footprint effect are what a
per-triangle ground code usually selects. The disc does not say so here.

## The fifteen words are one bit about the stage

They move as one: all 1, or all -1, never mixed. And so does a whole file.
**146 stages are entirely 1, 9 are entirely -1, and no stage mixes them** — so
this is not a per-triangle attribute at all. It is a single fact about the
stage, written into every triangle fifteen times over.

The nine are `010_01_01`, `010_01_02`, `010_02_02`, `010_02_03`, `020_01_02`,
`020_02_02`, `020_02_03`, `020_02_04` and `020_03_01`: the first two areas of
the game, and nothing after them.

## Still open

- What the fifteen-word bit says about those nine early stages.
- What the surface codes name. The `ECH` tables are the place to look, since a
  footstep table would key on the same small integers.
- The `0x7fffffff` at `0x20`, constant on all 155.
- The eleven stages with an edge used by three or four triangles — bridges and
  crossing ramps, most likely, but not checked.
- Nothing in the file indexes it. 2,044 triangles per stage is small enough to
  test linearly, but a shipped engine would build a grid or a BVH at load; if
  one is stored anywhere, it is not here.
