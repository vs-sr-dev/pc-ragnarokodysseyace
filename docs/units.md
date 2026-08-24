# The metre and the frame

**Status: the length unit is settled; the time unit is settled to the degree
the disc allows.** One world unit is **one metre**, and one animation frame is
**1/30 of a second**. Neither is declared anywhere on the disc, though session
18 found a stage script that **writes 30 as the number of ticks in a second**
(below). Both follow from measurements a reader can repeat:

```
python tools/cmdl.py gait extract/tree fas2.CMDL fas213run.CNOM
```

This matters more than it sounds. Every number in [`params.md`](params.md) —
acceleration, run speed, turn rate, gravity, hit-stop windows — is expressed
per frame in units, and until those two constants are known the whole
parameter set is dimensionless. With them, the first milestone
in [`STRATEGY.md`](STRATEGY.md) becomes a thing that can be checked against a
stopwatch rather than only against itself.

## One unit is one metre

The twelve player models — `fas2` through `msw2`, female and male of the six
classes — measure **1.551 to 1.884 units tall**, and the sole of the foot sits
at `z = 0.000` on every one of them, to within two thousandths. (A character
vertex buffer is Z-up; see [`format_cmdl.md`](format_cmdl.md).)

Arm span comes out at 1.512 units on every one, because they share a T-pose
rig. A human's arm span is about equal to their height, and 1.512 against 1.6
is the Vitruvian ratio to two percent.

So the models are ordinary human beings, modelled at 1:1, standing on the
origin. Nothing else on the disc has to be consulted, and nothing else would
give a different answer: the stage collision meshes are tens of units across
and the `borderline` fences that trace them are in hundredths of the same unit,
which are the numbers a hand-authored level in metres and centimetres has.

## The planted foot pins the speed

A locomotion cycle is authored against a translation speed. While a foot is on
the ground it must travel backwards, relative to the body, at exactly the rate
the character advances — any disagreement is a foot sliding on screen, which is
the one animation error everybody notices.

So: run the skeleton forward through the cycle, find the frames where an ankle
is at its lowest, and measure how fast that foot goes backwards.

| | walk (`211walk`) | run (`213run`) | dash (`215run_dash`) |
|---|---:|---:|---:|
| cycle length, all 12 models | **41 frames** | **21 frames** | 17 frames |
| median backward slide | **0.0492** | **0.1699** | **0.2790** |
| the parameter that should equal it | `walk_sp` = **0.05** | `run_sp` = **0.17** | `fast_sp` = **0.28** |
| models within 3% | 9 / 12 | 11 / 12 | |
| models within 8% | 12 / 12 | 11 / 12 | |

**The run agrees to one part in a thousand**, and the dash to four parts in a
thousand. Nothing was fitted: the three speeds come from the JSON, the three
slides come from the geometry, and they are the same numbers. The dash is the
one that had to be found rather than checked — the cycle was measured first at
0.279 and the parameter that matched it turned out to be called `fast_sp`,
which is also what names the motion.

Three things follow.

- **`_sp` is units per frame**, and the frame it counts is a `CNOM` frame. All
  three of `walk_sp`, `run_sp` and `fast_sp` are, so the suffix carries the
  unit the way [`params.md`](params.md) said it did.
- **The animations are authored against the parameter table**, so a
  reimplementation that drives locomotion from the JSON will not foot-slide.
- **The animation frame and the simulation frame are the same frame.** This is
  the loophole the measurement closes. Had the animations been authored at 30
  and the game ticked at 60, `walk_sp` would be per *game* frame and the
  animation would advance half an animation frame per tick — and the foot would
  slide by a factor of two. It does not.

The three non-player prefixes `cm`, `gn` and `nn` have their own walk and run
at their own speeds, which is why they are excluded: the six player classes are
`as`, `cl`, `hs`, `ht`, `mg` and `sw`, and
[`params.md`](params.md) already established that they share one movement
model.

**Session 16 got the same three numbers from a different definition of a
planted foot** — the height the contact node stands at in the model's *rest*
pose, rather than the lowest the ankle gets in that particular animation. The
medians come back 0.0484, 0.1696 and 0.2769 against the 0.0492, 0.1699 and
0.2790 above, and the point of the exercise was the new definition rather than
the old result: it is one a body can carry into an attack or a fall, where
there is no cycle to take a floor from. See [`pose.md`](pose.md).

## The frame is 1/30 of a second

Now the gait is in metres per frame, and the only free parameter left is how
long a frame lasts. A 1.6 m human running is a well-constrained thing, so put
both candidates side by side:

| | at 30 fps | at 60 fps | a human |
|---|---:|---:|---|
| walk speed | 1.48 m/s | 2.95 m/s | 1.4 m/s preferred |
| walk cadence | 88 steps/min | 176 steps/min | 100–120 |
| run speed | 5.09 m/s | 10.19 m/s | 5 m/s is a strong club runner |
| run cadence | **171 steps/min** | 343 steps/min | 170–180 at that speed |
| run step length | **1.78 m** | 1.78 m | 1.7–1.8 m at that speed |

**The run at 30 fps is a textbook gait.** Speed, cadence and step length are
three numbers that a real runner cannot choose independently, and all three
land where a physiologist would put them, with nothing tuned to make them.

At 60 fps the same animation is a 1.6 m person covering 100 metres in under ten
seconds while taking **343 steps a minute**. No human has ever run at that
cadence; a sprinter at world-record pace peaks near 260. The 60 fps reading is
not merely fast, it is kinematically impossible for the pose the animator drew.

The walk is the weaker of the two — 88 steps a minute is a slightly leisurely
stroll where a human averages 110 — but the failure mode at 60 fps is worse: a
176-step-per-minute, 2.95 m/s "walk" is a competitive race-walk, and the
animation plainly is not one.

### Gravity says the same thing

Independently of the gait, and from a different subsystem:

```
fall_gravity_y   = -0.035     units per frame squared
aerial_gravity_y = -0.02
jp_speed_y       =  0.42      units per frame
```

Since a unit is a metre, `g = 0.035 * fps²`:

| | 30 fps | 60 fps |
|---|---:|---:|
| fall gravity | 31.5 m/s² | 126 m/s² |
| as a multiple of Earth | **3.2×** | **12.8×** |

Action games run heavy gravity to keep jumps snappy, and two to four times
Earth is the ordinary range. Nearly thirteen times is not a value anybody
tunes to.

(The apex height of a jump, `v² / 2g`, does not depend on the frame rate at
all: 2.5 m against `fall_gravity_y`, 4.4 m against `aerial_gravity_y`. That is
a game jump either way and settles nothing, which is why it is a parenthesis.)

Two smaller pointers, worth no more than a mention. (The first has a
complication since session 18: the script layer's turn speeds are **binary
angles**, 65536 to the turn, and the NPC values `chrSetDir` is given — 2048,
4096, 8192 — are 8, 16 and 32 in units of 1/256 of a turn. `rot_y_spd = 32` is
in that set, and read that way it would be 45° a frame rather than 32°. The two
subsystems are separate and nothing on the disc joins them; the reading below
is the one this document has, and the coincidence is written down in
[`format_api.md`](format_api.md) rather than resolved.) `rot_y_spd = 32`
degrees per frame turns a character 180 degrees in 0.19 s at 30 fps and 0.09 s at 60,
and 0.09 s is below the threshold at which a turn reads as a turn. (That 0.19
is a lower bound and session 14 improved on it: `rot_y_acc = 8` has to spin the
turn up and brake it down, which makes the real figure **0.32 s at 30 fps** and
0.16 s at 60. The argument gets stronger, not weaker — see
[`milestone_numbers.md`](milestone_numbers.md).)
`camera_aerial_finish_keep_frame` holds the camera on a finisher for 15 to 30
frames, which is half a second to a second at 30 fps and a quarter-second blink
at 60.

## What this does not say

**It does not say the game renders at 30 Hz.** The disc's data describes a
simulation and animation tick, and nothing in it speaks about the display. A
PS Vita original and its PS3 port may well present 60 frames a second while
stepping the world 30 times — that structure is common, and it is exactly what
one would expect of a handheld game whose animation content is authored on
thirties. The frame this document is about is the one `CNOM`, `.anmcmd` and
every `_f` field in the JSON count in, and that is the frame a reimplementation
has to step.

**Nor is it a declaration.** No field anywhere on this disc says 30, or 60, or
carries a delta time. The number here is inferred from the geometry of a run
cycle and the physics of a fall, and it is quoted at the precision those
support: the animation tick is 1/30 s, and the evidence would have to be
substantially different to make it 1/60.

## Still open

- A *declared* frame rate or delta time, if one exists. The EBOOT is where a
  declaration would be — but session 18 found the **conversion constant** on
  the disc, in the clear, in a stage script:

      function genCycle(fix, random)
          local cycle = ((fix * 30) + ((random * 30) * cfGetRandF(1)).tointeger())

  `fix` and `random` are the `_sec_fix` and `_sec_rnd` of an effect record —
  fields whose names say seconds, and which
  [`format_effect.md`](format_effect.md) matched field for field against
  `effect.bin` — and the result is a countdown decremented once per update. So
  the game's own authors wrote **30 ticks to the second**. It is not a
  declaration, and it assumes the update runs once a frame, but it is the first
  seconds-to-frames constant found outside the executable and it agrees with
  the gait. See [`format_api.md`](format_api.md).
- Whether the render rate is 30 or 60. Nothing on the disc bears on this.
- ~~`fall_spd_max = 8` units per frame is 240 m/s at 30 fps, so it is a clamp
  that never fires or it is not a speed.~~ **Settled in session 14**, by
  letting a body fall out of the world. `engine/run.py sweep` reports the
  largest vertical move any capsule made in any single frame, and on
  `150_04_02` it is **8.000 m — the clamp exactly**. A body that walks off the
  mesh accelerates at `fall_gravity_y` for `8 / 0.035 = 229` frames, seven and
  a half seconds, and then stops accelerating. So it *is* a speed, and it is
  the terminal velocity of something that has left the level: unreachable in
  play, which is what a guard is. See
  [`milestone_numbers.md`](milestone_numbers.md). **Session 29 found what that
  body fell from** — not the edge of the mesh but out from under its own
  floor, `150_04_02` spawning five metres below it — which leaves the reading
  as it is and takes the demonstration away: with a body placed on the ground
  under its marker, nothing on the disc falls.
- `ab_tire_stamina_recovery_f = 0.1` — a `_f` field with a fractional value, so
  a rate per frame rather than a count of them. Five other `_f` fields on the
  disc are fractional the same way and none has been read.
