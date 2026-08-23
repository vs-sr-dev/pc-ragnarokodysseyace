# The pose — a skeleton standing on the ground

*Produced by [`engine/pose.py`](../engine/pose.py) and
[`engine/run.py`](../engine/run.py)'s `stride`.*

Session 14 gave the project a body that moves: a capsule with the game's own
acceleration, run speed and radius, crossing real stages
([`milestone_numbers.md`](milestone_numbers.md)). It had no shape at all. This
is the layer that gives it one — a [`CNOM`](format_cnom.md) played on a
[`CMDL`](format_cmdl.md) skeleton, placed on the moving actor, with the
collision mesh underneath.

The reason to build it now is that **it can be checked**, and by three
independent things:

- [`.mkc`](format_mkc.md) opcode `7ffa` fires on the frame a foot lands. That
  is a byte an animator put in a presentation track by hand. The skeleton's
  own answer to *when does a foot land* is forward kinematics over a
  quaternion channel. The two share nothing.
- `walk_sp`, `run_sp` and `fast_sp` say how fast the body travels. A
  locomotion cycle is authored against that speed and slides its planted foot
  backwards at exactly that rate, or it skates. [`units.md`](units.md)
  established that in session 13 and built the frame rate on it, so it is not
  in question — which makes it the right thing to hand this layer's own,
  different definition of *planted* and see whether it comes back.

- `7ff9`'s emitter says which limb a sound comes from, in a numbering nothing
  on the disc was known to define. It turns out to be the model's own locator
  table, and the limb it names is the one arriving on that frame.

The first and third are new, the second is a control, and none was fitted.

---

## The contact node, and the height it stands at

The node that touches the ground is **the toe when the skeleton has one and
the ankle when it does not**. The players are plantigrade and stop at
`node_l_foot`; every monster with legs carries a `node_l_toe` under it, and on
`b01_00` the ankle sits at 1.02 m while the toe sits at 0.42 — for a
digitigrade leg the ankle is a hock, and the hock is not on the floor.

The height that counts as *down* is read off the **rest pose**, because the
disc says the rest pose is a standing one: on every player model the lowest
node in it is at exactly `y = 0` and the ankle is at **0.1421 m**, which is an
ankle height. The same skeleton played through `fas213run` puts that ankle at
0.138 at its lowest. The rest pose is the standing pose to four millimetres,
so nothing here is fitted — `standing` is a number read out of the model.

    python engine/pose.py body extract/tree fas213run

    character.cpk/model.cpk/fas1.pac/fas1.pac/fas1.CMDL
      28 nodes, 2 of them touch the ground
        node_l_foot          stands at y = 0.1421
        node_r_foot          stands at y = 0.1421
      the lowest node in the rest pose is at y = 0.0000

---

## `7ffa` fires when the skeleton lands a foot

    python engine/pose.py footfall extract/tree

Of the 2,690 `.mkc` on the disc, 2,304 have a `CNOM` one directory up and
2,065 of those resolve to a skeleton with feet. **390 animations fire `7ffa`.**
On 131 of them no foot ever rises 10 cm off the ground — an animation whose
feet never leave the floor cannot be asked when a foot lands — so the question
is asked of the other **259, and their 650 firings**.

A foot is *down* when it is within some tolerance of where it stands, and the
answer is shown at three of them so the tolerance can be seen not to be
carrying it. The control is the same question asked of an arbitrary frame of
the same animation:

| a foot is down within | n | exact | within 1 | within 2 | | exact | within 1 | within 2 |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| **1 cm** | 635 | **47.1 %** | **79.5 %** | 85.5 % | | 8.8 % | 25.2 % | 38.5 % |
| **3 cm** | 635 | 38.1 % | 66.9 % | 77.3 % | | 6.7 % | 19.1 % | 30.0 % |
| **5 cm** | 648 | 29.5 % | 55.2 % | 64.7 % | | 5.8 % | 16.6 % | 26.2 % |

The three right-hand columns are what an arbitrary frame scores. **Four in
five firings land within a frame of a landing, against one in four for a frame
picked at random**, and the median offset is zero. Leave out the one cue of
the four that turns out not to be a footstep — the next section — and the 601
that remain come to **49.3 % exact and 81.9 % within one frame**.

The second measurement needs no tolerance at all. *Does the foot arrive?* —
how far the lower of the two contact nodes fell over the three frames into the
event:

| | n | fell | fell > 2 cm | height | on the floor |
|---|---:|---:|---:|---:|---:|
| at `7ffa` | 650 | **+0.0218 m** | **50.2 %** | −0.0009 m | 64.8 % |
| at any frame | 11,324 | +0.0005 m | 20.2 % | −0.0010 m | 62.4 % |

The foot is forty times further into a descent at a firing than at an ordinary
frame. Note the last two columns, which say nothing: *a foot on the floor* is
not evidence, because in most animations one of the two always is. It is the
falling and the frame that carry the result.

### And the fourth kind is not a footstep

`7ffa`'s argument picks one of the model's own four cues — `WALK`, `RUN`,
`LANDING`, `DRESS`. Split the same measurement by it:

| kind | n | fell | height | on the floor |
|---|---:|---:|---:|---:|
| 0 `WALK` | 407 | +0.0069 | −0.0014 | 74.0 % |
| 1 `RUN` | 188 | +0.1384 | −0.0000 | 52.1 % |
| 2 `LANDING` | 15 | +0.3526 | +0.0013 | 53.3 % |
| 3 `DRESS` | 40 | **−0.0002** | +0.0162 | 35.0 % |

The three ground contacts order themselves exactly as their names do — a walk
sets a foot down over seven millimetres, a run drops it fourteen centimetres,
and a landing arrives from thirty-five. **`DRESS` does not arrive at all**,
and it is the only one of the four that lives on the emote set —
`com051emo_1`, `com064emo_14_st` and the rest. Three of the four cues are the
ground; the fourth is cloth, and the skeleton is what says so.

---

## And the sound comes from a limb

    python engine/pose.py emitter extract/tree

`7ff9`'s third argument was the last unread field of the sound record. It is
0 four times in five, and where it is not it takes one of 23 values that
nothing on the disc was known to define. **It is a `CMDL` locator id** — a
`(u16 id, u16 node)` pair out of section `S4`, the same numeric attachment
points the 1,151 `.CTXT` collision and spring files are named after — and
**2,715 of the 2,716 references resolve** against the locator table of the
actor's own model. The full table is in
[`format_mkc.md`](format_mkc.md#it-is-a-cmdl-locator-id); the short version is
that 1300 is the head and carries the voice, 1100 and 1200 are the hands, 1700
and 1800 are the feet, 10600 is the tail, and `b19`'s 6200 is its shield.

That finding needs no pose at all — it is one table against another. What the
pose adds is a third opinion. If the id really is the limb a sound comes from,
that limb should be the one *arriving* on that frame. Over the 1,737
references whose emitter names a node with a mirror twin, how far each of the
two fell over the three frames into the event:

| | n | the named node fell | its twin fell | named fell further |
|---|---:|---:|---:|---:|
| a hand | 1,075 | **+0.502 m** | +0.022 m | 69.8 % |
| a foot | 615 | **+0.340 m** | +0.000 m | 80.8 % |
| elsewhere | 47 | +0.471 m | +0.176 m | 68.1 % |

**The named foot drops a third of a metre into the event and its twin does not
move at all.** On `b19213run` all four hooves are exact: `HORSE_STEP_F` from
31200 on the frame the right fore comes down, from 31100 on the frame the left
fore does, and the two `HORSE_STEP_B` on their own hind feet.

This one is worth reading twice for how it failed first. Measured as *height
above where the node stands in the rest pose* — the definition the footfall
check uses, and the one that works on every player model — the answer came
back at 50.0 %, exactly chance. The rest pose of a monster is not a standing
pose: `b19`'s horse hangs two metres above its own, so *height above standing*
is not a height above anything. Measuring a **descent** instead cancels the
offset, and the same data goes from nothing to 80.8 %. The reference was
wrong, not the pose, and the null result was three lines of code away from the
real one.

---

## The 48 locomotion cycles against the parameter table

    python engine/pose.py locomotion extract/tree extract/tree/job.cpk/sw/sw.json

Eighteen `*walk`, eighteen `*run` and twelve `*run_dash`, each measured by the
backward slide of its planted foot, against the field the class JSON declares.
Twelve of each belong to the six classes with a directory in `job.cpk` — the
six with a parameter table. The other sets, `cm`, `gn` and `nn`, have motion
and no class behind them, so they are a control that comes free:

| cycle | declared | the six classes | within 5 mm | the other sets | within 5 mm |
|---|---|---|---:|---|---:|
| `*walk` | `walk_sp` 0.05 | median **0.0484**, 0.0459–0.0507 | **12 of 12** | 0.0402–0.0558 | 0 of 4 |
| `*run` | `run_sp` 0.17 | median **0.1696**, 0.1668–0.1762 | **11 of 12** | 0.1241–0.1899 | 0 of 4 |
| `*run_dash` | `fast_sp` 0.28 | median **0.2769**, 0.2487–0.3265 | 6 of 12 | — | — |

Twenty-three of the twenty-four player walk and run cycles are within five
millimetres a frame of the number the table declares, and **not one of the
eight cycles belonging to a set with no parameter table is**. The dash is the
loose one: 17 frames long against the run's 21, so a planted foot gives it
fewer samples, and two of the twelve — `mht215run_dash` at 0.3265 and
`mas215run_dash` at 0.2487 — are three centimetres a frame either side. The
median is still 0.2769 against 0.28.

**This result is not new** — [`units.md`](units.md) established it in session
13, over twelve models, and built the frame rate on it. What is new is that it
comes back from a *different definition of a planted foot*. `cmdl.py gait`
takes each animation's own lowest ankle as its floor, which is a definition
that only works on a cycle that has one. `pose.py` takes the height the
contact node stands at **in the model's rest pose**, which is a property of
the skeleton and says nothing about the animation — and it is the definition
the engine needs, because a body walking over a stage has to know where its
foot is in an attack, a stagger and a fall as well as in a walk. The two
definitions agreeing to 0.0008 on the walk, 0.0003 on the run and 0.0021 on
the dash is what licenses the second one.

---

## On the stage: the foot against the collision mesh

    python engine/run.py stride extract/tree/stage.cpk/010_01_01/param.pac \
                                extract/tree/job.cpk/sw/sw.json \
                                extract/tree msw211walk walk

Now all three parts are in the same place at the same time: the actor moving
under `walk_sp`, the skeleton posed by the `CNOM`, and the ground read from
`<stage>.col` under wherever the foot actually is. Nothing has arranged for
them to meet.

      frame        x         z   speed   the lower foot       above the mesh    slips
         ...
         78    23.000    36.115   0.050   node_l_foot        +0.001     0.0080
         79    23.000    36.065   0.050   node_l_foot        -0.000     0.0057
         80    23.000    36.015   0.050   node_l_foot        -0.000     0.0075
         81    23.000    35.965   0.050   node_l_foot        -0.003     0.0049
         82    23.000    35.915   0.050   node_l_foot        -0.003     0.0069

      planted on 76 of 82 frames, and while it is planted the foot sits
        +0.0028 m above the collision mesh, -0.0047 to +0.0251
        and slides 0.0059 m a frame over the ground - the cycle is authored for
        0.0459 and the body is moving at 0.05, so 0.0041 of that is the disagreement

**Three millimetres.** The walking body's planted foot sits three millimetres
above the ground the stage declares, over the whole of a walk, and it slides
six millimetres a frame — of which four are the cycle being authored for
0.0459 while `walk_sp` says 0.05, and the remaining two are the foot settling
as it takes weight. The run comes out the same: −0.0048 m on `010_01_01`,
−0.0032 m on `030_01_01`.

Where there is nothing to stand on the report says so rather than hiding it.
`040_03_01`'s `appear01` declares `y = 4.000` over ground at −0.034, so the
body falls from frame one, reaches the floor at frame 16 and runs out of mesh
at 17; `stride` prints `never planted in 63 frames`, because a foot at its
standing height under a falling body is not planted on anything.

---

## What is assumed, and where

Four things, all of them stated in
[`pose.py`](../engine/pose.py)'s own docstring:

- **The animation is in place.** A locomotion cycle keeps its root still and
  slides the feet backwards, so the model is placed at the actor's position
  each frame and whatever root translation the animation carries is added on
  top. For a walk or a run that translation is zero; for a dodge or a lunge it
  is not, and this layer does not try to separate the two.
- **Model space is the stage's space** — Y up, one unit a metre, `+Z` forward.
  The first two are [`units.md`](units.md)'s; the third is the convention
  [`world.py`](../engine/world.py) adopted for a heading of zero. That the two
  agree is not proved anywhere. It is what makes a run cycle carry the body
  forwards instead of sideways, and `pose.py track` prints the slide so the
  claim can be argued with.
- **Contact has a tolerance**, because a foot planted on a floor still moves a
  few millimetres. `footfall` prints the answer at one, three and five
  centimetres rather than picking one.
- **A cycle whose last frame repeats its first is a loop one frame shorter.**
  `fas213run` declares 21 frames and its frame 20 is its frame 0 to the last
  digit. That is tested per animation, not assumed.

---

## Still open

- **The `gn` motion sets are authored for a different rig.** `fgn` and `mgn`
  key `node_hip` at `y = 0.899` and carry **no `xrot` track at all**, while
  every other player set keys the hip at ~0.07 under an `xrot` that the model
  puts at 0.9. Played on the shipped `fgn1`/`mgn1` skeleton the whole body
  floats 0.9 m and no foot ever touches: 72 animations, and both of their
  locomotion cycles report *no frame with a foot down*. **Drop the 0.9 and the
  walk's planted foot sits at −0.0014 m over 29 frames of contact**, which
  identifies the fault exactly; the cycles then slide 0.0369 and 0.2937 m a
  frame, neither of them a player number, which is what a set with no class
  behind it is entitled to. No model on the disc explains it either — of the
  180 that carry an `xrot` node, the only three that put it at the origin are
  `b18_00`, `b18_01` and `b18_02`.
  Whether the engine should skip a node the motion does not name is a rule
  nothing else on the disc needs, so it is not implemented here.
- **The 18 % that miss.** 109 firings of 601 are more than a frame from any
  landing at 1 cm once `DRESS` is set aside, and **they are not spread
  evenly**: 54 are on attack motions, 20 on damage reactions and 14 on emotes,
  while the locomotion cycles — the ones whose feet do nothing but land —
  contribute 17 between them. Attacks and staggers are where a foot pivots,
  drags and scuffs rather than landing, and where the animation is blended
  into rather than played from frame 0. On `fht303landing` the fire at frame
  14 comes two frames before the foot settles at 16, and a cue starting
  slightly ahead of contact is what an audio department does on purpose.
  Nothing here separates *fires early* from *is wrong*.
- **`7ffb`, the matching second event.** It fires one frame either side of
  `7ffa` — after it in `fas213run`, before it in `fas211walk` — and this
  measurement does not touch it.
- **Which foot `7ffa` means.** `7ffa` names a surface kind and not a side.
  `7ff9`'s emitter is settled — it is a locator id — but `7ffa` has no such
  field, and nothing on the disc says whether the engine tracks the side
  itself or simply plays one cue for either foot.
- **Four pacs resolve to no skeleton**: `bird_a`, `recycle_box`, `shield` and
  `treasure_big`, all of them stage props whose model sits somewhere the
  three arrangements in `skeleton_for` do not look.

---

## Running it

    python engine/pose.py body       extract/tree fas213run
    python engine/pose.py track      extract/tree fas213run
    python engine/pose.py footfall   extract/tree
    python engine/pose.py emitter    extract/tree
    python engine/pose.py locomotion extract/tree extract/tree/job.cpk/sw/sw.json
    python engine/run.py  stride     <stage dir> <class json> extract/tree \
                                     msw213run [gait] [start] [cycles]

`track` is the one to read first — one animation, one line a frame, both feet,
which of them is down and how fast the planted one is sliding:

     frame      node_l_foot  down      node_r_foot  down     slide
         6   y +0.208 z-0.669         y +0.057 z+0.333
         7   y +0.419 z-0.740         y +0.040 z+0.456
         8   y +0.602 z-0.688         y -0.004 z+0.270  on
         9   y +0.647 z-0.570         y -0.002 z+0.101  on    +0.1687
        10   y +0.577 z-0.473         y -0.002 z-0.070  on    +0.1712
        11   y +0.420 z-0.410         y -0.002 z-0.244  on    +0.1740

That is `fas213run`, and the `.mkc` beside it fires `7ffa` on frame 8.
