# Milestone 8 — the body gets there

**Status: reached, session 29.** Seven milestones read the disc and one thing
was never a reading at all. A stage loads, a script runs, a monster fights,
the player fights back, an arena closes on the script's own kill count and a
quest pays what its tables say — and between any two of those the body has to
*walk across a room*, which nothing on the disc describes and every session
since 24 has left where it stood. 125 of the 431 quest runs ended with *the
body stopped walking*.

This is that half. Nothing here is decoded; what is here is the walk made to
agree with the mesh it walks on, and **the instrument that says where it does
not** — [`run.py nav`](../engine/run.py), and
[`draw.py route`](../engine/draw.py), which draws the same run.

```
python engine/run.py  nav   extract/tree/stage.cpk extract/tree/job.cpk/sw/sw.json
python engine/run.py  sweep extract/tree/stage.cpk extract/tree/job.cpk/sw/sw.json
python engine/run.py  check extract/tree/stage.cpk
python engine/draw.py route extract/tree 030_03_01 route.png
python engine/mission.py runs extract/tree
```

## The body was standing under the floor

The first thing the walk needed was not a steering rule. `hta.bin` gives every
marker a position and [`run.py check`](../engine/run.py) has measured for six
sessions how far each one sits from the ground beneath it — a median of a
centimetre for `obj` and `appear`, which is why the table was called
consistent with the mesh and left alone.

It only ever measured the **distance**. The sign is the whole story:

```
  markers standing on the mesh - hta.bin against <stage>.col
    kind          n   none   median    <1cm   <10cm      max
    appear      660      1    0.018     297     497     6.32
    jump        269      3    0.069      76     199     2.00
    pl_q         74      0    0.145      14      28     4.66
    emgen_pos  2113     10    0.566     321     765    15.00
  and how many are more than col_r *below* their own floor:
    appear 36, jump 20, pl_q 14, emgen_pos 183
```

**36 of the 660 `appear` markers and 183 of the 2,113 `emgen_pos` sit more
than `col_r` under the ground they are on**, by fifteen metres on
`100_03_02`. A body put down on one of those is *beneath the floor*, and to
[`actor.py`](../engine/actor.py) — which asks for ground within a step of its
feet and finds none — that is a body in mid-air. It falls. `mission.py` then
catches it and puts it back where it fell from, which is the same place under
the same floor, and it falls again, for the whole of the run.

The rule that fixes it invents nothing: **a body placed on a marker stands on
the ground under the marker.** `world.stand(x, z, y)` is the query, and the
`y` matters — the ground *nearest the marker's own height*, not the highest
ground over that point, because a stage has storeys and a marker's Y names
which one it means.

Two of the three quests that failed in the first hundred failed on exactly
this, on `010_02_01` and `020_02_04`, and with the body put on the floor
instead the first ten quests of the game go from six finishing to nine, and
from fourteen arenas closed to seventeen.

### And it corrects a published number

`run.py sweep` walks a body from `appear01` straight at the exit on all 155
stages, and what it printed has been quoted since session 14:

```
  never left the collision mesh: 127 of 135          ->  135 of 135
  largest vertical move in one frame: 8.000 m        ->  0.109 m
  8 stages have frames with no ground underneath - a straight line at the
  exit crosses a hole in the mesh
```

There is no hole. **All 135 crossings now keep the body on legal ground for
every frame**, and the eight stages that did not were the eight whose spawn is
under their own floor — `150_04_02`, `010_02_01`, `070_01_02`, `040_04_01`,
`150_03_05`, `100_04_01` among them, every one of them on the list above. The
sentence about a hole in the mesh was wrong and is withdrawn.

The reading that came out of that fall is **not** withdrawn.
[`units.md`](units.md) closed `fall_spd_max = 8` as a speed because the sweep
made the clamp fire at 8.000 m in a frame on `150_04_02`, and it did fire,
after 229 frames of unobstructed fall. What is corrected is only what the body
was falling *from*: not off the edge of the level but out from under its own
floor. It was still a body outside the level, which is what the clamp guards,
so the conclusion stands and its provenance is now understood. The
demonstration no longer reproduces from `sweep`, because there is nothing left
on the disc that falls.

## A stair is not welded

[`format_ccls.md`](format_ccls.md) established the fact the navigation mesh is
built on: the collision mesh is **welded**, 150,236 of the disc's edges shared
by exactly two triangles under exact vertex equality, and *the edge of the
walkable region is the fence*. Session 24 read those two together as a navmesh
and nothing has questioned it since.

`070_01_02` questions it. Its exit stands eight metres above its spawn room
and the climb between them is **nine separate connected components** of the
welded graph — a staircase whose steps share no vertices, each pair 0.19 to
0.36 m from the next. A\* returns None from the spawn to the exit, and four
quests stood at the bottom of those stairs for a whole run each.

So the single-use edges are not all outline. Ask which of them has another
single-use edge within `col_r` in three dimensions **sharing no vertex** —
sharing one only means being the next edge along the same outline, which pairs
21,961 of them and says nothing:

```
22,020 single-use walkable edges over the 155 stages
   2,093 have another within col_r that shares no vertex  — a seam
  19,927 have nothing beside them                          — an outline
```

**One edge in ten is a seam**, and `world.graph` now joins the two triangles
across it. The step is `col_r`, which is [`actor.py`](../engine/actor.py)'s
own — that file already steps a body up or down anything within its capsule
radius, and the graph disagreeing with the walker about what a step is was the
whole defect. No new number.

The disc was asked whether it had a better one and it declined to answer.
Every pair of single-use edges within half a metre of each other in XZ, by the
height between them, decays smoothly from 0 to 0.9 m over 67 stages — real
stairs — and then spikes at exactly 1.0 m with 2,870 pairs, of which the
twelve largest counts are all `170_*`: the endless dungeon's floors, built
from a modular kit on a one-metre grid. That is a construction unit and not a
step height. Pushing the join from 0.5 m to 1.5 m buys **no additional
reachable exit anywhere on the disc** — 264 of 267 either way — so `col_r`
stays.

`070_01_02` is what it costs. Its nine islands become two, but the first riser
out of the spawn room is 0.61 m over a 0.21 m gap, which is a **71-degree
slope** and therefore a wall by the mesh's own walkability test. Its exit is
still out of reach and four quests still stop there. That is a limit, stated,
rather than a number chosen to make it go away.

## A fence between two slabs

Joining seams broke two quests before it fixed any, and the reason is worth
keeping. A\* refused a crossing whose **two triangle centres** are separated by
a fence, which is exact for two halves of one welded surface. A seam is not
that: two slabs that merely touch can have both centres on the same side of a
fence that runs between them, and the straight line between the centres misses
it. On `030_03_01` there is one, and a body sent over it stood against
`chara_line02` for the rest of the run.

The test is now centre → waypoint → centre rather than centre → centre, which
costs one more segment intersection per expansion and is what the crossing
actually is.

## The middle of an arena is not always a place

[`milestone_quest.md`](milestone_quest.md) sends the body to the middle of a
lock's `lockarea` rather than to its trigger, for a good reason: the trigger is
a slab across a corridor and standing at its near edge is still being outside
the room. But *the middle* is a centroid, and a centroid is not a location.

`lockarea05` on `010_01_02` is a polygon 54 by 87 metres with a lake in the
middle of it. Its centroid has **no ground under it at all**, so the fallback
picked the nearest triangle by distance — which was the one the body was
already standing on, on the wrong side of a fence — and the route degenerated
to a straight line into the water's edge. The body stood there for the rest of
the stage, inside the arena it was trying to reach.

`world.into(name, near)` answers with a walkable triangle centre **inside the
polygon**, nearest the body. A body already in the arena is already there,
which is what the arena means. On the eight stages of area 010 the walk goes
from 25 of 31 destinations reached to 31 of 31.

## The ground under a body is a disc, and the disc's radius is on the disc

`world.floor` asks what is under a point. A body is not a point, and a stair
whose steps are 0.2 m apart has nothing under the point halfway across while a
body moving 0.17 m in a frame is standing there. `world.under` asks under a
disc: the centre first, and the rim only when the centre finds nothing, so the
common case costs exactly what `floor` cost.

The radius wanted a number and [`params.md`](params.md) had one nobody had
read. The class table carries `ry_r_walk` 0.15, `ry_r_run` 0.30, `ry_r_fast`
0.35 and `ry_r_fall` 0.35 — **four radii keyed to exactly the four locomotion
states this model has**, carried by all six classes, carried by none of the 83
monsters, in the same metres as everything else, and consumed by nothing in
fifteen sessions. What `ry` abbreviates is not on the disc; that a per-gait
radius which grows with speed is the ground probe is a reading, and it is
marked as one in [`actor.py`](../engine/actor.py) beside the three assumptions
that file already declares.

## The instrument, and the picture

`run.py sweep` steers a body straight at the exit and measures the *movement
model*. What was missing was a measurement of the **steering**, which is this
repository's own. `run.py nav` walks `appear01` to every destination a quest
can be sent to — every `jump_` marker and the inside of every `lockarea` — with
the same rule `mission.py` steers by, and reports what it did not reach:

```
355 of 375 destinations reached over the nav mesh, 16 stages with one it never reaches
  stage          goal                  closest   walked  routes  no route
    050_01_02      jump_050_01_01           8.3 m     13 m     120       120
    050_02_02      jump_050_04_01          16.1 m      7 m     118       118
    050_02_03      jump_050_02_05          34.6 m     48 m      99        99
    050_02_04      lockarea01              24.3 m     22 m     119       119
    050_02_06      lockarea01              18.8 m     23 m     110       110
    070_01_02      jump_070_02_01          12.2 m      5 m     123       123
    080_01_02      jump_080_03_01          19.9 m      8 m     123       123
    080_01_02      lockarea02               3.0 m      4 m     124       124
    080_02_01      jump_080_01_01           2.4 m     74 m     124         0
    080_03_01      jump_080_03_02           8.5 m     35 m     114       114
    080_03_02      jump_080_03_04          27.5 m      3 m     125       125
    120_04_01      jump_120_01_03          18.3 m      4 m     124       124
    150_03_05      jump_150_02_01          91.0 m     21 m      95        95
    150_03_05      lockarea01              93.0 m     21 m     117       117
    150_03_05      lockarea02               4.1 m     28 m     102         5
    150_04_01      jump_150_03_03         129.1 m      5 m     123       123
    150_04_01      lockarea01              21.9 m     41 m     104       104
    170_08_01      jump_next              118.7 m     15 m     117       117
    170_08_02      jump_next              118.6 m     17 m     117       117
    170_18_02      jump_next               92.1 m     25 m     117       117
```

**355 of 375, and the last column is the point.** `no route` counts the times
A\* was asked and answered None. On **eighteen of the twenty misses it is
every single time** — the body never had a route to walk, because the
destination is not connected to it on the mesh at all. Those are not steering
failures and no amount of tuning the walker touches them; they are the same
family as `070_01_02`'s staircase, and each one is a specific piece of
geometry to go and look at.

Only two of the twenty are the walk itself, and both are near misses:
`080_02_01` walked **74 metres and stopped 2.4 m short** of a marker this
command calls arrived at 2.0, which is the instrument's own threshold showing
through rather than a body in trouble; and `150_03_05`'s second arena got
within 4.1 m with A\* failing 5 times out of 102.

So after this session **the steering is no longer the weak half — reachability
is**, and the two are different problems with different fixes. That is worth
more than the count: for five sessions "the body stopped walking" was one
undifferentiated failure, and it has turned out to be eighteen holes in a
graph and two rounding errors.

```
```

And `draw.py route` draws the same run, into a file this repository does not
ship: the walkable mesh from directly above, the fences over it in red, every
`lockarea` in blue, the spawn as a yellow cross, and the body's own trail —
**green where it arrived and red where it gave up**.

```
python engine/draw.py route extract/tree 030_03_01 route.png
  jump_030_02_03         arrived     2.0 m short,      8 m walked,   1 routes
  jump_030_03_02         arrived     1.9 m short,    148 m walked,   8 routes
  lockarea01             arrived     1.9 m short,     13 m walked,   1 routes
  lockarea02             arrived     1.9 m short,    115 m walked,   6 routes
```

`030_03_01` is a canyon, and the picture is four green threads following it:
the body walks 148 metres from the spawn through two arenas to the exit at the
far end, and rebuilds its route eight times on the way, which is the fence
pushing it off a waypoint and the steering asking again.

```
python engine/draw.py route extract/tree 070_01_02 route.png
  jump_070_01_01         arrived      2.0 m short,     6 m walked,   1 routes
  jump_070_02_01         gave up     12.2 m short,     5 m walked, 123 routes
  lockarea01             arrived      0.7 m short,     0 m walked,   0 routes
```

`070_01_02` is the failure, and the picture is the argument: two short green
threads to the arena and to the way back, and a red one that stops in the
middle of the room, with the exit it wants marked out on the terrace eight
metres above it. 123 route requests in a run that moved five metres. Nothing
about that is a steering bug — which is the point of having a picture, because
before this the run could say only *the body stopped walking*.

## What it comes to

`mission.py runs` drives all 431 quests. The left column is what
[`milestone_quest.md`](milestone_quest.md) published in session 24 and
[`milestone_reward.md`](milestone_reward.md) reproduced to the digit in
session 28; the right is the same command after this session.

```
                                              session 24/28      now
  quests finished                                     247        284
    of the ones that arm an arena                25 of 131    59 of 133
    of the ones that do not                     222 of 300   225 of 298
  walked their whole stage list                         252        287
  stages walked, of 1,708                             1,105      1,239
  arenas armed by a quest script                        272        344
    started                                             229        340
    ended by the script's own kill count                210        322
  monsters spawned                                    1,594      3,105
  monsters killed                                     1,534      3,017
  quests that paid something                            179        201
  zeny paid                                         568,871    689,375
  items paid                            2,762 of 279 kinds  5,086 of 349
```

**284 of 431 quests finish, against 247.** The line to read twice is the one
under it: of the quests that put a locked arena in front of the player,
**59 of 133 come out the other end against 25 of 131** — the walk between two
rooms was compounding, and a quest with four arenas needed four crossings to
go right.

The arena number moved on both sides and the ratio moved with it: **322 of
the 344 arenas the body reached were closed by the script's own kill count,
against 210 of 272** — 94 % against 77 %. The extra 72 armed arenas are
rooms the body could not previously get to at all, and the ones that close
close because the tables were already right.

**The kill count nearly doubled**, 1,534 to 3,017, on the same policy
(`BLOWS`) and the same tables. So did the pay-out, which is milestone 7
running over more of the disc than it could reach before: 689,375 zeny and
5,086 items of 349 kinds.

And the failure that named this session:

```
  the body stopped walking          125  ->  66
  ran out of its frame budget                  2
  raised anything at all                       0
```

**66 runs of 431, and eleven stages account for every one of them** —
`070_01_02` thirteen times, `100_02_01` ten, `170_08_01`, `080_01_02` and
`050_02_03` eight each. That is a short list against a disc of 155 stages,
and `run.py nav` and `draw.py route` say what is wrong with each one.

## What is still not walked, and one rule that lost

- **`070_01_02`'s exit**, above. Four quests.
- A rule that looked free and was not. `route` established that
  `piecelist.bin` is a **graph** rather than a path, so passing over an exit
  the mesh cannot reach in favour of one it can seemed obviously right. It
  changed nothing on the four quests it was aimed at — their other exit leads
  backwards — and it turned `q00306` from finishing into walking between two
  rooms for the rest of the run, because A\* is conservative about a fence and
  says None for places a body does get to. It is not in the code; the comment
  where it would have gone says why.
- **The body does not jump.** `jp_speed_y` is 0.42 m a frame against
  `fall_gravity_y` of −0.035, which is an apex of 2.5 m, and no steering in
  this repository has ever used it. A 0.61 m riser is nothing to a jump.
