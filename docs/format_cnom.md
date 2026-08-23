# `CNOM` — the motion format

**Status: solved.** 3,043 animations, 77,331 tracks, 231,993 channels,
3,020,726 keys, 0 unreadable, every check closing on every file. Reader:
[`../tools/cnom.py`](../tools/cnom.py).

This is the format session 3's actor parameters were waiting on. The stagger
thresholds, the dash distances and the guard windows describe movement; these
are the movements.

## The container is the one the engine always uses

```
file length == 16 + payload + 16 + POF0 payload + 16       on all 3,043
```

```
0x00  'CNOM'
0x04  u32   payload size
0x08  u32   0x00010005
0x0C  u32   zero
0x10  u16   length in frames     u16 1
0x18  char[24]  the animation's name
0x30  u32   pointer to the track table
0x34  u32   pointer to the name table
0x4C  float 1000.0               constant on all 3,043
```

Every `C___` format on the disc opens this way. What follows the payload sorts
them in two:

| carries a `POF0` relocation table | ends at the payload |
|---|---|
| `CMDL` 1,127, `CNOM` 3,043, `CSCN` 82, `CSCM` 78, `CMTM` 91 | `CTEX` 11,536, `CCLS` 155 (plus sixteen zero bytes) |

The `POF0` encoding is in [`format_cmdl.md`](format_cmdl.md), including the
trap where the 22-bit delta is three bytes and not four. Offsets are relative
to `0x10` here too.

Reading `POF0` first is what made this format take an hour rather than a day:
it names every word in the file that holds a pointer, so the track table, the
name table, the per-channel value blocks and the key-time blocks all announce
themselves before a single field has been guessed.

## Tracks, channels, keys

The track table is `u32 count` then that many pointers. The name table is the
same shape with the same count on every file — one name per track — and the
names are `CMDL` node names:

```
top  trans  xrot  node_hip  node_r_thigh  node_r_calf  node_r_foot
node_l_thigh  ...  node_r_clavicle  node_r_upperarm  node_r_forearm
node_r_hand  node_r_weapon  node_neck  node_head  ...
```

Of the 3,043 animations, **3,019 have every track name present as a node name
somewhere on the disc**. The 61 names that are not are `*_PIVOT` helpers and
scene props — things that move and have no geometry. So a motion binds to a
skeleton by name, with no index table in between and nothing to resolve.

A track is `u16 channel count` then a pointer per channel. **Every track on the
disc has exactly three channels**, 77,331 of them, always the same three:

| slot | kind | bytes per key | |
|---|---|---:|---|
| 0 | `0x00` | 12 | translation |
| 1 | `0x04` | 16 | rotation |
| 2 | `0x05` | 12 | scale |

A channel is 16 bytes:

```
+0x00  u16   key count
+0x02  u8    bytes per key, 12 or 16
+0x03  u8    zero
+0x04  u8    0x0f for the twelve-byte channels, 0x10 for the sixteen
+0x05  u8    kind
+0x06  u16   zero
+0x08  u32   pointer to the values
+0x0C  u32   pointer to the key times
```

Values are floats, `count * size` bytes, and the blocks **tile the file with no
gap and no overlap, aligned to sixteen**. Key times are `u16` frame numbers,
`count` of them, strictly ascending, and those blocks tile **aligned to four**.
Both hold on all 3,043 files, which is what turns the layout from a plausible
reading into a proved one — a wrong stride or a missed alignment shows up as a
block that does not meet its neighbour.

## The sixteen-byte channel is a quaternion, and the file says so

Four floats could be a lot of things. Of the **77,331 rotation channels on the
disc, every key of every one is a unit quaternion** to within a thousandth.
Nothing else four floats wide passes that test by accident, and it costs one
square root per key to run.

The reader therefore interpolates them spherically, and takes the shorter arc:
a quaternion and its negation are the same rotation, so the sign has to be
chosen rather than trusted, and getting it wrong sends a limb the long way
round.

## What the keys are spent on

```
3,020,726 keys      rotation 2,676,338    translation 253,427    scale 90,961
```

**70% of channels carry a single key** — a bone that never moves on that axis
still gets a channel, holding one constant value. That is what makes a skeleton
of 24 bones and 41 frames fit in 11 kB: only the joints that actually rotate
pay for their keys, and in `fas211walk` the hip has 22 rotation keys and the
calves 40 while the arms and the root have one apiece.

Animations run from 2 frames to 1,801, with a typical length around 113.

## Reading one

```
$ python tools/cnom.py info extract/tree fas211walk.CNOM
character.cpk/motion.cpk/fas.pac/fas211walk.CNOM
  name        fas211walk
  length      41 frames
  tracks      24
  payload     11,616 bytes, POF0 272, 266 relocations
   bone                       trans   rot  scale
   top                           1     1      1
   trans                         1     1      1
   xrot                          1     1      1
   node_hip                      7    22      1
   node_l_thigh                  1    38      1
   node_l_calf                   1    40      1

$ python tools/cnom.py pose extract/tree fas211walk.CNOM 14
$ python tools/cnom.py track extract/tree fas211walk.CNOM node_hip
```

`pose` samples every bone at a frame, interpolating between keys. Composing
that against a `CMDL` skeleton and drawing the bones is what proved the format:
`fas211walk` on `fas2.CMDL` draws a walk cycle in profile — legs scissoring
through contact and passing, arms counter-swinging — and the bind pose stands
in a T. A wrong quaternion order or a wrong key stride does not produce that.

That pose is also all the other half needs. `CMDL` carries an inverse bind
matrix per bone per mesh, so hanging the mesh on this skeleton is one
multiplication per influence — see [the skinning section of
`format_cmdl.md`](format_cmdl.md). Note what the animated path does *not* touch:
the node table's Euler angles. Every rotation from here is a quaternion.

## `CMTM` is this file with scalars instead of bones

**Status: solved.** 91 files, 231 tracks, 254 channels, 1,388 keys, 0
unreadable. Reader: [`../tools/cmtm.py`](../tools/cmtm.py), which is this
reader with one magic word changed — `Cmtm` subclasses `Cnom` and overrides
nothing but the magic and how a value is read.

`CMTM` sits beside `CNOM` under `*.mot.pac/`, and in the same `.pac` as the
model it belongs to. Shell, header, track table, name table, channel record and
key blocks are all the same, down to the constant `1000.0` at `0x4C`. What
differs follows entirely from what it animates — materials, not bones:

- **a track names a material.** 227 of the 231 track names are material names
  of a `CMDL` sitting beside the file; the other four are the model's own name.
  `CNOM` binds to `S5`, the node names; this binds to `S6`;
- **a track has one to three channels**, not always three: 208 have one, 17 two,
  4 three, 2 none. There is no fixed translation-rotation-scale triple to fill;
- **every key is four bytes**, all 1,388 of them.

Five channel kinds, `0x40` to `0x44`. **`0x40` and `0x41` are not floats** —
read as floats they come out around -4e37, which is the tell; read as four
bytes they are `80808000`, `05050b00`, `00000000`, the same packed RGBA the
`CMDL` material table writes at `+0x08`. So two of the five animate the
material's colours, and on this disc the two always carry the same values as
each other. `0x42` (1,084 keys), `0x43` (28) and `0x44` (148) are floats in
small ranges — 0 to 1, -1 to 0.75, -0.5 to 2 — and which is alpha and which
are texture coordinates is not settled.

Two files key past their own declared length, `menu.cpk/animeicon_00` and
`animeicon_20`, both ending at frame 60 against headers saying 31 and 51.
`CNOM` has no such case in 3,043 files.

## The frame

A `CNOM` frame is **1/30 of a second**, and nothing in the file says so. It is
recovered from the geometry of the locomotion cycles — the planted foot of a
run slides backwards at exactly `run_sp`, and the resulting gait is a human one
only at 30 fps. See [`units.md`](units.md).

## Two motion sets are keyed for a rig this disc does not ship

`fgn` and `mgn` — 72 animations — **carry no `xrot` track at all** and key
`node_hip` at `y = 0.899`. Every other player set keys the hip at about 0.07
and leaves `xrot` where the model puts it, which is 0.9. Played on the
`fgn1`/`mgn1` skeleton the disc ships, the 0.9 is therefore counted twice and
the whole body floats a metre off the ground: no foot ever touches, and both
`gn` locomotion cycles report no planted frame at all.

Drop the `xrot` contribution and the walk's planted foot sits at −0.0014 m
over 29 frames of contact, which identifies the fault exactly — the set was
exported from a rig whose hip hangs directly off the root. Nothing on the disc
supplies that rig: of the 180 models with an `xrot` node, the only three that
put it at the origin are `b18_00`, `b18_01` and `b18_02`. Found by
[`pose.py`](../engine/pose.py); see [`pose.md`](pose.md).

## Still open

- The `u8` at `+0x04` of a channel — `0x0f` on the twelve-byte channels and
  `0x10` on the sixteen, so it tracks the size and adds nothing. Probably an
  interpolation or component-count code.
- The constant `1000.0` at `0x4C`, and the `u16 1` at `0x12`.
- Which of `CMTM`'s float kinds is alpha and which are texture coordinates, and
  why two channels carry the same colour.
- Whether frames are 30 or 60 to the second. Nothing in the file says, and the
  actor parameters in [`params.md`](params.md) are the place to settle it —
  they carry durations that these animations have to match.
