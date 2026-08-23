# Milestone 1 — the numbers are real

**Status: reached, session 14.** A capsule with the game's own acceleration,
run speed, turn rate and radius crosses `010_01_01` from the player spawn to
the exit in **405 frames — 13.5 seconds — without once leaving the collision
mesh.** Code: [`../engine`](../engine).

```
python engine/run.py numbers extract/tree/job.cpk/sw/sw.json
python engine/run.py walk   extract/tree/stage.cpk/010_01_01/param.pac \
                            extract/tree/job.cpk/sw/sw.json
python engine/run.py trace  <stage dir> <class json> out.png
python engine/run.py check  extract/tree/stage.cpk
```

## Why this mattered more than another format

Thirteen sessions produced a complete reading of the disc and never once ran
any of it. Every check in this repository is *arithmetic* — the files consume
exactly, the sentinels return, the indices resolve — and cross-checked, script
against table. Those are strong checks. They are not the same thing as a body
moving at `acc = 0.035` and arriving somewhere, and the difference is the
whole question the project is asking.

The milestone had had everything it needed since session 8 and had never been
attempted.

## What the parameters produce

Every number below is read, not tuned. The parameters are `job.cpk/sw/sw.json`
record 0, which [`params.md`](params.md) showed is shared with the other five
classes in every locomotion field; the two unit constants are
[`units.md`](units.md)'s.

```
speed
  walk   0.050 m/frame =  1.50 m/s, reached in  1.43 frames (0.05 s) over 0.04 m
  run    0.170 m/frame =  5.10 m/s, reached in  4.86 frames (0.16 s) over 0.41 m
  dash   0.280 m/frame =  8.40 m/s, reached in  6.22 frames (0.21 s) over 0.87 m

turning
  rot_y_acc 8 deg/frame^2, capped at rot_y_spd 32 deg/frame
  a 180 degree turn takes 9.62 frames = 0.32 s

the jump
  apex 2.52 m after 12.0 frames, airtime 0.80 s
  gravity is 31.5 m/s^2, 3.2 times Earth
```

**Nothing here is absurd, and two of them are better than expected.** A run
that reaches full speed in a sixth of a second over forty centimetres is an
action game with no run-up, which is what this game looks like. A 180-degree
turn in a third of a second is a turn a player can see happen —
[`units.md`](units.md) had estimated 0.19 s from `rot_y_spd` alone and worried
it was too fast to read; with `rot_y_acc` integrated properly it is 0.32 s, and
the worry goes away. That is a small thing, and it is exactly the kind of small
thing that only shows up when the numbers are put in a loop instead of a table.

## The crossing

`010_01_01` is the first field of the game. The player enters at `appear01`,
`(23, 0, 40)`, with the marker's Y rotation at 180 degrees; the only exit is
`jump_010_01_02` at `(6.8, -0.5, -31.2)`, 73 metres away.

- **The spawn marker faces its own exit to within 12.8 degrees.** That settles
  a convention nothing on the disc declares: a heading of zero faces `+Z`.
  Under the other convention the player spawns facing the wall behind them.
- **The ground under the spawn is at `y = -0.001` and the marker says
  `0.000`.** `hta.bin` and `<stage>.col` are two files written by different
  parts of a level pipeline and nobody had ever put them in the same
  coordinate frame.
- **405 frames, 13.5 seconds, 0 frames with no ground underneath.** The floor
  varied from `-0.09` to `+0.33` metres along the way, which is a field with a
  gentle roll in it.

The path is not a straight line, because the field is a curved corridor. The
capsule steers at the exit, meets the west fence 51 frames in, and is in
contact with it for **207 of its 405 frames** — and the fence never lets it out
and never traps it in a corner.

## And then every other stage

One crossing proves the loop runs. The claim worth making is the one across
the disc, so `run.py sweep` spawns the same capsule at `appear01` on every
stage that has a spawn, an exit and a fence, steers it straight at the exit,
and counts:

```
135 stages walked, 28 skipped for want of a spawn, an exit or a fence
  never left the collision mesh: 127 of 135
  reached the exit steering straight at it: 126 of 135
  of those, 62 are a real crossing (spawn at least 20 m from the exit):
    time     median  18.8 s, 3.3 s to 49.4 s
    speed    median  5.05 m/s over the ground, against 5.10 m/s flat out
    detour   median  1.00 times the straight line
    longest  020_01_02 at 49.4 s over 93 m
  largest vertical move in one frame, anywhere: 8.000 m on 150_04_02
  8 stages have frames with no ground underneath
```

**127 of 135 stages crossed with the body on legal ground for every frame.**
The eight that are not are stages where a straight line at the exit walks over
a hole in the mesh and the body falls through it, and the nine that do not
arrive are stages with an L-bend a naive steer cannot see round. Both are
facts about the steering rule, which has no idea the world has pits or
corners in it, and neither is a fact about the world.

The speed line is the one to read twice. **5.05 m/s achieved against 5.10 m/s
flat out** means the capsule is at full speed for essentially the whole
crossing: the fence contact costs almost nothing, and the acceleration ramp is
a sixth of a second out of nineteen seconds. And a field that takes a *median
of nineteen seconds to cross at a run* is the size a field in this game should
be.

### `fall_spd_max` fires, and it is a speed

[`units.md`](units.md) left `fall_spd_max = 8` on its open list: *"8 units per
frame is 240 m/s at 30 fps, so it is a clamp that never fires or it is not a
speed."*

The sweep prints the largest vertical move any body made in any single frame,
and on `150_04_02` it is **8.000 m — the clamp, exactly.** A body that walks
off the edge of the mesh accelerates at `fall_gravity_y` for `8 / 0.035 = 229`
frames, seven and a half seconds, and then stops accelerating.

That is not "it is not a speed": it is a speed, and it is the terminal
velocity of something that has fallen out of the world. Which is exactly what
such a clamp is for, and it is not reachable inside a level — nothing in this
game gives a player seven seconds of unobstructed fall. The open item can be
closed as *a fall-out-of-the-world guard*, and it was closed by letting a body
fall out of the world.

## The fence is a closed loop, and this is how that got settled

[`format_stage.md`](format_stage.md) has had *"whether a fence is a closed
loop"* on its open list since session 8. On `010_01_01` the answer is visible
the moment a body has to live inside one: `chara_line01` ends at
`(10.9, -33.1)`, which is where `chara_line02` begins, and `chara_line02` ends
at `(15.2, 49.5)`, which is where `chara_line01` begins. **Two polylines, one
loop.**

Across the disc, counting an endpoint as closed when exactly two polyline ends
meet there:

```
105 of 145 stages close, 20 branch, 20 leave an end loose
```

So a `borderline` **is** a closed region, drawn as however many polylines the
level designer felt like splitting it into. The 20 that branch have a node
where three ends meet — a fence with a spur, which is what an island inside the
playable area looks like.

## The marker table stands on the collision mesh

The other question a simulation asks that a reader never does: *is a marker
actually on the floor?* Nearest ground under each marker, over all 155 stages
with a mesh:

| kind | n | none | median | ≤1 cm | ≤10 cm | max |
|---|---:|---:|---:|---:|---:|---:|
| `obj` | 772 | 0 | **0.010 m** | 394 | 718 | 0.57 |
| `appear` | 660 | 1 | **0.018 m** | 297 | 497 | 6.32 |
| `jump` | 269 | 3 | 0.069 m | 76 | 199 | 2.00 |
| `pl_q` | 74 | 0 | 0.145 m | 14 | 28 | 4.66 |
| `emgen_pos` | 2,113 | 10 | 0.566 m | 321 | 765 | 15.00 |

**`obj` and `appear` sit on the ground to a centimetre**, and of 1,432 of them
exactly one has no ground under it at all. Those are the two kinds that *are* a
placement — an object on the floor, a player standing — and they were placed
against this mesh.

`emgen_pos` is the loose one, at half a metre, and that is a finding rather
than a failure: a monster generator is a point a monster comes *from*, and
several are metres above the floor or under it. `pl_q` is a volume, so its
centre has no reason to be on the ground.

None of these five rows could have been produced by reading a file. They are
`hta.bin` joined to `<stage>.col`, and the join only becomes an obvious thing
to do once something has to stand up.

## What is assumed, and where

The engine is honest about the seam between what it read and what it chose.
Five things are not on the disc, and all five are marked in
[`actor.py`](../engine/actor.py):

- **Deceleration.** There is no ground brake field — `brake` exists only for
  attacks, evades, knockback and landing — so the model decelerates at `acc`.
- **Turn braking.** `rot_y_acc` and `rot_y_spd` are an acceleration and a cap;
  the rule for stopping on the target heading is the textbook one.
- **The stick.** Four discrete gaits rather than an analogue magnitude.
- **Walls.** A blocked step is pushed back to exactly `col_r` from the fence,
  which yields sliding for free. What happens at a wall is not on the disc —
  but the 0.5 metres it happens at is.
- **Step height.** Nothing names one, so the body steps up or down by at most
  `col_r` and otherwise walks off the edge and falls. This one was found by
  checking rather than by thinking: the sweep's own report of *the largest
  vertical move in a single frame* came back at **4.03 m on `040_03_01`**,
  which is not a step, it is a teleport — the first version snapped to
  whatever ground it could find rather than admitting there was a cliff. A
  claim of "never left the mesh" that hides a four-metre jump is worth
  nothing, which is why the number is printed.

## What this does not claim

It does not claim the movement *feels* right, because nothing here renders and
nobody has held a pad. It claims something narrower and checkable: the disc's
numbers, in the disc's units, on the disc's geometry, produce a body that
crosses a real level in a plausible time along a legal path, and produce
physical quantities — 5.1 m/s, 0.32 s, 3.2 g — that a person can recognise.

The thesis of the project is that this game can be honestly reimplemented from
its data. This is the first evidence for that thesis that is not a file
consuming to the byte.

## Next

- **Milestone 2, "a stage runs"**, needs a Squirrel VM and the eight `cf*`
  natives [`TODO.md`](TODO.md) names. The stage's own `.psq` and its triggers
  are already read.
- **Milestone 3, "a monster fights"**, needs the AI loop of
  [`format_ai.md`](format_ai.md) driving this same capsule, plus the 40-odd
  state predicates.
- The obvious immediate extension was to give the capsule the animation, and
  **session 16 did it**: [`pose.md`](pose.md) plays a `CNOM` on the walking
  body and puts its planted foot three millimetres above the collision mesh,
  checked against `.mkc`'s own footfall opcode over 650 firings. What that
  layer still does not settle is *which of the hit record's three vectors is
  which*, open since session 9 — but it now has the forward kinematics that
  question needs.
