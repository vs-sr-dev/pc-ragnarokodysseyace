# Milestone 6 — "it is drawn"

*Session 26. The code is [`../engine/draw.py`](../engine/draw.py); the frame
is [`010_01_01`](format_stage.md), the first field of the game.*

Five milestones measured the disc and reported numbers. This one is the first
that produces a **picture**, out of the same data and with nothing else: a
software rasteriser, no GPU, no third-party dependency, 500 lines. It walks a
`CMDL`'s draw list, skins each mesh, projects it through a camera, samples the
`CTEX` the material names, and z-buffers the result.

```
python engine/draw.py model extract/tree b17_00.CMDL loki.png
python engine/draw.py model extract/tree msw2.CMDL run.png msw213run 12
python engine/draw.py scene extract/tree q00101 arena.png
python engine/draw.py top   extract/tree 010_01_01 top.png
```

Every input was already read. What had never been asked is whether the
readings are **consistent with each other**, and the answer turned out to be
no — the first stage drawn came out with nine trees piled on the world origin.

## The finding: a rigid mesh is in its node's own space

`cmdl.py`'s `skin_matrices` has two branches. A **skinned** mesh goes through
the bone palette, and that branch was verified in session 5 by looking at an
OBJ export of `b17_00` and of the walking player body. A **rigid** mesh — one
with no palette — took the other branch, which multiplied by

    world[node] · (Rx(90) · bind[node])⁻¹

and **no picture had ever been taken of the result**, because both models that
proved the format are skinned. The `Rx(90)` is real, but it belongs to the
*inverse bind matrices*: `cmdl.py check` confirms it on 872 of 931 skinned
models. Carrying it into the rigid branch was a copy that nothing tested.

Drawing tests it. Three candidates, measured against two things a model does
not touch:

| transform | mesh centroid, from its own node | stage ground, from its collision mesh |
|---|---:|---:|
| `world[node]` | **0.055 m**, 523 of 612 within a metre | **0.034 m** |
| `world · bind⁻¹` | 2.240 m, 174 of 612 | 0.042 m |
| `world · (Rx90·bind)⁻¹` | 2.138 m, 169 of 612 | 0.345 m |

Two independent measurements, two orders of magnitude, one answer: **the
vertices of a rigid mesh are in its node's own space, so the matrix is that
node's world matrix and nothing else.** Fixed in
[`cmdl.py`](../tools/cmdl.py); it is the sixth time on this project that
*running* something produced a fact that reading it had not.

The tell was visible before it was measured. `010_01_01` has nine
`small_tree_*` nodes, each with its own translation out on the field; under
the old transform their vertices were used raw and every one of them landed
on the origin, in a heap that reads as fallen logs until you count them.

## The rasteriser, checked against the one already here

`stage.py minimap` has been fitting each stage's `.map` texture over its
collision mesh since session 19, with its own scanline fill. `draw.py minimap`
puts **the same triangles** under **the same fitted transform** through
`draw.py`'s camera and `draw.py`'s inner loop and asks for the same number
back. Nothing is refitted.

```
stage         stage.py  draw.py   agree   model   px/m
010_01_01        0.802    0.796   0.969   0.041  1.120
010_02_03        0.838    0.834   0.961   0.576  1.460
030_03_04        0.927    0.915   0.971   0.330  1.360
170_18_02        0.711    0.716   0.957   0.122  1.260
...
135 stages
  stage.py rasterises the mesh     median 0.805   >= 0.95 on 6 of 135
  draw.py renders the same mesh    median 0.797   >= 0.95 on 4 of 135
  and the two masks agree          median 0.964   >= 0.95 on 103 of 135
  the stage model over the floor   median 0.169   >= 0.95 on 0 of 135
  the two scores differ by a median of 0.0050, worst 0.0300
```

**0.805 is the number [`format_stage.md`](format_stage.md) has published
since session 19, and `draw.py` returns 0.797 for it** — the two scores differ
by a median of **0.005** per stage and never by more than 0.030, and the two
masks themselves agree at 0.964. Two rasterisers written seven sessions
apart, one answer. That is what says
the camera is right — the projection, the pixel mapping, and the sign
convention `stage.py` had to measure (world `+z` runs *down* a map drawn
looking along `-y`).

The last column is the honest secondary fact, and it is a fact about the game
rather than about the renderer: the stage's **model**, seen from a camera hung
half a metre over the floor, has a silhouette much larger than the walkable
region, because a player can see ground they cannot stand on. The minimap
follows the collision mesh, not the art.

*Session 27:* the first three columns are unchanged to the digit under the
new shading — 0.805, 0.797, 0.964, differing by a median of 0.0050 and a
worst of 0.0300 — because none of them depends on colour. The last one moves
to **0.226**, and for a stated reason: the mask is built from the depth
buffer, and blended and additive geometry no longer writes depth, so what it
now measures is the silhouette of a stage's *opaque* geometry rather than of
everything in its model.

## Everything on the disc draws

```
python engine/draw.py check extract/tree

1127 models rendered at 96x96, 2 blank
9,304 draw calls, 9,095 found their texture beside the model, 209 did not
44 models drew with no texture at all
```

The two blanks are `aaa1` and `dummy`, which are placeholders and carry no
geometry. **9,095 of the 9,304 draw calls found the `CTEX` their material
names sitting in the same `.pac`** — the lookup
[`format_cmdl.md`](format_cmdl.md) described is a directory read and never a
search. The 209 that did not split cleanly in two: **120 name a texture index
that is out of range**, all of them stage grounds — that is the open item
`format_cmdl.md` already lists, seen from the drawing side — and **89 name a
`CTEX` that is not in the same `.pac`**, 72 of them in `menu.cpk` and 17 in
`misc.cpk`, which are interface models and are the one place the
same-directory rule does not hold.

The failure this catches is the one a reader cannot: geometry that parses,
passes every arithmetic check, and draws nothing. 1,125 of 1,127 do not.

## What the pictures show

- **`b17_00`** comes out as [`format_cmdl.md`](format_cmdl.md) described it
  from an external viewer in session 5 — a symmetric winged boss, gold and
  teal plumage, six eyes down the wings. The difference is that this time the
  engine drew it.
- **`msw2` under `msw213run` at frame 12** is a running pose: leading leg
  forward, trailing arm back, the mesh creasing at hip and knee. The skinning
  and [`pose.py`](pose.md)'s sampling are the same code the planted-foot
  measurement uses.
- **`q00101`'s arena** is the picture five sessions of table work were for.
  `quest.py` says which stage the quest starts on, which monster sits in each
  of the eight slots and which `emgen_pos` marker each generator stands on;
  `stage.py` says where those markers are. The camera stands at `appear01`,
  facing the way [`milestone_numbers.md`](milestone_numbers.md)'s capsule
  faces on frame 0.

## Superseded in session 27

The three things below were true when this was written and are not true now.
The shading, the blending and the draw order all came off the disc in the
next session: `stageparam.bin`'s own named light rig, the `CMDL` vertex
colour lane, and the blend mode in byte 0 of a material's `+0x04`. See
[`lighting.md`](lighting.md). What survives of the list is the two-sidedness,
which is still a policy.

## What this is not — as of session 26

Three things, stated because a picture invites the assumption:

- **Shading is flat and this file's own.** A face normal computed in world
  space, one directional light, ambient, no specular and no shadow. The disc
  ships normals in a separate lane and material colours at material `+0x08`,
  and neither is read here yet.
- **Triangles are drawn two-sided.** Winding is consistent inside a mesh but
  nothing on the disc declares which way is out, so culling would be a guess;
  every triangle is drawn and its shading normal is turned towards the eye.
- **There is no scene graph, no draw order and no blending.** Alpha is a
  test, not a blend: a texel under a threshold is not drawn. That is why the
  grass and the tree cards look like cut-outs.

None of the three reads anything off the disc, and all three are policies of
`draw.py` in the same sense that `mission.py`'s `blows` is one.

## What it opens

- ~~**The material's three RGBA words at `+0x08`**, and the normal lane.~~
  **Done in session 27**, along with a third lane nobody had asked for — the
  baked vertex colour — and the stage's own light rig. See
  [`lighting.md`](lighting.md).
- **`PTP` and `effect.bin`**, which have been read for four sessions and have
  had no consumer that could show them: [`format_ptp.md`](format_ptp.md)'s
  `(category, slot)` pair now has somewhere to go.
- ~~**The `CTEX` alpha modes.**~~ **Done in session 27**: the mode is in the
  material record and not in its name, and the name covers 15 of 5,425.
- **A second camera.** `.mkc` carries a camera track and `cfSetCameraType`
  has five modes nobody has separated; a renderer is what makes them
  testable.
